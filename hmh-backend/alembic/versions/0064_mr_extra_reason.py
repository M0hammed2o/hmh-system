"""mr_extra_reason — extra_reason_type and extra_reason_notes on material_request_items

Revision ID: 0064
Revises: 0063
Create Date: 2026-07-08
"""

from alembic import op
from sqlalchemy import text

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

# Valid reason types: BREAKAGE | MISMANAGEMENT | EXTRAS | OTHER
# Stored as varchar(50) — no DB enum so new values can be added without migrations.


def upgrade() -> None:
    op.execute(text("""
        ALTER TABLE material_request_items
            ADD COLUMN IF NOT EXISTS extra_reason_type  VARCHAR(50),
            ADD COLUMN IF NOT EXISTS extra_reason_notes TEXT;
    """))


def downgrade() -> None:
    op.execute(text("""
        ALTER TABLE material_request_items
            DROP COLUMN IF EXISTS extra_reason_type,
            DROP COLUMN IF EXISTS extra_reason_notes;
    """))
