"""Phase 3Q.3 — add PAYMENT_DUE to alert_type_enum.

Revision ID: 0023
Revises:     0022
Create Date: 2026-05-22

Changes:
  alert_type_enum: PAYMENT_DUE — invoice due date approaching (scan alert, 1-3 days ahead).
  Distinct from OVERDUE_PAYMENT (already past due) to allow separate recipient category routing.

ROLLBACK:
  Enum values cannot be removed. PAYMENT_DUE will remain but cause no harm if unused.
"""

from alembic import op

revision      = "0023"
down_revision = "0022"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("ALTER TYPE alert_type_enum ADD VALUE IF NOT EXISTS 'PAYMENT_DUE'")


def downgrade() -> None:
    pass  # enum values cannot be removed
