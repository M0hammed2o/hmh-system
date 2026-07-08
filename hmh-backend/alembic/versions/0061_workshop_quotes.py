"""workshop_quotes — supplier quotes and their approval votes

Revision ID: 0061
Revises: 0060
Create Date: 2026-07-08
"""

from alembic import op
from sqlalchemy import text

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("""
        CREATE TABLE workshop_quotes (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workshop_mr_id  UUID NOT NULL REFERENCES workshop_mrs(id) ON DELETE CASCADE,
            supplier_id     UUID REFERENCES suppliers(id) ON DELETE SET NULL,
            supplier_name   VARCHAR(255),
            quote_file_url  VARCHAR(1000),
            total_amount    NUMERIC(14, 2),
            currency        VARCHAR(10)  NOT NULL DEFAULT 'ZAR',
            notes           TEXT,
            status          VARCHAR(50)  NOT NULL DEFAULT 'PENDING',
            rejection_reason TEXT,
            submitted_at    TIMESTAMPTZ,
            created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX ix_workshop_quotes_mr_id      ON workshop_quotes(workshop_mr_id);
        CREATE INDEX ix_workshop_quotes_supplier_id ON workshop_quotes(supplier_id);
        CREATE INDEX ix_workshop_quotes_status      ON workshop_quotes(status);

        CREATE TABLE workshop_quote_approvals (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            quote_id    UUID NOT NULL REFERENCES workshop_quotes(id) ON DELETE CASCADE,
            approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
            approved_at TIMESTAMPTZ NOT NULL,
            is_override BOOLEAN NOT NULL DEFAULT FALSE,
            notes       TEXT,
            CONSTRAINT uq_workshop_quote_approvals_quote_approver UNIQUE (quote_id, approved_by)
        );

        CREATE INDEX ix_workshop_quote_approvals_quote_id ON workshop_quote_approvals(quote_id);
    """))


def downgrade() -> None:
    op.execute(text("""
        DROP TABLE IF EXISTS workshop_quote_approvals;
        DROP TABLE IF EXISTS workshop_quotes;
    """))
