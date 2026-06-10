"""Create quotations table.

Revision ID: 0038
Revises: 0037
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision      = "0038"
down_revision = "0037"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'quotationstatus') THEN
                CREATE TYPE quotationstatus AS ENUM (
                    'DRAFT', 'SENT', 'RECEIVED', 'APPROVED', 'REJECTED', 'EXPIRED'
                );
            END IF;
        END
        $$
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS quotations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            quote_number VARCHAR(100) NOT NULL UNIQUE,
            supplier_id UUID REFERENCES suppliers(id) ON DELETE SET NULL,
            project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
            material_request_id UUID REFERENCES material_requests(id) ON DELETE SET NULL,
            status quotationstatus NOT NULL DEFAULT 'DRAFT',
            quote_date DATE,
            expiry_date DATE,
            net_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            vat_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            gross_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            vat_rate_used NUMERIC(5,2) NOT NULL DEFAULT 15.00,
            notes TEXT,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS ix_quotations_quote_number ON quotations (quote_number)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_quotations_supplier_id ON quotations (supplier_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_quotations_project_id ON quotations (project_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_quotations_material_request_id ON quotations (material_request_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_quotations_status ON quotations (status)")


def downgrade() -> None:
    op.drop_table("quotations")
    op.execute("DROP TYPE IF EXISTS quotationstatus")
