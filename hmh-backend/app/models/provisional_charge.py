"""
Provisional charges — supplier money asked for, but not yet owed.

A pro-forma invoice is a request for payment before supply. It prints the
word "Invoice" across the top, usually carries an invoice number and a VAT
registration number, and frequently arrives stamped PAID. It is not a tax
invoice, and the business does not owe it: the liability comes into being
when the supplier issues the tax invoice for the goods actually supplied.

Booking a pro-forma into Accounts Payable therefore does two kinds of damage.
It overstates what is owed today, and it doubles the charge tomorrow when the
real invoice arrives for the same goods — which is not hypothetical: a real
batch of twenty HMH documents contained that pair three times over.

So pro-formas live here instead. They are stored, searchable, linked to the
order and the quotation they came from, and reported *separately* from
Accounts Payable. When the tax invoice arrives, the charge is marked INVOICED
and points at the invoice that superseded it, which is what stops the same
purchase being counted twice.

This table holds no balance of its own. It records what a supplier has asked
for; app.models.invoice.Invoice records what is owed.
"""

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import (
    Boolean, Date, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin
from app.models.enums import ProvisionalChargeStatus


class ProvisionalCharge(TimestampMixin, Base):
    """One pro-forma invoice or advance payment request from a supplier."""

    __tablename__ = "provisional_charges"
    __table_args__ = (
        # The same pro-forma number from the same supplier is the same
        # request for payment, however many times the paperwork is scanned.
        # This is the duplicate guard, enforced by the database rather than
        # by whichever code path happens to be creating the row.
        UniqueConstraint("supplier_id", "reference", name="uq_provisional_charge_supplier_reference"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # The supplier's own number for the document (QTE880114, P77120, …).
    reference: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )

    # ── What it relates to ────────────────────────────────────────────────────
    # Both optional: a pro-forma often arrives before anyone has raised an
    # order, and linking it to the wrong one is worse than leaving it loose.
    purchase_order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    quotation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    subtotal_amount: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    vat_amount: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    status: Mapped[ProvisionalChargeStatus] = mapped_column(
        Enum(ProvisionalChargeStatus, name="provisional_charge_status_enum", create_type=False),
        nullable=False,
        default=ProvisionalChargeStatus.PENDING,
        server_default="PENDING",
        index=True,
    )

    # Set when the supplier's tax invoice for the same purchase is recorded.
    # The pair (status=INVOICED, settled_by_invoice_id) is what proves the
    # charge was not counted twice.
    settled_by_invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # ── Payment evidence ──────────────────────────────────────────────────────
    # A PAID stamp on a pro-forma is a claim by whoever held the rubber stamp.
    # It is recorded as evidence requiring verification and never as a
    # reconciled payment: a real payment is a Payment row against an invoice.
    payment_evidence_detected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    payment_evidence_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    supplier = relationship("Supplier", foreign_keys=[supplier_id])
    purchase_order = relationship("PurchaseOrder", foreign_keys=[purchase_order_id])
    quotation = relationship("Quotation", foreign_keys=[quotation_id])
    settled_by_invoice = relationship("Invoice", foreign_keys=[settled_by_invoice_id])

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ProvisionalCharge {self.reference} {self.status.value} {self.total_amount}>"
