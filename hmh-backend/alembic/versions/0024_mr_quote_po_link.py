"""Phase 3Z — link mr_quotes to the PO they were converted into.

Revision ID: 0024
Revises:     0023
Create Date: 2026-06-22

Changes:
  mr_quotes.purchase_order_id (UUID, nullable, FK → purchase_orders.id SET NULL)
  Used by the finalize-pos endpoint to know which approved quotes have already
  been included in a PO, so re-runs only process newly approved quotes.

ROLLBACK:
  Drops the column; existing data is unaffected.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision      = "0024"
down_revision = "0023"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "mr_quotes",
        sa.Column(
            "purchase_order_id",
            UUID(as_uuid=True),
            sa.ForeignKey("purchase_orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_mr_quotes_purchase_order_id", "mr_quotes", ["purchase_order_id"])


def downgrade() -> None:
    op.drop_index("ix_mr_quotes_purchase_order_id", table_name="mr_quotes")
    op.drop_column("mr_quotes", "purchase_order_id")
