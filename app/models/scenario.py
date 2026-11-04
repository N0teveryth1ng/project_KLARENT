import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, JSON

from app.database.base import Base
from app.models.base_uuid import GUID


class Scenario(Base):
    __tablename__ = "scenarios"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    configuration = Column(JSON, nullable=False)  # steps, retry policy, failure injection
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
