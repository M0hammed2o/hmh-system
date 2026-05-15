"""Add vehicle_id FK to fuel_logs and soft-delete columns to key tables.

Revision ID: 0002
Revises:     0001
Create Date: 2026-05-15

Safety notes:
- All new columns are nullable or have safe defaults (is_active=true, vat_number nullable).
- No existing data is modified.
- Rollback drops only the columns/FKs added here.
- vehicle_id is nullable so existing fuel logs without a linked vehicle continue to work.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision    = "0002"
down_revision = "0001"
branch_labels = None
depends_on    = None


def _add_column_if_missing(table: str, column_name: str, column_def: sa.Column) -> None:
    """Add a column only if it does not already exist."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = [c["name"] for c in inspector.get_columns(table)]
    if column_name not in existing_cols:
        op.add_column(table, column_def)


def _create_index_if_missing(index_name: str, table: str, columns: list) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = [i["name"] for i in inspector.get_indexes(table)]
    if index_name not in existing_indexes:
        op.create_index(index_name, table, columns)


def upgrade() -> None:

    # ── 1. fuel_logs: add nullable vehicle_id FK ───────────────────────────────
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

    # ── 2-7. Soft-delete columns ───────────────────────────────────────────────
    for table in ("material_requests", "purchase_orders", "deliveries",
                  "invoices", "payments", "job_cards"):
        _add_column_if_missing(
            table, "is_active",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        )

    # ── 8. suppliers: vat_number ──────────────────────────────────────────────
    _add_column_if_missing(
        "suppliers", "vat_number",
        sa.Column("vat_number", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    # Remove in reverse order

    try:
        op.drop_column("suppliers", "vat_number")
    except Exception:
        pass

    op.drop_column("job_cards",          "is_active")
    op.drop_column("payments",           "is_active")
    op.drop_column("invoices",           "is_active")
    op.drop_column("deliveries",         "is_active")
    op.drop_column("purchase_orders",    "is_active")
    op.drop_column("material_requests",  "is_active")

    op.drop_index("ix_fuel_logs_vehicle_id", table_name="fuel_logs")
    op.drop_column("fuel_logs", "vehicle_id")
