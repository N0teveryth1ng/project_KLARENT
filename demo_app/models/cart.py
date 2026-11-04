import uuid
from datetime import datetime

from sqlalchemy import Column, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


class CartItem(Base):
    __tablename__ = "demo_cart_items"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("demo_users.id"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("demo_products.id"), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")
    product = relationship("Product")
