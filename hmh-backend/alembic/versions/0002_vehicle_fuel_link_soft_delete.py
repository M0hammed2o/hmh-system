"""Add vehicle_id FK to fuel_logs and soft-delete columns to key tables.

Revision ID: 0002
Revises:     0001
Create Date: 2026-05-15

Safety notes:
- All new columns are nullable or have safe defaults (is_active=true, vat_number nullable).
- No existing data is modified.
- Every helper checks whether the TABLE exists before inspecting its columns/indexes.
- If a table is absent (e.g. job_cards not yet created on this DB), the operation is
  skipped with a log message.  This makes the migration safe for any DB state.
- Rollback also skips missing tables/columns gracefully.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0002"
down_revision = "0001"
branch_labels = None
depends_on    = None


# ── Safe helper functions ─────────────────────────────────────────────────────

def _table_exists(inspector: sa.Inspector, table: str) -> bool:
    """Return True if the table exists in the current schema."""
    return table in inspector.get_table_names()


def _add_column_if_missing(table: str, column_name: str, column_def: sa.Column) -> None:
    """
    Add a column to *table* only if:
      1. The table exists.
      2. The column does not already exist.
    Silently skips both conditions so the migration is idempotent and
    safe against databases that have not yet run the initial schema.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, table):
        print(f"[0002] SKIP add column '{column_name}': table '{table}' does not exist.")
        return

    existing_cols = [c["name"] for c in inspector.get_columns(table)]
    if column_name not in existing_cols:
        op.add_column(table, column_def)
        print(f"[0002] ADDED column '{column_name}' to '{table}'.")
    else:
        print(f"[0002] SKIP add column '{column_name}': already exists on '{table}'.")


def _create_index_if_missing(index_name: str, table: str, columns: list) -> None:
    """
    Create an index only if both the table and the index are absent.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, table):
        print(f"[0002] SKIP create index '{index_name}': table '{table}' does not exist.")
        return

    existing_indexes = [i["name"] for i in inspector.get_indexes(table)]
    if index_name not in existing_indexes:
        op.create_index(index_name, table, columns)
        print(f"[0002] CREATED index '{index_name}' on '{table}'.")
    else:
        print(f"[0002] SKIP create index '{index_name}': already exists.")


def _drop_column_if_exists(table: str, column_name: str) -> None:
    """
    Drop a column only if both the table and the column exist.
    Used in downgrade so rollbacks are equally idempotent.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, table):
        print(f"[0002] SKIP drop column '{column_name}': table '{table}' does not exist.")
        return

    existing_cols = [c["name"] for c in inspector.get_columns(table)]
    if column_name in existing_cols:
        op.drop_column(table, column_name)
        print(f"[0002] DROPPED column '{column_name}' from '{table}'.")
    else:
        print(f"[0002] SKIP drop column '{column_name}': not present on '{table}'.")


def _drop_index_if_exists(index_name: str, table: str) -> None:
    """
    Drop an index only if both the table and the index exist.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, table):
        print(f"[0002] SKIP drop index '{index_name}': table '{table}' does not exist.")
        return

    existing_indexes = [i["name"] for i in inspector.get_indexes(table)]
    if index_name in existing_indexes:
        op.drop_index(index_name, table_name=table)
        print(f"[0002] DROPPED index '{index_name}' from '{table}'.")
    else:
        print(f"[0002] SKIP drop index '{index_name}': not present.")


# ── Upgrade ───────────────────────────────────────────────────────────────────

def upgrade() -> None:

    # ── 1. fuel_logs: add nullable vehicle_id FK ──────────────────────────────
    _add_column_if_missing(
        "fuel_logs", "vehicle_id",
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    _create_index_if_missing("ix_fuel_logs_vehicle_id", "fuel_logs", ["vehicle_id"])

    # ── 2-7. Soft-delete: add is_active where table exists ────────────────────
    # Tables are checked individually so a missing table (e.g. job_cards on an
    # older DB schema) does not abort the entire migration.
    for table in (
        "material_requests",
        "purchase_orders",
        "deliveries",
        "invoices",
        "payments",
        "job_cards",   # may not exist on older production schemas — skipped safely
    ):
        _add_column_if_missing(
            table, "is_active",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        )

    # ── 8. suppliers: vat_number ───────────────────────────────────────────────
    _add_column_if_missing(
        "suppliers", "vat_number",
        sa.Column("vat_number", sa.String(50), nullable=True),
    )


# ── Downgrade ─────────────────────────────────────────────────────────────────

def downgrade() -> None:
    # Remove in reverse order — all operations are table-and-column safe.

    _drop_column_if_exists("suppliers",         "vat_number")
    _drop_column_if_exists("job_cards",         "is_active")
    _drop_column_if_exists("payments",          "is_active")
    _drop_column_if_exists("invoices",          "is_active")
    _drop_column_if_exists("deliveries",        "is_active")
    _drop_column_if_exists("purchase_orders",   "is_active")
    _drop_column_if_exists("material_requests", "is_active")

    _drop_index_if_exists("ix_fuel_logs_vehicle_id", "fuel_logs")
    _drop_column_if_exists("fuel_logs", "vehicle_id")
