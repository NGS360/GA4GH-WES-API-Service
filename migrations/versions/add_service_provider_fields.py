"""Add service provider fields to workflow_runs table

Revision ID: add_service_provider_fields
Revises: 65510080a98b
Create Date: 2025-05-14 20:57:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_service_provider_fields'
down_revision = '65510080a98b'
branch_labels = None
depends_on = None


def upgrade():
    # Add service provider fields to workflow_runs table
    op.add_column('workflow_runs', sa.Column('service_provider', sa.String(50), nullable=True))
    op.add_column('workflow_runs', sa.Column('provider_run_id', sa.String(100), nullable=True))
    op.add_column('workflow_runs', sa.Column('provider_status', sa.String(50), nullable=True))
    op.add_column('workflow_runs', sa.Column('provider_metadata', sa.JSON(), nullable=True))


def downgrade():
    # Remove service provider fields from workflow_runs table
    op.drop_column('workflow_runs', 'service_provider')
    op.drop_column('workflow_runs', 'provider_run_id')
    op.drop_column('workflow_runs', 'provider_status')
    op.drop_column('workflow_runs', 'provider_metadata')