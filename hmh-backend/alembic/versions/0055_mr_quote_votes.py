"""Add mr_quote_votes table — 3-staff-vote approval system for quotes.

Revision ID: 0055
Revises:     0054
Create Date: 2026-06-25

Each user may cast exactly one vote per quote (unique constraint on quote_id + voted_by).
Three staff votes auto-approve the quote. PROCUREMENT_LEAD/OWNER override via
/approve endpoint which records is_override=True.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision      = "0055"
down_revision = "0054"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "mr_quote_votes",
        sa.Column("id",          UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("quote_id",    UUID(as_uuid=True), sa.ForeignKey("mr_quotes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("voted_by",    UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("voted_at",    sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_override", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("notes",       sa.Text, nullable=True),
        sa.UniqueConstraint("quote_id", "voted_by", name="uq_mr_quote_votes_quote_voter"),
    )
    print("[0055] Created mr_quote_votes table.", flush=True)


def downgrade() -> None:
    op.drop_table("mr_quote_votes")
