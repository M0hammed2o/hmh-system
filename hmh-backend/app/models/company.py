"""Company model — main contractor/client linked to a project."""

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin


class Company(TimestampMixin, Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    registration_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    supplier_links: Mapped[list["CompanySupplierLink"]] = relationship(
        "CompanySupplierLink",
        foreign_keys="[CompanySupplierLink.company_id]",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<Company {self.name}>"


class CompanySupplierLink(Base):
    """Many-to-many link between a Company and its approved Suppliers."""
    __tablename__ = "company_supplier_links"
    __table_args__ = (
        UniqueConstraint("company_id", "supplier_id", name="uq_company_supplier_links"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    company: Mapped[Optional[object]] = relationship("Company", foreign_keys=[company_id], viewonly=True)
    supplier: Mapped[Optional[object]] = relationship("Supplier", foreign_keys=[supplier_id], viewonly=True)

    def __repr__(self) -> str:
        return f"<CompanySupplierLink co={self.company_id} sup={self.supplier_id}>"
