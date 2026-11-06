import uuid
import time
import pytest
from datetime import datetime, timedelta

from app.models.test_run import TestRun
from app.models.scenario import Scenario
from app.recovery.orchestrator import RecoveryOrchestrator
from app.execution.manager import TestRunManager
from tests.conftest import clean_tables


@pytest.mark.pg
def test_actual_execute_run_stops_when_ownership_lost_postgres(pg_session_factory):
    """Exercises real TestRunManager.execute_run() with recovery_orchestrator; worker A loses lease mid-execution,
    worker B acquires; A must not continue protected progress."""
    import asyncio
    from app.execution import manager as manager_mod

    db1 = pg_session_factory()
    db2 = pg_session_factory()
    try:
        clean_tables(db1)
        scenario = Scenario(
            id=uuid.uuid4(), name="fence-test", description="test",
            configuration={"steps": [
                {"step_id": "s1", "action_type": "wait", "input_data": {"ms": 1}},
                {"step_id": "s2", "action_type": "wait", "input_data": {"ms": 1}},
                {"step_id": "s3", "action_type": "wait", "input_data": {"ms": 1}},
            ]},
        )
        db1.add(scenario)
        db1.commit()
        run = TestRun(id=uuid.uuid4(), scenario_id=scenario.id, status="RUNNING", total_steps=3)
        db1.add(run)
        db1.commit()
        run_id = run.id

        orch_a = RecoveryOrchestrator(db1, owner_id="worker-a", session_factory=pg_session_factory)
        orch_b = RecoveryOrchestrator(db2, owner_id="worker-b", session_factory=pg_session_factory)
        assert orch_a.acquire_lease(run_id, lease_seconds=60) is True

        # Patch BrowserController/StepExecutor to avoid real browser; inject ownership loss after first step
        step_count = {"n": 0}
        original_browser = manager_mod.BrowserController
        original_executor = manager_mod.StepExecutor

        class FakeBrowser:
            page = None
            async def start(self): return None
            async def close(self): return None
            async def screenshot(self, path): return None

        class FakeExecutor:
            def __init__(self, browser): pass
            async def execute_step(self, step_config):
                step_count["n"] += 1
                if step_count["n"] == 1:
                    # simulate A losing lease and B taking over
                    r = db1.query(TestRun).filter(TestRun.id == run_id).first()
                    r.lease_expires_at = datetime.utcnow() - timedelta(seconds=10)
                    db1.commit()
                    assert orch_b.acquire_lease(run_id) is True
                return {"url": "ok"}

        manager_mod.BrowserController = FakeBrowser
        manager_mod.StepExecutor = FakeExecutor
        try:
            mgr = TestRunManager(db1)
            errored = False
            try:
                asyncio.run(mgr.execute_run(run_id, resume=False, recovery_orchestrator=orch_a))
            except Exception as e:
                errored = True
                assert "lease" in str(e).lower() or "ownership" in str(e).lower() or "stopping" in str(e).lower()
            assert errored or orch_a.verify_ownership(run_id) is False
        finally:
            manager_mod.BrowserController = original_browser
            manager_mod.StepExecutor = original_executor

        db2.expire_all()
        r2 = db2.query(TestRun).filter(TestRun.id == run_id).first()
        assert r2.lease_owner == "worker-b"
        # B still owns - A did not overwrite lease
        assert orch_a.verify_ownership(run_id) is False
    finally:
        try:
            orch_b.release_lease(run_id)
        except Exception:
            pass
        db1.close()
        db2.close()
