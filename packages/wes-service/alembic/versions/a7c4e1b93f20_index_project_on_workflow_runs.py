"""index (project, created_at) on workflow_runs

Run listings are always scoped to one project and ordered newest first, and
they now return a COUNT(*) over the same filter. This composite index serves
both: the count reads it as a covering index, and the page query walks it
backwards instead of sorting.

Indexing project on its own was measured to be actively harmful. It gives the
optimizer a cheaper-looking access path than created_at, so it filters on
project and then filesorts the matching rows -- 13,669 of them for the largest
project, each carrying wide JSON columns -- which overruns the default 256 KB
sort_buffer_size and fails the request with MySQL error 1038.

Revision ID: a7c4e1b93f20
Revises: 61019f4b738b
Create Date: 2026-08-07 00:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a7c4e1b93f20'
down_revision = '61019f4b738b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'ix_workflow_runs_project_created_at',
        'workflow_runs',
        ['project', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_workflow_runs_project_created_at', table_name='workflow_runs')
