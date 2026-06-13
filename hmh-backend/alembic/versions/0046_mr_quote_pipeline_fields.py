"""Add pipeline status/source/BOQ fields to mr_quotes.

Revision ID: 0046
Revises: 0045
Create Date: 2026-06-13

New columns on mr_quotes:
  source          — 'MANUAL' (manually entered) or 'EMAIL' (auto-detected from Gmail)
  status          — 'PENDING' | 'APPROVED' | 'REJECTED'
  boq_unit_price  — BOQ reference unit price for comparison display
  rejection_reason — free-text reason sent to supplier on rejection
  rejected_at     — timestamp of rejection
  approved_at     — timestamp of approval
"""

from alembic import op
import sqlalchemy as sa

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE mr_quotes
            ADD COLUMN IF NOT EXISTS source          VARCHAR(20)    NOT NULL DEFAULT 'MANUAL',
            ADD COLUMN IF NOT EXISTS status          VARCHAR(20)    NOT NULL DEFAULT 'PENDING',
            ADD COLUMN IF NOT EXISTS boq_unit_price  NUMERIC(14,2),
            ADD COLUMN IF NOT EXISTS rejection_reason TEXT,
            ADD COLUMN IF NOT EXISTS rejected_at     TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS approved_at     TIMESTAMPTZ;
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_mr_quotes_status ON mr_quotes (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mr_quotes_source ON mr_quotes (source)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_mr_quotes_source")
    op.execute("DROP INDEX IF EXISTS ix_mr_quotes_status")
    op.execute("""
        ALTER TABLE mr_quotes
            DROP COLUMN IF EXISTS source,
            DROP COLUMN IF EXISTS status,
            DROP COLUMN IF EXISTS boq_unit_price,
            DROP COLUMN IF EXISTS rejection_reason,
            DROP COLUMN IF EXISTS rejected_at,
            DROP COLUMN IF EXISTS approved_at;
    """)
