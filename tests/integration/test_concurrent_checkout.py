import uuid
import threading
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.session import get_db
from demo_app.models.user import User
from demo_app.models.product import Product
from demo_app.models.order import Order
from demo_app.models.cart import CartItem
from tests.conftest import clean_tables


def override_db(factory):
    def _override():
        s = factory()
        try:
            yield s
        finally:
            s.close()
    return _override


@pytest.mark.pg
def test_concurrent_duplicate_checkout_creates_one_order(pg_session_factory):
    db = pg_session_factory()
    try:
        clean_tables(db)
        user = User(id=uuid.uuid4(), username="testuser", email="test@test.com", password_hash="hash")
        product = Product(id=uuid.uuid4(), name="Laptop", description="test", price=999.99, stock=10)
        db.add(user); db.add(product); db.commit()
        db.refresh(user); db.refresh(product)
        cart = CartItem(id=uuid.uuid4(), user_id=user.id, product_id=product.id, quantity=1)
        db.add(cart); db.commit()
        user_id = str(user.id)
    finally:
        db.close()

    app.dependency_overrides[get_db] = override_db(pg_session_factory)
    key = str(uuid.uuid4())
    results = []
    errors = []

    def make_request():
        try:
            c = TestClient(app)
            resp = c.post("/demo/checkout/submit", headers={"Idempotency-Key": key}, cookies={"user_id": user_id})
            results.append(resp.status_code)
        except Exception as e:
            errors.append(str(e))
            results.append(500)

    try:
        t1 = threading.Thread(target=make_request)
        t2 = threading.Thread(target=make_request)
        t1.start(); t2.start()
        t1.join(timeout=30); t2.join(timeout=30)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert not errors, f"Errors: {errors}"
    db2 = pg_session_factory()
    try:
        orders = db2.query(Order).filter(Order.idempotency_key == key).all()
        assert len(orders) == 1, f"Expected exactly 1 order, got {len(orders)}, statuses={results}"
    finally:
        db2.close()
