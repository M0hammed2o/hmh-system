"""Make stock_ledger.site_id and usage_logs.site_id nullable.

Revision ID: 0015
Revises:     0014
Create Date: 2026-05-21

WHY
---
The warehouse architecture requires stock ledger entries that are NOT tied to a
specific site:

  Project Warehouse entries: site_id IS NULL, lot_id IS NULL
  Main Warehouse entries:    site_id IS NULL, lot_id IS NULL (project-level)

Both concepts require site_id to be nullable. The current NOT NULL constraint
was inherited from the original V1 schema where every stock movement was
assumed to belong to a site — that assumption is no longer valid.

This is a NON-DESTRUCTIVE migration:
  - No existing rows are modified.
  - All existing rows already have a site_id value; they remain unchanged.
  - The FK is changed from CASCADE (delete stock rows when site deleted) to
    SET NULL (stock rows survive site deletion with site_id = NULL).

ROLLBACK
--------
Safe only if no NULL rows have been inserted yet:
  ALTER TABLE stock_ledger ALTER COLUMN site_id SET NOT NULL;
  ALTER TABLE usage_logs   ALTER COLUMN site_id SET NOT NULL;
"""

from alembic import op


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── stock_ledger ──────────────────────────────────────────────────────────
    # 1. Drop NOT NULL constraint
    op.alter_column("stock_ledger", "site_id", nullable=True)

    # 2. Replace CASCADE FK with SET NULL FK
    op.drop_constraint(
        "stock_ledger_site_id_fkey",
        "stock_ledger",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "stock_ledger_site_id_fkey",
        "stock_ledger",
        "sites",
        ["site_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── usage_logs ────────────────────────────────────────────────────────────
    # 1. Drop NOT NULL constraint
    op.alter_column("usage_logs", "site_id", nullable=True)

    # 2. Replace CASCADE FK with SET NULL FK
    op.drop_constraint(
        "usage_logs_site_id_fkey",
        "usage_logs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "usage_logs_site_id_fkey",
        "usage_logs",
        "sites",
        ["site_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Restore NOT NULL — ONLY SAFE if no NULL rows have been inserted.
    # Check first:
    #   SELECT COUNT(*) FROM stock_ledger WHERE site_id IS NULL;
    #   SELECT COUNT(*) FROM usage_logs   WHERE site_id IS NULL;

    # stock_ledger
    op.drop_constraint(
        "stock_ledger_site_id_fkey",
        "stock_ledger",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "stock_ledger_site_id_fkey",
        "stock_ledger",
        "sites",
        ["site_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("stock_ledger", "site_id", nullable=False)

    # usage_logs
    op.drop_constraint(
        "usage_logs_site_id_fkey",
        "usage_logs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "usage_logs_site_id_fkey",
        "usage_logs",
        "sites",
        ["site_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("usage_logs", "site_id", nullable=False)
