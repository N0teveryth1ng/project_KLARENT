from sqlalchemy.orm import Session
from datetime import datetime

from app.models.test_run import TestRun
from app.models.step_execution import StepExecution
from app.models.action_ledger import ActionLedger
from app.idempotency.manager import IdempotencyManager
from app.core.logging import logger


class RecoveryOrchestrator:
    def __init__(self, db: Session):
        self.db = db
        self.idem_manager = IdempotencyManager(db)
    
    async def resume_run(self, run_id: str):
        run = self.db.query(TestRun).filter(TestRun.id == run_id).first()
        if not run:
            raise ValueError("Run not found")
        
        logger.info("Resuming run", run_id=run_id, status=run.status)
        
        # Find last completed step
        completed_steps = self.db.query(StepExecution).filter(
            StepExecution.run_id == run_id,
            StepExecution.status == "PASSED"
        ).all()
        completed_step_ids = [s.step_id for s in completed_steps]
        
        logger.info("Found completed steps", count=len(completed_step_ids))
        
        # Mark as running again
        run.status = "RUNNING"
        self.db.commit()
        
        return run, completed_step_ids
    
    def check_side_effect(self, run_id: str, step_id: str):
        ledger, key = self.idem_manager.check_action(run_id, step_id)
        if ledger and self.idem_manager.should_skip(ledger):
            logger.info("Side effect already occurred, skipping", step_id=step_id)
            return True, ledger
        return False, ledger
    
    def verify_order_exists(self, db_demo, order_id: str = None, idempotency_key: str = None):
        from demo_app.models.order import Order
        if order_id:
            order = db_demo.query(Order).filter(Order.id == order_id).first()
        elif idempotency_key:
            order = db_demo.query(Order).filter(Order.idempotency_key == idempotency_key).first()
        else:
            return None
        return order
