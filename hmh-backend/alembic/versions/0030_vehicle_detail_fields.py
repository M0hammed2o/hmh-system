"""Add detail fields to vehicles table

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS make VARCHAR(100)")
    op.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS model VARCHAR(100)")
    op.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS year INTEGER")
    op.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS fuel_type fuel_type_enum")
    op.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS tank_capacity_l NUMERIC(8,1)")
    op.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS fuel_consumption_per_100km NUMERIC(6,2)")
    op.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS current_odometer_km NUMERIC(10,1)")
    op.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS service_interval_km INTEGER")


def downgrade() -> None:
    op.drop_column("vehicles", "service_interval_km")
    op.drop_column("vehicles", "current_odometer_km")
    op.drop_column("vehicles", "fuel_consumption_per_100km")
    op.drop_column("vehicles", "tank_capacity_l")
    op.drop_column("vehicles", "fuel_type")
    op.drop_column("vehicles", "year")
    op.drop_column("vehicles", "model")
    op.drop_column("vehicles", "make")
