"""add payment_due_days to suppliers

Revision ID: 0067
Revises: 0066
Create Date: 2026-07-10
"""

from alembic import op
from sqlalchemy import text

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS payment_due_days INTEGER"))


def downgrade() -> None:
    op.execute(text("ALTER TABLE suppliers DROP COLUMN IF EXISTS payment_due_days"))
