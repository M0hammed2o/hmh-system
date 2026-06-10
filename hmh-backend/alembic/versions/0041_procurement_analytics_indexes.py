"""0041_procurement_analytics_indexes

Add composite indexes to accelerate procurement analytics queries.

Revision ID: 0041
Revises: 0040
Create Date: 2026-06-10
"""
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # purchase_orders — supplier+status for spend aggregations, project+status for project analytics
    op.execute("CREATE INDEX IF NOT EXISTS ix_po_supplier_status ON purchase_orders(supplier_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_po_project_status  ON purchase_orders(project_id,  status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_po_po_date         ON purchase_orders(po_date)")

    # deliveries — supplier for performance metrics, PO linkage for speed calculations
    op.execute("CREATE INDEX IF NOT EXISTS ix_deliveries_supplier_id ON deliveries(supplier_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_deliveries_po_id       ON deliveries(purchase_order_id)")

    # invoices — supplier+project composite for cross-filter analytics
    op.execute("CREATE INDEX IF NOT EXISTS ix_invoices_supplier_project ON invoices(supplier_id, project_id)")

    # payments — supplier for spend totals, project+status for outstanding calculations
    op.execute("CREATE INDEX IF NOT EXISTS ix_payments_supplier_id    ON payments(supplier_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_payments_project_status ON payments(project_id, status)")

    # quotations — supplier+status for acceptance rate
    op.execute("CREATE INDEX IF NOT EXISTS ix_quotations_supplier_status ON quotations(supplier_id, status)")

    # reconciliations — PO linkage for match rate per supplier
    op.execute("CREATE INDEX IF NOT EXISTS ix_recon_po_id ON procurement_reconciliations(purchase_order_id)")

    # purchase_order_items — PO linkage and item linkage for price history
    op.execute("CREATE INDEX IF NOT EXISTS ix_po_items_po_id   ON purchase_order_items(purchase_order_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_po_items_item_id ON purchase_order_items(item_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_po_supplier_status")
    op.execute("DROP INDEX IF EXISTS ix_po_project_status")
    op.execute("DROP INDEX IF EXISTS ix_po_po_date")
    op.execute("DROP INDEX IF EXISTS ix_deliveries_supplier_id")
    op.execute("DROP INDEX IF EXISTS ix_deliveries_po_id")
    op.execute("DROP INDEX IF EXISTS ix_invoices_supplier_project")
    op.execute("DROP INDEX IF EXISTS ix_payments_supplier_id")
    op.execute("DROP INDEX IF EXISTS ix_payments_project_status")
    op.execute("DROP INDEX IF EXISTS ix_quotations_supplier_status")
    op.execute("DROP INDEX IF EXISTS ix_recon_po_id")
    op.execute("DROP INDEX IF EXISTS ix_po_items_po_id")
    op.execute("DROP INDEX IF EXISTS ix_po_items_item_id")
