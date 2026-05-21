"""LotType model — Phase 3D.

A LotType is a project-level master definition for a category of lots/units.
It links to a BOQ template and enables bulk propagation of BOQ changes to all
lots assigned to this type.

Examples: "Type A House", "2BR Duplex", "Corner Unit", "Garage Unit"
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin


class LotType(TimestampMixin, Base):
    __tablename__ = "lot_types"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
        # unique within project enforced by DB partial unique index
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Default BOQ template — the source used for propagation.
    # SET NULL if the template is deleted; propagation will then raise
    # a clear error rather than silently doing nothing.
    default_template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("boq_headers.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project")  # type: ignore[name-defined]
    lots: Mapped[list["Lot"]] = relationship("Lot", back_populates="lot_type")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return f"<LotType {self.name!r} project={self.project_id}>"
