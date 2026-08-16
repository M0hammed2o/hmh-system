"""Manual/exceptional Fuel receipt distinction

Phase 7 of the Fuel Procurement Integration Restructuring.

Adds fuel_deliveries.is_manual_emergency and .emergency_reason so that
fuel.admin-gated emergency receipts (bypassing the real MR/PO/Delivery
procurement chain entirely — e.g. an emergency cash fuel purchase with no
prior Material Request) are structurally distinguishable from both the
real procurement hand-off (Phase 5) and the legacy FuelOrder-based
delivery path, rather than being inferred from a free-text notes field.

Revision ID: 0073
Revises: 0072
Create Date: 2026-08-16
"""
from alembic import op
from sqlalchemy import text

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text(
        "ALTER TABLE fuel_deliveries "
        "ADD COLUMN IF NOT EXISTS is_manual_emergency BOOLEAN NOT NULL DEFAULT FALSE"
    ))
    conn.execute(text(
        "ALTER TABLE fuel_deliveries "
        "ADD COLUMN IF NOT EXISTS emergency_reason TEXT NULL"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_fuel_deliveries_is_manual_emergency "
        "ON fuel_deliveries(is_manual_emergency)"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP INDEX IF EXISTS ix_fuel_deliveries_is_manual_emergency"))
    conn.execute(text("ALTER TABLE fuel_deliveries DROP COLUMN IF EXISTS emergency_reason"))
    conn.execute(text("ALTER TABLE fuel_deliveries DROP COLUMN IF EXISTS is_manual_emergency"))
