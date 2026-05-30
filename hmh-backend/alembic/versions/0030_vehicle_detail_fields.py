"""Add detail fields to vehicles table

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vehicles", sa.Column("make", sa.String(100), nullable=True))
    op.add_column("vehicles", sa.Column("model", sa.String(100), nullable=True))
    op.add_column("vehicles", sa.Column("year", sa.Integer(), nullable=True))
    op.add_column(
        "vehicles",
        sa.Column(
            "fuel_type",
            sa.Enum(name="fuel_type_enum", create_type=False),
            nullable=True,
        ),
    )
    op.add_column("vehicles", sa.Column("tank_capacity_l", sa.Numeric(8, 1), nullable=True))
    op.add_column("vehicles", sa.Column("fuel_consumption_per_100km", sa.Numeric(6, 2), nullable=True))
    op.add_column("vehicles", sa.Column("current_odometer_km", sa.Numeric(10, 1), nullable=True))
    op.add_column("vehicles", sa.Column("service_interval_km", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("vehicles", "service_interval_km")
    op.drop_column("vehicles", "current_odometer_km")
    op.drop_column("vehicles", "fuel_consumption_per_100km")
    op.drop_column("vehicles", "tank_capacity_l")
    op.drop_column("vehicles", "fuel_type")
    op.drop_column("vehicles", "year")
    op.drop_column("vehicles", "model")
    op.drop_column("vehicles", "make")
