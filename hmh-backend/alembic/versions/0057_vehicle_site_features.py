"""Add fuel deliveries, vehicle transfer requests, hours tracking, repair job quotation/approval.

Revision ID: 0057
Revises:     0056
Create Date: 2026-07-02
"""

from alembic import op
from sqlalchemy import text

revision      = "0057"
down_revision = "0056"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # 1. vehicles: hours tracking
    op.execute(text("""
        ALTER TABLE vehicles
        ADD COLUMN IF NOT EXISTS uses_hours BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS current_hours_reading NUMERIC(10,1)
    """))

    # 2. fuel_logs: hours reading
    op.execute(text("""
        ALTER TABLE fuel_logs
        ADD COLUMN IF NOT EXISTS hours_reading NUMERIC(10,1)
    """))

    # 3. repair_jobs: quotation / approval / invoice
    op.execute(text("""
        ALTER TABLE repair_jobs
        ADD COLUMN IF NOT EXISTS quote_amount NUMERIC(14,2),
        ADD COLUMN IF NOT EXISTS quote_file_url VARCHAR(500),
        ADD COLUMN IF NOT EXISTS invoice_amount NUMERIC(14,2),
        ADD COLUMN IF NOT EXISTS invoice_file_url VARCHAR(500),
        ADD COLUMN IF NOT EXISTS approval_stage INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS approval_1_by UUID REFERENCES users(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS approval_1_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS approval_2_by UUID REFERENCES users(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS approval_2_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS approval_3_by UUID REFERENCES users(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS approval_3_at TIMESTAMPTZ
    """))

    # 4. fuel_deliveries table (bulk diesel tank deliveries per site)
    op.execute(text("""
        CREATE TABLE IF NOT EXISTS fuel_deliveries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
            project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
            delivery_date DATE NOT NULL,
            fuel_type VARCHAR(20) NOT NULL DEFAULT 'DIESEL',
            litres_delivered NUMERIC(10,2) NOT NULL,
            cost_per_litre NUMERIC(10,4),
            supplier_name VARCHAR(200),
            invoice_number VARCHAR(100),
            notes TEXT,
            recorded_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_fuel_deliveries_site_id ON fuel_deliveries(site_id)
    """))

    # 5. fuel_logs: link to bulk delivery
    op.execute(text("""
        ALTER TABLE fuel_logs
        ADD COLUMN IF NOT EXISTS fuel_delivery_id UUID REFERENCES fuel_deliveries(id) ON DELETE SET NULL
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_fuel_logs_fuel_delivery_id ON fuel_logs(fuel_delivery_id)
    """))

    # 6. vehicle_transfer_requests table
    op.execute(text("""
        CREATE TABLE IF NOT EXISTS vehicle_transfer_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vehicle_id UUID NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
            from_site_id UUID REFERENCES sites(id) ON DELETE SET NULL,
            to_site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
            reason TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            requested_by UUID REFERENCES users(id) ON DELETE SET NULL,
            approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
            approved_at TIMESTAMPTZ,
            rejected_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_vehicle_transfer_requests_vehicle_id
        ON vehicle_transfer_requests(vehicle_id)
    """))

    print("[0057] Added fuel deliveries, vehicle transfer requests, hours tracking, repair job quotation/approval.", flush=True)


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS vehicle_transfer_requests"))
    op.execute(text("DROP INDEX IF EXISTS ix_fuel_logs_fuel_delivery_id"))
    op.execute(text("ALTER TABLE fuel_logs DROP COLUMN IF EXISTS fuel_delivery_id"))
    op.execute(text("DROP TABLE IF EXISTS fuel_deliveries"))
    op.execute(text("""
        ALTER TABLE repair_jobs
        DROP COLUMN IF EXISTS quote_amount,
        DROP COLUMN IF EXISTS quote_file_url,
        DROP COLUMN IF EXISTS invoice_amount,
        DROP COLUMN IF EXISTS invoice_file_url,
        DROP COLUMN IF EXISTS approval_stage,
        DROP COLUMN IF EXISTS approval_1_by,
        DROP COLUMN IF EXISTS approval_1_at,
        DROP COLUMN IF EXISTS approval_2_by,
        DROP COLUMN IF EXISTS approval_2_at,
        DROP COLUMN IF EXISTS approval_3_by,
        DROP COLUMN IF EXISTS approval_3_at
    """))
    op.execute(text("ALTER TABLE fuel_logs DROP COLUMN IF EXISTS hours_reading"))
    op.execute(text("""
        ALTER TABLE vehicles
        DROP COLUMN IF EXISTS uses_hours,
        DROP COLUMN IF EXISTS current_hours_reading
    """))
