"""Fix NOT NULL on purchase_order_items.quantity (legacy column).

Revision ID: 0007
Revises:     0006
Create Date: 2026-05-17

ROOT CAUSE
----------
Migration 0001 created purchase_order_items with:
  quantity  NUMERIC(14,3)  NOT NULL   ← original column

Migration 0003 added the ORM-mapped replacement as nullable:
  quantity_ordered  NUMERIC(14,3)  NULLABLE

The ORM model (PurchaseOrderItem) only knows quantity_ordered.
convert_to_po() creates PurchaseOrderItem(quantity_ordered=5.0, ...).
PostgreSQL rejects it:
  "null value in column quantity violates not-null constraint"

FIX
---
1. Backfill quantity from quantity_ordered for existing rows.
2. Drop NOT NULL constraint from quantity so new ORM INSERTs succeed.
"""

from alembic import op
import sqlalchemy as sa

revision      = "0007"
down_revision = "0006"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    cols = {c["name"] for c in insp.get_columns("purchase_order_items")}

    if "quantity" in cols and "quantity_ordered" in cols:
        op.execute(sa.text("""
            UPDATE purchase_order_items
               SET quantity = quantity_ordered
             WHERE quantity IS NULL
               AND quantity_ordered IS NOT NULL
        """))
        print("[0007] Backfilled purchase_order_items.quantity from quantity_ordered.", flush=True)

    if "quantity" in cols:
        op.alter_column("purchase_order_items", "quantity", nullable=True)
        print("[0007] Dropped NOT NULL from purchase_order_items.quantity.", flush=True)


def downgrade() -> None:
    op.execute(sa.text("""
        UPDATE purchase_order_items
           SET quantity = quantity_ordered
         WHERE quantity IS NULL AND quantity_ordered IS NOT NULL
    """))
    op.alter_column("purchase_order_items", "quantity", nullable=False)
