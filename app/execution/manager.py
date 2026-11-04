import uuid
from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from app.models.test_run import TestRun
from app.models.step_execution import StepExecution
from app.models.scenario import Scenario
from app.execution.executor import StepExecutor
from app.browser.controller import BrowserController
from app.failure_injection.injector import FailureInjector
from app.recovery.retry_manager import RetryManager
from app.idempotency.manager import IdempotencyManager
from app.core.logging import logger


class TestRunManager:
    def __init__(self, db: Session):
        self.db = db
        self.retry_manager = RetryManager()
    
    async def create_run(self, scenario_id: uuid.UUID, environment: str = "default") -> TestRun:
        scenario = self.db.query(Scenario).filter(Scenario.id == scenario_id).first()
        if not scenario:
            raise ValueError("Scenario not found")
        
        run = TestRun(
            scenario_id=scenario_id,
            status="PENDING",
            environment=environment,
            total_steps=len(scenario.configuration.get("steps", [])),
            run_metadata={}
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        logger.info("Test run created", run_id=str(run.id))
        return run
    
    async def execute_run(self, run_id: uuid.UUID, resume: bool = False):
        run = self.db.query(TestRun).filter(TestRun.id == run_id).first()
        scenario = self.db.query(Scenario).filter(Scenario.id == run.scenario_id).first()
        
        run.status = "RUNNING"
        if not run.started_at:
            run.started_at = datetime.utcnow()
        self.db.commit()
        
        browser = BrowserController()
        failure_injector = FailureInjector(scenario.configuration)
        idem_manager = IdempotencyManager(self.db)
        
        try:
            await browser.start()
            executor = StepExecutor(browser)
            
            steps = scenario.configuration.get("steps", [])
            completed_step_ids = []
            
            if resume:
                completed = self.db.query(StepExecution).filter(
                    StepExecution.run_id == run.id,
                    StepExecution.status == "PASSED"
                ).all()
                completed_step_ids = [s.step_id for s in completed]
                logger.info("Resuming, skipping completed steps", count=len(completed_step_ids))
            
            for step_config in steps:
                step_id = step_config["step_id"]
                if resume and step_id in completed_step_ids:
                    logger.info("Skipping already completed step", step_id=step_id)
                    continue
                
                step_exec = StepExecution(
                    run_id=run.id,
                    step_id=step_id,
                    status="RUNNING",
                    attempt_number=1,
                    started_at=datetime.utcnow()
                )
                self.db.add(step_exec)
                self.db.commit()
                
                try:
                    # Check for side effects (idempotency)
                    skip, ledger = idem_manager.check_action(str(run.id), step_id)
                    if skip and ledger:
                        logger.info("Skipping due to existing side effect", step_id=step_id)
                        step_exec.status = "PASSED"
                        step_exec.verification_result = {"skipped": True, "reason": "side_effect_exists"}
                        step_exec.completed_at = datetime.utcnow()
                        self.db.commit()
                        continue
                    # If ledger exists but not completed (e.g., from crashed worker), reconcile
                    if ledger and ledger.status in ["EXECUTING", "PENDING"]:
                        if "order" in step_id.lower() or "submit" in step_id.lower() or "checkout" in step_id.lower():
                            try:
                                from app.database.session import SessionLocal
                                from demo_app.models.order import Order
                                demo_db = SessionLocal()
                                try:
                                    existing = demo_db.query(Order).filter(Order.idempotency_key == ledger.idempotency_key).first()
                                    if existing:
                                        logger.info("Reconciled existing order from crashed state", order_id=str(existing.id))
                                        step_exec.status = "PASSED"
                                        step_exec.verification_result = {"reconciled": True, "order_id": str(existing.id)}
                                        step_exec.completed_at = datetime.utcnow()
                                        self.db.commit()
                                        ledger.external_reference = str(existing.id)
                                        self.db.commit()
                                        idem_manager.mark_completed(ledger)
                                        idem_manager.mark_verified(ledger)
                                        demo_db.close()
                                        continue
                                finally:
                                    demo_db.close()
                            except Exception as rex:
                                logger.error("Reconciliation failed", error=str(rex))
                    
                    if ledger is None and step_config.get("action_type") in ["click"]:  # side-effecting actions
                        if "order" in step_id.lower() or "submit" in step_id.lower() or "checkout" in step_id.lower():
                            ledger = idem_manager.create_action(str(run.id), step_id, step_config.get("action_type"))
                    
                    # Inject idempotency key into page before checkout/submit
                    try:
                        if ledger and ("order" in step_id.lower() or "submit" in step_id.lower() or "checkout" in step_id.lower()):
                            if browser.page:
                                await browser.page.evaluate(f"window.__IDEMPOTENCY_KEY__ = '{ledger.idempotency_key}'; localStorage.setItem('__IDEMPOTENCY_KEY__', '{ledger.idempotency_key}');")
                    except Exception as ke:
                        logger.warning("Failed to inject idempotency key", error=str(ke))
                    
                    # Setup lost response after commit if needed
                    failure_config = scenario.configuration.get("failure_injection", {})
                    if failure_config.get("target_step") == step_id and failure_config.get("type") in ["lost_response", "lost_response_after_commit", "network_timeout"]:
                        try:
                            if browser.page and ledger:
                                async def handle_route(route):
                                    headers = dict(route.request.headers)
                                    headers["x-fail-after-commit"] = "lost-response"
                                    if ledger:
                                        headers["idempotency-key"] = ledger.idempotency_key
                                    await route.continue_(headers=headers)
                                await browser.page.route("**/demo/checkout/submit", handle_route)
                        except Exception as re:
                            logger.warning("Failed to setup route interception", error=str(re))
                    
                    # Inject failure if configured
                    try:
                        failure_config = scenario.configuration.get("failure_injection", {})
                        if failure_config.get("target_step") == step_id and failure_config.get("type") in ["lost_response", "lost_response_after_commit"]:
                            # For lost response after commit, let demo app handle it via headers/routes
                            pass
                        else:
                            await failure_injector.inject(step_id, {"run_id": str(run.id), "ledger": ledger, "idempotency_key": ledger.idempotency_key if ledger else None})
                    except Exception as fe:
                        logger.warning("Failure injected", error=str(fe))
                        raise
                    
                    # Execute with retry
                    if ledger:
                        idem_manager.mark_executing(ledger)
                    
                    async def execute():
                        return await executor.execute_step(step_config)
                    
                    try:
                        result = await self.retry_manager.retry_with_backoff(execute)
                    except Exception as ex:
                        # Unknown outcome for side-effecting actions - try reconciliation
                        if ledger and ("order" in step_id.lower() or "submit" in step_id.lower() or "checkout" in step_id.lower()):
                            try:
                                from app.recovery.orchestrator import RecoveryOrchestrator
                                from demo_app.models.order import Order
                                from app.database.session import SessionLocal
                                demo_db = SessionLocal()
                                try:
                                    existing = demo_db.query(Order).filter(Order.idempotency_key == ledger.idempotency_key).first()
                                    if existing:
                                        logger.info("Reconciled: order exists after unknown outcome", order_id=str(existing.id))
                                        step_exec.status = "PASSED"
                                        step_exec.verification_result = {"reconciled": True, "order_id": str(existing.id), "order_number": existing.order_number}
                                        step_exec.completed_at = datetime.utcnow()
                                        self.db.commit()
                                        if ledger:
                                            ledger.external_reference = str(existing.id)
                                            self.db.commit()
                                            idem_manager.mark_completed(ledger)
                                            idem_manager.mark_verified(ledger)
                                        continue  # Move to next step
                                finally:
                                    demo_db.close()
                            except Exception as rex:
                                logger.error("Reconciliation failed", error=str(rex))
                        raise
                    
                    if result.get("status") == "success":
                        step_exec.status = "PASSED"
                        if "screenshot_path" in result:
                            step_exec.screenshot_path = result["screenshot_path"]
                        if ledger:
                            idem_manager.mark_completed(ledger)
                            idem_manager.mark_verified(ledger)
                    else:
                        step_exec.status = "FAILED"
                        step_exec.error_message = result.get("error")
                        run.status = "FAILED"
                    
                    step_exec.completed_at = datetime.utcnow()
                    self.db.commit()
                    
                except Exception as e:
                    step_exec.status = "FAILED"
                    step_exec.error_message = str(e)
                    step_exec.error_type = type(e).__name__
                    step_exec.completed_at = datetime.utcnow()
                    self.db.commit()
                    
                    if self.retry_manager.is_retryable(e):
                        run.status = "RETRYING"
                    else:
                        run.status = "FAILED"
                    self.db.commit()
                    raise
            
            # Check if all passed
            failed_steps = self.db.query(StepExecution).filter(
                StepExecution.run_id == run.id,
                StepExecution.status == "FAILED"
            ).count()
            
            if failed_steps == 0:
                if resume:
                    run.status = "RECOVERED"
                else:
                    run.status = "PASSED"
            else:
                run.status = "FAILED"
            
            run.completed_at = datetime.utcnow()
            self.db.commit()
            
        except Exception as e:
            logger.error("Run execution failed", run_id=str(run.id), error=str(e))
            if run.status not in ["FAILED", "RETRYING"]:
                run.status = "FAILED"
            run.completed_at = datetime.utcnow()
            self.db.commit()
        finally:
            await browser.close()
        
        logger.info("Test run completed", run_id=str(run.id), status=run.status)
        return run
