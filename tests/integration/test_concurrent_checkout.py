import uuid
import threading
from fastapi.testclient import TestClient
from app.main import app
from app.database.session import SessionLocal
from demo_app.models.user import User
from demo_app.models.product import Product
from demo_app.models.order import Order
from demo_app.models.cart import CartItem


client = TestClient(app)


def test_concurrent_duplicate_checkout_creates_one_order():
    db = SessionLocal()
    try:
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
        user_id = str(user.id)
    finally:
        db.close()
    
    key = str(uuid.uuid4())
    results = []
    
    def make_request():
        try:
            client.cookies.set("user_id", user_id)
            resp = client.post("/demo/checkout/submit", headers={"Idempotency-Key": key})
            results.append(resp.status_code)
        except Exception as e:
            results.append(500)
    
    t1 = threading.Thread(target=make_request)
    t2 = threading.Thread(target=make_request)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    
    db = SessionLocal()
    try:
        orders = db.query(Order).filter(Order.idempotency_key == key).all()
        assert len(orders) == 1
    finally:
        db.close()
