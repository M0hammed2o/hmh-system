"""0070 - fuel request evidence feasibility notifications and email audit

Revision ID: 0070
Revises: 0069
"""

from alembic import op
from sqlalchemy import text

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(text("""
        ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS fuel_consumption_per_hour NUMERIC(8,3);
        ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS fuel_tolerance_pct NUMERIC(6,2) NOT NULL DEFAULT 20;
        ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS fuel_minimum_issue_interval_hours NUMERIC(8,2) NOT NULL DEFAULT 0;
        ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS fuel_override_required BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS hour_meter_required BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS tracker_provider VARCHAR(100);
        ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS tracker_external_id VARCHAR(200);

        ALTER TABLE fuel_orders ADD COLUMN IF NOT EXISTS intended_use VARCHAR(80);
        ALTER TABLE fuel_orders ADD COLUMN IF NOT EXISTS destination_type VARCHAR(30);
        ALTER TABLE fuel_orders ADD COLUMN IF NOT EXISTS vehicle_id UUID REFERENCES vehicles(id) ON DELETE SET NULL;
        ALTER TABLE fuel_orders ADD COLUMN IF NOT EXISTS equipment_reference VARCHAR(200);
        ALTER TABLE fuel_orders ADD COLUMN IF NOT EXISTS notes TEXT;
        ALTER TABLE fuel_orders ADD COLUMN IF NOT EXISTS feasibility_status VARCHAR(30) NOT NULL DEFAULT 'NOT_EVALUATED';
        ALTER TABLE fuel_orders ADD COLUMN IF NOT EXISTS feasibility_message TEXT;
        ALTER TABLE fuel_orders ADD COLUMN IF NOT EXISTS estimated_remaining_litres NUMERIC(12,2);
        ALTER TABLE fuel_orders ADD COLUMN IF NOT EXISTS feasibility_override_reason TEXT;
        ALTER TABLE fuel_orders ADD COLUMN IF NOT EXISTS feasibility_override_by UUID REFERENCES users(id) ON DELETE SET NULL;
        ALTER TABLE fuel_orders ADD COLUMN IF NOT EXISTS feasibility_override_at TIMESTAMPTZ;

        ALTER TABLE fuel_issues ADD COLUMN IF NOT EXISTS reading_source VARCHAR(40) NOT NULL DEFAULT 'MANUAL';
        ALTER TABLE fuel_issues ADD COLUMN IF NOT EXISTS tracker_provider VARCHAR(100);
        ALTER TABLE fuel_issues ADD COLUMN IF NOT EXISTS tracker_reading_at TIMESTAMPTZ;
        ALTER TABLE fuel_issues ADD COLUMN IF NOT EXISTS estimated_remaining_litres NUMERIC(12,2);
        ALTER TABLE fuel_issues ADD COLUMN IF NOT EXISTS feasibility_status VARCHAR(30) NOT NULL DEFAULT 'NOT_EVALUATED';
        ALTER TABLE fuel_issues ADD COLUMN IF NOT EXISTS evidence_override_reason TEXT;
        ALTER TABLE fuel_issues ADD COLUMN IF NOT EXISTS evidence_override_by UUID REFERENCES users(id) ON DELETE SET NULL;
        ALTER TABLE fuel_issues ADD COLUMN IF NOT EXISTS evidence_override_at TIMESTAMPTZ;
        ALTER TABLE fuel_issues ADD COLUMN IF NOT EXISTS feasibility_override_reason TEXT;
        ALTER TABLE fuel_issues ADD COLUMN IF NOT EXISTS feasibility_override_by UUID REFERENCES users(id) ON DELETE SET NULL;
        ALTER TABLE fuel_issues ADD COLUMN IF NOT EXISTS feasibility_override_at TIMESTAMPTZ;
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS fuel_equipment_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(), project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            site_id UUID REFERENCES sites(id) ON DELETE SET NULL, equipment_reference VARCHAR(200) NOT NULL,
            destination_type VARCHAR(30) NOT NULL, expected_litres_per_hour NUMERIC(8,3),
            tolerance_pct NUMERIC(6,2) NOT NULL DEFAULT 20, tank_capacity_litres NUMERIC(12,2),
            minimum_issue_interval_hours NUMERIC(8,2) NOT NULL DEFAULT 0, hour_meter_required BOOLEAN NOT NULL DEFAULT TRUE,
            override_required BOOLEAN NOT NULL DEFAULT FALSE, is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_fuel_equipment_project_ref UNIQUE(project_id, equipment_reference)
        );
        CREATE TABLE IF NOT EXISTS fuel_order_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(), order_id UUID NOT NULL REFERENCES fuel_orders(id) ON DELETE CASCADE,
            from_status VARCHAR(30), to_status VARCHAR(30) NOT NULL, actor_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            reason TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS fuel_issue_evidence (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(), issue_id UUID NOT NULL REFERENCES fuel_issues(id) ON DELETE CASCADE,
            attachment_id UUID NOT NULL REFERENCES attachments(id) ON DELETE RESTRICT, evidence_type VARCHAR(40) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), CONSTRAINT uq_fuel_issue_evidence_type UNIQUE(issue_id, evidence_type)
        );
        CREATE TABLE IF NOT EXISTS fuel_email_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(), order_id UUID REFERENCES fuel_orders(id) ON DELETE CASCADE,
            delivery_id UUID REFERENCES fuel_deliveries(id) ON DELETE CASCADE, event_type VARCHAR(30) NOT NULL,
            recipient_user_id UUID REFERENCES users(id) ON DELETE SET NULL, recipient_email VARCHAR(255) NOT NULL,
            subject VARCHAR(300) NOT NULL, status VARCHAR(30) NOT NULL DEFAULT 'PENDING', attempt_count INTEGER NOT NULL DEFAULT 0,
            last_attempt_at TIMESTAMPTZ, next_attempt_at TIMESTAMPTZ, error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_fuel_order_history_order ON fuel_order_history(order_id);
        CREATE INDEX IF NOT EXISTS ix_fuel_issue_evidence_issue ON fuel_issue_evidence(issue_id);
        CREATE INDEX IF NOT EXISTS ix_fuel_email_logs_order ON fuel_email_logs(order_id);
        CREATE INDEX IF NOT EXISTS ix_fuel_email_logs_status ON fuel_email_logs(status);
    """))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("""
        DROP TABLE IF EXISTS fuel_email_logs;
        DROP TABLE IF EXISTS fuel_issue_evidence;
        DROP TABLE IF EXISTS fuel_order_history;
        DROP TABLE IF EXISTS fuel_equipment_profiles;
        ALTER TABLE fuel_issues DROP COLUMN IF EXISTS feasibility_override_at;
        ALTER TABLE fuel_issues DROP COLUMN IF EXISTS feasibility_override_by;
        ALTER TABLE fuel_issues DROP COLUMN IF EXISTS feasibility_override_reason;
        ALTER TABLE fuel_issues DROP COLUMN IF EXISTS evidence_override_at;
        ALTER TABLE fuel_issues DROP COLUMN IF EXISTS evidence_override_by;
        ALTER TABLE fuel_issues DROP COLUMN IF EXISTS evidence_override_reason;
        ALTER TABLE fuel_issues DROP COLUMN IF EXISTS feasibility_status;
        ALTER TABLE fuel_issues DROP COLUMN IF EXISTS estimated_remaining_litres;
        ALTER TABLE fuel_issues DROP COLUMN IF EXISTS tracker_reading_at;
        ALTER TABLE fuel_issues DROP COLUMN IF EXISTS tracker_provider;
        ALTER TABLE fuel_issues DROP COLUMN IF EXISTS reading_source;
        ALTER TABLE fuel_orders DROP COLUMN IF EXISTS feasibility_override_at;
        ALTER TABLE fuel_orders DROP COLUMN IF EXISTS feasibility_override_by;
        ALTER TABLE fuel_orders DROP COLUMN IF EXISTS feasibility_override_reason;
        ALTER TABLE fuel_orders DROP COLUMN IF EXISTS estimated_remaining_litres;
        ALTER TABLE fuel_orders DROP COLUMN IF EXISTS feasibility_message;
        ALTER TABLE fuel_orders DROP COLUMN IF EXISTS feasibility_status;
        ALTER TABLE fuel_orders DROP COLUMN IF EXISTS notes;
        ALTER TABLE fuel_orders DROP COLUMN IF EXISTS equipment_reference;
        ALTER TABLE fuel_orders DROP COLUMN IF EXISTS vehicle_id;
        ALTER TABLE fuel_orders DROP COLUMN IF EXISTS destination_type;
        ALTER TABLE fuel_orders DROP COLUMN IF EXISTS intended_use;
        ALTER TABLE vehicles DROP COLUMN IF EXISTS tracker_external_id;
        ALTER TABLE vehicles DROP COLUMN IF EXISTS tracker_provider;
        ALTER TABLE vehicles DROP COLUMN IF EXISTS hour_meter_required;
        ALTER TABLE vehicles DROP COLUMN IF EXISTS fuel_override_required;
        ALTER TABLE vehicles DROP COLUMN IF EXISTS fuel_minimum_issue_interval_hours;
        ALTER TABLE vehicles DROP COLUMN IF EXISTS fuel_tolerance_pct;
        ALTER TABLE vehicles DROP COLUMN IF EXISTS fuel_consumption_per_hour;
    """))
