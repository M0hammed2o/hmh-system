"""MunicipalityInvoice + MunicipalityInvoiceItem models."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MunicipalityInvoice(Base):
    __tablename__ = "municipality_invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_number: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    cert_number:    Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    project_id:     Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    invoice_date: Mapped[date]           = mapped_column(Date, nullable=False)
    due_date:     Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    client_name:    Mapped[str]           = mapped_column(String(200), nullable=False, default="Ethekweni Municipality")
    client_vat_no:  Mapped[Optional[str]] = mapped_column(String(60),  nullable=True)
    client_address: Mapped[Optional[str]] = mapped_column(Text,        nullable=True)

    company_email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    project_description: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    contract_reference:  Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    subtotal:        Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    previously_paid: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    vat_rate:        Mapped[Decimal] = mapped_column(Numeric(5, 2),  nullable=False, default=Decimal("15.00"))
    vat_amount:      Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total_due:       Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    notes:          Mapped[Optional[str]] = mapped_column(Text,        nullable=True)
    bank_name:      Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    account_number: Mapped[Optional[str]] = mapped_column(String(60),  nullable=True)
    branch_name:    Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    branch_code:    Mapped[Optional[str]] = mapped_column(String(20),  nullable=True)

    status:     Mapped[str]           = mapped_column(String(20), nullable=False, default="DRAFT")
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    items: Mapped[list["MunicipalityInvoiceItem"]] = relationship(
        "MunicipalityInvoiceItem",
        back_populates="invoice",
        order_by="MunicipalityInvoiceItem.sort_order",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<MunicipalityInvoice {self.invoice_number} [{self.status}] R{self.total_due}>"


class MunicipalityInvoiceItem(Base):
    __tablename__ = "municipality_invoice_items"

    id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("municipality_invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sort_order:  Mapped[int]           = mapped_column(Integer, nullable=False, default=0)
    line_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    description: Mapped[str]           = mapped_column(Text, nullable=False)
    quantity:    Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 3), nullable=True)
    unit_price:  Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    total:       Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    disc_pct:    Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2),  nullable=True)
    comments:    Mapped[Optional[str]]     = mapped_column(Text, nullable=True)
    created_at:  Mapped[datetime]          = mapped_column(DateTime(timezone=True), nullable=False)

    invoice: Mapped["MunicipalityInvoice"] = relationship("MunicipalityInvoice", back_populates="items")
