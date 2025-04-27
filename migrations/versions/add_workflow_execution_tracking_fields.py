"""Add workflow execution tracking fields

Revision ID: add_workflow_execution_tracking_fields
Revises: 65510080a98b
Create Date: 2025-04-26 20:47:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_workflow_execution_tracking_fields'
down_revision = '65510080a98b'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to workflow_runs table
    op.add_column('workflow_runs', sa.Column('submitted_at', sa.DateTime(), nullable=True))
    op.add_column('workflow_runs', sa.Column('processed_at', sa.DateTime(), nullable=True))
    op.add_column('workflow_runs', sa.Column('processed', sa.Boolean(), nullable=True, default=False))
    op.add_column('workflow_runs', sa.Column('external_id', sa.String(length=100), nullable=True))
    op.add_column('workflow_runs', sa.Column('error_message', sa.Text(), nullable=True))


def downgrade():
    # Remove columns from workflow_runs table
    op.drop_column('workflow_runs', 'submitted_at')
    op.drop_column('workflow_runs', 'processed_at')
    op.drop_column('workflow_runs', 'processed')
    op.drop_column('workflow_runs', 'external_id')
    op.drop_column('workflow_runs', 'error_message')