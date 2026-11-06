import os
import uuid
import time
import subprocess
import sys
import pytest

from demo_app.models.user import User
from demo_app.models.product import Product
from demo_app.models.order import Order
from demo_app.models.cart import CartItem
from app.models.test_run import TestRun
from app.models.scenario import Scenario
from app.models.step_execution import StepExecution
from app.models.action_ledger import ActionLedger
from tests.conftest import clean_tables, pg_test_url


@pytest.mark.pg
@pytest.mark.skipif(
    os.environ.get("RUN_WORKER_RESTART_E2E") != "1",
    reason=(
        "Heavy E2E test: requires running demo server on localhost:8000, "
        "Playwright browsers, and subprocess workers using the test DB. "
        "Set RUN_WORKER_RESTART_E2E=1 to run."
    )
)
def test_worker_process_restart_recovers_interrupted_checkout_postgres(
    pg_session_factory
):
    """Attempts real worker process restart recovery."""

    db_url = pg_test_url()
    db = pg_session_factory()

    try:
        clean_tables(db)

        user = User(
            id=uuid.uuid4(),
            username="testuser",
            email="test@test.com",
            password_hash="hash"
        )

        product = Product(
            id=uuid.uuid4(),
            name="Laptop",
            description="test",
            price=999.99,
            stock=10
        )

        db.add(user)
        db.add(product)
        db.commit()

        user_id_str = str(user.id)

        cart = CartItem(
            id=uuid.uuid4(),
            user_id=user.id,
            product_id=product.id,
            quantity=1
        )

        db.add(cart)

        scenario = Scenario(
            id=uuid.uuid4(),
            name="interrupted_checkout_restart",
            description="test",
            configuration={
                "steps": [
                    {
                        "step_id": "goto_checkout",
                        "action_type": "navigate",
                        "target": "http://localhost:8000/demo/checkout"
                    },
                    {
                        "step_id": "submit_order",
                        "action_type": "click",
                        "target": "#checkoutForm button[type='submit']"
                    }
                ],
                "failure_injection": {
                    "type": "lost_response_after_commit",
                    "target_step": "submit_order",
                    "occurrence": 1
                },
                "browser_cookies": [
                    {
                        "name": "user_id",
                        "value": user_id_str,
                        "url": "http://localhost"
                    }
                ]
            }
        )

        db.add(scenario)

        run = TestRun(
            id=uuid.uuid4(),
            scenario_id=scenario.id,
            status="PENDING",
            total_steps=2
        )

        db.add(run)
        db.commit()

        run_id = str(run.id)

    finally:
        db.close()

    cwd = os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
    )

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    env["TEST_DATABASE_URL"] = db_url

    runner_script = os.path.join(
        cwd,
        "scripts",
        "run_single.py"
    )

    # Start the initial worker process.
    proc = subprocess.Popen(
        [sys.executable, runner_script, run_id],
        cwd=cwd,
        env=env
    )

    time.sleep(5)

    # Simulate worker interruption.
    try:
        proc.terminate()
        proc.wait(timeout=5)

    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    time.sleep(2)

    # Start recovery worker.
    worker_script = os.path.join(
        cwd,
        "app",
        "worker.py"
    )

    proc2 = subprocess.Popen(
        [sys.executable, "-m", "app.worker"],
        cwd=cwd,
        env=env
    )

    try:
        proc2.wait(timeout=60)

    except subprocess.TimeoutExpired:
        proc2.terminate()
        proc2.wait(timeout=5)

    time.sleep(2)

    # Verify exactly one order exists.
    db = pg_session_factory()

    try:
        orders = db.query(Order).all()
        assert len(orders) == 1, (
            f"Expected exactly one order, found {len(orders)}"
        )

    finally:
        db.close()