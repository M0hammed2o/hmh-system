"""Add DELIVERED and READ values to notification_status_enum

Revision ID: 0034
Revises: 0033
Create Date: 2026-05-30
"""
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_status_enum ADD VALUE IF NOT EXISTS 'DELIVERED'")
    op.execute("ALTER TYPE notification_status_enum ADD VALUE IF NOT EXISTS 'READ'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values — manual recovery required
    pass
