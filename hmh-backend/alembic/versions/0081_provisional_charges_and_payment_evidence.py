"""Provisional charges, and payment evidence on an imported document.

Revision ID: 0081
Revises: 0080
Create Date: 2026-10-29

Two gaps that both lead to money being recorded wrongly.

1. A pro-forma invoice had nowhere to live. It is a request for payment
   before supply — not a liability — but it prints "Invoice" across the top
   and looks exactly like one, so without a home of its own it either became
   an Accounts Payable entry that is not owed, or it was discarded and the
   supplier's request vanished. `provisional_charges` holds it: visible,
   searchable, linked to its order and quotation, reported separately from
   Accounts Payable, and marked INVOICED against the tax invoice that
   eventually supersedes it so the purchase is never counted twice.

2. Documents arrive stamped PAID. The stamp is a claim, not a bank record,
   and nothing in the system could carry it, so the information was simply
   lost. Two columns on ai_import_documents record it as evidence awaiting
   verification. They never affect payment status, which stays derived from
   Payment rows.

Purely additive: one new table, one new enum type, two nullable-or-defaulted
columns. No existing row changes and no existing query behaves differently.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # create_type=False on the model, so the type is created here. IF NOT
    # EXISTS because an environment may already have been patched by hand.
    conn.exec_driver_sql(
        "DO $$ BEGIN "
        "CREATE TYPE provisional_charge_status_enum AS ENUM "
        "('PENDING', 'INVOICED', 'CANCELLED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )

    op.create_table(
        "provisional_charges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(100), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("quotation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("quotations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("subtotal_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("vat_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING", "INVOICED", "CANCELLED",
                name="provisional_charge_status_enum", create_type=False,
            ),
            nullable=False, server_default="PENDING",
        ),
        sa.Column("settled_by_invoice_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payment_evidence_detected", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("payment_evidence_note", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        # The same pro-forma number from the same supplier is the same request
        # for payment, however many times it is scanned. Enforced here rather
        # than in whichever code path happens to be inserting.
        sa.UniqueConstraint("supplier_id", "reference",
                            name="uq_provisional_charge_supplier_reference"),
    )
    op.create_index("ix_provisional_charges_reference", "provisional_charges", ["reference"])
    op.create_index("ix_provisional_charges_supplier_id", "provisional_charges", ["supplier_id"])
    op.create_index("ix_provisional_charges_project_id", "provisional_charges", ["project_id"])
    op.create_index("ix_provisional_charges_status", "provisional_charges", ["status"])
    op.create_index("ix_provisional_charges_purchase_order_id",
                    "provisional_charges", ["purchase_order_id"])

    op.add_column(
        "ai_import_documents",
        sa.Column("payment_evidence_detected", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )
    op.add_column(
        "ai_import_documents",
        sa.Column("payment_evidence_note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_import_documents", "payment_evidence_note")
    op.drop_column("ai_import_documents", "payment_evidence_detected")
    op.drop_index("ix_provisional_charges_purchase_order_id", table_name="provisional_charges")
    op.drop_index("ix_provisional_charges_status", table_name="provisional_charges")
    op.drop_index("ix_provisional_charges_project_id", table_name="provisional_charges")
    op.drop_index("ix_provisional_charges_supplier_id", table_name="provisional_charges")
    op.drop_index("ix_provisional_charges_reference", table_name="provisional_charges")
    op.drop_table("provisional_charges")
    op.execute("DROP TYPE IF EXISTS provisional_charge_status_enum")
