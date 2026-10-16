"""
Payments made to mechanics and workshops for vehicle repairs.

This is a settlement record, not a second expense. The cost of a repair is
already recognised elsewhere — as VehicleCost rows, or as the repair's quoted
or invoiced amount — and nothing here adds to it. A row in this table says
"some of what we already owe on that repair has been paid", which is why the
amount payable is always derived from the repair rather than restated here:
a stored copy would be free to drift from the figure the books use.

It is deliberately separate from `payments`, which settles supplier invoices.
Routing repairs through that table would mean raising a supplier invoice for
every mechanic job, creating an expense the repair had already recorded.

Nothing is ever deleted. A payment entered in error is reversed, leaving both
the original and the reversal visible.
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date, DateTime, ForeignKey, Index, Numeric, String, Text, func, text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MechanicPayment(Base):
    """One payment, or part-payment, made to a mechanic for one repair."""

    __tablename__ = "mechanic_payments"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    repair_job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("repair_jobs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Where the mechanic is already a supplier, that link is kept so the
    # relationship, contact details and history stay in one place. External
    # one-off mechanics who are not suppliers are named instead — requiring a
    # supplier record for every roadside repair would be worse than a name.
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=True
    )
    mechanic_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Proof of payment, stored the way every other evidence upload is.
    proof_file_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # A controlled reversal instead of a delete: a payment that was recorded
    # and then undone is part of the history, and the audit trail has to be
    # able to show both halves.
    reversed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reversed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reversal_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    recorded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_mechanic_payments_repair", "repair_job_id", "payment_date"),
        Index("ix_mechanic_payments_supplier", "supplier_id"),
        # A double-tapped submit or a retried request must not record the same
        # payment twice. Scoped to live payments so a reversed one does not
        # block re-capturing it correctly, and only where a reference was
        # given — cash payments often have none, and blanks must not collide.
        Index(
            "uq_mechanic_payments_live_reference",
            "repair_job_id",
            text("lower(trim(payment_reference))"),
            unique=True,
            postgresql_where=text("payment_reference IS NOT NULL AND reversed_at IS NULL"),
        ),
    )

    @property
    def is_reversed(self) -> bool:
        return self.reversed_at is not None
