"""Create procurement_reconciliations table — Phase 4.

Revision ID: 0040
Revises: 0039
Create Date: 2026-06-10
"""
from alembic import op

revision      = "0040"
down_revision = "0039"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'reconciliationstatus') THEN
                CREATE TYPE reconciliationstatus AS ENUM (
                    'PENDING', 'MATCHED', 'VARIANCE_DETECTED', 'APPROVED', 'REJECTED'
                );
            END IF;
        END
        $$
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS procurement_reconciliations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            reconciliation_number VARCHAR(100) NOT NULL UNIQUE,
            status reconciliationstatus NOT NULL DEFAULT 'PENDING',

            purchase_order_id  UUID REFERENCES purchase_orders(id)   ON DELETE SET NULL,
            invoice_id         UUID REFERENCES invoices(id)           ON DELETE SET NULL,
            delivery_id        UUID REFERENCES deliveries(id)         ON DELETE SET NULL,
            quotation_id       UUID REFERENCES quotations(id)         ON DELETE SET NULL,
            material_request_id UUID REFERENCES material_requests(id) ON DELETE SET NULL,

            variance_data      JSONB,
            notes              TEXT,
            reviewed_by        UUID REFERENCES users(id)              ON DELETE SET NULL,
            reviewed_at        TIMESTAMPTZ,
            created_by         UUID REFERENCES users(id)              ON DELETE SET NULL,

            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS ix_proc_recon_status           ON procurement_reconciliations (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_proc_recon_po_id            ON procurement_reconciliations (purchase_order_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_proc_recon_invoice_id       ON procurement_reconciliations (invoice_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_proc_recon_number           ON procurement_reconciliations (reconciliation_number)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS procurement_reconciliations")
    op.execute("DROP TYPE IF EXISTS reconciliationstatus")
