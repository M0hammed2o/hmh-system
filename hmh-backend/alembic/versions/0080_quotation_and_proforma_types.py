"""Recognise quotations and pro-forma invoices.

Revision ID: 0080
Revises: 0079
Create Date: 2026-10-29

Half of a real batch of HMH paperwork is quotations and pro-forma invoices,
and the import engine had no type for either. Both were therefore destined
for SUPPLIER_INVOICE or UNKNOWN — and SUPPLIER_INVOICE is the dangerous one,
because a pro-forma says "Invoice" across the top while being a request for
payment in advance, not a liability. Booking one as a supplier invoice
creates an Accounts Payable entry that does not exist, and when the real tax
invoice arrives for the same goods the business owes it twice.

They are genuinely different things:

  QUOTATION          a price offer. Commits nobody. No liability, no stock.
  PRO_FORMA_INVOICE  a request for payment before supply. Provisional only;
                     it becomes a liability when the tax invoice arrives, and
                     must not be counted twice at that point.

Additive: two new values on an existing enum. PostgreSQL cannot remove enum
values, so the downgrade is deliberately a no-op rather than a rebuild of
every dependent column — see below.
"""

from alembic import op

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


NEW_TYPES = ("QUOTATION", "PRO_FORMA_INVOICE")


def upgrade() -> None:
    conn = op.get_bind()
    for value in NEW_TYPES:
        # IF NOT EXISTS so a re-run is harmless, and because an environment
        # may already have been patched by hand.
        conn.exec_driver_sql(
            f"ALTER TYPE ai_import_document_type_enum ADD VALUE IF NOT EXISTS '{value}'"
        )


def downgrade() -> None:
    """
    Deliberately does nothing.

    PostgreSQL has no DROP VALUE. Removing these would mean recreating the
    type and rewriting every column that uses it, which risks far more than
    an unused label costs — and any document already classified as a
    quotation would have to be reassigned to something untrue. Leaving the
    values in place is harmless: nothing reads them unless a document
    carries one.
    """
