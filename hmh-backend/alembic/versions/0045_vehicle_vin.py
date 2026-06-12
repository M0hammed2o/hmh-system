"""0045_vehicle_vin

Add vin_number column to vehicles table.

Revision ID: 0045
Revises: 0044
"""

from alembic import op
import sqlalchemy as sa

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vehicles", sa.Column("vin_number", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("vehicles", "vin_number")
