"""Add recovery lease fields

Revision ID: 003
Revises: 002
Create Date: 2026-11-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('test_runs', sa.Column('lease_owner', sa.String(length=255), nullable=True))
    op.add_column('test_runs', sa.Column('lease_expires_at', sa.DateTime(), nullable=True))
    op.add_column('test_runs', sa.Column('lease_token', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('test_runs', 'lease_token')
    op.drop_column('test_runs', 'lease_expires_at')
    op.drop_column('test_runs', 'lease_owner')
