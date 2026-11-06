import uuid
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
def test_same_idempotency_key_creates_only_one_order(pg_session_factory):
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
    try:
        client = TestClient(app)
        key = str(uuid.uuid4())
        resp1 = client.post("/demo/checkout/submit", headers={"Idempotency-Key": key}, cookies={"user_id": user_id})
        assert resp1.status_code == 200, resp1.text
        data1 = resp1.json()
        resp2 = client.post("/demo/checkout/submit", headers={"Idempotency-Key": key}, cookies={"user_id": user_id})
        assert resp2.status_code == 200, resp2.text
        data2 = resp2.json()
        assert data1["order_id"] == data2["order_id"]
    finally:
        app.dependency_overrides.pop(get_db, None)

    db2 = pg_session_factory()
    try:
        orders = db2.query(Order).filter(Order.idempotency_key == key).all()
        assert len(orders) == 1
    finally:
        db2.close()


@pytest.mark.pg
def test_same_key_different_payload_rejected(pg_session_factory):
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
        product1_id = product.id
    finally:
        db.close()

    app.dependency_overrides[get_db] = override_db(pg_session_factory)
    try:
        client = TestClient(app)
        key = str(uuid.uuid4())
        resp1 = client.post("/demo/checkout/submit", headers={"Idempotency-Key": key}, cookies={"user_id": user_id})
        assert resp1.status_code == 200, resp1.text
    finally:
        app.dependency_overrides.pop(get_db, None)

    # Add different item to cart
    db2 = pg_session_factory()
    try:
        user = db2.query(User).filter(User.id == uuid.UUID(user_id)).first()
        product2 = Product(id=uuid.uuid4(), name="Mouse", description="test", price=29.99, stock=10)
        db2.add(product2); db2.commit()
        cart2 = CartItem(id=uuid.uuid4(), user_id=user.id, product_id=product2.id, quantity=1)
        db2.add(cart2); db2.commit()
    finally:
        db2.close()

    app.dependency_overrides[get_db] = override_db(pg_session_factory)
    try:
        client = TestClient(app)
        resp2 = client.post("/demo/checkout/submit", headers={"Idempotency-Key": key}, cookies={"user_id": user_id})
        assert resp2.status_code == 409, resp2.text
    finally:
        app.dependency_overrides.pop(get_db, None)
