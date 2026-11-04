import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


class StepExecution(Base):
    __tablename__ = "step_executions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False)
    step_id = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False)
    attempt_number = Column(Integer, default=1)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_type = Column(String(100))
    error_message = Column(String)
    error_details = Column(JSON)
    verification_result = Column(JSON)
    screenshot_path = Column(String(512))
    step_metadata = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    test_run = relationship("TestRun", back_populates="step_executions")
    
    __table_args__ = (
        UniqueConstraint('run_id', 'step_id', 'attempt_number'),
    )
