"""Add preferred_supplier_id to material_request_items

Revision ID: 0051
Revises: 0050
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "material_request_items",
        sa.Column(
            "preferred_supplier_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("material_request_items", "preferred_supplier_id")
