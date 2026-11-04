import uuid
import time
import subprocess
import sys
from fastapi.testclient import TestClient
from app.main import app
from app.database.session import SessionLocal
from demo_app.models.user import User
from demo_app.models.product import Product
from demo_app.models.order import Order
from demo_app.models.cart import CartItem
from app.models.test_run import TestRun
from app.models.scenario import Scenario


client = TestClient(app)


def test_checkout_commits_response_lost_recovery_finds_original_order():
    db = SessionLocal()
    try:
        db.query(CartItem).delete()
        db.query(Order).delete()
        db.query(Product).delete()
        db.query(User).delete()
        db.query(TestRun).delete()
        db.query(Scenario).delete()
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
        
        # Create scenario
        scenario = Scenario(
            id=uuid.uuid4(),
            name="lost_response_test",
            description="test",
            configuration={
                "steps": [
                    {"step_id": "submit_order", "action_type": "click", "target": "#checkoutForm button[type='submit']"}
                ],
                "failure_injection": {
                    "type": "lost_response_after_commit",
                    "target_step": "submit_order",
                    "occurrence": 1
                }
            }
        )
        db.add(scenario)
        db.commit()
        scenario_id = scenario.id
    finally:
        db.close()
    
    key = "LOST-" + str(uuid.uuid4())
    db2 = SessionLocal()
    try:
        from app.idempotency.manager import IdempotencyManager
        idem = IdempotencyManager(db2)
        run = TestRun(id=uuid.uuid4(), scenario_id=scenario_id, status="RUNNING", total_steps=1)
        db2.add(run)
        db2.commit()
        ledger = idem.create_action(str(run.id), "submit_order", "click")
        # Override key to our test key
        ledger.idempotency_key = key
        db2.commit()
    finally:
        db2.close()
    
    # Simulate the request - order gets committed then response lost
    client.cookies.set("user_id", user_id)
    try:
        resp = client.post("/demo/checkout/submit", headers={"Idempotency-Key": key, "X-Fail-After-Commit": "lost-response"}, timeout=2)
    except Exception:
        pass  # Expected timeout/lost response
    
    time.sleep(1)
    
    # Check order was created
    db3 = SessionLocal()
    try:
        orders = db3.query(Order).filter(Order.idempotency_key == key).all()
        assert len(orders) == 1  # Order was committed
        order_id = orders[0].id
    finally:
        db3.close()
    
    # Recovery should find the original order
    from app.recovery.orchestrator import RecoveryOrchestrator
    db4 = SessionLocal()
    try:
        orch = RecoveryOrchestrator(db4)
        from app.database.session import SessionLocal as DemoSession
        demo_db = DemoSession()
        try:
            found = orch.verify_order_exists(demo_db, idempotency_key=key)
            assert found is not None
            assert found.id == order_id
        finally:
            demo_db.close()
    finally:
        db4.close()
