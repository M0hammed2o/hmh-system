"""Milestone planned completion date — Phase FINAL-1

Adds planned_completion_date (DATE, nullable) to project_stage_status.
Used for overdue milestone detection — is_overdue is computed at query time,
not stored.

Revision ID: 0026
Revises: 0025
"""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_stage_status",
        sa.Column("planned_completion_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_stage_status", "planned_completion_date")
