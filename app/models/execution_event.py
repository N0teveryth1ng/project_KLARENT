import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


class ExecutionEvent(Base):
    __tablename__ = "execution_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False)
    step_id = Column(String(255))
    event_type = Column(String(100), nullable=False)
    event_metadata = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    test_run = relationship("TestRun")
