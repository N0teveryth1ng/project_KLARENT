import uuid
import time
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.session import get_db
from demo_app.models.user import User
from demo_app.models.product import Product
from demo_app.models.order import Order
from demo_app.models.cart import CartItem
from app.models.test_run import TestRun
from app.models.scenario import Scenario
from app.models.step_execution import StepExecution
from app.models.action_ledger import ActionLedger
from tests.conftest import clean_tables


@pytest.mark.pg
def test_checkout_commits_response_lost_recovery_finds_original_order(pg_session_factory):
    """Order is committed to DB, response lost after commit; recovery/orchestrator can find original order by idempotency key; no duplicate."""
    db = pg_session_factory()
    try:
        clean_tables(db)
        user = User(id=uuid.uuid4(), username="testuser", email="test@test.com", password_hash="hash")
        product = Product(id=uuid.uuid4(), name="Laptop", description="test", price=999.99, stock=10)
        db.add(user)
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

    # Override app DB to use test PG
    def override_get_db():
        s = pg_session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app, raise_server_exceptions=False)
        key = "LOST-" + str(uuid.uuid4())
        client.cookies.set("user_id", user_id)

        # This request commits the order, then simulates lost response (sleeps/raises)
        resp = client.post(
            "/demo/checkout/submit",
            headers={"Idempotency-Key": key, "X-Fail-After-Commit": "lost-response"},
            timeout=15,
        )
        # Response may be 504 or exception surfaced; the critical thing is order committed
    finally:
        app.dependency_overrides.pop(get_db, None)

    # Verify order was committed despite lost response
    db2 = pg_session_factory()
    try:
        orders = db2.query(Order).filter(Order.idempotency_key == key).all()
        assert len(orders) == 1, f"Expected 1 committed order, found {len(orders)}"
        order_id = orders[0].id

        # Recovery path: orchestrator can verify/find the original order
        from app.recovery.orchestrator import RecoveryOrchestrator
        orch = RecoveryOrchestrator(db2)
        found = orch.verify_order_exists(db2, idempotency_key=key)
        assert found is not None
        assert found.id == order_id

        # Retry with same key must not create duplicate
        app.dependency_overrides[get_db] = override_get_db
        try:
            client2 = TestClient(app)
            client2.cookies.set("user_id", user_id)
            # Cart was cleared; retry should return existing order
            resp2 = client2.post("/demo/checkout/submit", headers={"Idempotency-Key": key})
            assert resp2.status_code == 200
            data = resp2.json()
            assert str(data.get("order_id")) == str(order_id) or data.get("order_number") == orders[0].order_number
        finally:
            app.dependency_overrides.pop(get_db, None)

        orders_after = db2.query(Order).filter(Order.idempotency_key == key).all()
        assert len(orders_after) == 1, "Duplicate order created on retry after lost response"
    finally:
        db2.close()
