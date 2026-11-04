import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, Numeric, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID

from app.database.base import Base


class Product(Base):
    __tablename__ = "demo_products"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    price = Column(Numeric(10, 2), nullable=False)
    stock = Column(Integer, default=0)
    image_url = Column(String(512))
    created_at = Column(DateTime, default=datetime.utcnow)
