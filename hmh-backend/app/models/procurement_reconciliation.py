"""ProcurementReconciliation model — Phase 4."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin
from app.models.enums import ReconciliationStatus


class ProcurementReconciliation(TimestampMixin, Base):
    __tablename__ = "procurement_reconciliations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reconciliation_number: Mapped[str] = mapped_column(
        "reconciliation_number",
        index=True,
        unique=True,
        nullable=False,
    )
    status: Mapped[ReconciliationStatus] = mapped_column(
        Enum(ReconciliationStatus, name="reconciliationstatus", create_type=False),
        nullable=False,
        default=ReconciliationStatus.PENDING,
        index=True,
    )

    # Document links — all optional; at minimum purchase_order_id should be set
    purchase_order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    delivery_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deliveries.id", ondelete="SET NULL"),
        nullable=True,
    )
    quotation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotations.id", ondelete="SET NULL"),
        nullable=True,
    )
    material_request_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("material_requests.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Computed variance data stored as JSONB
    variance_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Review
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Audit
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    purchase_order: Mapped[Optional["PurchaseOrder"]] = relationship(  # type: ignore[name-defined]
        "PurchaseOrder", foreign_keys=[purchase_order_id]
    )
    invoice: Mapped[Optional["Invoice"]] = relationship(  # type: ignore[name-defined]
        "Invoice", foreign_keys=[invoice_id]
    )
    delivery: Mapped[Optional["Delivery"]] = relationship(  # type: ignore[name-defined]
        "Delivery", foreign_keys=[delivery_id]
    )
    quotation: Mapped[Optional["Quotation"]] = relationship(  # type: ignore[name-defined]
        "Quotation", foreign_keys=[quotation_id]
    )
    material_request: Mapped[Optional["MaterialRequest"]] = relationship(  # type: ignore[name-defined]
        "MaterialRequest", foreign_keys=[material_request_id]
    )

    def __repr__(self) -> str:
        return f"<ProcurementReconciliation {self.reconciliation_number} {self.status}>"
