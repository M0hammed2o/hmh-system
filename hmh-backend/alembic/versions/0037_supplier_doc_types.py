"""Add ORDER_NOTE and CREDIT_NOTE attachment types for supplier document centre.

Revision ID: 0037
Revises: 0036
Create Date: 2026-06-10
"""
from alembic import op

revision      = "0037"
down_revision = "0036"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("ALTER TYPE attachment_type_enum ADD VALUE IF NOT EXISTS 'ORDER_NOTE'")
    op.execute("ALTER TYPE attachment_type_enum ADD VALUE IF NOT EXISTS 'CREDIT_NOTE'")


def downgrade() -> None:
    pass  # PostgreSQL enum values cannot be removed
