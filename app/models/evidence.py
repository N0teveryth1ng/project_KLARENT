import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


class Evidence(Base):
    __tablename__ = "evidence"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False)
    step_id = Column(String(255))
    artifact_type = Column(String(50), nullable=False)  # screenshot, log, network_trace, console_log
    artifact_path = Column(String(512), nullable=False)
    artifact_size = Column(Integer)
    evidence_metadata = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    test_run = relationship("TestRun")
