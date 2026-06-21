"""Add driver_name column to deliveries

Revision ID: 0049
Revises: 0048
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deliveries", sa.Column("driver_name", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("deliveries", "driver_name")
