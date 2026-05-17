"""Make fuel_logs.log_date nullable; backfill from fuel_date.

Revision ID: 0010
Revises:     0009
Create Date: 2026-05-18

ROOT CAUSE (same pattern as 0006-0009)
Migration 0001 created fuel_logs with:
  log_date  DATE  NOT NULL   (legacy column, stores date only)

The current FuelLog ORM model uses:
  fuel_date  TIMESTAMPTZ  NOT NULL  (added in a later migration)

The service sets fuel_date but never touches log_date, so every INSERT
leaves log_date = NULL → NotNullViolation → 500 on fuel logging.

FIX: backfill log_date from fuel_date, then drop NOT NULL so new
INSERTs succeed without the ORM needing to know about the legacy column.
"""

from alembic import op
import sqlalchemy as sa

revision      = "0010"
down_revision = "0009"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("fuel_logs")}

    if "log_date" in cols and "fuel_date" in cols:
        op.execute(sa.text("""
            UPDATE fuel_logs
               SET log_date = fuel_date::date
             WHERE log_date IS NULL AND fuel_date IS NOT NULL
        """))
        print("[0010] Backfilled fuel_logs.log_date from fuel_date.", flush=True)

    if "log_date" in cols:
        op.alter_column("fuel_logs", "log_date", nullable=True)
        print("[0010] Dropped NOT NULL from fuel_logs.log_date.", flush=True)


def downgrade() -> None:
    op.execute(sa.text("""
        UPDATE fuel_logs SET log_date = fuel_date::date
        WHERE log_date IS NULL AND fuel_date IS NOT NULL
    """))
    op.alter_column("fuel_logs", "log_date", nullable=False)
