"""Add repair_jobs table and link to vehicle_costs + material_requests.

Revision ID: 0056
Revises:     0055
Create Date: 2026-06-28
"""

from alembic import op
from sqlalchemy import text

revision      = "0056"
down_revision = "0055"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute(text("""
        CREATE TABLE IF NOT EXISTS repair_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vehicle_id UUID NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
            workshop_name VARCHAR(200),
            date_opened DATE NOT NULL,
            date_closed DATE,
            odometer_at_repair NUMERIC(10,1),
            notes TEXT,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))

    op.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_repair_jobs_vehicle_id ON repair_jobs(vehicle_id)
    """))

    op.execute(text("""
        ALTER TABLE vehicle_costs ADD COLUMN IF NOT EXISTS repair_job_id UUID REFERENCES repair_jobs(id) ON DELETE SET NULL
    """))

    op.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_vehicle_costs_repair_job_id ON vehicle_costs(repair_job_id)
    """))

    op.execute(text("""
        ALTER TABLE material_requests ADD COLUMN IF NOT EXISTS repair_job_id UUID REFERENCES repair_jobs(id) ON DELETE SET NULL
    """))

    op.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_material_requests_repair_job_id ON material_requests(repair_job_id)
    """))

    print("[0056] Created repair_jobs table and linked vehicle_costs + material_requests.", flush=True)


def downgrade() -> None:
    op.execute(text("DROP INDEX IF EXISTS ix_material_requests_repair_job_id"))
    op.execute(text("ALTER TABLE material_requests DROP COLUMN IF EXISTS repair_job_id"))

    op.execute(text("DROP INDEX IF EXISTS ix_vehicle_costs_repair_job_id"))
    op.execute(text("ALTER TABLE vehicle_costs DROP COLUMN IF EXISTS repair_job_id"))

    op.execute(text("DROP INDEX IF EXISTS ix_repair_jobs_vehicle_id"))
    op.execute(text("DROP TABLE IF EXISTS repair_jobs"))
