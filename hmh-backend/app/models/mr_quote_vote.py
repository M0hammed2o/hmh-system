"""Vote for an MRQuote item — same pattern as MRApproval for MR votes."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MRQuoteVote(Base):
    """Individual staff approval vote for a single quote.

    Each user may cast exactly one vote per quote (enforced by unique constraint).
    Three staff votes → quote status auto-set to APPROVED.
    PROCUREMENT_LEAD/OWNER override via /approve endpoint (is_override=True).
    """
    __tablename__ = "mr_quote_votes"
    __table_args__ = (
        UniqueConstraint("quote_id", "voted_by", name="uq_mr_quote_votes_quote_voter"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mr_quotes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    voted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    voted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<MRQuoteVote quote={self.quote_id} by={self.voted_by} override={self.is_override}>"
