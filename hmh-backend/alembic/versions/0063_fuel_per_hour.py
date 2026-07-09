"""fuel_per_hour — hours_operated and fuel_per_hour fields on fuel_logs

Revision ID: 0063
Revises: 0062
Create Date: 2026-07-08
"""

from alembic import op
from sqlalchemy import text

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("""
        ALTER TABLE fuel_logs
            ADD COLUMN IF NOT EXISTS hours_operated NUMERIC(10, 2),
            ADD COLUMN IF NOT EXISTS fuel_per_hour  NUMERIC(8, 3);
    """))


def downgrade() -> None:
    op.execute(text("""
        ALTER TABLE fuel_logs
            DROP COLUMN IF EXISTS hours_operated,
            DROP COLUMN IF EXISTS fuel_per_hour;
    """))
