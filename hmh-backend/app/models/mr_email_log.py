"""
Email log for Material Request approval emails sent to preferred suppliers.
Separate from PoEmailLog (which requires purchase_order_id NOT NULL).
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MREmailLog(Base):
    __tablename__ = "mr_email_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    material_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("material_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
    )
    sent_to_email:  Mapped[str]           = mapped_column(String(255), nullable=False)
    email_subject:  Mapped[Optional[str]] = mapped_column(String(255))
    email_body:     Mapped[Optional[str]] = mapped_column(Text)

    # SENT | MOCK_SENT | FAILED
    status:         Mapped[str]           = mapped_column(String(50), nullable=False, index=True)
    error_message:  Mapped[Optional[str]] = mapped_column(Text)

    sent_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    sent_at:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime]           = mapped_column(DateTime(timezone=True), nullable=False)
