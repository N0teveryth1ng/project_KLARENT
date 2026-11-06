import os
import sys
from contextlib import contextmanager
import pytest

# Ensure project root is importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# Test database URL handling
# ---------------------------------------------------------------------------
# If the user has not provided TEST_DATABASE_URL (or the legacy
# POSTGRES_TEST_URL) we fall back to the application's DATABASE_URL but
# enforce the psycopg2 driver. This keeps credentials out of source control
# because we read them from the Settings model, which itself pulls from the
# .env file.
from app.core.config import settings
if not os.getenv("TEST_DATABASE_URL") and not os.getenv("POSTGRES_TEST_URL"):
    # Only apply the fallback when the app's configured URL points to a
    # PostgreSQL server.
    if settings.database_url.startswith("postgresql://"):
        os.environ["TEST_DATABASE_URL"] = settings.database_url.replace(
            "postgresql://", "postgresql+psycopg2://", 1
        )
    else:
        # Use the built‑in default test DB URL (localhost) with the psycopg2 driver.
        os.environ["TEST_DATABASE_URL"] = settings.default_test_database_url

# ---------------------------------------------------------------------------
# Existing helper functions follow
# ---------------------------------------------------------------------------

def pg_test_url():
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("POSTGRES_TEST_URL")


def is_pg_url(url):
    return bool(url) and url.startswith("postgresql")


def require_pg_or_skip_explicit():
    """For required PG tests: fail loudly unless explicit opt-in skip is set."""
    url = pg_test_url()
    if is_pg_url(url):
        return url
    if os.environ.get("ALLOW_SKIP_PG_TESTS") == "1":
        pytest.skip("PG tests explicitly skipped via ALLOW_SKIP_PG_TESTS=1 (local unit-only mode)")
    pytest.fail(
        "Required PostgreSQL tests need TEST_DATABASE_URL (or POSTGRES_TEST_URL) pointing to a dedicated test database. "
        "Set it, e.g. postgresql://postgres:postgres@localhost:5432/agent_reliability_lab_test. "
        "For local unit-only runs, set ALLOW_SKIP_PG_TESTS=1 explicitly."
    )


def _assert_safe_test_db(url):
    # Basic safety: refuse obvious non-test DB names unless explicitly allowed
    if os.environ.get("ALLOW_UNSAFE_TEST_DB") == "1":
        return
    lower = url.lower()
    # allow if contains test
    if "test" in lower:
        return
    # refuse common dev/prod names
    for bad in ("/agent_reliability_lab", "/postgres", "/production", "/prod"):
        if lower.rstrip("/").endswith(bad) or f"{bad}?" in lower or f"{bad} " in lower:
            raise RuntimeError(f"Refusing to use potentially unsafe database for tests: {url}. Use a dedicated *_test database or set ALLOW_UNSAFE_TEST_DB=1.")


@pytest.fixture(scope="session")
def pg_engine_session():
    url = require_pg_or_skip_explicit()
    _assert_safe_test_db(url)
    from sqlalchemy import create_engine, text
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        pytest.fail(f"Cannot connect to PostgreSQL test database ({url}): {e}")
    # Apply migrations
    try:
        from alembic.config import Config
        from alembic import command
        alembic_cfg = Config(os.path.join(ROOT, "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", url)
        alembic_cfg.set_main_option("script_location", os.path.join(ROOT, "migrations"))
        command.upgrade(alembic_cfg, "head")
    except Exception as e:
        pytest.fail(f"Failed to apply migrations to test database: {e}")
    yield engine
    engine.dispose()


@pytest.fixture
def pg_session_factory(pg_engine_session):
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=pg_engine_session, autoflush=False, autocommit=False, expire_on_commit=False)
    return Session


@pytest.fixture
def pg_db(pg_session_factory):
    db = pg_session_factory()
    try:
        yield db
    finally:
        try:
            db.rollback()
        except Exception:
            pass
        db.close()


def clean_tables(db):
    from app.models.action_ledger import ActionLedger
    from app.models.step_execution import StepExecution
    from app.models.evidence import Evidence
    from app.models.execution_event import ExecutionEvent
    from app.models.evaluation import Evaluation
    from app.models.test_run import TestRun
    from app.models.scenario import Scenario
    from demo_app.models.cart import CartItem
    from demo_app.models.order import Order
    from demo_app.models.product import Product
    from demo_app.models.user import User
    for model in (ActionLedger, StepExecution, Evidence, ExecutionEvent, Evaluation, TestRun, Scenario, CartItem, Order, Product, User):
        try:
            db.query(model).delete()
        except Exception:
            db.rollback()
    db.commit()
