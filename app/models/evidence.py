import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.base_uuid import GUID


class Evidence(Base):
    __tablename__ = "evidence"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id = Column(GUID(), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False)
    step_id = Column(String(255))
    artifact_type = Column(String(50), nullable=False)
    artifact_path = Column(String(512), nullable=False)
    artifact_size = Column(Integer)
    evidence_metadata = Column('metadata', JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    test_run = relationship("TestRun")
