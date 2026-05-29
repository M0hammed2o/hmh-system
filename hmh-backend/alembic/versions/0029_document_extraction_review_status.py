"""Add review_status to document_extractions

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "document_extractions",
        sa.Column(
            "review_status",
            sa.String(50),
            nullable=False,
            server_default="PENDING_REVIEW",
        ),
    )
    op.create_index(
        "ix_document_extractions_review_status",
        "document_extractions",
        ["review_status"],
    )


def downgrade():
    op.drop_index("ix_document_extractions_review_status", table_name="document_extractions")
    op.drop_column("document_extractions", "review_status")
