"""Trustworthy Fuel stock cutover

Phase 8 of the Fuel Procurement Integration Restructuring.

Adds fuel_storage_locations.cutover_confirmed_at / .cutover_confirmed_by.
A storage location's calculated stock is only trustworthy enough to issue
fuel FROM once it has been "cut over" — proven by either (A) a real,
VERIFIED delivery (procurement hand-off, legacy FuelOrder path, or an
audited manual emergency receipt) or (B) a controlled opening balance
recorded through the existing FuelStockAdjustment(OPENING) mechanism.
Cutover is set automatically the first time either happens — never a bare
manual toggle with no evidence behind it.

Revision ID: 0074
Revises: 0073
Create Date: 2026-08-16
"""
from alembic import op
from sqlalchemy import text

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text(
        "ALTER TABLE fuel_storage_locations "
        "ADD COLUMN IF NOT EXISTS cutover_confirmed_at TIMESTAMPTZ NULL"
    ))
    conn.execute(text(
        "ALTER TABLE fuel_storage_locations "
        "ADD COLUMN IF NOT EXISTS cutover_confirmed_by UUID NULL"
    ))
    conn.execute(text(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_fuel_storage_locations_cutover_confirmed_by') THEN "
        "ALTER TABLE fuel_storage_locations ADD CONSTRAINT fk_fuel_storage_locations_cutover_confirmed_by "
        "FOREIGN KEY (cutover_confirmed_by) REFERENCES users(id) ON DELETE SET NULL; "
        "END IF; "
        "END $$;"
    ))
    # Backfill: any storage location that already has a VERIFIED delivery or an
    # OPENING adjustment is already trustworthy today — cutover happened in the
    # past even though nothing recorded when. Backfill from the earliest such
    # evidence rather than leaving pre-existing locations permanently blocked.
    conn.execute(text("""
        UPDATE fuel_storage_locations fsl
        SET cutover_confirmed_at = evidence.earliest_at
        FROM (
            SELECT storage_location_id, MIN(delivered_at) AS earliest_at
            FROM fuel_deliveries
            WHERE verification_status = 'VERIFIED' AND storage_location_id IS NOT NULL
            GROUP BY storage_location_id
            UNION ALL
            SELECT storage_location_id, MIN(created_at) AS earliest_at
            FROM fuel_stock_adjustments
            WHERE adjustment_type = 'OPENING' AND storage_location_id IS NOT NULL
            GROUP BY storage_location_id
        ) AS evidence
        WHERE fsl.id = evidence.storage_location_id AND fsl.cutover_confirmed_at IS NULL
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text(
        "ALTER TABLE fuel_storage_locations DROP CONSTRAINT IF EXISTS fk_fuel_storage_locations_cutover_confirmed_by"
    ))
    conn.execute(text("ALTER TABLE fuel_storage_locations DROP COLUMN IF EXISTS cutover_confirmed_by"))
    conn.execute(text("ALTER TABLE fuel_storage_locations DROP COLUMN IF EXISTS cutover_confirmed_at"))
