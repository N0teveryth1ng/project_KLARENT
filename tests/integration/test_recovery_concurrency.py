import uuid
import time
from datetime import datetime, timedelta

import pytest

from app.models.test_run import TestRun
from app.models.scenario import Scenario
from app.recovery.orchestrator import RecoveryOrchestrator
from tests.conftest import clean_tables


@pytest.mark.pg
def test_two_workers_cannot_acquire_same_active_lease_postgres(pg_session_factory):
    db1 = pg_session_factory()
    db2 = pg_session_factory()
    try:
        clean_tables(db1)
        scenario = Scenario(id=uuid.uuid4(), name="test", description="test", configuration={"steps": []})
        db1.add(scenario)
        db1.commit()
        run = TestRun(id=uuid.uuid4(), scenario_id=scenario.id, status="RUNNING", total_steps=0)
        db1.add(run)
        db1.commit()
        run_id = run.id

        orch1 = RecoveryOrchestrator(db1, owner_id="worker-1", session_factory=pg_session_factory)
        orch2 = RecoveryOrchestrator(db2, owner_id="worker-2", session_factory=pg_session_factory)

        assert orch1.acquire_lease(run_id) is True
        assert orch2.acquire_lease(run_id) is False
        # verify owner/token still worker-1
        db2.expire_all()
        r = db2.query(TestRun).filter(TestRun.id == run_id).first()
        assert r.lease_owner == "worker-1"
        assert r.lease_token is not None
    finally:
        try:
            orch1.release_lease(run_id)
        except Exception:
            pass
        db1.close()
        db2.close()


@pytest.mark.pg
def test_expired_lease_can_be_reclaimed_postgres(pg_session_factory):
    db1 = pg_session_factory()
    db2 = pg_session_factory()
    try:
        clean_tables(db1)
        scenario = Scenario(id=uuid.uuid4(), name="test2", description="test", configuration={"steps": []})
        db1.add(scenario)
        db1.commit()
        run = TestRun(id=uuid.uuid4(), scenario_id=scenario.id, status="RUNNING", total_steps=0)
        db1.add(run)
        db1.commit()
        run_id = run.id

        orch1 = RecoveryOrchestrator(db1, owner_id="worker-crashed", session_factory=pg_session_factory)
        orch2 = RecoveryOrchestrator(db2, owner_id="worker-new", session_factory=pg_session_factory)

        assert orch1.acquire_lease(run_id, lease_seconds=60) is True
        r = db1.query(TestRun).filter(TestRun.id == run_id).first()
        r.lease_expires_at = datetime.utcnow() - timedelta(seconds=10)
        db1.commit()

        assert orch2.acquire_lease(run_id) is True
        db2.expire_all()
        r2 = db2.query(TestRun).filter(TestRun.id == run_id).first()
        assert r2.lease_owner == "worker-new"
    finally:
        try:
            orch2.release_lease(run_id)
        except Exception:
            pass
        db1.close()
        db2.close()


@pytest.mark.pg
def test_old_worker_cannot_renew_or_release_new_lease_postgres(pg_session_factory):
    db1 = pg_session_factory()
    db2 = pg_session_factory()
    try:
        clean_tables(db1)
        scenario = Scenario(id=uuid.uuid4(), name="test3", description="test", configuration={"steps": []})
        db1.add(scenario)
        db1.commit()
        run = TestRun(id=uuid.uuid4(), scenario_id=scenario.id, status="RUNNING", total_steps=0)
        db1.add(run)
        db1.commit()
        run_id = run.id

        orch1 = RecoveryOrchestrator(db1, owner_id="worker-old", session_factory=pg_session_factory)
        orch2 = RecoveryOrchestrator(db2, owner_id="worker-new", session_factory=pg_session_factory)

        assert orch1.acquire_lease(run_id, lease_seconds=60) is True
        old_token = orch1.current_lease_token
        r = db1.query(TestRun).filter(TestRun.id == run_id).first()
        r.lease_expires_at = datetime.utcnow() - timedelta(seconds=10)
        db1.commit()
        assert orch2.acquire_lease(run_id) is True
        assert orch2.current_lease_token != old_token

        assert orch1.extend_lease(run_id) is False
        assert orch1.release_lease(run_id) is False

        db2.expire_all()
        run_check = db2.query(TestRun).filter(TestRun.id == run_id).first()
        assert run_check.lease_owner == "worker-new"
        assert run_check.lease_token == orch2.current_lease_token
    finally:
        try:
            orch2.release_lease(run_id)
        except Exception:
            pass
        db1.close()
        db2.close()


@pytest.mark.pg
def test_worker_loses_lease_cannot_continue_postgres(pg_session_factory):
    db1 = pg_session_factory()
    db2 = pg_session_factory()
    try:
        clean_tables(db1)
        scenario = Scenario(id=uuid.uuid4(), name="test4", description="test", configuration={"steps": []})
        db1.add(scenario)
        db1.commit()
        run = TestRun(id=uuid.uuid4(), scenario_id=scenario.id, status="RUNNING", total_steps=0)
        db1.add(run)
        db1.commit()
        run_id = run.id

        orch1 = RecoveryOrchestrator(db1, owner_id="worker-1", session_factory=pg_session_factory)
        orch2 = RecoveryOrchestrator(db2, owner_id="worker-2", session_factory=pg_session_factory)

        assert orch1.acquire_lease(run_id, lease_seconds=60) is True
        assert orch1.verify_ownership(run_id) is True

        r = db1.query(TestRun).filter(TestRun.id == run_id).first()
        r.lease_expires_at = datetime.utcnow() - timedelta(seconds=10)
        db1.commit()
        assert orch2.acquire_lease(run_id) is True

        assert orch1.verify_ownership(run_id) is False
        assert orch1.extend_lease(run_id) is False
        assert orch1.current_lease_token is None or orch1.verify_ownership(run_id) is False
    finally:
        try:
            orch2.release_lease(run_id)
        except Exception:
            pass
        db1.close()
        db2.close()


@pytest.mark.pg
def test_recovery_acquires_lease_once_and_reaches_execution_postgres(pg_session_factory):
    import asyncio
    from app.execution.manager import TestRunManager

    db = pg_session_factory()
    try:
        clean_tables(db)
        scenario = Scenario(
            id=uuid.uuid4(), name="test5", description="test",
            configuration={"steps": [{"step_id": "s1", "action_type": "wait", "input_data": {"ms": 1}}]},
        )
        db.add(scenario)
        db.commit()
        run = TestRun(id=uuid.uuid4(), scenario_id=scenario.id, status="RUNNING", total_steps=1)
        db.add(run)
        db.commit()
        run_id = run.id

        orch = RecoveryOrchestrator(db, owner_id="worker-recover", session_factory=pg_session_factory)
        acquire_calls = []
        original_acquire = orch.acquire_lease

        def counting_acquire(*args, **kwargs):
            acquire_calls.append((args, kwargs))
            return original_acquire(*args, **kwargs)

        orch.acquire_lease = counting_acquire
        reached_execute = {"v": False}
        original_execute = TestRunManager.execute_run

        async def fake_execute(self, run_id, resume=False, recovery_orchestrator=None):
            reached_execute["v"] = True
            # verify lease is held
            assert recovery_orchestrator is not None
            assert recovery_orchestrator.verify_ownership(run_id) is True

        TestRunManager.execute_run = fake_execute
        try:
            asyncio.run(orch.recover_incomplete_runs(TestRunManager))
        finally:
            TestRunManager.execute_run = original_execute

        assert len(acquire_calls) == 1, f"expected 1 acquire, got {len(acquire_calls)}"
        assert reached_execute["v"] is True
    finally:
        try:
            orch.release_lease(run_id)
        except Exception:
            pass
        db.close()


@pytest.mark.pg
def test_crashed_worker_lease_expires_and_reclaimed_postgres(pg_session_factory):
    db1 = pg_session_factory()
    db2 = pg_session_factory()
    try:
        clean_tables(db1)
        scenario = Scenario(id=uuid.uuid4(), name="test6", description="test", configuration={"steps": []})
        db1.add(scenario)
        db1.commit()
        run = TestRun(id=uuid.uuid4(), scenario_id=scenario.id, status="RUNNING", total_steps=0)
        db1.add(run)
        db1.commit()
        run_id = run.id

        orch1 = RecoveryOrchestrator(db1, owner_id="worker-crashed", session_factory=pg_session_factory)
        orch2 = RecoveryOrchestrator(db2, owner_id="worker-recover", session_factory=pg_session_factory)

        assert orch1.acquire_lease(run_id, lease_seconds=1) is True
        time.sleep(2)
        db2.expire_all()
        assert orch2.acquire_lease(run_id) is True
        db2.expire_all()
        r = db2.query(TestRun).filter(TestRun.id == run_id).first()
        assert r.lease_owner == "worker-recover"
    finally:
        try:
            orch2.release_lease(run_id)
        except Exception:
            pass
        db1.close()
        db2.close()
