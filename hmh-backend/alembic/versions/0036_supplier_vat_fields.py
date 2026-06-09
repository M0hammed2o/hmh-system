"""Add VAT configuration fields to suppliers

Revision ID: 0036
Revises: 0035
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pricingmethod') THEN
                CREATE TYPE pricingmethod AS ENUM ('EX_VAT', 'INCL_VAT');
            END IF;
        END
        $$
    """)

    op.add_column("suppliers", sa.Column(
        "vat_registered", sa.Boolean(), nullable=False, server_default="true"
    ))
    op.add_column("suppliers", sa.Column(
        "pricing_method",
        sa.Enum("EX_VAT", "INCL_VAT", name="pricingmethod", create_type=False),
        nullable=False,
        server_default="EX_VAT",
    ))
    op.add_column("suppliers", sa.Column(
        "default_vat_rate", sa.Numeric(5, 2), nullable=False, server_default="15.00"
    ))


def downgrade() -> None:
    op.drop_column("suppliers", "default_vat_rate")
    op.drop_column("suppliers", "pricing_method")
    op.drop_column("suppliers", "vat_registered")
    op.execute("DROP TYPE IF EXISTS pricingmethod")
