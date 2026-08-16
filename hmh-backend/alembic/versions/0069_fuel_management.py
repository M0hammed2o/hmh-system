"""0069 - dedicated fuel ordering and monitoring ledger

Revision ID: 0069
Revises: 0068
"""

from alembic import op
from sqlalchemy import text

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    existing_labels = {
        row[0]
        for row in conn.execute(text(
            "SELECT enumlabel FROM pg_enum WHERE enumtypid = 'attachment_entity_enum'::regtype"
        ))
    }
    for value in ["FUEL_ORDER", "FUEL_DELIVERY", "FUEL_ISSUE", "FUEL_RECONCILIATION"]:
        if value not in existing_labels:
            conn.execute(text(f"ALTER TYPE attachment_entity_enum ADD VALUE '{value}'"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS fuel_types (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            code VARCHAR(40) NOT NULL UNIQUE,
            name VARCHAR(100) NOT NULL UNIQUE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(text("""
        INSERT INTO fuel_types (code, name) VALUES
            ('DIESEL', 'Diesel'),
            ('PETROL_93', 'Petrol 93'),
            ('PETROL_95', 'Petrol 95'),
            ('OTHER', 'Other')
        ON CONFLICT (code) DO NOTHING
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS fuel_storage_locations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            site_id UUID REFERENCES sites(id) ON DELETE SET NULL,
            fuel_type_id UUID NOT NULL REFERENCES fuel_types(id) ON DELETE RESTRICT,
            name VARCHAR(160) NOT NULL,
            location_type VARCHAR(30) NOT NULL DEFAULT 'TANK',
            capacity_litres NUMERIC(12,2),
            low_stock_threshold_litres NUMERIC(12,2),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_fuel_storage_project_site_name UNIQUE NULLS NOT DISTINCT
                (project_id, site_id, name),
            CONSTRAINT ck_fuel_storage_capacity_positive CHECK
                (capacity_litres IS NULL OR capacity_litres > 0),
            CONSTRAINT ck_fuel_storage_threshold_nonnegative CHECK
                (low_stock_threshold_litres IS NULL OR low_stock_threshold_litres >= 0)
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fuel_storage_project ON fuel_storage_locations(project_id)"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS fuel_orders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_number VARCHAR(60) NOT NULL UNIQUE,
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
            site_id UUID REFERENCES sites(id) ON DELETE SET NULL,
            fuel_type_id UUID NOT NULL REFERENCES fuel_types(id) ON DELETE RESTRICT,
            supplier_id UUID REFERENCES suppliers(id) ON DELETE SET NULL,
            storage_location_id UUID REFERENCES fuel_storage_locations(id) ON DELETE SET NULL,
            requested_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            request_date DATE NOT NULL,
            requested_litres NUMERIC(12,2) NOT NULL,
            expected_delivery_date DATE,
            delivery_location VARCHAR(300) NOT NULL,
            purpose TEXT,
            status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
            approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
            approved_at TIMESTAMPTZ,
            rejected_by UUID REFERENCES users(id) ON DELETE SET NULL,
            rejected_at TIMESTAMPTZ,
            rejection_reason TEXT,
            supplier_reference VARCHAR(150),
            purchase_order_reference VARCHAR(150),
            submitted_at TIMESTAMPTZ,
            ordered_at TIMESTAMPTZ,
            closed_at TIMESTAMPTZ,
            cancelled_at TIMESTAMPTZ,
            cancellation_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_fuel_order_litres_positive CHECK (requested_litres > 0),
            CONSTRAINT ck_fuel_order_status CHECK (status IN (
                'DRAFT','SUBMITTED','APPROVED','ORDERED','PARTIALLY_DELIVERED',
                'DELIVERED','CLOSED','REJECTED','CANCELLED'
            ))
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fuel_orders_project_status ON fuel_orders(project_id, status)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fuel_orders_expected_date ON fuel_orders(expected_delivery_date)"))

    for statement in [
        "ADD COLUMN IF NOT EXISTS order_id UUID REFERENCES fuel_orders(id) ON DELETE SET NULL",
        "ADD COLUMN IF NOT EXISTS supplier_id UUID REFERENCES suppliers(id) ON DELETE SET NULL",
        "ADD COLUMN IF NOT EXISTS fuel_type_id UUID REFERENCES fuel_types(id) ON DELETE RESTRICT",
        "ADD COLUMN IF NOT EXISTS storage_location_id UUID REFERENCES fuel_storage_locations(id) ON DELETE SET NULL",
        "ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ",
        "ADD COLUMN IF NOT EXISTS delivery_note_number VARCHAR(120)",
        "ADD COLUMN IF NOT EXISTS opening_reading NUMERIC(12,2)",
        "ADD COLUMN IF NOT EXISTS closing_reading NUMERIC(12,2)",
        "ADD COLUMN IF NOT EXISTS calculated_received_litres NUMERIC(12,2)",
        "ADD COLUMN IF NOT EXISTS confirmed_litres NUMERIC(12,2)",
        "ADD COLUMN IF NOT EXISTS variance_litres NUMERIC(12,2)",
        "ADD COLUMN IF NOT EXISTS tanker_registration VARCHAR(100)",
        "ADD COLUMN IF NOT EXISTS driver_details VARCHAR(300)",
        "ADD COLUMN IF NOT EXISTS received_by UUID REFERENCES users(id) ON DELETE SET NULL",
        "ADD COLUMN IF NOT EXISTS verification_status VARCHAR(30) NOT NULL DEFAULT 'LEGACY'",
        "ADD COLUMN IF NOT EXISTS verified_by UUID REFERENCES users(id) ON DELETE SET NULL",
        "ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ",
        "ADD COLUMN IF NOT EXISTS excess_override BOOLEAN NOT NULL DEFAULT FALSE",
        "ADD COLUMN IF NOT EXISTS excess_override_reason TEXT",
        "ADD COLUMN IF NOT EXISTS excess_override_by UUID REFERENCES users(id) ON DELETE SET NULL",
    ]:
        conn.execute(text(f"ALTER TABLE fuel_deliveries {statement}"))
    conn.execute(text("ALTER TABLE fuel_deliveries ALTER COLUMN verification_status SET DEFAULT 'PENDING'"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fuel_deliveries_order ON fuel_deliveries(order_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fuel_deliveries_storage_verified ON fuel_deliveries(storage_location_id, verification_status)"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS fuel_issues (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            issue_number VARCHAR(60) NOT NULL UNIQUE,
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
            site_id UUID REFERENCES sites(id) ON DELETE SET NULL,
            storage_location_id UUID NOT NULL REFERENCES fuel_storage_locations(id) ON DELETE RESTRICT,
            fuel_type_id UUID NOT NULL REFERENCES fuel_types(id) ON DELETE RESTRICT,
            vehicle_id UUID REFERENCES vehicles(id) ON DELETE SET NULL,
            destination_type VARCHAR(30) NOT NULL,
            equipment_reference VARCHAR(200),
            issued_at TIMESTAMPTZ NOT NULL,
            litres NUMERIC(12,2) NOT NULL,
            odometer_reading NUMERIC(12,1),
            hour_meter_reading NUMERIC(12,1),
            issued_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            received_by VARCHAR(200),
            purpose TEXT,
            evidence_url VARCHAR(1000),
            notes TEXT,
            distance_since_previous_km NUMERIC(12,1),
            litres_per_100km NUMERIC(10,3),
            operating_hours_since_previous NUMERIC(12,1),
            litres_per_hour NUMERIC(10,3),
            anomaly_flag BOOLEAN NOT NULL DEFAULT FALSE,
            anomaly_reason TEXT,
            is_reversed BOOLEAN NOT NULL DEFAULT FALSE,
            reversed_at TIMESTAMPTZ,
            reversed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            reversal_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_fuel_issue_litres_positive CHECK (litres > 0),
            CONSTRAINT ck_fuel_issue_destination CHECK (destination_type IN (
                'VEHICLE','PLANT','GENERATOR','STORAGE_TANK','OTHER_EQUIPMENT'
            )),
            CONSTRAINT ck_fuel_issue_destination_ref CHECK (
                (destination_type = 'VEHICLE' AND vehicle_id IS NOT NULL) OR
                (destination_type <> 'VEHICLE' AND equipment_reference IS NOT NULL)
            )
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fuel_issues_storage_date ON fuel_issues(storage_location_id, issued_at)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fuel_issues_vehicle_date ON fuel_issues(vehicle_id, issued_at)"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS fuel_reconciliations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            reconciliation_number VARCHAR(60) NOT NULL UNIQUE,
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
            site_id UUID REFERENCES sites(id) ON DELETE SET NULL,
            storage_location_id UUID NOT NULL REFERENCES fuel_storage_locations(id) ON DELETE RESTRICT,
            fuel_type_id UUID NOT NULL REFERENCES fuel_types(id) ON DELETE RESTRICT,
            reconciliation_date TIMESTAMPTZ NOT NULL,
            calculated_balance_litres NUMERIC(12,2) NOT NULL,
            physical_balance_litres NUMERIC(12,2) NOT NULL,
            variance_litres NUMERIC(12,2) NOT NULL,
            variance_pct NUMERIC(8,3),
            explanation TEXT NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'COMPLETED',
            requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
            reconciled_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
            approved_at TIMESTAMPTZ,
            approval_notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_fuel_reconciliation_physical_nonnegative CHECK (physical_balance_litres >= 0),
            CONSTRAINT ck_fuel_reconciliation_status CHECK (status IN ('COMPLETED','PENDING_APPROVAL','APPROVED','REJECTED'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS fuel_stock_adjustments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
            site_id UUID REFERENCES sites(id) ON DELETE SET NULL,
            storage_location_id UUID NOT NULL REFERENCES fuel_storage_locations(id) ON DELETE RESTRICT,
            fuel_type_id UUID NOT NULL REFERENCES fuel_types(id) ON DELETE RESTRICT,
            adjustment_type VARCHAR(30) NOT NULL,
            litres_delta NUMERIC(12,2) NOT NULL,
            reason TEXT NOT NULL,
            authorised_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            reference_reconciliation_id UUID REFERENCES fuel_reconciliations(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_fuel_adjustment_nonzero CHECK (litres_delta <> 0),
            CONSTRAINT ck_fuel_adjustment_type CHECK (adjustment_type IN ('OPENING','CORRECTION','LOSS','GAIN','REVERSAL'))
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fuel_adjustments_storage_date ON fuel_stock_adjustments(storage_location_id, created_at)"))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("DROP TABLE IF EXISTS fuel_stock_adjustments"))
    conn.execute(text("DROP TABLE IF EXISTS fuel_reconciliations"))
    conn.execute(text("DROP TABLE IF EXISTS fuel_issues"))
    for column in [
        "excess_override_by", "excess_override_reason", "excess_override",
        "verified_at", "verified_by", "verification_status", "received_by",
        "driver_details", "tanker_registration", "variance_litres", "confirmed_litres",
        "calculated_received_litres", "closing_reading", "opening_reading",
        "delivery_note_number", "delivered_at", "storage_location_id", "fuel_type_id",
        "supplier_id", "order_id",
    ]:
        conn.execute(text(f"ALTER TABLE fuel_deliveries DROP COLUMN IF EXISTS {column}"))
    conn.execute(text("DROP TABLE IF EXISTS fuel_orders"))
    conn.execute(text("DROP TABLE IF EXISTS fuel_storage_locations"))
    conn.execute(text("DROP TABLE IF EXISTS fuel_types"))
