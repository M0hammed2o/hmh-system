"""Quotation model — header-level supplier quotation."""

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin
from app.models.enums import QuotationStatus


class Quotation(TimestampMixin, Base):
    __tablename__ = "quotations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    quote_number: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    material_request_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("material_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[QuotationStatus] = mapped_column(
        Enum(QuotationStatus, name="quotationstatus", create_type=False),
        nullable=False,
        default=QuotationStatus.DRAFT,
        server_default="DRAFT",
        index=True,
    )
    quote_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    net_amount: Mapped[float] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    vat_amount: Mapped[float] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    gross_amount: Mapped[float] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    vat_rate_used: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=15.0, server_default="15.00"
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    supplier = relationship("Supplier", foreign_keys=[supplier_id])
    purchase_orders = relationship("PurchaseOrder", back_populates="quotation")

    def __repr__(self) -> str:
        return f"<Quotation {self.quote_number} status={self.status.value}>"
