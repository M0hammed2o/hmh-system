"""Add partial payment support to the payments/invoices system.

Revision ID: 0020
Revises:     0019
Create Date: 2026-05-22

Phase 3L — Payments / Reconciliation System.

Changes:

  record_status_enum:
    PARTIALLY_PAID — invoice has at least one payment but balance > 0
    OVERPAID       — total payments exceed invoice total

  payments table:
    payment_method  VARCHAR(50) nullable  — EFT, CASH, CHEQUE, BANK_TRANSFER, etc.
    lot_id          UUID nullable FK      — optional link to a specific lot/unit

ROLLBACK:
  ALTER TABLE payments DROP COLUMN lot_id;
  ALTER TABLE payments DROP COLUMN payment_method;
  (PARTIALLY_PAID/OVERPAID enum values cannot be removed — no harm if unused)
"""

import sqlalchemy as sa
from alembic import op

revision      = "0020"
down_revision = "0019"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # New invoice/PO lifecycle statuses
    op.execute("ALTER TYPE record_status_enum ADD VALUE IF NOT EXISTS 'PARTIALLY_PAID'")
    op.execute("ALTER TYPE record_status_enum ADD VALUE IF NOT EXISTS 'OVERPAID'")

    # New payment fields
    op.add_column("payments", sa.Column("payment_method", sa.String(50), nullable=True))
    op.add_column("payments", sa.Column("lot_id", sa.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "payments_lot_id_fkey",
        "payments", "lots",
        ["lot_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("payments_lot_id_fkey", "payments", type_="foreignkey")
    op.drop_column("payments", "lot_id")
    op.drop_column("payments", "payment_method")
    # Enum values cannot be removed
