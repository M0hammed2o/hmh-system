"""
Models for document AI extraction, site delivery verification, and expense records.

Tables:
  document_extractions         — OCR/AI extraction results from PDFs and images
  delivery_verifications       — site staff delivery note verification workflow
  delivery_verification_items  — line items within a delivery verification
  expense_records              — operational expense invoices/receipts
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Numeric, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ── Document Extraction ───────────────────────────────────────────────────────

class DocumentExtraction(Base):
    """OCR/AI extraction result from a PDF or image file."""
    __tablename__ = "document_extractions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # What produced this extraction
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_id:   Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    file_path:   Mapped[str] = mapped_column(Text, nullable=False)

    # INVOICE | DELIVERY_NOTE | QUOTE | OTHER
    document_type: Mapped[str] = mapped_column(String(50), nullable=False, default="OTHER")

    # EXTRACTED | OCR_REQUIRED | OCR_NOT_AVAILABLE | FAILED | NEEDS_REVIEW
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="NEEDS_REVIEW", index=True)

    raw_text:               Mapped[Optional[str]] = mapped_column(Text)
    extracted_json:         Mapped[Optional[str]] = mapped_column(Text)       # JSON string
    manually_corrected_json: Mapped[Optional[str]] = mapped_column(Text)      # JSON string

    confidence_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))

    created_at:   Mapped[datetime]          = mapped_column(DateTime(timezone=True), nullable=False)
    corrected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    corrected_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


# ── Delivery Verification ─────────────────────────────────────────────────────

class DeliveryVerification(Base):
    """Site staff verification of a physical delivery against the PO and delivery note."""
    __tablename__ = "delivery_verifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Optional links to existing records
    delivery_note_id:  Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("deliveries.id", ondelete="SET NULL"), nullable=True)
    purchase_order_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True)
    extraction_id:     Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("document_extractions.id", ondelete="SET NULL"), nullable=True)

    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    lot_id:  Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("lots.id", ondelete="SET NULL"), nullable=True)

    received_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    verified_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # DRAFT | VERIFIED | MISMATCH | REJECTED
    verification_status: Mapped[str] = mapped_column(String(50), nullable=False, default="DRAFT", index=True)

    # Captured from the physical document
    supplier_name:        Mapped[Optional[str]] = mapped_column(String(255))
    delivery_note_number: Mapped[Optional[str]] = mapped_column(String(100))
    vehicle_reg:          Mapped[Optional[str]] = mapped_column(String(50))
    driver_name:          Mapped[Optional[str]] = mapped_column(String(255))
    notes:                Mapped[Optional[str]] = mapped_column(Text)

    # File paths
    photo_path:      Mapped[Optional[str]] = mapped_column(Text)   # uploaded delivery note photo
    signature_path:  Mapped[Optional[str]] = mapped_column(Text)
    signed_at:       Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    items: Mapped[list["DeliveryVerificationItem"]] = relationship(
        back_populates="verification", cascade="all, delete-orphan"
    )


class DeliveryVerificationItem(Base):
    __tablename__ = "delivery_verification_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    delivery_verification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("delivery_verifications.id", ondelete="CASCADE"),
        nullable=False,
    )

    description:          Mapped[str]              = mapped_column(Text, nullable=False)
    unit:                 Mapped[Optional[str]]    = mapped_column(String(50))
    expected_qty:         Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 3))
    ocr_qty:              Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 3))    # AI-extracted
    actual_received_qty:  Mapped[Decimal]           = mapped_column(Numeric(14, 3), nullable=False, default=0)
    accepted_qty:         Mapped[Decimal]           = mapped_column(Numeric(14, 3), nullable=False, default=0)
    rejected_qty:         Mapped[Decimal]           = mapped_column(Numeric(14, 3), nullable=False, default=0)
    mismatch_reason:      Mapped[Optional[str]]    = mapped_column(Text)
    matched_po_item_id:   Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_order_items.id", ondelete="SET NULL"), nullable=True)

    verification: Mapped["DeliveryVerification"] = relationship(back_populates="items")


# ── Expense Records ───────────────────────────────────────────────────────────

class ExpenseRecord(Base):
    """Operational expense — vehicle repair, tool, site cost — linked to invoice/receipt."""
    __tablename__ = "expense_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    site_id:    Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True)
    lot_id:     Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("lots.id", ondelete="SET NULL"), nullable=True)
    vehicle_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True)

    # VEHICLE_REPAIR | FUEL | TOOL_REPAIR | SITE_EXPENSE | OTHER
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="OTHER")

    supplier_name:  Mapped[str]              = mapped_column(String(255), nullable=False)
    invoice_number: Mapped[Optional[str]]    = mapped_column(String(100))
    amount:         Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    file_path:      Mapped[Optional[str]]    = mapped_column(Text)

    # UPLOADED | NEEDS_REVIEW | APPROVED | REJECTED | PAID
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="UPLOADED", index=True)

    uploaded_by: Mapped[uuid.UUID]          = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    signature_path: Mapped[Optional[str]] = mapped_column(Text)
    notes:          Mapped[Optional[str]] = mapped_column(Text)

    extraction_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("document_extractions.id", ondelete="SET NULL"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
