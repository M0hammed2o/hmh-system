"""Add is_test flag to notification_queue for test send tracking

Revision ID: 0032
Revises: 0031
Create Date: 2026-05-30
"""
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE notification_queue ADD COLUMN IF NOT EXISTS is_test BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.drop_column("notification_queue", "is_test")
