"""Extend enums for procurement document management.

Revision ID: 0018
Revises:     0017
Create Date: 2026-05-22

Phase 3I — Procurement / External PO Flow.

Changes (all additive — enum ADD VALUE only):

  attachment_entity_enum:
    MATERIAL_REQUEST — attach documents (quotations, specs) to material requests
    SUPPLIER         — attach documents (contracts, certificates) to suppliers

  record_status_enum:
    INVOICED         — purchase order has a linked invoice captured

ROLLBACK:
  PostgreSQL enum values cannot be removed.
  These additions cause no harm if unused.
"""

from alembic import op

revision      = "0018"
down_revision = "0017"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("ALTER TYPE attachment_entity_enum ADD VALUE IF NOT EXISTS 'MATERIAL_REQUEST'")
    op.execute("ALTER TYPE attachment_entity_enum ADD VALUE IF NOT EXISTS 'SUPPLIER'")
    op.execute("ALTER TYPE record_status_enum    ADD VALUE IF NOT EXISTS 'INVOICED'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values — this is intentional.
    pass
