"""
Models for emails received at the procurement Gmail inbox via IMAP.

IncomingEmail        — one row per fetched email message
IncomingEmailAttachment — one row per attachment found in that email
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class IncomingEmail(Base):
    __tablename__ = "incoming_emails"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # IMAP message-id header — used to prevent duplicate ingestion
    message_id: Mapped[Optional[str]] = mapped_column(String(500), unique=True, index=True)

    from_email: Mapped[str]           = mapped_column(String(255), nullable=False)
    subject:    Mapped[Optional[str]] = mapped_column(Text)
    body_snippet: Mapped[Optional[str]] = mapped_column(Text)

    received_at:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    has_attachments: Mapped[bool]              = mapped_column(Boolean, default=False)

    # UNPROCESSED | PROCESSED | IGNORED
    processed_status: Mapped[str] = mapped_column(String(50), default="UNPROCESSED", index=True)

    # Matched PO if auto-detected
    matched_po_number: Mapped[Optional[str]] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    attachments: Mapped[list["IncomingEmailAttachment"]] = relationship(
        back_populates="email", cascade="all, delete-orphan"
    )


class IncomingEmailAttachment(Base):
    __tablename__ = "incoming_email_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    incoming_email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incoming_emails.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    filename:     Mapped[str]           = mapped_column(String(500), nullable=False)
    file_path:    Mapped[str]           = mapped_column(String(1000), nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(200))

    # INVOICE | DELIVERY_NOTE | QUOTE | OTHER
    detected_type: Mapped[str] = mapped_column(String(50), default="OTHER", index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    email: Mapped["IncomingEmail"] = relationship(back_populates="attachments")
