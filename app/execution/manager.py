import uuid
from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from app.models.test_run import TestRun
from app.models.step_execution import StepExecution
from app.models.scenario import Scenario
from app.execution.executor import StepExecutor
from app.browser.controller import BrowserController
from app.core.logging import logger


class TestRunManager:
    def __init__(self, db: Session):
        self.db = db
    
    async def create_run(self, scenario_id: uuid.UUID, environment: str = "default") -> TestRun:
        scenario = self.db.query(Scenario).filter(Scenario.id == scenario_id).first()
        if not scenario:
            raise ValueError("Scenario not found")
        
        run = TestRun(
            scenario_id=scenario_id,
            status="PENDING",
            environment=environment,
            total_steps=len(scenario.configuration.get("steps", [])),
            metadata={}
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        logger.info("Test run created", run_id=str(run.id))
        return run
    
    async def execute_run(self, run_id: uuid.UUID):
        run = self.db.query(TestRun).filter(TestRun.id == run_id).first()
        scenario = self.db.query(Scenario).filter(Scenario.id == run.scenario_id).first()
        
        run.status = "RUNNING"
        run.started_at = datetime.utcnow()
        self.db.commit()
        
        browser = BrowserController()
        try:
            await browser.start()
            executor = StepExecutor(browser)
            
            steps = scenario.configuration.get("steps", [])
            for step_config in steps:
                step_exec = StepExecution(
                    run_id=run.id,
                    step_id=step_config["step_id"],
                    status="RUNNING",
                    attempt_number=1,
                    started_at=datetime.utcnow()
                )
                self.db.add(step_exec)
                self.db.commit()
                
                result = await executor.execute_step(step_config)
                
                if result["status"] == "success":
                    step_exec.status = "PASSED"
                    if "screenshot_path" in result:
                        step_exec.screenshot_path = result["screenshot_path"]
                else:
                    step_exec.status = "FAILED"
                    step_exec.error_message = result.get("error")
                
                step_exec.completed_at = datetime.utcnow()
                self.db.commit()
            
            # Check if all passed
            failed_steps = self.db.query(StepExecution).filter(
                StepExecution.run_id == run.id,
                StepExecution.status == "FAILED"
            ).count()
            
            if failed_steps == 0:
                run.status = "PASSED"
            else:
                run.status = "FAILED"
            
            run.completed_at = datetime.utcnow()
            self.db.commit()
            
        finally:
            await browser.close()
        
        logger.info("Test run completed", run_id=str(run.id), status=run.status)
        return run
