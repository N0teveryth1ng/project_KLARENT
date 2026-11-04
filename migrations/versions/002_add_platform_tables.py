"""Add platform tables

Revision ID: 002
Revises: 001
Create Date: 2025-10-15 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('scenarios',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('configuration', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('test_runs',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('scenario_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('environment', sa.String(length=100), nullable=True),
    sa.Column('total_steps', sa.Integer(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('worker_id', sa.String(length=255), nullable=True),
    sa.Column('metadata', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['scenario_id'], ['scenarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('step_executions',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('step_id', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('attempt_number', sa.Integer(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('error_type', sa.String(length=100), nullable=True),
    sa.Column('error_message', sa.String(), nullable=True),
    sa.Column('error_details', sa.JSON(), nullable=True),
    sa.Column('verification_result', sa.JSON(), nullable=True),
    sa.Column('screenshot_path', sa.String(length=512), nullable=True),
    sa.Column('metadata', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['run_id'], ['test_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id', 'step_id', 'attempt_number')
    )
    op.create_table('action_ledger',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('step_id', sa.String(length=255), nullable=False),
    sa.Column('idempotency_key', sa.String(length=255), nullable=False),
    sa.Column('action_type', sa.String(length=100), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('attempt_number', sa.Integer(), nullable=True),
    sa.Column('external_reference', sa.String(length=255), nullable=True),
    sa.Column('verification_status', sa.String(length=50), nullable=True),
    sa.Column('side_effect_occurred', sa.Boolean(), nullable=True),
    sa.Column('request_data', sa.JSON(), nullable=True),
    sa.Column('response_data', sa.JSON(), nullable=True),
    sa.Column('verified_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['run_id'], ['test_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key')
    )
    op.create_table('execution_events',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('step_id', sa.String(length=255), nullable=True),
    sa.Column('event_type', sa.String(length=100), nullable=False),
    sa.Column('metadata', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['run_id'], ['test_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('evidence',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('step_id', sa.String(length=255), nullable=True),
    sa.Column('artifact_type', sa.String(length=50), nullable=False),
    sa.Column('artifact_path', sa.String(length=512), nullable=False),
    sa.Column('artifact_size', sa.Integer(), nullable=True),
    sa.Column('metadata', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['run_id'], ['test_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('evaluations',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('scenario_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('sample_size', sa.Integer(), nullable=False),
    sa.Column('metrics', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['scenario_id'], ['scenarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('evaluations')
    op.drop_table('evidence')
    op.drop_table('execution_events')
    op.drop_table('action_ledger')
    op.drop_table('step_executions')
    op.drop_table('test_runs')
    op.drop_table('scenarios')
