"""Add SUPPLIER_CONFIRMED to record_status_enum.

Revision ID: 0021
Revises:     0020
Create Date: 2026-05-22

Phase 3I — Procurement Improvements.

Changes:

  record_status_enum:
    SUPPLIER_CONFIRMED — PO has been confirmed / acknowledged by the supplier
                         (transition: SENT → SUPPLIER_CONFIRMED → PARTIALLY_RECEIVED / RECEIVED)

ROLLBACK:
  Enum values cannot be removed from PostgreSQL enums once added.
  SUPPLIER_CONFIRMED will remain in the type but unused records won't be affected.
"""

from alembic import op

revision      = "0021"
down_revision = "0020"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("ALTER TYPE record_status_enum ADD VALUE IF NOT EXISTS 'SUPPLIER_CONFIRMED'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values — no-op.
    pass
