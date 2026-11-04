import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.base_uuid import GUID


class TestRun(Base):
    __tablename__ = "test_runs"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    scenario_id = Column(GUID(), ForeignKey("scenarios.id"), nullable=False)
    status = Column(String(50), nullable=False)
    environment = Column(String(100))
    total_steps = Column(Integer)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    worker_id = Column(String(255))
    run_metadata = Column('metadata', JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    scenario = relationship("Scenario")
    step_executions = relationship("StepExecution", back_populates="test_run")
