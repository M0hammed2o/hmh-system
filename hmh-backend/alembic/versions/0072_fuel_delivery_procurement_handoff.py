"""Fuel delivery procurement hand-off + corrected variance model

Phase 5/6 of the Fuel Procurement Integration Restructuring.

Adds:
  - fuel_deliveries.procurement_delivery_item_id: nullable UNIQUE FK to
    delivery_items.id. This is the hand-off point from the real procurement
    Delivery/DeliveryItem chain into the Fuel Control layer. UNIQUE at the
    DB level guarantees the same procurement DeliveryItem can never be
    confirmed into Fuel stock twice, even under concurrent/duplicate
    requests (double-click, retry).
  - fuel_deliveries.supplier_variance_litres: confirmed_litres - litres_delivered
    (the documented/supplier-invoiced quantity vs what was physically confirmed).
  - fuel_deliveries.meter_variance_litres: confirmed_litres - calculated_received_litres
    (the tank dip/meter-measured quantity vs what was physically confirmed).
    NULL whenever no opening/closing readings were captured — never silently
    falls back to the supplier quantity.

Revision ID: 0072
Revises: 0071
Create Date: 2026-08-16
"""
from alembic import op
from sqlalchemy import text

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text(
        "ALTER TABLE fuel_deliveries "
        "ADD COLUMN IF NOT EXISTS procurement_delivery_item_id UUID NULL"
    ))
    conn.execute(text(
        "ALTER TABLE fuel_deliveries "
        "ADD COLUMN IF NOT EXISTS supplier_variance_litres NUMERIC(12, 2) NULL"
    ))
    conn.execute(text(
        "ALTER TABLE fuel_deliveries "
        "ADD COLUMN IF NOT EXISTS meter_variance_litres NUMERIC(12, 2) NULL"
    ))
    conn.execute(text(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_fuel_deliveries_procurement_delivery_item') THEN "
        "ALTER TABLE fuel_deliveries ADD CONSTRAINT fk_fuel_deliveries_procurement_delivery_item "
        "FOREIGN KEY (procurement_delivery_item_id) REFERENCES delivery_items(id) ON DELETE SET NULL; "
        "END IF; "
        "END $$;"
    ))
    conn.execute(text(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_fuel_deliveries_procurement_delivery_item') THEN "
        "ALTER TABLE fuel_deliveries ADD CONSTRAINT uq_fuel_deliveries_procurement_delivery_item "
        "UNIQUE (procurement_delivery_item_id); "
        "END IF; "
        "END $$;"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_fuel_deliveries_procurement_delivery_item_id "
        "ON fuel_deliveries(procurement_delivery_item_id)"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP INDEX IF EXISTS ix_fuel_deliveries_procurement_delivery_item_id"))
    conn.execute(text(
        "ALTER TABLE fuel_deliveries DROP CONSTRAINT IF EXISTS uq_fuel_deliveries_procurement_delivery_item"
    ))
    conn.execute(text(
        "ALTER TABLE fuel_deliveries DROP CONSTRAINT IF EXISTS fk_fuel_deliveries_procurement_delivery_item"
    ))
    conn.execute(text("ALTER TABLE fuel_deliveries DROP COLUMN IF EXISTS meter_variance_litres"))
    conn.execute(text("ALTER TABLE fuel_deliveries DROP COLUMN IF EXISTS supplier_variance_litres"))
    conn.execute(text("ALTER TABLE fuel_deliveries DROP COLUMN IF EXISTS procurement_delivery_item_id"))
