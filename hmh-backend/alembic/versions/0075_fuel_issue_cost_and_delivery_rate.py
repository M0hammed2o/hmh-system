"""Fuel cost reporting for the canonical FuelIssue ledger

Phase 10 of the Fuel Procurement Integration Restructuring.

cost_summary.py and dashboard_service.py currently sum FuelLog.total_cost
for project fuel spend. Once a project cuts over to Fuel Management
(Phase 8/9), NEW fuel fills stop writing to FuelLog entirely, so those
reports would silently under-report spend unless FuelIssue carries its own
cost. Rather than fabricate a number, cost is derived from the real
procurement/delivery price already on FuelDelivery.cost_per_litre (an
existing column, previously unused by the Fuel Management service) via a
moving weighted-average across that storage location's VERIFIED
deliveries, computed and locked in at issue time — standard weighted-
average inventory costing. Where no delivery in a storage location has a
recorded cost_per_litre, FuelIssue.unit_cost/.total_cost stay NULL rather
than guessing.

fuel_issues.unit_cost / .total_cost: NULL-able, computed at issue time.

Revision ID: 0075
Revises: 0074
Create Date: 2026-08-16
"""
from alembic import op
from sqlalchemy import text

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text(
        "ALTER TABLE fuel_issues ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(10, 4) NULL"
    ))
    conn.execute(text(
        "ALTER TABLE fuel_issues ADD COLUMN IF NOT EXISTS total_cost NUMERIC(12, 2) NULL"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE fuel_issues DROP COLUMN IF EXISTS total_cost"))
    conn.execute(text("ALTER TABLE fuel_issues DROP COLUMN IF EXISTS unit_cost"))
