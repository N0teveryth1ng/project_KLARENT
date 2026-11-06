import asyncio
import uuid
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.test_run import TestRun
from app.models.scenario import Scenario
from app.models.step_execution import StepExecution
from app.models.execution_event import ExecutionEvent
from app.browser.controller import BrowserController
from app.execution.executor import StepExecutor
from app.failure_injection.injector import FailureInjector
from app.idempotency.manager import IdempotencyManager
from app.recovery.retry_manager import RetryManager
from app.core.logging import logger


class TestRunManager:
    def __init__(self, db: Session):
        self.db = db
        self.retry_manager = RetryManager()

    def _check_lease(self, recovery_orchestrator, run_id):
        if recovery_orchestrator and not recovery_orchestrator.verify_ownership(run_id):
            raise ValueError("Lease ownership lost; stopping execution")

    def _fenced_commit_status(self, recovery_orchestrator, run_id, status: str, **extra):
        if recovery_orchestrator:
            if not recovery_orchestrator.fenced_update_status(run_id, status, **extra):
                raise ValueError("Lease ownership lost before committing recovery state")
            self.db.expire_all()
        else:
            self.db.commit()

    def _fenced_commit(self, recovery_orchestrator, run_id):
        if recovery_orchestrator:
            if not recovery_orchestrator.fence_gate(run_id):
                self.db.rollback()
                raise ValueError("Lease ownership lost before committing protected state")
        self.db.commit()

    async def execute_run(self, run_id: uuid.UUID, resume: bool = False, recovery_orchestrator=None):
        run = self.db.query(TestRun).filter(TestRun.id == run_id).first()
        if not run:
            raise ValueError("Run not found")
        scenario = self.db.query(Scenario).filter(Scenario.id == run.scenario_id).first()

        self._check_lease(recovery_orchestrator, run_id)
        run.status = "RUNNING"
        if not run.started_at:
            run.started_at = datetime.utcnow()
        self._check_lease(recovery_orchestrator, run_id)
        self._fenced_commit_status(recovery_orchestrator, run_id, "RUNNING", started_at=run.started_at)
        # preserve started_at if we used fenced update path (it only set status/worker)
        if recovery_orchestrator and run.started_at:
            try:
                run2 = self.db.query(TestRun).filter(TestRun.id == run_id).first()
                if run2 and not run2.started_at:
                    # best effort; not critical
                    pass
            except Exception:
                pass

        browser = BrowserController()
        failure_injector = FailureInjector(scenario.configuration)
        idem_manager = IdempotencyManager(self.db)

        try:
            browser_cookies = scenario.configuration.get("browser_cookies", [])
            await browser.start(cookies=browser_cookies)
            executor = StepExecutor(browser)

            steps = scenario.configuration.get("steps", [])
            run.total_steps = len(steps)
            self._fenced_commit(recovery_orchestrator, run.id)

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

                if recovery_orchestrator:
                    self._check_lease(recovery_orchestrator, run.id)
                    if not recovery_orchestrator.extend_lease(run.id):
                        raise ValueError("Failed to extend lease; stopping execution")

                step_exec = StepExecution(
                    run_id=run.id,
                    step_id=step_id,
                    status="RUNNING",
                    attempt_number=1,
                    started_at=datetime.utcnow()
                )
                self.db.add(step_exec)
                self._check_lease(recovery_orchestrator, run.id)
                self._fenced_commit(recovery_orchestrator, run.id)

                logger.info("Executing step", run_id=str(run.id), step_id=step_id)

                # Check idempotency - avoid duplicate side effects
                ledger, key = idem_manager.check_action(str(run.id), step_id)
                action_type = step_config.get("action_type", "unknown")
                if not ledger:
                    ledger = idem_manager.create_action(str(run.id), step_id, action_type, commit=(recovery_orchestrator is None))

                if idem_manager.should_skip(ledger) and ledger.status == "VERIFIED":
                    logger.info("Skipping verified step", step_id=step_id)
                    step_exec.status = "PASSED"
                    step_exec.completed_at = datetime.utcnow()
                    self._fenced_commit(recovery_orchestrator, run.id)
                    continue

                # For side-effecting actions (e.g. submit order), inject idempotency key into the page
                is_side_effect = action_type == "click" and step_id == "submit_order"
                if is_side_effect and browser.page:
                    try:
                        await browser.page.evaluate(f"""() => {{ window.__IDEMPOTENCY_KEY__ = '{key}'; }}""")
                    except Exception:
                        pass

                injection = failure_injector.should_inject(step_id)
                if injection:
                    inj_type = injection.get("type")
                    if inj_type == "browser_crash":
                        await browser.close()
                        step_exec.status = "INTERRUPTED"
                        step_exec.error_type = "BrowserCrash"
                        step_exec.error_message = "Browser crashed (injected)"
                        run.status = "INTERRUPTED"
                        self.db.commit()
                        raise Exception("Browser crashed")
                    elif inj_type == "timeout":
                        step_exec.status = "FAILED"
                        step_exec.error_type = "Timeout"
                        step_exec.error_message = "Timeout (injected)"
                        self.db.commit()
                        if not self.retry_manager.is_retryable({"error": "Timeout"}):
                            run.status = "FAILED"
                            self.db.commit()
                            raise Exception("Timeout")
                        continue
                    elif inj_type == "delay":
                        await asyncio.sleep(injection.get("value", 1000) / 1000)
                    elif inj_type == "lost_response_after_commit":
                        # Let execution proceed; we will reconcile after
                        logger.info("Lost response after commit injection - will reconcile", step_id=step_id)

                try:
                    result = await executor.execute_step(step_config)

                    # Handle lost response injection - treat as unknown outcome, reconcile
                    if injection and injection.get("type") == "lost_response_after_commit":
                        logger.info("Lost response simulated, reconciling side effects", step_id=step_id)
                        from app.database.session import SessionLocal
                        demo_db = SessionLocal()
                        try:
                            from app.recovery.orchestrator import RecoveryOrchestrator
                            orch = RecoveryOrchestrator(self.db)
                            existing = orch.verify_order_exists(demo_db, idempotency_key=key)
                            if existing:
                                idem_manager.mark_completed(ledger, external_reference=str(existing.id), response_data={"order_id": str(existing.id)}, commit=(recovery_orchestrator is None))
                                idem_manager.mark_verified(ledger, commit=(recovery_orchestrator is None))
                                step_exec.status = "PASSED"
                                step_exec.completed_at = datetime.utcnow()
                                self._fenced_commit(recovery_orchestrator, run.id)
                                logger.info("Reconciled lost response - order exists", order_id=str(existing.id))
                                continue
                            else:
                                step_exec.status = "FAILED"
                                step_exec.error_message = "Lost response and order not found"
                                run.status = "FAILED"
                                self._fenced_commit(recovery_orchestrator, run.id)
                                raise Exception("Lost response and order not found")
                        finally:
                            demo_db.close()

                    step_exec.status = "PASSED"
                    step_exec.completed_at = datetime.utcnow()
                    idem_manager.mark_executing(ledger, commit=(recovery_orchestrator is None))
                    idem_manager.mark_completed(ledger, external_reference=result.get("url"), commit=(recovery_orchestrator is None))
                    idem_manager.mark_verified(ledger, commit=(recovery_orchestrator is None))
                    self._fenced_commit(recovery_orchestrator, run.id)
                except Exception as e:
                    logger.error("Step failed", step_id=step_id, error=str(e))
                    # Check if this might be a lost response with side effect
                    if is_side_effect and ("timeout" in str(e).lower() or "connection" in str(e).lower() or "lost" in str(e).lower()):
                        from app.database.session import SessionLocal
                        demo_db = SessionLocal()
                        try:
                            from app.recovery.orchestrator import RecoveryOrchestrator
                            orch = RecoveryOrchestrator(self.db)
                            existing = orch.verify_order_exists(demo_db, idempotency_key=key)
                            if existing:
                                idem_manager.mark_completed(ledger, external_reference=str(existing.id), response_data={"order_id": str(existing.id)}, commit=(recovery_orchestrator is None))
                                idem_manager.mark_verified(ledger, commit=(recovery_orchestrator is None))
                                step_exec.status = "PASSED"
                                step_exec.completed_at = datetime.utcnow()
                                self._fenced_commit(recovery_orchestrator, run.id)
                                logger.info("Reconciled timeout - order exists", order_id=str(existing.id))
                                continue
                        finally:
                            demo_db.close()

                    is_retryable = self.retry_manager.is_retryable(e)
                    step_exec.status = "FAILED"
                    step_exec.error_message = str(e)
                    step_exec.error_type = type(e).__name__
                    self._fenced_commit(recovery_orchestrator, run.id)

                    screenshot_path = f"artifacts/screenshots/{run.id}_{step_id}_error.png"
                    try:
                        await browser.screenshot(screenshot_path)
                        step_exec.screenshot_path = screenshot_path
                        self._fenced_commit(recovery_orchestrator, run.id)
                    except:
                        pass

                    if not is_retryable:
                        run.status = "FAILED"
                        self._fenced_commit(recovery_orchestrator, run.id)
                        raise
                    # Retryable - could be retried by retry manager in future; for now fail run
                    run.status = "FAILED"
                    self._fenced_commit(recovery_orchestrator, run.id)
                    raise

            self._check_lease(recovery_orchestrator, run.id)
            run.status = "PASSED"
            run.completed_at = datetime.utcnow()
            self._fenced_commit_status(recovery_orchestrator, run.id, "PASSED", completed_at=run.completed_at)
            logger.info("Run completed", run_id=str(run.id), status="PASSED")

        except Exception as e:
            logger.error("Run failed", run_id=str(run.id), error=str(e))
            try:
                if run.status == "RUNNING":
                    run.status = "FAILED"
                    run.completed_at = datetime.utcnow()
                    if recovery_orchestrator:
                        if recovery_orchestrator.fence_gate(run.id):
                            self.db.commit()
                        else:
                            self.db.rollback()
                    else:
                        self.db.commit()
            except Exception:
                try:
                    self.db.rollback()
                except Exception:
                    pass
            try:
                screenshot_path = f"artifacts/screenshots/{run.id}_failure.png"
                await browser.screenshot(screenshot_path)
            except:
                pass
        finally:
            await browser.close()
