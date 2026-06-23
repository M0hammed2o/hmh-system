"""Add 4-way MR approval system.

Revision ID: 0054
Revises:     0053
Create Date: 2026-06-23

Changes:
  user_role_enum:
    PROCUREMENT_LEAD — dedicated role for the person who gives final
                        approval (or override) on material requests.

  record_status_enum:
    STAFF_APPROVED — MR has received the required number of staff votes
                     and is waiting for PROCUREMENT_LEAD final approval.

  mr_approvals (new table):
    Records each individual vote/approval for an MR.
    Unique constraint on (mr_id, approved_by) so one person can only
    vote once per MR.  is_override=true means a PROCUREMENT_LEAD
    approved without the full staff vote count.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision      = "0054"
down_revision = "0053"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── New enum values ────────────────────────────────────────────────────────
    op.execute(sa.text("""
        DO $$
        BEGIN
            ALTER TYPE user_role_enum ADD VALUE IF NOT EXISTS 'PROCUREMENT_LEAD';
        EXCEPTION WHEN others THEN NULL;
        END$$;
    """))

    op.execute(sa.text("""
        DO $$
        BEGIN
            ALTER TYPE record_status_enum ADD VALUE IF NOT EXISTS 'STAFF_APPROVED';
        EXCEPTION WHEN others THEN NULL;
        END$$;
    """))

    # ── mr_approvals table ────────────────────────────────────────────────────
    op.create_table(
        "mr_approvals",
        sa.Column("id",          UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mr_id",       UUID(as_uuid=True), sa.ForeignKey("material_requests.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("approved_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_override", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("notes",       sa.Text, nullable=True),
        sa.UniqueConstraint("mr_id", "approved_by", name="uq_mr_approvals_mr_approver"),
    )

    print("[0054] Added PROCUREMENT_LEAD, STAFF_APPROVED, mr_approvals table.", flush=True)


def downgrade() -> None:
    op.drop_table("mr_approvals")
    # Enum values cannot be removed from PostgreSQL enums — no-op for those.
