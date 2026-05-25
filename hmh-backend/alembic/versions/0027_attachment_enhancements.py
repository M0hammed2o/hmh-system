"""Attachment enhancements: caption, uploaded_role, 4 new attachment types.

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add caption and uploaded_role columns to attachments
    op.add_column(
        "attachments",
        sa.Column("caption", sa.String(500), nullable=True),
    )
    op.add_column(
        "attachments",
        sa.Column("uploaded_role", sa.String(50), nullable=True),
    )

    # Add 4 new attachment type enum values
    op.execute("ALTER TYPE attachment_type_enum ADD VALUE IF NOT EXISTS 'BEFORE_PHOTO'")
    op.execute("ALTER TYPE attachment_type_enum ADD VALUE IF NOT EXISTS 'COMPLETION_PHOTO'")
    op.execute("ALTER TYPE attachment_type_enum ADD VALUE IF NOT EXISTS 'ISSUE_PHOTO'")
    op.execute("ALTER TYPE attachment_type_enum ADD VALUE IF NOT EXISTS 'DELIVERY_EVIDENCE'")


def downgrade() -> None:
    op.drop_column("attachments", "caption")
    op.drop_column("attachments", "uploaded_role")
    # Note: PostgreSQL enum values cannot be removed without recreating the type
