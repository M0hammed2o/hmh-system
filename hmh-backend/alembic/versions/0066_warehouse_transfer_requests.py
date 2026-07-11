"""warehouse transfer requests with 3-person approval

Revision ID: 0066
Revises: 0065
Create Date: 2026-07-10
"""

from alembic import op
from sqlalchemy import text

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("""
        CREATE TABLE warehouse_transfer_requests (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            from_project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            to_project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            item_id         UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            quantity        NUMERIC(12,3) NOT NULL,
            unit            VARCHAR(50),
            reason          TEXT NOT NULL,
            notes           TEXT,
            status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            requested_by    UUID NOT NULL REFERENCES users(id) ON DELETE SET NULL,
            requested_at    TIMESTAMPTZ NOT NULL,
            executed_at     TIMESTAMPTZ,
            executed_by     UUID REFERENCES users(id) ON DELETE SET NULL,
            rejection_reason TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))

    op.execute(text("""
        CREATE TABLE warehouse_transfer_votes (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            transfer_request_id   UUID NOT NULL REFERENCES warehouse_transfer_requests(id) ON DELETE CASCADE,
            voted_by              UUID NOT NULL REFERENCES users(id) ON DELETE SET NULL,
            voted_at              TIMESTAMPTZ NOT NULL,
            is_override           BOOLEAN NOT NULL DEFAULT FALSE,
            notes                 TEXT,
            UNIQUE (transfer_request_id, voted_by)
        )
    """))

    op.execute(text("CREATE INDEX ix_wtr_from_project ON warehouse_transfer_requests(from_project_id)"))
    op.execute(text("CREATE INDEX ix_wtr_to_project ON warehouse_transfer_requests(to_project_id)"))
    op.execute(text("CREATE INDEX ix_wtr_status ON warehouse_transfer_requests(status)"))
    op.execute(text("CREATE INDEX ix_wtv_transfer_request ON warehouse_transfer_votes(transfer_request_id)"))


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS warehouse_transfer_votes"))
    op.execute(text("DROP TABLE IF EXISTS warehouse_transfer_requests"))
