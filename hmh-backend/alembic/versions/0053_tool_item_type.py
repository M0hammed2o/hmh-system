"""Phase 3AA — add TOOL to item_type_enum.

Revision ID: 0053
Revises:     0052
Create Date: 2026-06-22

Changes:
  item_type_enum: TOOL — re-usable assets (drills, levels, scaffolding) that
  are transferred to sites and returned to the main warehouse when done.
  Distinct from MATERIAL (consumed) and PLANT (heavy equipment / vehicles).

ROLLBACK:
  Enum values cannot be removed once added; TOOL will remain but cause no
  harm if unused.
"""

from alembic import op

revision      = "0053"
down_revision = "0052"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("ALTER TYPE item_type_enum ADD VALUE IF NOT EXISTS 'TOOL'")


def downgrade() -> None:
    pass  # enum values cannot be removed
