import uuid
from datetime import datetime

from sqlalchemy import Column, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.base_uuid import GUID


class Evaluation(Base):
    __tablename__ = "evaluations"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    scenario_id = Column(GUID(), ForeignKey("scenarios.id"), nullable=False)
    sample_size = Column(Integer, nullable=False)
    metrics = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    scenario = relationship("Scenario")
