"""workshop_mr_approvals — 3-person vote table for Workshop MRs

Revision ID: 0059
Revises: 0058
Create Date: 2026-07-08
"""

from alembic import op
from sqlalchemy import text

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("""
        CREATE TABLE workshop_mr_approvals (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            mr_id       UUID NOT NULL REFERENCES workshop_mrs(id) ON DELETE CASCADE,
            approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
            approved_at TIMESTAMPTZ NOT NULL,
            is_override BOOLEAN NOT NULL DEFAULT FALSE,
            notes       TEXT,
            CONSTRAINT uq_workshop_mr_approvals_mr_approver UNIQUE (mr_id, approved_by)
        );

        CREATE INDEX ix_workshop_mr_approvals_mr_id ON workshop_mr_approvals(mr_id);
    """))


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS workshop_mr_approvals;"))
