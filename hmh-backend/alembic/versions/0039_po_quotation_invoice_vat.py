"""Add quotation_id to purchase_orders and vat_rate_used to invoices.

Revision ID: 0039
Revises: 0038
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision      = "0039"
down_revision = "0038"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "purchase_orders",
        sa.Column(
            "quotation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("quotations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_purchase_orders_quotation_id", "purchase_orders", ["quotation_id"])

    op.add_column(
        "invoices",
        sa.Column("vat_rate_used", sa.Numeric(5, 2), nullable=True, server_default="15.00"),
    )


def downgrade() -> None:
    op.drop_index("ix_purchase_orders_quotation_id", table_name="purchase_orders")
    op.drop_column("purchase_orders", "quotation_id")
    op.drop_column("invoices", "vat_rate_used")
