import os
import uuid
from datetime import datetime, timedelta
from contextlib import contextmanager
from sqlalchemy.orm import Session
from sqlalchemy import or_, update

from app.models.test_run import TestRun
from app.models.step_execution import StepExecution
from app.idempotency.manager import IdempotencyManager
from app.core.logging import logger

def _schema_error(e: Exception):
    msg = str(e).lower()
    if 'lease_token' in msg or 'no such column' in msg or 'undefinedcolumn' in msg.replace('_',''):
        raise RuntimeError(
            "Database schema is incompatible with lease/recovery features (missing lease columns such as lease_token). "
            "PostgreSQL is required for recovery/lease guarantees. Run `alembic upgrade head` on a supported PostgreSQL database. "
            "SQLite migrations are not portable in this project (migrations use PostgreSQL-specific types)."
        ) from e


class RecoveryOrchestrator:
    def __init__(self, db: Session, owner_id: str = None, session_factory=None):
        self.db = db  # workflow/app session
        self.idem_manager = IdempotencyManager(db)
        self.owner_id = owner_id or f"worker-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.current_lease_token = None
        if session_factory is not None:
            self._session_factory = session_factory
        else:
            # default to app's session factory
            from app.database.session import SessionLocal
            self._session_factory = SessionLocal

    @contextmanager
    def _lease_session(self):
        db = self._session_factory()
        try:
            yield db
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                db.close()
            except Exception:
                pass

    def _is_owner_row(self, run) -> bool:
        if not run:
            return False
        now = datetime.utcnow()
        return (
            run.lease_owner == self.owner_id
            and run.lease_token
            and run.lease_token == self.current_lease_token
            and run.lease_expires_at
            and run.lease_expires_at > now
        )

    def acquire_lease(self, run_id, lease_seconds: int = 300):
        now = datetime.utcnow()
        expires = now + timedelta(seconds=lease_seconds)
        run_uuid = run_id if isinstance(run_id, uuid.UUID) else uuid.UUID(str(run_id))
        token = uuid.uuid4().hex
        try:
            with self._lease_session() as ldb:
                result = ldb.execute(
                    update(TestRun)
                    .where(
                        TestRun.id == run_uuid,
                        or_(TestRun.lease_owner.is_(None), TestRun.lease_expires_at <= now),
                    )
                    .values(
                        lease_owner=self.owner_id,
                        lease_expires_at=expires,
                        lease_token=token,
                        worker_id=self.owner_id,
                    )
                )
                if result.rowcount == 0:
                    ldb.rollback()
                    self.current_lease_token = None
                    return False
                ldb.commit()
                run = ldb.query(TestRun).filter(TestRun.id == run_uuid).first()
                if run and run.lease_owner == self.owner_id and run.lease_token == token and run.lease_expires_at and run.lease_expires_at > now:
                    self.current_lease_token = token
                    try:
                        self.db.expire_all()
                    except Exception:
                        pass
                    return True
                self.current_lease_token = None
                return False
        except RuntimeError:
            raise
        except Exception as e:
            _schema_error(e)
            self.current_lease_token = None
            return False

    def extend_lease(self, run_id, lease_seconds: int = 300):
        if not self.current_lease_token:
            return False
        now = datetime.utcnow()
        expires = now + timedelta(seconds=lease_seconds)
        run_uuid = run_id if isinstance(run_id, uuid.UUID) else uuid.UUID(str(run_id))
        try:
            with self._lease_session() as ldb:
                result = ldb.execute(
                    update(TestRun)
                    .where(
                        TestRun.id == run_uuid,
                        TestRun.lease_owner == self.owner_id,
                        TestRun.lease_token == self.current_lease_token,
                        TestRun.lease_expires_at > now,
                    )
                    .values(lease_expires_at=expires)
                )
                if result.rowcount == 0:
                    ldb.rollback()
                    self.current_lease_token = None
                    return False
                ldb.commit()
                return True
        except RuntimeError:
            raise
        except Exception as e:
            _schema_error(e)
            self.current_lease_token = None
            return False

    def release_lease(self, run_id):
        if not self.current_lease_token:
            return False
        run_uuid = run_id if isinstance(run_id, uuid.UUID) else uuid.UUID(str(run_id))
        try:
            with self._lease_session() as ldb:
                result = ldb.execute(
                    update(TestRun)
                    .where(
                        TestRun.id == run_uuid,
                        TestRun.lease_owner == self.owner_id,
                        TestRun.lease_token == self.current_lease_token,
                    )
                    .values(lease_owner=None, lease_expires_at=None, lease_token=None)
                )
                if result.rowcount == 0:
                    ldb.rollback()
                    self.current_lease_token = None
                    return False
                ldb.commit()
                self.current_lease_token = None
                return True
        except RuntimeError:
            raise
        except Exception as e:
            _schema_error(e)
            self.current_lease_token = None
            return False

    def verify_ownership(self, run_id) -> bool:
        if not self.current_lease_token:
            return False
        run_uuid = run_id if isinstance(run_id, uuid.UUID) else uuid.UUID(str(run_id))
        try:
            with self._lease_session() as ldb:
                run = ldb.query(TestRun).filter(TestRun.id == run_uuid).first()
                if not run:
                    self.current_lease_token = None
                    return False
                # Ensure we have the latest state from the DB
                try:
                    ldb.refresh(run)
                except Exception:
                    pass
                now = datetime.utcnow()
                ok = (run.lease_owner == self.owner_id and run.lease_token == self.current_lease_token and
                      run.lease_expires_at and run.lease_expires_at > now)
                if not ok:
                    self.current_lease_token = None
                return ok
        except RuntimeError:
            raise
        except Exception as e:
            _schema_error(e)
    

    def fence_gate(self, run_id) -> bool:
        """Atomic ownership gate on the WORKFLOW session (self.db). Executes conditional UPDATE but does NOT commit.
        If True, caller should commit protected workflow state. If False, caller must rollback and stop."""
        if not self.current_lease_token:
            return False
        run_uuid = run_id if isinstance(run_id, uuid.UUID) else uuid.UUID(str(run_id))
        now = datetime.utcnow()
        try:
            result = self.db.execute(
                update(TestRun)
                .where(
                    TestRun.id == run_uuid,
                    TestRun.lease_owner == self.owner_id,
                    TestRun.lease_token == self.current_lease_token,
                    TestRun.lease_expires_at > now,
                )
                .values(worker_id=self.owner_id)
            )
            if result.rowcount == 0:
                self.db.rollback()
                self.current_lease_token = None
                return False
            return True
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass
            self.current_lease_token = None
            return False

    def fenced_update_status(self, run_id, status: str, **extra) -> bool:
        if not self.current_lease_token:
            return False
        run_uuid = run_id if isinstance(run_id, uuid.UUID) else uuid.UUID(str(run_id))
        now = datetime.utcnow()
        values = {"status": status, "worker_id": self.owner_id}
        values.update(extra)
        try:
            result = self.db.execute(
                update(TestRun)
                .where(
                    TestRun.id == run_uuid,
                    TestRun.lease_owner == self.owner_id,
                    TestRun.lease_token == self.current_lease_token,
                    TestRun.lease_expires_at > now,
                )
                .values(**values)
            )
            if result.rowcount == 0:
                self.db.rollback()
                self.current_lease_token = None
                return False
            self.db.commit()
            return True
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass
            self.current_lease_token = None
            return False

    async def resume_run(self, run_id: str, lock: bool = True):
        run_uuid = run_id if isinstance(run_id, uuid.UUID) else uuid.UUID(str(run_id))
        if lock:
            if not self.acquire_lease(run_uuid):
                raise ValueError("Cannot acquire lease for run recovery")
        else:
            if not self.verify_ownership(run_uuid):
                raise ValueError("Not authorized: lease ownership not verified")
        run = self.db.query(TestRun).filter(TestRun.id == run_uuid).first()
        if not run or not self.verify_ownership(run_uuid):
            raise ValueError("Not owner of run lease")
        logger.info("Resuming run", run_id=run_id, status=getattr(run, "status", None), owner=self.owner_id)
        completed_steps = self.db.query(StepExecution).filter(
            StepExecution.run_id == run_uuid, StepExecution.status == "PASSED"
        ).all()
        completed_step_ids = [s.step_id for s in completed_steps]
        if not self.fenced_update_status(run_uuid, "RUNNING"):
            raise ValueError("Lease lost before updating run state")
        return run, completed_step_ids

    def check_side_effect(self, run_id: str, step_id: str):
        ledger, key = self.idem_manager.check_action(run_id, step_id)
        if ledger and self.idem_manager.should_skip(ledger):
            logger.info("Side effect already occurred, skipping", step_id=step_id)
            return True, ledger
        return False, ledger

    def verify_order_exists(self, db_demo, order_id: str = None, idempotency_key: str = None):
        from demo_app.models.order import Order
        if order_id:
            return db_demo.query(Order).filter(Order.id == order_id).first()
        if idempotency_key:
            return db_demo.query(Order).filter(Order.idempotency_key == idempotency_key).first()
        return None

    def find_incomplete_runs(self):
        return self.db.query(TestRun).filter(
            TestRun.status.in_(["RUNNING", "RETRYING", "INTERRUPTED", "PENDING"])
        ).all()

    async def recover_incomplete_runs(self, manager_class):
        incomplete = self.find_incomplete_runs()
        for run in incomplete:
            acquired = False
            try:
                if not self.acquire_lease(run.id):
                    continue
                acquired = True
                await self.resume_run(str(run.id), lock=False)
                manager = manager_class(self.db)
                await manager.execute_run(run.id, resume=True, recovery_orchestrator=self)
            except Exception as e:
                logger.error("Failed to recover run", run_id=str(run.id), error=str(e))
            finally:
                if acquired:
                    try:
                        self.release_lease(run.id)
                    except Exception:
                        pass
