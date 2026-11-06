"""Cost per litre on a fuel stock adjustment.

Every other way litres enter a storage location can carry its price.
fuel_deliveries.cost_per_litre has existed since the legacy delivery model,
and migration 0075 built FuelIssue's weighted-average costing on top of it.
A stock adjustment could not, which left two real gaps.

An opening balance taken over at cutover is written as a
FuelStockAdjustment(OPENING) by create_storage(). Those litres were bought at
a known price, but there was nowhere to record it, so the entire opening
balance was invisible to costing: a tank stocked only by an opening balance
produced NULL-cost fuel issues forever, and project fuel spend under-reported
by exactly that fuel.

A controlled GAIN or CORRECTION has the same problem — fuel genuinely
arriving into the tank, priced, with no column to hold the price.

cost_per_litre is nullable and has no default, deliberately. An existing
adjustment has no recorded price, and NOT NULL DEFAULT 0 would inject
zero-cost litres into the weighted-average denominator and drag every
existing tank's average towards zero. That is a fabricated number, which is
the one thing this costing model refuses to produce. Litres with no recorded
price are excluded from both the numerator and the denominator instead,
exactly as an uncosted delivery already is, so no existing tank's average
cost changes by one cent.

NUMERIC(10, 4) matches fuel_deliveries.cost_per_litre and
fuel_issues.unit_cost, so the weighted average is computed at one scale with
no implicit cast.

The CHECK constrains positivity only. "A price belongs on litres coming in,
not going out" is a rule about intent rather than about the data, so it lives
in create_adjustment where it can say so in words a person can act on — and
where a future "value this loss" feature can relax it without a migration.

Revision ID: 0082
Revises: 0081
Create Date: 2026-11-07
"""

from alembic import op
from sqlalchemy import text

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text(
        "ALTER TABLE fuel_stock_adjustments "
        "ADD COLUMN IF NOT EXISTS cost_per_litre NUMERIC(10, 4) NULL"
    ))
    # Guarded so a re-run is harmless and an environment patched by hand is
    # left alone, matching 0074's constraint handling.
    conn.execute(text("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_fuel_adjustment_cost_positive'
            ) THEN
                ALTER TABLE fuel_stock_adjustments
                    ADD CONSTRAINT ck_fuel_adjustment_cost_positive
                    CHECK (cost_per_litre IS NULL OR cost_per_litre > 0);
            END IF;
        END $$;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text(
        "ALTER TABLE fuel_stock_adjustments "
        "DROP CONSTRAINT IF EXISTS ck_fuel_adjustment_cost_positive"
    ))
    conn.execute(text(
        "ALTER TABLE fuel_stock_adjustments DROP COLUMN IF EXISTS cost_per_litre"
    ))
