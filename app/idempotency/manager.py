import hashlib
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.action_ledger import ActionLedger
from app.core.logging import logger


class IdempotencyManager:
    def __init__(self, db: Session):
        self.db = db
    
    def generate_key(self, run_id: str, step_id: str) -> str:
        data = f"{run_id}:{step_id}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def check_action(self, run_id: str, step_id: str):
        key = self.generate_key(run_id, step_id)
        ledger = self.db.query(ActionLedger).filter(ActionLedger.idempotency_key == key).first()
        return ledger, key
    
    def create_action(self, run_id: str, step_id: str, action_type: str):
        key = self.generate_key(run_id, step_id)
        ledger = ActionLedger(
            run_id=run_id,
            step_id=step_id,
            idempotency_key=key,
            action_type=action_type,
            status="PENDING",
            attempt_number=1
        )
        self.db.add(ledger)
        self.db.commit()
        self.db.refresh(ledger)
        return ledger
    
    def mark_executing(self, ledger: ActionLedger):
        ledger.status = "EXECUTING"
        self.db.commit()
    
    def mark_completed(self, ledger: ActionLedger, external_reference: str = None, response_data: dict = None):
        ledger.status = "COMPLETED"
        ledger.side_effect_occurred = True
        if external_reference:
            ledger.external_reference = external_reference
        if response_data:
            ledger.response_data = response_data
        self.db.commit()
        logger.info("Action marked completed", idempotency_key=ledger.idempotency_key)
    
    def mark_verified(self, ledger: ActionLedger):
        ledger.status = "VERIFIED"
        ledger.verification_status = "VERIFIED"
        ledger.verified_at = datetime.utcnow()
        self.db.commit()
        logger.info("Action verified", idempotency_key=ledger.idempotency_key)
    
    def should_skip(self, ledger: ActionLedger) -> bool:
        # If already completed and verified, skip
        if ledger and ledger.status in ["COMPLETED", "VERIFIED"] and ledger.side_effect_occurred:
            return True
        # If executing/completed but uncertain, need reconciliation - don't blindly skip
        if ledger and ledger.status == "COMPLETED":
            return True
        if ledger and ledger.status == "VERIFIED":
            return True
        return False
