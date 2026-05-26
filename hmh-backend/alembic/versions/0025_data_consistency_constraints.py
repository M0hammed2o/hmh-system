"""Data consistency constraints — Phase 3S

Adds DB-level unique constraints that back existing application-level checks.
These prevent race conditions where two concurrent requests both pass the
app-level check before either commits.

All constraints use partial unique indexes (PostgreSQL) so NULL values
are excluded — consistent with the application model.

Revision ID: 0025
Revises: 0024
"""

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. invoices — (supplier_id, invoice_number) uniqueness
    #    Application already checks this in invoice_service.create_invoice(), but a
    #    concurrent pair of requests can both pass the check before either commits.
    #    Partial index: only applies when BOTH columns are non-null.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_invoices_supplier_invoice_number
        ON invoices(supplier_id, invoice_number)
        WHERE supplier_id IS NOT NULL AND invoice_number IS NOT NULL
    """)

    # 2. payments — (project_id, payment_reference) uniqueness
    #    Application already checks this in payment_service.create_payment(), but
    #    concurrent requests race past the unlocked .first() check.
    #    Partial index: only when payment_reference is supplied (it's optional).
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_project_reference
        ON payments(project_id, payment_reference)
        WHERE payment_reference IS NOT NULL
    """)

    # 3. notification_queue — provider_message_id uniqueness
    #    Prevents the WhatsApp webhook from creating duplicate status entries
    #    for the same outbound message ID returned by Meta.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_queue_provider_message_id
        ON notification_queue(provider_message_id)
        WHERE provider_message_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_notification_queue_provider_message_id")
    op.execute("DROP INDEX IF EXISTS uq_payments_project_reference")
    op.execute("DROP INDEX IF EXISTS uq_invoices_supplier_invoice_number")
