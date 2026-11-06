import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.test_run import TestRun
from app.models.scenario import Scenario
from app.recovery.orchestrator import RecoveryOrchestrator, _schema_error
import app.models
import demo_app.models


def test_schema_error_raises_actionable_runtime_error():
    e = Exception('no such column: test_runs.lease_token')
    with pytest.raises(RuntimeError) as exc:
        _schema_error(e)
    assert 'alembic upgrade head' in str(exc.value)
    assert 'PostgreSQL' in str(exc.value)


def test_extend_release_verify_propagate_schema_runtime_error(tmp_path, monkeypatch):
    """Schema incompatibility should surface as actionable RuntimeError, not silent False."""
    db_path = tmp_path / "s.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SF = sessionmaker(bind=engine)
    db = SF()
    try:
        sc = Scenario(id=uuid.uuid4(), name="t", description="t", configuration={"steps": []})
        db.add(sc); db.commit()
        run = TestRun(id=uuid.uuid4(), scenario_id=sc.id, status="RUNNING", total_steps=0)
        db.add(run); db.commit()
        orch = RecoveryOrchestrator(db, owner_id="w1", session_factory=SF)
        orch.current_lease_token = "tok"

        class BadSession:
            def execute(self, *a, **k): raise Exception("no such column: test_runs.lease_token")
            def query(self, *a, **k): raise Exception("no such column: test_runs.lease_token")
            def rollback(self): pass
            def close(self): pass
            def commit(self): pass
        class BadCtx:
            def __enter__(self): return BadSession()
            def __exit__(self, *a): return False
        monkeypatch.setattr(orch, "_lease_session", lambda: BadCtx())

        with pytest.raises(RuntimeError):
            orch.extend_lease(run.id)
        with pytest.raises(RuntimeError):
            orch.release_lease(run.id)
        with pytest.raises(RuntimeError):
            orch.verify_ownership(run.id)
    finally:
        db.close()
        engine.dispose()


def test_fenced_update_status_passes_extra_fields(tmp_path):
    db_path = tmp_path / "f.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SF = sessionmaker(bind=engine)
    db = SF()
    try:
        from datetime import datetime
        sc = Scenario(id=uuid.uuid4(), name="t", description="t", configuration={"steps": []})
        db.add(sc); db.commit()
        run = TestRun(id=uuid.uuid4(), scenario_id=sc.id, status="RUNNING", total_steps=0)
        db.add(run); db.commit()
        orch = RecoveryOrchestrator(db, owner_id="w1", session_factory=SF)
        assert orch.acquire_lease(run.id) is True
        ts = datetime(2026, 1, 1, 12, 0, 0)
        assert orch.fenced_update_status(run.id, "PASSED", completed_at=ts) is True
        db.expire_all()
        r2 = db.query(TestRun).filter(TestRun.id == run.id).first()
        assert r2.status == "PASSED"
        assert r2.completed_at is not None
    finally:
        db.close()
        engine.dispose()
