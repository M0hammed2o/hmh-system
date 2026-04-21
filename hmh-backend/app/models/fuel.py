"""Fuel tracking model.

Covers on-site equipment, generators, delivery vehicles, and general
transport. total_cost is GENERATED ALWAYS AS STORED in PostgreSQL —
SQLAlchemy declares it as Computed(persisted=True) so it is never
written by the application; the DB computes and stores it.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Computed, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TimestampMixin
from app.models.enums import FuelType, FuelUsageType


class FuelLog(TimestampMixin, Base):
    __tablename__ = "fuel_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Scope ────────────────────────────────────────────────────────────────
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Fuel detail ──────────────────────────────────────────────────────────
    fuel_type: Mapped[FuelType] = mapped_column(
        Enum(FuelType, name="fuel_type_enum", create_type=False),
        nullable=False,
        default=FuelType.DIESEL,
    )
    usage_type: Mapped[FuelUsageType] = mapped_column(
        Enum(FuelUsageType, name="fuel_usage_type_enum", create_type=False),
        nullable=False,
        default=FuelUsageType.EQUIPMENT,
    )
    # Vehicle plate / plant number / generator ID
    equipment_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    litres: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    cost_per_litre: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)

    # GENERATED ALWAYS AS STORED — never written by this application.
    # Computed(persisted=True) tells SQLAlchemy to exclude from INSERT/UPDATE.
    total_cost: Mapped[Optional[float]] = mapped_column(
        Numeric(14, 2),
        Computed(
            "CASE WHEN cost_per_litre IS NOT NULL "
            "THEN ROUND(litres * cost_per_litre, 2) ELSE NULL END",
            persisted=True,
        ),
        nullable=True,
    )

    # ── Accountability ───────────────────────────────────────────────────────
    fuelled_by: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    recorded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    fuel_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # ── Notes ────────────────────────────────────────────────────────────────
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<FuelLog {self.litres}L {self.fuel_type} proj={self.project_id}>"
