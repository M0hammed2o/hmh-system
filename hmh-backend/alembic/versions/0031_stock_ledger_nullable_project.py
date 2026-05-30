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
    # Make nullable (no-op if already nullable)
    op.execute("ALTER TABLE stock_ledger ALTER COLUMN project_id DROP NOT NULL")
    # Recreate FK with SET NULL only if it exists with the old behaviour
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.referential_constraints
                WHERE constraint_name = 'stock_ledger_project_id_fkey'
            ) THEN
                ALTER TABLE stock_ledger DROP CONSTRAINT stock_ledger_project_id_fkey;
            END IF;
            ALTER TABLE stock_ledger
                ADD CONSTRAINT stock_ledger_project_id_fkey
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END
        $$
    """)


def downgrade() -> None:
    op.drop_constraint("stock_ledger_project_id_fkey", "stock_ledger", type_="foreignkey")
    op.create_foreign_key(
        "stock_ledger_project_id_fkey",
        "stock_ledger", "projects",
        ["project_id"], ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("stock_ledger", "project_id", existing_type=sa.UUID(), nullable=False)
