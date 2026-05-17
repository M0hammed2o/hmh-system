"""Drop NOT NULL from attachments.file_url and payments.amount; backfill both.

Revision ID: 0009
Revises:     0008
Create Date: 2026-05-18

ROOT CAUSE (same pattern as 0006/0007/0008)
Migration 0001 created:
  attachments.file_url   VARCHAR(1000) NOT NULL
  payments.amount        NUMERIC(14,2) NOT NULL

The ORM models now use:
  Attachment.stored_path  (added in migration 0004 as nullable)
  Payment.amount_paid     (added in migration 0004 as nullable)

Every INSERT sets the new column and leaves the legacy column NULL
→ NotNullViolation → 500 on delivery recording and payment capture.

FIX: backfill legacy column from new column, then drop NOT NULL.
"""

from alembic import op
import sqlalchemy as sa

revision      = "0009"
down_revision = "0008"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # ── attachments.file_url ─────────────────────────────────────────────────
    att_cols = {c["name"] for c in insp.get_columns("attachments")}
    if "file_url" in att_cols and "stored_path" in att_cols:
        op.execute(sa.text("""
            UPDATE attachments
               SET file_url = stored_path
             WHERE file_url IS NULL AND stored_path IS NOT NULL
        """))
        op.execute(sa.text("""
            UPDATE attachments
               SET stored_path = file_url
             WHERE stored_path IS NULL AND file_url IS NOT NULL
        """))
        print("[0009] Backfilled attachments.file_url / stored_path.", flush=True)

    if "file_url" in att_cols:
        op.alter_column("attachments", "file_url", nullable=True)
        print("[0009] Dropped NOT NULL from attachments.file_url.", flush=True)

    # ── payments.amount ──────────────────────────────────────────────────────
    pay_cols = {c["name"] for c in insp.get_columns("payments")}
    if "amount" in pay_cols and "amount_paid" in pay_cols:
        op.execute(sa.text("""
            UPDATE payments
               SET amount = amount_paid
             WHERE amount IS NULL AND amount_paid IS NOT NULL
        """))
        op.execute(sa.text("""
            UPDATE payments
               SET amount_paid = amount
             WHERE amount_paid IS NULL AND amount IS NOT NULL
        """))
        print("[0009] Backfilled payments.amount / amount_paid.", flush=True)

    if "amount" in pay_cols:
        op.alter_column("payments", "amount", nullable=True)
        print("[0009] Dropped NOT NULL from payments.amount.", flush=True)


def downgrade() -> None:
    # Restore NOT NULL (safe only if no NULLs remain)
    op.execute(sa.text("UPDATE attachments SET file_url = stored_path WHERE file_url IS NULL AND stored_path IS NOT NULL"))
    op.alter_column("attachments", "file_url", nullable=False)

    op.execute(sa.text("UPDATE payments SET amount = amount_paid WHERE amount IS NULL AND amount_paid IS NOT NULL"))
    op.alter_column("payments", "amount", nullable=False)
