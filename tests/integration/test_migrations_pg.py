import os
import uuid
import subprocess
import sys
import pytest

from tests.conftest import clean_tables, pg_test_url, _assert_safe_test_db


@pytest.mark.pg
def test_migrations_upgrade_downgrade_reupgrade_on_disposable_db(pg_session_factory):
    """Validate migration chain on PG: upgrade head (already applied by fixture), verify schema, downgrade/upgrade on a disposable schema/db approach.
    We test downgrade/upgrade of 003 specifically to avoid destroying all data; full cycle tested via alembic commands."""
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import inspect, text

    url = pg_test_url()
    _assert_safe_test_db(url)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    alembic_cfg = Config(os.path.join(root, "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    alembic_cfg.set_main_option("script_location", os.path.join(root, "migrations"))

    engine = pg_session_factory.kw["bind"]
    insp = inspect(engine)
    # Verify key tables/columns exist
    assert "test_runs" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("test_runs")}
    assert {"lease_owner", "lease_expires_at", "lease_token"}.issubset(cols)
    assert "demo_orders" in insp.get_table_names()

    # Downgrade 003 -> 002 and re-upgrade
    command.downgrade(alembic_cfg, "002")
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("test_runs")}
    assert "lease_token" not in cols
    command.upgrade(alembic_cfg, "head")
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("test_runs")}
    assert "lease_token" in cols
