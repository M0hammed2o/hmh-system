"""Make po_email_logs.sent_to nullable; backfill from sent_to_email.

Revision ID: 0008
Revises:     0007
Create Date: 2026-05-17

ROOT CAUSE
Migration 0001 created po_email_logs with:
  sent_to  VARCHAR(255)  NOT NULL

Migration 0003 added the ORM-mapped replacement:
  sent_to_email  VARCHAR(255)  NULLABLE

The ORM PoEmailLog model only sets sent_to_email. Every INSERT leaves
sent_to = NULL → NotNullViolation → 500 on POST /prepare-email.

FIX: backfill + drop NOT NULL on the legacy column.
"""

from alembic import op
import sqlalchemy as sa

revision      = "0008"
down_revision = "0007"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    cols = {c["name"] for c in insp.get_columns("po_email_logs")}

    # Backfill legacy column from the new ORM column for existing rows
    if "sent_to" in cols and "sent_to_email" in cols:
        op.execute(sa.text("""
            UPDATE po_email_logs
               SET sent_to = sent_to_email
             WHERE sent_to IS NULL AND sent_to_email IS NOT NULL
        """))
        op.execute(sa.text("""
            UPDATE po_email_logs
               SET sent_to_email = sent_to
             WHERE sent_to_email IS NULL AND sent_to IS NOT NULL
        """))
        print("[0008] Backfilled po_email_logs.sent_to / sent_to_email.", flush=True)

    if "sent_to" in cols:
        op.alter_column("po_email_logs", "sent_to", nullable=True)
        print("[0008] Dropped NOT NULL from po_email_logs.sent_to.", flush=True)

    # Also make the old subject column nullable (was VARCHAR(500) nullable in 0001, fine)


def downgrade() -> None:
    op.execute(sa.text("""
        UPDATE po_email_logs SET sent_to = sent_to_email
        WHERE sent_to IS NULL AND sent_to_email IS NOT NULL
    """))
    op.alter_column("po_email_logs", "sent_to", nullable=False)
