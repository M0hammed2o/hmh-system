"""add procurement_category to material_requests

Revision ID: 0071
Revises: 0070

Classifies the procurement request itself (MATERIAL vs FUEL), not the
catalogue item — MaterialRequestItem.item_id/boq_item_id already support a
fully non-BOQ item today (both nullable), so no item-level schema change is
needed for Fuel to travel through the existing Material Request pipeline.

Safe sequence on a populated table: add nullable -> backfill -> constrain ->
make NOT NULL with a default, so no existing row is ever briefly invalid.
"""

from alembic import op
from sqlalchemy import text

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text(
        "ALTER TABLE material_requests ADD COLUMN IF NOT EXISTS procurement_category VARCHAR(20)"
    ))
    conn.execute(text(
        "UPDATE material_requests SET procurement_category = 'MATERIAL' "
        "WHERE procurement_category IS NULL"
    ))
    conn.execute(text(
        "ALTER TABLE material_requests "
        "ADD CONSTRAINT ck_material_requests_procurement_category "
        "CHECK (procurement_category IN ('MATERIAL', 'FUEL'))"
    ))
    conn.execute(text(
        "ALTER TABLE material_requests ALTER COLUMN procurement_category SET NOT NULL"
    ))
    conn.execute(text(
        "ALTER TABLE material_requests ALTER COLUMN procurement_category SET DEFAULT 'MATERIAL'"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_material_requests_procurement_category "
        "ON material_requests(procurement_category)"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP INDEX IF EXISTS ix_material_requests_procurement_category"))
    conn.execute(text(
        "ALTER TABLE material_requests DROP CONSTRAINT IF EXISTS ck_material_requests_procurement_category"
    ))
    conn.execute(text("ALTER TABLE material_requests DROP COLUMN IF EXISTS procurement_category"))
