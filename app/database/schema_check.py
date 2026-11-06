"""Schema compatibility checks. Fails clearly when DB schema is incompatible with current models."""
from sqlalchemy import inspect, text
from app.core.logging import logger


REQUIRED_TEST_RUNS_COLUMNS = {"lease_owner", "lease_expires_at", "lease_token"}


def check_schema_compatibility(engine):
    try:
        insp = inspect(engine)
        if "test_runs" not in insp.get_table_names():
            return  # fresh DB / migrations pending in some contexts; let app/migrations handle
        cols = {c["name"] for c in insp.get_columns("test_runs")}
        missing = REQUIRED_TEST_RUNS_COLUMNS - cols
        if missing:
            raise RuntimeError(
                f"Database schema is incompatible: test_runs missing columns {sorted(missing)}. "
                f"Run `alembic upgrade head` against a supported PostgreSQL database. "
                f"SQLite is not supported for recovery/lease migrations (migrations use PostgreSQL-specific types); "
                f"use PostgreSQL for production/recovery features."
            )
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning("Schema compatibility check skipped", error=str(e))
