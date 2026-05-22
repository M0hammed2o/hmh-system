"""Extend attachment enums for universal attachment system.

Revision ID: 0019
Revises:     0018
Create Date: 2026-05-22

Phase 3K — Universal Multi-Image/Attachment System.

Changes (all additive):

  attachment_type_enum:
    PROGRESS_PHOTO  — construction/milestone progress shot
    PROOF_OF_WORK   — evidence that work was completed
    FUEL_SLIP       — fuel receipt / pump photo
    QUOTATION       — supplier quote document
    PO_DOCUMENT     — purchase order document (PDF, etc.)

  attachment_entity_enum:
    LOT     — attach documents directly to a lot/unit
    PROJECT — attach project-level documents

ROLLBACK: PostgreSQL enum values cannot be removed — no harm if unused.
"""

from alembic import op

revision      = "0019"
down_revision = "0018"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # New attachment type categories
    for val in ["PROGRESS_PHOTO", "PROOF_OF_WORK", "FUEL_SLIP", "QUOTATION", "PO_DOCUMENT"]:
        op.execute(f"ALTER TYPE attachment_type_enum ADD VALUE IF NOT EXISTS '{val}'")

    # New entity types
    op.execute("ALTER TYPE attachment_entity_enum ADD VALUE IF NOT EXISTS 'LOT'")
    op.execute("ALTER TYPE attachment_entity_enum ADD VALUE IF NOT EXISTS 'PROJECT'")


def downgrade() -> None:
    pass   # enum values cannot be removed from PostgreSQL
