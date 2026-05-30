"""Add pin_hash to users and SITE_MANAGER_VIEW role enum value

Revision ID: 0033
Revises: 0032
Create Date: 2026-05-30
"""
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS pin_hash TEXT")
    op.execute("ALTER TYPE user_role_enum ADD VALUE IF NOT EXISTS 'SITE_MANAGER_VIEW'")


def downgrade() -> None:
    op.drop_column("users", "pin_hash")
    # PostgreSQL does not support removing enum values — manual recovery required
