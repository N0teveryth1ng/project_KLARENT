import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


class ActionLedger(Base):
    __tablename__ = "action_ledger"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False)
    step_id = Column(String(255), nullable=False)
    idempotency_key = Column(String(255), nullable=False, unique=True)
    action_type = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False)  # PENDING, EXECUTING, COMPLETED, FAILED, VERIFIED
    attempt_number = Column(Integer, default=1)
    external_reference = Column(String(255))  # e.g., order_id
    verification_status = Column(String(50))
    side_effect_occurred = Column(Boolean, default=False)
    request_data = Column(JSON)
    response_data = Column(JSON)
    verified_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    test_run = relationship("TestRun")
