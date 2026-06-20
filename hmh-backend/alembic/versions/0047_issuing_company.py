"""Add issuing_company to material_requests and purchase_orders.

Revision ID: 0047
Revises: 0046
Create Date: 2026-06-20

New columns:
  material_requests.issuing_company  — VARCHAR(50) nullable, 'HMH_GROUP' or 'MINERAT'
  purchase_orders.issuing_company    — VARCHAR(50) nullable, 'HMH_GROUP' or 'MINERAT'
"""

from alembic import op
import sqlalchemy as sa

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "material_requests",
        sa.Column("issuing_company", sa.String(50), nullable=True),
    )
    op.add_column(
        "purchase_orders",
        sa.Column("issuing_company", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("purchase_orders", "issuing_company")
    op.drop_column("material_requests", "issuing_company")
