"""workshop_mr_email_logs — email log for quote requests sent to suppliers

Revision ID: 0060
Revises: 0059
Create Date: 2026-07-08
"""

from alembic import op
from sqlalchemy import text

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("""
        CREATE TABLE workshop_mr_email_logs (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workshop_mr_id  UUID NOT NULL REFERENCES workshop_mrs(id) ON DELETE CASCADE,
            supplier_id     UUID REFERENCES suppliers(id) ON DELETE SET NULL,
            sent_to_email   VARCHAR(255) NOT NULL,
            email_subject   VARCHAR(255),
            email_body      TEXT,
            status          VARCHAR(50)  NOT NULL,
            error_message   TEXT,
            sent_by         UUID REFERENCES users(id) ON DELETE SET NULL,
            sent_at         TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL
        );

        CREATE INDEX ix_workshop_mr_email_logs_mr_id ON workshop_mr_email_logs(workshop_mr_id);
        CREATE INDEX ix_workshop_mr_email_logs_status ON workshop_mr_email_logs(status);
    """))


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS workshop_mr_email_logs;"))
