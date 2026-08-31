"""add parent_run_id to workflow_runs

Records launcher lineage: a launcher (orchestrator) execution is itself a
workflow run, and every child workflow it submits points back at it. This is
what lets launcher progress be derived from persisted state instead of from a
status endpoint on the launcher container.

The index is composite (parent_run_id, created_at) for the same reason
ix_workflow_runs_project_created_at is: child listings are "one parent, newest
first", and a launcher fans out to hundreds of children, so indexing the pair
keeps both the listing and the progress rollup off a filesort. It also satisfies
InnoDB's requirement that a foreign key column be indexed, so no separate index
is created for the constraint.

ON DELETE SET NULL, not CASCADE: deleting a launcher run must not delete the
child workflows it submitted -- those are independent executions whose outputs
outlive the orchestration that started them.

Revision ID: 952781491f2f
Revises: a7c4e1b93f20
Create Date: 2026-08-17 20:49:16.991649

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '952781491f2f'
down_revision = 'a7c4e1b93f20'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'workflow_runs',
        sa.Column(
            'parent_run_id',
            sa.String(length=36),
            nullable=True,
            comment='Launcher run that submitted this run, if any',
        ),
    )
    op.create_index(
        'ix_workflow_runs_parent_created_at',
        'workflow_runs',
        ['parent_run_id', 'created_at'],
        unique=False,
    )
    op.create_foreign_key(
        'fk_workflow_runs_parent_run_id',
        'workflow_runs',
        'workflow_runs',
        ['parent_run_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_workflow_runs_parent_run_id', 'workflow_runs', type_='foreignkey')
    op.drop_index('ix_workflow_runs_parent_created_at', table_name='workflow_runs')
    op.drop_column('workflow_runs', 'parent_run_id')
