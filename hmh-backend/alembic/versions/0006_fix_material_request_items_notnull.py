"""Fix NOT NULL violations on material_request_items legacy columns.

Revision ID: 0006
Revises:     0005
Create Date: 2026-05-17

ROOT CAUSE
----------
Migration 0001 created material_request_items with:
  - request_id        UUID  NOT NULL  FK → material_requests.id
  - quantity_requested NUMERIC NOT NULL

Migration 0003 added the ORM-mapped replacements as nullable:
  - material_request_id UUID  NULLABLE  FK → material_requests.id
  - requested_quantity   NUMERIC NULLABLE

The ORM model uses material_request_id and requested_quantity exclusively.
Every INSERT via the ORM leaves request_id = NULL and quantity_requested = NULL,
which PostgreSQL rejects:
  "null value in column request_id violates not-null constraint"

FIX
---
1. Backfill material_request_id from request_id (existing rows).
2. Backfill requested_quantity from quantity_requested (existing rows).
3. Drop NOT NULL from request_id  (old column — ORM ignores it).
4. Drop NOT NULL from quantity_requested (old column — ORM ignores it).
"""

from alembic import op
import sqlalchemy as sa

revision      = "0006"
down_revision = "0005"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    cols = {c["name"]: c for c in insp.get_columns("material_request_items")}

    # ── 1. Backfill new columns from old columns for rows that pre-date 0003 ──
    if "request_id" in cols and "material_request_id" in cols:
        op.execute(sa.text("""
            UPDATE material_request_items
               SET material_request_id = request_id
             WHERE material_request_id IS NULL
               AND request_id IS NOT NULL
        """))
        print("[0006] Backfilled material_request_id from request_id.", flush=True)

    if "quantity_requested" in cols and "requested_quantity" in cols:
        op.execute(sa.text("""
            UPDATE material_request_items
               SET requested_quantity = quantity_requested
             WHERE requested_quantity IS NULL
               AND quantity_requested IS NOT NULL
        """))
        print("[0006] Backfilled requested_quantity from quantity_requested.", flush=True)

    # ── 2. Drop NOT NULL from request_id ────────────────────────────────────
    if "request_id" in cols:
        op.alter_column("material_request_items", "request_id", nullable=True)
        print("[0006] Dropped NOT NULL from material_request_items.request_id.", flush=True)

    # ── 3. Drop NOT NULL from quantity_requested ─────────────────────────────
    if "quantity_requested" in cols:
        op.alter_column("material_request_items", "quantity_requested", nullable=True)
        print("[0006] Dropped NOT NULL from material_request_items.quantity_requested.", flush=True)


def downgrade() -> None:
    # Re-apply NOT NULL constraints (safe only if no NULLs exist)
    op.execute(sa.text("""
        UPDATE material_request_items
           SET request_id = material_request_id
         WHERE request_id IS NULL AND material_request_id IS NOT NULL
    """))
    op.execute(sa.text("""
        UPDATE material_request_items
           SET quantity_requested = requested_quantity
         WHERE quantity_requested IS NULL AND requested_quantity IS NOT NULL
    """))
    op.alter_column("material_request_items", "request_id",         nullable=False)
    op.alter_column("material_request_items", "quantity_requested",  nullable=False)
