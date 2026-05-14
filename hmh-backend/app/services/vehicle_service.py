"""Vehicle and VehicleCost service."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.alert import SystemAlert
from app.models.enums import AlertSeverity, AlertStatus, AlertType, AuditAction, VehicleCostType
from app.models.vehicle import Vehicle, VehicleCost
from app.schemas.vehicle import VehicleCostCreate, VehicleCreate, VehicleUpdate
from app.services import audit_service


def list_vehicles(db: Session, project_id: Optional[uuid.UUID] = None) -> list[Vehicle]:
    q = db.query(Vehicle).filter(Vehicle.status != "RETIRED")
    if project_id:
        q = q.filter(Vehicle.assigned_project_id == project_id)
    return q.order_by(Vehicle.name).all()


def get_vehicle(db: Session, vehicle_id: uuid.UUID) -> Vehicle:
    v = db.get(Vehicle, vehicle_id)
    if not v:
        raise NotFoundError(f"Vehicle {vehicle_id} not found.")
    return v


def create_vehicle(db: Session, data: VehicleCreate, actor_id: Optional[uuid.UUID] = None) -> Vehicle:
    existing = db.query(Vehicle).filter(Vehicle.registration == data.registration.upper()).first()
    if existing:
        raise ConflictError(f"Vehicle with registration '{data.registration}' already exists.")

    now = datetime.now(timezone.utc)
    vehicle = Vehicle(
        registration=data.registration.upper(),
        name=data.name,
        vehicle_type=data.vehicle_type,
        status=data.status,
        assigned_project_id=data.assigned_project_id,
        assigned_site_id=data.assigned_site_id,
        last_service_date=data.last_service_date,
        next_service_date=data.next_service_date,
        notes=data.notes,
        created_by=actor_id,
        created_at=now,
        updated_at=now,
    )
    db.add(vehicle)
    db.flush()

    audit_service.write_event(
        db,
        action=AuditAction.CREATE,
        entity_type="vehicle",
        actor_id=actor_id,
        entity_id=vehicle.id,
        after_value={"registration": vehicle.registration, "name": vehicle.name},
    )

    db.commit()
    db.refresh(vehicle)
    return vehicle


def update_vehicle(db: Session, vehicle_id: uuid.UUID, data: VehicleUpdate, actor_id: Optional[uuid.UUID] = None) -> Vehicle:
    vehicle = get_vehicle(db, vehicle_id)

    before = {"status": vehicle.status.value if vehicle.status else None, "name": vehicle.name}

    if data.name is not None:
        vehicle.name = data.name
    if data.vehicle_type is not None:
        vehicle.vehicle_type = data.vehicle_type
    if data.status is not None:
        vehicle.status = data.status
    if data.assigned_project_id is not None:
        vehicle.assigned_project_id = data.assigned_project_id
    if data.assigned_site_id is not None:
        vehicle.assigned_site_id = data.assigned_site_id
    if data.last_service_date is not None:
        vehicle.last_service_date = data.last_service_date
    if data.next_service_date is not None:
        vehicle.next_service_date = data.next_service_date
    if data.notes is not None:
        vehicle.notes = data.notes

    audit_service.write_event(
        db,
        action=AuditAction.UPDATE,
        entity_type="vehicle",
        actor_id=actor_id,
        entity_id=vehicle.id,
        before_value=before,
        after_value={"status": vehicle.status.value if vehicle.status else None, "name": vehicle.name},
    )

    db.commit()
    db.refresh(vehicle)
    return vehicle


def log_cost(
    db: Session,
    vehicle_id: uuid.UUID,
    data: VehicleCostCreate,
    actor_id: Optional[uuid.UUID] = None,
) -> VehicleCost:
    vehicle = get_vehicle(db, vehicle_id)

    now = datetime.now(timezone.utc)
    cost = VehicleCost(
        vehicle_id=vehicle_id,
        cost_type=data.cost_type,
        amount=data.amount,
        description=data.description,
        project_id=data.project_id,
        site_id=data.site_id,
        lot_id=data.lot_id,
        proof_image_url=data.proof_image_url,
        cost_date=data.cost_date,
        recorded_by=actor_id,
        notes=data.notes,
        created_at=now,
    )
    db.add(cost)

    # Alert owner for repairs
    if data.cost_type in (VehicleCostType.REPAIR, VehicleCostType.TYRE):
        alert = SystemAlert(
            project_id=data.project_id,
            site_id=data.site_id,
            reference_type="vehicle_cost",
            alert_type=AlertType.VEHICLE_REPAIR_LOGGED,
            severity=AlertSeverity.MEDIUM,
            title=f"Vehicle repair logged: {vehicle.registration}",
            message=(
                f"{vehicle.name} ({vehicle.registration}): {data.cost_type.value} "
                f"— R{data.amount:.2f}. {data.description or ''}"
            ),
            status=AlertStatus.OPEN,
            notification_channel="in_app",
            created_at=now,
        )
        db.add(alert)

    audit_service.write_event(
        db,
        action=AuditAction.CREATE,
        entity_type="vehicle_cost",
        actor_id=actor_id,
        entity_id=vehicle_id,
        after_value={
            "vehicle_registration": vehicle.registration,
            "cost_type": data.cost_type.value,
            "amount": float(data.amount),
        },
    )

    db.commit()
    db.refresh(cost)
    return cost


def list_costs(db: Session, vehicle_id: uuid.UUID) -> list[VehicleCost]:
    get_vehicle(db, vehicle_id)
    return (
        db.query(VehicleCost)
        .filter(VehicleCost.vehicle_id == vehicle_id)
        .order_by(VehicleCost.cost_date.desc())
        .all()
    )
