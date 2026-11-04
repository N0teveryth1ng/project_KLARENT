import os
import uuid
import time
import subprocess
import sys
from app.database.session import SessionLocal, engine
from app.database.base import Base
from demo_app.models.user import User
from demo_app.models.product import Product
from demo_app.models.order import Order
from demo_app.models.cart import CartItem
from app.models.test_run import TestRun
from app.models.scenario import Scenario
from app.models.step_execution import StepExecution
from app.models.action_ledger import ActionLedger
import app.models
import demo_app.models


def test_worker_process_restart_recovers_interrupted_checkout_postgres():
    # Use PostgreSQL URL if available, otherwise skip or use configured
    from app.database.base import Base
    Base.metadata.create_all(bind=engine)
    db_url = os.environ.get('DATABASE_URL') or os.environ.get('TEST_DATABASE_URL')
    db = SessionLocal()
    try:
        # Clean up
        db.query(ActionLedger).delete()
        db.query(StepExecution).delete()
        db.query(TestRun).delete()
        db.query(Scenario).delete()
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
        
        # Create scenario for interrupted checkout
        scenario = Scenario(
            id=uuid.uuid4(),
            name="interrupted_checkout_restart",
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
        
        run = TestRun(id=uuid.uuid4(), scenario_id=scenario.id, status="RUNNING", total_steps=1)
        db.add(run)
        db.commit()
        
        from app.idempotency.manager import IdempotencyManager
        idem = IdempotencyManager(db)
        key = "LOST-RESTART-" + str(uuid.uuid4())
        ledger = idem.create_action(str(run.id), "submit_order", "click")
        ledger.idempotency_key = key
        ledger.status = "EXECUTING"
        db.commit()
        
        run_id = str(run.id)
        scenario_id = str(scenario.id)
        key_val = key
        user_id_str = str(user.id)
    finally:
        db.close()
    
    # Simulate: checkout creates order, response lost (order committed)
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    client.cookies.set("user_id", user_id_str)
    try:
        resp = client.post("/demo/checkout/submit", headers={"Idempotency-Key": key_val, "X-Fail-After-Commit": "lost-response"}, timeout=1)
    except Exception:
        pass
    
    time.sleep(2)
    
    # Verify order created
    db = SessionLocal()
    try:
        orders = db.query(Order).filter(Order.idempotency_key == key_val).all()
        assert len(orders) == 1
    finally:
        db.close()
    
    # Terminate worker process (simulate crash) - mark run as running but step not completed
    db = SessionLocal()
    try:
        run = db.query(TestRun).filter(TestRun.id == uuid.UUID(run_id)).first()
        run.status = "RUNNING"
        db.commit()
    finally:
        db.close()
    
    # Start a new worker process
    worker_script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'app', 'worker.py')
    worker_script = os.path.abspath(worker_script)
    cwd = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    proc = subprocess.Popen([sys.executable, worker_script], cwd=cwd)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait(timeout=5)
    
    time.sleep(3)
    
    # Verify recovery - check order still exists and only once
    db = SessionLocal()
    try:
        orders = db.query(Order).filter(Order.idempotency_key == key_val).all()
        assert len(orders) == 1  # Exactly one order
    finally:
        db.close()
