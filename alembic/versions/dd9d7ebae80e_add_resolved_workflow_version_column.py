"""add resolved_workflow_version column

Revision ID: dd9d7ebae80e
Revises: 61019f4b738b
Create Date: 2026-09-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dd9d7ebae80e'
down_revision = '61019f4b738b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'workflow_runs',
        sa.Column(
            'resolved_workflow_version',
            sa.String(length=50),
            nullable=True,
            comment=(
                "NGS360 workflow version resolved at submission time. "
                "Captures the actual version used when workflow_url specifies "
                "an alias or omits a version (which can change later)."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column('workflow_runs', 'resolved_workflow_version')
