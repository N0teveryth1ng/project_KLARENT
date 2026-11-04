import uuid
from datetime import datetime

from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


class Order(Base):
    __tablename__ = "demo_orders"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("demo_users.id"), nullable=False)
    order_number = Column(String(50), unique=True, nullable=False)
    items = Column(JSON, nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)
    status = Column(String(50), default="pending")
    idempotency_key = Column(String(255), unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User")
