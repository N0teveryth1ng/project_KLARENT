import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.base_uuid import GUID


class ExecutionEvent(Base):
    __tablename__ = "execution_events"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id = Column(GUID(), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False)
    step_id = Column(String(255))
    event_type = Column(String(100), nullable=False)
    event_metadata = Column('metadata', JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    test_run = relationship("TestRun")
