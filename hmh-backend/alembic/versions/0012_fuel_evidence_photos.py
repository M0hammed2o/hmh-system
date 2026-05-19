"""Add evidence photo URL columns to fuel_logs.

Revision ID: 0012
Revises:     0011
Create Date: 2026-05-19

Adds three nullable VARCHAR(1000) columns for evidence photo URLs:
  photo_odometer  — odometer/mileage photo
  photo_pump      — fuel pump / tank photo
  photo_invoice   — receipt / invoice slip photo

Also adds distance_km and efficiency_kpl computed from consecutive odometer
readings (stored when the fuel log is created — not GENERATED ALWAYS since
it requires a cross-row calculation).
"""

from alembic import op
import sqlalchemy as sa

revision      = "0012"
down_revision = "0011"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("fuel_logs")}

    for col, definition in [
        ("photo_odometer",  sa.Column("photo_odometer",  sa.String(1000), nullable=True)),
        ("photo_pump",      sa.Column("photo_pump",      sa.String(1000), nullable=True)),
        ("photo_invoice",   sa.Column("photo_invoice",   sa.String(1000), nullable=True)),
        ("distance_km",     sa.Column("distance_km",     sa.Numeric(10, 1), nullable=True)),
        ("efficiency_kpl",  sa.Column("efficiency_kpl",  sa.Numeric(8, 3), nullable=True)),
        ("l_per_100km",     sa.Column("l_per_100km",     sa.Numeric(8, 3), nullable=True)),
    ]:
        if col not in cols:
            op.add_column("fuel_logs", definition)
            print(f"[0012] Added fuel_logs.{col}", flush=True)


def downgrade() -> None:
    for col in ["photo_odometer", "photo_pump", "photo_invoice",
                "distance_km", "efficiency_kpl", "l_per_100km"]:
        try:
            op.drop_column("fuel_logs", col)
        except Exception:
            pass
