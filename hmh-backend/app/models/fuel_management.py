"""Fuel ordering, stock movement, issue, and reconciliation models."""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TimestampMixin


class FuelTypeDefinition(TimestampMixin, Base):
    __tablename__ = "fuel_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class FuelStorageLocation(TimestampMixin, Base):
    __tablename__ = "fuel_storage_locations"
    __table_args__ = (
        UniqueConstraint("project_id", "site_id", "name", name="uq_fuel_storage_project_site_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    site_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fuel_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fuel_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    location_type: Mapped[str] = mapped_column(String(30), nullable=False, default="TANK")
    capacity_litres: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    low_stock_threshold_litres: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Phase 8: set automatically the first time this storage location has
    # trustworthy evidence behind its stock — a VERIFIED delivery or a
    # controlled OPENING adjustment. Never a bare manual toggle.
    cutover_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cutover_confirmed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class FuelOrder(TimestampMixin, Base):
    __tablename__ = "fuel_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fuel_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fuel_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    storage_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fuel_storage_locations.id", ondelete="SET NULL"), nullable=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    request_date: Mapped[date] = mapped_column(Date, nullable=False)
    requested_litres: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    expected_delivery_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    delivery_location: Mapped[str] = mapped_column(String(300), nullable=False)
    purpose: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    intended_use: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    destination_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    vehicle_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    equipment_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feasibility_status: Mapped[str] = mapped_column(String(30), nullable=False, default="NOT_EVALUATED")
    feasibility_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estimated_remaining_litres: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    feasibility_override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feasibility_override_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    feasibility_override_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT", index=True)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    supplier_reference: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    purchase_order_reference: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ordered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class FuelIssue(TimestampMixin, Base):
    __tablename__ = "fuel_issues"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issue_number: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True
    )
    storage_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fuel_storage_locations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    fuel_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fuel_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    vehicle_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    destination_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    equipment_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    litres: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    odometer_reading: Mapped[Optional[float]] = mapped_column(Numeric(12, 1), nullable=True)
    hour_meter_reading: Mapped[Optional[float]] = mapped_column(Numeric(12, 1), nullable=True)
    issued_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    received_by: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    purpose: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    distance_since_previous_km: Mapped[Optional[float]] = mapped_column(Numeric(12, 1), nullable=True)
    litres_per_100km: Mapped[Optional[float]] = mapped_column(Numeric(10, 3), nullable=True)
    operating_hours_since_previous: Mapped[Optional[float]] = mapped_column(Numeric(12, 1), nullable=True)
    litres_per_hour: Mapped[Optional[float]] = mapped_column(Numeric(10, 3), nullable=True)
    anomaly_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    anomaly_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reading_source: Mapped[str] = mapped_column(String(40), nullable=False, default="MANUAL")
    tracker_provider: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tracker_reading_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_remaining_litres: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    feasibility_status: Mapped[str] = mapped_column(String(30), nullable=False, default="NOT_EVALUATED")
    evidence_override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_override_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    evidence_override_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    feasibility_override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feasibility_override_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    feasibility_override_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_reversed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    reversed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reversed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reversal_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class FuelStockAdjustment(Base):
    __tablename__ = "fuel_stock_adjustments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True
    )
    storage_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fuel_storage_locations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    fuel_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fuel_types.id", ondelete="RESTRICT"), nullable=False
    )
    adjustment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    litres_delta: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    authorised_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reference_reconciliation_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FuelReconciliation(TimestampMixin, Base):
    __tablename__ = "fuel_reconciliations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reconciliation_number: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True
    )
    storage_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fuel_storage_locations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    fuel_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fuel_types.id", ondelete="RESTRICT"), nullable=False
    )
    reconciliation_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    calculated_balance_litres: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    physical_balance_litres: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    variance_litres: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    variance_pct: Mapped[Optional[float]] = mapped_column(Numeric(8, 3), nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="COMPLETED", index=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reconciled_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class FuelEquipmentProfile(TimestampMixin, Base):
    """Consumption configuration for non-vehicle destinations without duplicating Vehicle."""
    __tablename__ = "fuel_equipment_profiles"
    __table_args__ = (UniqueConstraint("project_id", "equipment_reference", name="uq_fuel_equipment_project_ref"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True)
    equipment_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    destination_type: Mapped[str] = mapped_column(String(30), nullable=False)
    expected_litres_per_hour: Mapped[Optional[float]] = mapped_column(Numeric(8, 3), nullable=True)
    tolerance_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=20)
    tank_capacity_litres: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    minimum_issue_interval_hours: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    hour_meter_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    override_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class FuelOrderHistory(Base):
    __tablename__ = "fuel_order_history"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fuel_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FuelIssueEvidence(Base):
    __tablename__ = "fuel_issue_evidence"
    __table_args__ = (UniqueConstraint("issue_id", "evidence_type", name="uq_fuel_issue_evidence_type"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fuel_issues.id", ondelete="CASCADE"), nullable=False, index=True)
    attachment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("attachments.id", ondelete="RESTRICT"), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FuelEmailLog(TimestampMixin, Base):
    __tablename__ = "fuel_email_logs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("fuel_orders.id", ondelete="CASCADE"), nullable=True, index=True)
    delivery_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("fuel_deliveries.id", ondelete="CASCADE"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    recipient_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
