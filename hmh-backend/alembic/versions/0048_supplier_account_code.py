"""Add customer_account_code to suppliers

Revision ID: 0048
Revises: 0047
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("customer_account_code", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("suppliers", "customer_account_code")
