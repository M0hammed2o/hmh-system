"""Add lot_types table and extend lots + boq_items for inheritance.

Revision ID: 0016
Revises:     0015
Create Date: 2026-05-21

Phase 3D.1 — Schema only. No business logic changed.

New objects:
  TABLE lot_types
    id                  UUID PK
    project_id          UUID NOT NULL FK projects(id) CASCADE
    name                VARCHAR(100) NOT NULL
    code                VARCHAR(50)            optional short identifier
    description         TEXT
    default_template_id UUID FK boq_headers(id) SET NULL
    created_at          TIMESTAMPTZ NOT NULL
    updated_at          TIMESTAMPTZ NOT NULL

  ix_lot_types_project_id          — query by project
  uq_lot_types_project_code        — uniqueness of code within project (nullable)

Extended existing tables (all additive — no existing rows touched):
  lots.lot_type_id             UUID nullable FK lot_types(id) SET NULL
  lots.boq_customized_at       TIMESTAMPTZ nullable
                                 NULL  = BOQ was only ever generated (never hand-edited)
                                 Value = timestamp of first manual edit
  boq_items.generated_from_lot_type_id
                               UUID nullable FK lot_types(id) SET NULL
                                 Records which LotType generated this item.
                                 NULL on items created before Phase 3D or without a type.

ROLLBACK:
  ALTER TABLE boq_items DROP COLUMN generated_from_lot_type_id;
  ALTER TABLE lots DROP COLUMN boq_customized_at;
  ALTER TABLE lots DROP COLUMN lot_type_id;
  DROP TABLE lot_types CASCADE;
  (safe only if no lot_type_id values have been written)
"""

import sqlalchemy as sa
from alembic import op

revision      = "0016"
down_revision = "0015"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── 1. Create lot_types table ────────────────────────────────────────────
    op.create_table(
        "lot_types",
        sa.Column("id",                  sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id",          sa.UUID(as_uuid=True), nullable=False),
        sa.Column("name",                sa.String(100),         nullable=False),
        sa.Column("code",                sa.String(50),          nullable=True),
        sa.Column("description",         sa.Text(),              nullable=True),
        sa.Column("default_template_id", sa.UUID(as_uuid=True),  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["default_template_id"], ["boq_headers.id"], ondelete="SET NULL"
        ),
    )

    # Index: fast lookup by project
    op.create_index("ix_lot_types_project_id", "lot_types", ["project_id"])

    # Partial unique index: code must be unique within a project, but only when set
    op.execute(
        "CREATE UNIQUE INDEX uq_lot_types_project_code "
        "ON lot_types(project_id, code) "
        "WHERE code IS NOT NULL"
    )

    # ── 2. Extend lots table ─────────────────────────────────────────────────
    op.add_column(
        "lots",
        sa.Column("lot_type_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "lots_lot_type_id_fkey",
        "lots", "lot_types",
        ["lot_type_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_lots_lot_type_id", "lots", ["lot_type_id"])

    op.add_column(
        "lots",
        sa.Column("boq_customized_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── 3. Extend boq_items table ────────────────────────────────────────────
    op.add_column(
        "boq_items",
        sa.Column("generated_from_lot_type_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "boq_items_generated_from_lot_type_id_fkey",
        "boq_items", "lot_types",
        ["generated_from_lot_type_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Remove in reverse order to avoid FK violations
    op.drop_constraint(
        "boq_items_generated_from_lot_type_id_fkey", "boq_items", type_="foreignkey"
    )
    op.drop_column("boq_items", "generated_from_lot_type_id")

    op.drop_column("lots", "boq_customized_at")
    op.drop_index("ix_lots_lot_type_id", "lots")
    op.drop_constraint("lots_lot_type_id_fkey", "lots", type_="foreignkey")
    op.drop_column("lots", "lot_type_id")

    op.drop_index("ix_lot_types_project_id", "lot_types")
    op.execute("DROP INDEX IF EXISTS uq_lot_types_project_code")
    op.drop_table("lot_types")
