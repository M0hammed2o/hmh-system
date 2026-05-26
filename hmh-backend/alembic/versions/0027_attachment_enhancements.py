"""Attachment enhancements: caption, uploaded_role, 4 new attachment types.

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-26
"""

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE attachments ADD COLUMN IF NOT EXISTS caption VARCHAR(500)")
    op.execute("ALTER TABLE attachments ADD COLUMN IF NOT EXISTS uploaded_role VARCHAR(50)")

    for val in ["BEFORE_PHOTO", "COMPLETION_PHOTO", "ISSUE_PHOTO", "DELIVERY_EVIDENCE"]:
        op.execute(f"ALTER TYPE attachment_type_enum ADD VALUE IF NOT EXISTS '{val}'")


def downgrade() -> None:
    op.execute("ALTER TABLE attachments DROP COLUMN IF EXISTS uploaded_role")
    op.execute("ALTER TABLE attachments DROP COLUMN IF EXISTS caption")
    # Note: PostgreSQL enum values cannot be removed without recreating the type
