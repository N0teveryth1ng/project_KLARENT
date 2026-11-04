import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.database.session import SessionLocal
from demo_app.models.user import User
from demo_app.models.product import Product
from demo_app.models.order import Order
from demo_app.models.cart import CartItem
from app.database.base import Base
from app.database.session import engine


client = TestClient(app)


def setup_test_data():
    db = SessionLocal()
    try:
        # Clear
        db.query(CartItem).delete()
        db.query(Order).delete()
        db.query(Product).delete()
        db.query(User).delete()
        db.commit()
        
        user = User(id=uuid.uuid4(), username="testuser", email="test@test.com", password_hash="hash")
        db.add(user)
        product = Product(id=uuid.uuid4(), name="Laptop", description="test", price=999.99, stock=10)
        db.add(product)
        db.commit()
        db.refresh(user)
        db.refresh(product)
        
        cart = CartItem(id=uuid.uuid4(), user_id=user.id, product_id=product.id, quantity=1)
        db.add(cart)
        db.commit()
        return str(user.id)
    finally:
        db.close()


def test_same_idempotency_key_creates_only_one_order():
    user_id = setup_test_data()
    db = SessionLocal()
    try:
        key = str(uuid.uuid4())
        # Simulate login by setting cookie
        client.cookies.set("user_id", user_id)
        resp1 = client.post("/demo/checkout/submit", headers={"Idempotency-Key": key})
        assert resp1.status_code == 200
        data1 = resp1.json()
        resp2 = client.post("/demo/checkout/submit", headers={"Idempotency-Key": key})
        assert resp2.status_code == 200
        data2 = resp2.json()
        # Same order returned
        assert data1["order_id"] == data2["order_id"]
        # Only one order exists
        orders = db.query(Order).filter(Order.idempotency_key == key).all()
        assert len(orders) == 1
    finally:
        db.close()


def test_same_key_different_payload_rejected():
    user_id = setup_test_data()
    db = SessionLocal()
    try:
        key = str(uuid.uuid4())
        client.cookies.set("user_id", user_id)
        resp1 = client.post("/demo/checkout/submit", headers={"Idempotency-Key": key})
        assert resp1.status_code == 200
        # Add different item to cart
        user = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
        product2 = Product(id=uuid.uuid4(), name="Mouse", description="test", price=29.99, stock=10)
        db.add(product2)
        db.commit()
        cart2 = CartItem(id=uuid.uuid4(), user_id=user.id, product_id=product2.id, quantity=1)
        db.add(cart2)
        db.commit()
        resp2 = client.post("/demo/checkout/submit", headers={"Idempotency-Key": key})
        assert resp2.status_code == 409
    finally:
        db.close()
