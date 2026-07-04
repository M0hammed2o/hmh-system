"""Vehicle, VehicleCost, RepairJob, FuelDelivery, and VehicleTransferRequest models."""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin
from app.models.enums import FuelType, VehicleCostType, VehicleStatus, VehicleType


class Vehicle(TimestampMixin, Base):
    __tablename__ = "vehicles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    registration: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    vehicle_type: Mapped[VehicleType] = mapped_column(
        Enum(VehicleType, name="vehicle_type_enum", create_type=True),
        nullable=False,
        default=VehicleType.OTHER,
    )
    status: Mapped[VehicleStatus] = mapped_column(
        Enum(VehicleStatus, name="vehicle_status_enum", create_type=True),
        nullable=False,
        default=VehicleStatus.ACTIVE,
    )
    assigned_project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assigned_site_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Identification
    vin_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    make: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Fuel / consumption
    fuel_type: Mapped[Optional[FuelType]] = mapped_column(
        Enum(FuelType, name="fuel_type_enum", create_type=False),
        nullable=True,
    )
    tank_capacity_l: Mapped[Optional[float]] = mapped_column(Numeric(8, 1), nullable=True)
    fuel_consumption_per_100km: Mapped[Optional[float]] = mapped_column(Numeric(6, 2), nullable=True)

    # Odometer / service
    current_odometer_km: Mapped[Optional[float]] = mapped_column(Numeric(10, 1), nullable=True)
    service_interval_km: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_service_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    next_service_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Hours tracking (for machines that run on hours, not km)
    uses_hours: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_hours_reading: Mapped[Optional[float]] = mapped_column(Numeric(10, 1), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    costs: Mapped[list["VehicleCost"]] = relationship(
        "VehicleCost", back_populates="vehicle", cascade="all, delete-orphan"
    )
    repair_jobs: Mapped[list["RepairJob"]] = relationship(
        "RepairJob", back_populates="vehicle", cascade="all, delete-orphan"
    )
    transfer_requests: Mapped[list["VehicleTransferRequest"]] = relationship(
        "VehicleTransferRequest", back_populates="vehicle", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Vehicle {self.registration} — {self.name}>"


class RepairJob(TimestampMixin, Base):
    __tablename__ = "repair_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    workshop_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    date_opened: Mapped[date] = mapped_column(Date, nullable=False)
    date_closed: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    odometer_at_repair: Mapped[Optional[float]] = mapped_column(Numeric(10, 1), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Quotation / approval workflow
    quote_amount: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    quote_file_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    invoice_amount: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    invoice_file_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    approval_stage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approval_1_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approval_1_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_2_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approval_2_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_3_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approval_3_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    vehicle: Mapped["Vehicle"] = relationship("Vehicle", back_populates="repair_jobs")
    costs: Mapped[list["VehicleCost"]] = relationship(
        "VehicleCost", back_populates="repair_job", cascade="all, delete-orphan"
    )
    material_requests: Mapped[list] = relationship(
        "MaterialRequest",
        back_populates="repair_job",
        foreign_keys="MaterialRequest.repair_job_id",
    )

    def __repr__(self) -> str:
        return f"<RepairJob {self.title!r} vehicle={self.vehicle_id} status={self.status}>"


class VehicleCost(Base):
    __tablename__ = "vehicle_costs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repair_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repair_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cost_type: Mapped[VehicleCostType] = mapped_column(
        Enum(VehicleCostType, name="vehicle_cost_type_enum", create_type=True),
        nullable=False,
    )
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    site_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
    )
    lot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lots.id", ondelete="SET NULL"),
        nullable=True,
    )
    proof_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    cost_date: Mapped[date] = mapped_column(Date, nullable=False)
    recorded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    vehicle: Mapped["Vehicle"] = relationship("Vehicle", back_populates="costs")
    repair_job: Mapped[Optional["RepairJob"]] = relationship("RepairJob", back_populates="costs")

    def __repr__(self) -> str:
        return f"<VehicleCost {self.cost_type} R{self.amount} vehicle={self.vehicle_id}>"


class FuelDelivery(TimestampMixin, Base):
    """Bulk fuel delivery to a site — tracked as a countdown tank balance."""

    __tablename__ = "fuel_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    fuel_type: Mapped[str] = mapped_column(String(20), nullable=False, default="DIESEL")
    litres_delivered: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    cost_per_litre: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    supplier_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    invoice_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<FuelDelivery {self.litres_delivered}L site={self.site_id}>"


class VehicleTransferRequest(TimestampMixin, Base):
    """Request to move a vehicle from one site to another — requires office approval."""

    __tablename__ = "vehicle_transfer_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_site_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
    )
    to_site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    requested_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    vehicle: Mapped["Vehicle"] = relationship("Vehicle", back_populates="transfer_requests")

    def __repr__(self) -> str:
        return f"<VehicleTransferRequest vehicle={self.vehicle_id} status={self.status}>"
