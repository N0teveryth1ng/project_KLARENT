"""Add lease_token column to test_runs

Revision ID: 004
Revises: 003
Create Date: 2026-11-06 15:53:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add lease_token column (nullable) to test_runs table
    op.add_column("test_runs", sa.Column("lease_token", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("test_runs", "lease_token")
