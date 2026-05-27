"""Phase E — add DUPLICATE_INVOICE, OCR_EXTRACTION_FAILED, SUPPLIER_MISMATCH to alert_type_enum.

Revision ID: 0028
Revises:     0027
Create Date: 2026-05-27

Changes:
  alert_type_enum:
    DUPLICATE_INVOICE     — same invoice number submitted more than once
    OCR_EXTRACTION_FAILED — attachment OCR produced no usable text
    SUPPLIER_MISMATCH     — supplier in document does not match the linked PO supplier

ROLLBACK:
  Enum values cannot be removed in PostgreSQL once added.
"""

from alembic import op

revision      = "0028"
down_revision = "0027"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("ALTER TYPE alert_type_enum ADD VALUE IF NOT EXISTS 'DUPLICATE_INVOICE'")
    op.execute("ALTER TYPE alert_type_enum ADD VALUE IF NOT EXISTS 'OCR_EXTRACTION_FAILED'")
    op.execute("ALTER TYPE alert_type_enum ADD VALUE IF NOT EXISTS 'SUPPLIER_MISMATCH'")


def downgrade() -> None:
    pass  # enum values cannot be removed
