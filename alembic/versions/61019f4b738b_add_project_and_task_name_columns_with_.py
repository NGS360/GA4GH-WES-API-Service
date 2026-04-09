"""add_project_and_task_name_columns_with_defaults

Revision ID: 61019f4b738b
Revises: ea7b7b3086d2
Create Date: 2026-03-10 14:01:47.886905

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '61019f4b738b'
down_revision = 'ea7b7b3086d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    # Step 1: Add columns as nullable first
    op.add_column('workflow_runs', sa.Column('project', sa.String(length=50), nullable=True))
    op.add_column('workflow_runs', sa.Column('task_name', sa.String(length=200), nullable=True))

    # Step 2: Update existing records with values from tags or smart defaults
    connection = op.get_bind()

    if dialect == 'sqlite':
        # SQLite uses json_extract natively (returns quoted strings), and || for concat
        connection.execute(sa.text("""
            UPDATE workflow_runs
            SET project = CASE
                WHEN json_extract(tags, '$.ProjectId') IS NOT NULL
                THEN json_extract(tags, '$.ProjectId')
                ELSE 'test_project'
            END
            WHERE project IS NULL
        """))

        connection.execute(sa.text("""
            UPDATE workflow_runs
            SET task_name = CASE
                WHEN json_extract(tags, '$.TaskName') IS NOT NULL
                THEN json_extract(tags, '$.TaskName')
                ELSE 'wes-run-' || id
            END
            WHERE task_name IS NULL
        """))
    else:
        # MySQL uses JSON_EXTRACT + JSON_UNQUOTE and CONCAT
        connection.execute(sa.text("""
            UPDATE workflow_runs
            SET project = CASE
                WHEN JSON_EXTRACT(tags, '$.ProjectId') IS NOT NULL
                THEN JSON_UNQUOTE(JSON_EXTRACT(tags, '$.ProjectId'))
                ELSE 'test_project'
            END
            WHERE project IS NULL
        """))

        connection.execute(sa.text("""
            UPDATE workflow_runs
            SET task_name = CASE
                WHEN JSON_EXTRACT(tags, '$.TaskName') IS NOT NULL
                THEN JSON_UNQUOTE(JSON_EXTRACT(tags, '$.TaskName'))
                ELSE CONCAT('wes-run-', id)
            END
            WHERE task_name IS NULL
        """))

    # Step 3: Make columns non-nullable
    # SQLite doesn't support ALTER COLUMN, so use batch mode
    if dialect == 'sqlite':
        with op.batch_alter_table('workflow_runs') as batch_op:
            batch_op.alter_column('project', nullable=False, existing_type=sa.String(length=50))
            batch_op.alter_column('task_name', nullable=False, existing_type=sa.String(length=200))
    else:
        op.alter_column('workflow_runs', 'project', nullable=False, existing_type=sa.String(length=50))
        op.alter_column('workflow_runs', 'task_name', nullable=False, existing_type=sa.String(length=200))

    # Update workflow_run_id comment (MySQL only)
    if dialect == 'mysql':
        op.alter_column('workflow_runs', 'workflow_run_id',
                   existing_type=mysql.VARCHAR(length=36),
                   comment='ID for executed workflow run in underlying execution system (e.g. Omics Run ID)',
                   existing_comment='ID for the executed workflow run in the underlying execution system (e.g. Omics Run ID)',
                   existing_nullable=True)


def downgrade() -> None:
    dialect = op.get_bind().dialect.name

    if dialect == 'mysql':
        op.alter_column('workflow_runs', 'workflow_run_id',
                   existing_type=mysql.VARCHAR(length=36),
                   comment='ID for the executed workflow run in the underlying execution system (e.g. Omics Run ID)',
                   existing_comment='ID for executed workflow run in underlying execution system (e.g. Omics Run ID)',
                   existing_nullable=True)
    op.drop_column('workflow_runs', 'task_name')
    op.drop_column('workflow_runs', 'project')
