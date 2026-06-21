"""Add PICKUP value to delivery_destination_enum

Revision ID: 0050
Revises: 0049
Create Date: 2026-06-21
"""
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL supports adding enum values without recreating the type
    op.execute("ALTER TYPE delivery_destination_enum ADD VALUE IF NOT EXISTS 'PICKUP'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; downgrade is a no-op
    pass
