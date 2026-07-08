"""workshop phase D — purchase orders, invoices, delivery notes

Revision ID: 0062
Revises: 0061
Create Date: 2026-07-08
"""

from alembic import op
from sqlalchemy import text

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("""
        CREATE TABLE workshop_purchase_orders (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workshop_mr_id  UUID NOT NULL REFERENCES workshop_mrs(id) ON DELETE CASCADE,
            quote_id        UUID REFERENCES workshop_quotes(id) ON DELETE SET NULL,
            po_number       VARCHAR(50) NOT NULL UNIQUE,
            supplier_id     UUID REFERENCES suppliers(id) ON DELETE SET NULL,
            supplier_name   VARCHAR(255),
            total_amount    NUMERIC(14, 2),
            currency        VARCHAR(10)  NOT NULL DEFAULT 'ZAR',
            notes           TEXT,
            status          VARCHAR(50)  NOT NULL DEFAULT 'DRAFT',
            po_file_url     VARCHAR(1000),
            sent_at         TIMESTAMPTZ,
            sent_by         UUID REFERENCES users(id) ON DELETE SET NULL,
            created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX ix_workshop_pos_mr_id    ON workshop_purchase_orders(workshop_mr_id);
        CREATE INDEX ix_workshop_pos_quote_id ON workshop_purchase_orders(quote_id);
        CREATE INDEX ix_workshop_pos_status   ON workshop_purchase_orders(status);

        CREATE TABLE workshop_invoices (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workshop_mr_id   UUID NOT NULL REFERENCES workshop_mrs(id) ON DELETE CASCADE,
            po_id            UUID REFERENCES workshop_purchase_orders(id) ON DELETE SET NULL,
            invoice_number   VARCHAR(100),
            supplier_id      UUID REFERENCES suppliers(id) ON DELETE SET NULL,
            supplier_name    VARCHAR(255),
            invoice_file_url VARCHAR(1000),
            total_amount     NUMERIC(14, 2),
            currency         VARCHAR(10) NOT NULL DEFAULT 'ZAR',
            invoice_date     DATE,
            notes            TEXT,
            created_by       UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX ix_workshop_invoices_mr_id ON workshop_invoices(workshop_mr_id);
        CREATE INDEX ix_workshop_invoices_po_id ON workshop_invoices(po_id);

        CREATE TABLE workshop_delivery_notes (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workshop_mr_id   UUID NOT NULL REFERENCES workshop_mrs(id) ON DELETE CASCADE,
            po_id            UUID REFERENCES workshop_purchase_orders(id) ON DELETE SET NULL,
            delivery_number  VARCHAR(100),
            delivery_file_url VARCHAR(1000),
            delivery_date    DATE,
            received_by_name VARCHAR(255),
            notes            TEXT,
            created_by       UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX ix_workshop_delivery_notes_mr_id ON workshop_delivery_notes(workshop_mr_id);
        CREATE INDEX ix_workshop_delivery_notes_po_id ON workshop_delivery_notes(po_id);
    """))


def downgrade() -> None:
    op.execute(text("""
        DROP TABLE IF EXISTS workshop_delivery_notes;
        DROP TABLE IF EXISTS workshop_invoices;
        DROP TABLE IF EXISTS workshop_purchase_orders;
    """))
