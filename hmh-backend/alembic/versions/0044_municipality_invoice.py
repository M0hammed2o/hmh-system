"""0044_municipality_invoice

Municipality Invoice + Invoice Line Items module.

Creates:
  - municipality_invoices table
  - municipality_invoice_items table

Revision ID: 0044
Revises: 0043
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "municipality_invoices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("invoice_number", sa.String(60), nullable=False, unique=True, index=True),
        sa.Column("cert_number",    sa.String(60), nullable=True),
        sa.Column("project_id",     UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),

        # Invoice header
        sa.Column("invoice_date",   sa.Date, nullable=False),
        sa.Column("due_date",       sa.Date, nullable=True),

        # Client (municipality)
        sa.Column("client_name",    sa.String(200), nullable=False, server_default="Ethekweni Municipality"),
        sa.Column("client_vat_no",  sa.String(60),  nullable=True),
        sa.Column("client_address", sa.Text,        nullable=True),

        # Supplier / company
        sa.Column("company_email",  sa.String(200), nullable=True),

        # Contract
        sa.Column("project_description", sa.String(300), nullable=True),
        sa.Column("contract_reference",  sa.String(100), nullable=True),

        # Totals (stored so the lady can override)
        sa.Column("subtotal",        sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("previously_paid", sa.Numeric(14, 2), nullable=True),
        sa.Column("vat_rate",        sa.Numeric(5, 2),  nullable=False, server_default="15.00"),
        sa.Column("vat_amount",      sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total_due",       sa.Numeric(14, 2), nullable=False, server_default="0"),

        # Notes + banking
        sa.Column("notes",        sa.Text, nullable=True),
        sa.Column("bank_name",    sa.String(100), nullable=True),
        sa.Column("account_number", sa.String(60), nullable=True),
        sa.Column("branch_name",  sa.String(100), nullable=True),
        sa.Column("branch_code",  sa.String(20),  nullable=True),

        sa.Column("status",     sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    op.create_table(
        "municipality_invoice_items",
        sa.Column("id",         UUID(as_uuid=True), primary_key=True),
        sa.Column("invoice_id", UUID(as_uuid=True), sa.ForeignKey("municipality_invoices.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("sort_order",   sa.Integer, nullable=False, server_default="0"),
        sa.Column("line_number",  sa.String(20), nullable=True),
        sa.Column("description",  sa.Text, nullable=False),
        sa.Column("quantity",     sa.Numeric(12, 3), nullable=True),
        sa.Column("unit_price",   sa.Numeric(14, 2), nullable=True),
        sa.Column("total",        sa.Numeric(14, 2), nullable=True),
        sa.Column("disc_pct",     sa.Numeric(5, 2),  nullable=True),
        sa.Column("comments",     sa.Text, nullable=True),
        sa.Column("created_at",   sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("municipality_invoice_items")
    op.drop_table("municipality_invoices")
