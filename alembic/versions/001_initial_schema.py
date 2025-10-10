"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create workflow_runs table
    op.create_table(
        'workflow_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('state', sa.Enum(
            'UNKNOWN', 'QUEUED', 'INITIALIZING', 'RUNNING', 'PAUSED',
            'COMPLETE', 'EXECUTOR_ERROR', 'SYSTEM_ERROR', 'CANCELED',
            'CANCELING', 'PREEMPTED',
            name='workflowstate'
        ), nullable=False),
        sa.Column('workflow_type', sa.String(50), nullable=False),
        sa.Column('workflow_type_version', sa.String(50), nullable=False),
        sa.Column('workflow_url', sa.Text, nullable=False),
        sa.Column('workflow_params', sa.JSON, nullable=True),
        sa.Column('workflow_engine', sa.String(50), nullable=True),
        sa.Column('workflow_engine_version', sa.String(50), nullable=True),
        sa.Column('workflow_engine_parameters', sa.JSON, nullable=True),
        sa.Column('tags', sa.JSON, nullable=False),
        sa.Column('start_time', sa.DateTime, nullable=True),
        sa.Column('end_time', sa.DateTime, nullable=True),
        sa.Column('stdout_url', sa.Text, nullable=True),
        sa.Column('stderr_url', sa.Text, nullable=True),
        sa.Column('exit_code', sa.Integer, nullable=True),
        sa.Column('system_logs', sa.JSON, nullable=False),
        sa.Column('outputs', sa.JSON, nullable=True),
        sa.Column('user_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )
    
    # Create indexes
    op.create_index('ix_workflow_runs_state', 'workflow_runs', ['state'])
    op.create_index('ix_workflow_runs_user_id', 'workflow_runs', ['user_id'])
    op.create_index('ix_workflow_runs_created_at', 'workflow_runs', ['created_at'])

    # Create task_logs table
    op.create_table(
        'task_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('run_id', sa.String(36), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('cmd', sa.JSON, nullable=True),
        sa.Column('start_time', sa.DateTime, nullable=True),
        sa.Column('end_time', sa.DateTime, nullable=True),
        sa.Column('stdout_url', sa.Text, nullable=True),
        sa.Column('stderr_url', sa.Text, nullable=True),
        sa.Column('exit_code', sa.Integer, nullable=True),
        sa.Column('system_logs', sa.JSON, nullable=False),
        sa.Column('tes_uri', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['workflow_runs.id'], ondelete='CASCADE'),
    )
    
    # Create indexes
    op.create_index('ix_task_logs_run_id', 'task_logs', ['run_id'])

    # Create workflow_attachments table
    op.create_table(
        'workflow_attachments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('run_id', sa.String(36), nullable=False),
        sa.Column('filename', sa.String(500), nullable=False),
        sa.Column('storage_path', sa.Text, nullable=False),
        sa.Column('content_type', sa.String(255), nullable=True),
        sa.Column('size_bytes', sa.Integer, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['workflow_runs.id'], ondelete='CASCADE'),
    )
    
    # Create indexes
    op.create_index('ix_workflow_attachments_run_id', 'workflow_attachments', ['run_id'])


def downgrade() -> None:
    op.drop_table('workflow_attachments')
    op.drop_table('task_logs')
    op.drop_table('workflow_runs')