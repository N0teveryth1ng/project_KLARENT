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
    from app.database.base import Base
    Base.metadata.create_all(bind=engine)
    db_url = os.environ.get('DATABASE_URL') or os.environ.get('TEST_DATABASE_URL')
    db = SessionLocal()
    try:
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
        user_id_str = str(user.id)
        
        # Create scenario for interrupted checkout with lost response after commit
        scenario = Scenario(
            id=uuid.uuid4(),
            name="interrupted_checkout_restart",
            description="test",
            configuration={
                "steps": [
                    {"step_id": "goto_checkout", "action_type": "navigate", "target": "http://localhost:8000/demo/checkout"},
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
        
        run = TestRun(id=uuid.uuid4(), scenario_id=scenario.id, status="PENDING", total_steps=2)
        db.add(run)
        db.commit()
        run_id = str(run.id)
        key = "LOST-RESTART-" + str(run_id)
    finally:
        db.close()
    
    # Add item to cart for the user
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    client.cookies.set("user_id", user_id_str)
    # Login/add to cart
    db = SessionLocal()
    try:
        from demo_app.models.cart import CartItem
        prod = db.query(Product).first()
        cart = CartItem(id=uuid.uuid4(), user_id=uuid.UUID(user_id_str), product_id=prod.id, quantity=1)
        db.add(cart)
        db.commit()
    finally:
        db.close()
    
    # Start worker process to execute the run
    cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    runner_script = os.path.join(cwd, 'scripts', 'run_single.py')
    proc = subprocess.Popen([sys.executable, runner_script, run_id], cwd=cwd)
    
    # Give it time to start and reach checkout
    time.sleep(5)
    
    # Terminate the worker process while it's running (simulating crash)
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    
    time.sleep(2)
    
    # Check if order was created (checkout commits then response lost)
    db = SessionLocal()
    try:
        orders = db.query(Order).all()
        assert len(orders) >= 1  # Order should exist
    finally:
        db.close()
    
    # Start a new worker process to recover
    worker_script = os.path.join(cwd, 'app', 'worker.py')
    proc2 = subprocess.Popen([sys.executable, worker_script], cwd=cwd)
    try:
        proc2.wait(timeout=60)
    except subprocess.TimeoutExpired:
        proc2.terminate()
        proc2.wait(timeout=5)
    
    time.sleep(3)
    
    # Verify recovery - original order verified, exactly one order exists
    db = SessionLocal()
    try:
        orders = db.query(Order).all()
        assert len(orders) == 1  # Exactly one order
    finally:
        db.close()
