"""Make stock_ledger.project_id nullable for global warehouse receives

Revision ID: 0031
Revises: 0030
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the NOT NULL constraint so global (non-project) stock is supported
    op.alter_column("stock_ledger", "project_id", existing_type=sa.UUID(), nullable=True)
    # Also update the on-delete behaviour to SET NULL (was CASCADE)
    op.drop_constraint("stock_ledger_project_id_fkey", "stock_ledger", type_="foreignkey")
    op.create_foreign_key(
        "stock_ledger_project_id_fkey",
        "stock_ledger", "projects",
        ["project_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("stock_ledger_project_id_fkey", "stock_ledger", type_="foreignkey")
    op.create_foreign_key(
        "stock_ledger_project_id_fkey",
        "stock_ledger", "projects",
        ["project_id"], ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("stock_ledger", "project_id", existing_type=sa.UUID(), nullable=False)
