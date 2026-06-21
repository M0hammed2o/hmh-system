"""Supplier model."""

import uuid
from typing import Optional

from sqlalchemy import Boolean, Enum, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin
from app.models.enums import PricingMethod


class Supplier(TimestampMixin, Base):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_person: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    whatsapp_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    vat_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_terms: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    customer_account_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # VAT configuration (Phase 1)
    vat_registered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    pricing_method: Mapped[PricingMethod] = mapped_column(
        Enum(PricingMethod, name="pricingmethod", create_type=False),
        nullable=False,
        default=PricingMethod.EX_VAT,
        server_default="EX_VAT",
    )
    default_vat_rate: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=15.0, server_default="15.00"
    )

    # Relationships
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(  # type: ignore[name-defined]
        "PurchaseOrder", back_populates="supplier"
    )
    invoices: Mapped[list["Invoice"]] = relationship(  # type: ignore[name-defined]
        "Invoice", back_populates="supplier"
    )

    def __repr__(self) -> str:
        return f"<Supplier {self.name}>"
