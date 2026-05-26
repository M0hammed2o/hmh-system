"""Milestone planned completion date — Phase FINAL-1

Adds planned_completion_date (DATE, nullable) to project_stage_status.
Used for overdue milestone detection — is_overdue is computed at query time,
not stored.

Revision ID: 0026
Revises: 0025
"""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE project_stage_status
        ADD COLUMN IF NOT EXISTS planned_completion_date DATE
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE project_stage_status
        DROP COLUMN IF EXISTS planned_completion_date
    """)
