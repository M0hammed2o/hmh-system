"""Business rules for the standalone Fuel Management ledger."""

import csv
import io
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, InvalidStateError, NotFoundError, ValidationError
from app.models.alert import SystemAlert
from app.models.enums import AlertSeverity, AlertStatus, AlertType, AuditAction
from app.models.fuel_management import (
    FuelEquipmentProfile, FuelIssue, FuelOrder, FuelOrderHistory, FuelReconciliation,
    FuelStockAdjustment, FuelStorageLocation, FuelTypeDefinition,
)
from app.models.delivery import Delivery, DeliveryItem
from app.models.material_request import MaterialRequest
from app.models.project import Project
from app.models.purchase_order import PurchaseOrder
from app.models.site import Site
from app.models.supplier import Supplier
from app.models.vehicle import FuelDelivery, Vehicle
from app.schemas.fuel_management import (
    FuelAdjustmentCreate, FuelDeliveryCreate, FuelDeliveryFromProcurementCreate, FuelIssueCreate,
    FuelOrderCreate, FuelOrderUpdate, FuelReconciliationCreate, FuelStorageCreate, FuelTransition,
)
from app.services import audit_service, fuel_email_service, notification_service

log = logging.getLogger(__name__)

ORDER_TRANSITIONS = {
    "DRAFT": {"SUBMITTED", "CANCELLED"},
    "SUBMITTED": {"APPROVED", "REJECTED", "CANCELLED"},
    "APPROVED": {"ORDERED", "CANCELLED"},
    "ORDERED": {"PARTIALLY_DELIVERED", "DELIVERED", "CANCELLED"},
    "PARTIALLY_DELIVERED": {"DELIVERED", "CANCELLED"},
    "DELIVERED": {"CLOSED"},
    "CLOSED": set(), "REJECTED": set(), "CANCELLED": set(),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _number(prefix: str) -> str:
    return f"{prefix}-{_now().year}-{uuid.uuid4().hex[:8].upper()}"


def _get(db: Session, model, object_id: uuid.UUID, label: str):
    obj = db.get(model, object_id)
    if not obj:
        raise NotFoundError(f"{label} {object_id} not found.")
    return obj


def _audit(db: Session, actor_id, action, entity_type, entity_id, *, before=None, after=None, notes=None):
    audit_service.write_event(
        db, action, entity_type, actor_id=actor_id, entity_id=entity_id,
        before_value=before, after_value=after, notes=notes,
    )


def _notify(db: Session, *, alert_type: AlertType, severity: AlertSeverity, title: str,
            message: str, project_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID):
    """Queue notifications in a savepoint so failure never poisons the fuel transaction."""
    try:
        with db.begin_nested():
            alert = SystemAlert(
                project_id=project_id, reference_type=entity_type,
                reference_id=entity_id, alert_type=alert_type, severity=severity,
                title=title, message=message, status=AlertStatus.OPEN,
                notification_channel="in_app", created_at=_now(),
            )
            db.add(alert)
            db.flush()
            notification_service.enqueue_for_alert(db, alert, entity_type=entity_type, entity_id=entity_id)
    except Exception:
        log.exception("Non-blocking fuel notification failed for %s %s", entity_type, entity_id)


def list_fuel_types(db: Session, active_only: bool = True):
    q = db.query(FuelTypeDefinition)
    if active_only:
        q = q.filter(FuelTypeDefinition.is_active.is_(True))
    return q.order_by(FuelTypeDefinition.name).all()


def _validate_scope(db: Session, project_id: uuid.UUID, site_id: Optional[uuid.UUID]):
    _get(db, Project, project_id, "Project")
    if site_id:
        site = _get(db, Site, site_id, "Site")
        if site.project_id != project_id:
            raise ValidationError("Site does not belong to the selected project.")


def create_storage(db: Session, project_id: uuid.UUID, data: FuelStorageCreate, actor_id: uuid.UUID):
    _validate_scope(db, project_id, data.site_id)
    fuel_type = _get(db, FuelTypeDefinition, data.fuel_type_id, "Fuel type")
    if not fuel_type.is_active:
        raise ValidationError("Fuel type is inactive.")
    storage = FuelStorageLocation(
        project_id=project_id, site_id=data.site_id, fuel_type_id=data.fuel_type_id,
        name=data.name.strip(), location_type=data.location_type.upper(),
        capacity_litres=data.capacity_litres,
        low_stock_threshold_litres=data.low_stock_threshold_litres,
        notes=data.notes, is_active=True,
    )
    db.add(storage)
    db.flush()
    if data.opening_stock_litres:
        db.add(FuelStockAdjustment(
            project_id=project_id, site_id=data.site_id, storage_location_id=storage.id,
            fuel_type_id=data.fuel_type_id, adjustment_type="OPENING",
            litres_delta=data.opening_stock_litres, reason="Opening stock on storage creation",
            authorised_by=actor_id, created_at=_now(),
        ))
    _audit(db, actor_id, AuditAction.CREATE, "FUEL_STORAGE", storage.id,
           after={"name": storage.name, "opening_stock_litres": data.opening_stock_litres})
    db.commit(); db.refresh(storage)
    return storage


def list_storage(db: Session, project_id: uuid.UUID):
    return db.query(FuelStorageLocation).filter(
        FuelStorageLocation.project_id == project_id,
        FuelStorageLocation.is_active.is_(True),
    ).order_by(FuelStorageLocation.name).all()


def stock_balance(db: Session, storage_id: uuid.UUID, *, as_of: Optional[datetime] = None) -> float:
    storage = _get(db, FuelStorageLocation, storage_id, "Fuel storage")
    delivered_q = db.query(func.coalesce(func.sum(FuelDelivery.confirmed_litres), 0)).filter(
        FuelDelivery.storage_location_id == storage.id,
        FuelDelivery.verification_status == "VERIFIED",
    )
    issued_q = db.query(func.coalesce(func.sum(FuelIssue.litres), 0)).filter(
        FuelIssue.storage_location_id == storage.id,
        FuelIssue.is_reversed.is_(False),
    )
    adjusted_q = db.query(func.coalesce(func.sum(FuelStockAdjustment.litres_delta), 0)).filter(
        FuelStockAdjustment.storage_location_id == storage.id,
    )
    if as_of:
        delivered_q = delivered_q.filter(FuelDelivery.delivered_at <= as_of)
        issued_q = issued_q.filter(FuelIssue.issued_at <= as_of)
        adjusted_q = adjusted_q.filter(FuelStockAdjustment.created_at <= as_of)
    return round(float(delivered_q.scalar() or 0) - float(issued_q.scalar() or 0) + float(adjusted_q.scalar() or 0), 2)


def _validate_order_links(db: Session, project_id: uuid.UUID, data):
    _validate_scope(db, project_id, getattr(data, "site_id", None))
    ft = _get(db, FuelTypeDefinition, data.fuel_type_id, "Fuel type")
    if not ft.is_active:
        raise ValidationError("Fuel type is inactive.")
    if getattr(data, "supplier_id", None):
        supplier = _get(db, Supplier, data.supplier_id, "Supplier")
        if not supplier.is_active:
            raise ValidationError("Supplier is inactive.")
    if getattr(data, "storage_location_id", None):
        storage = _get(db, FuelStorageLocation, data.storage_location_id, "Fuel storage")
        if storage.project_id != project_id or storage.fuel_type_id != data.fuel_type_id:
            raise ValidationError("Fuel storage does not match the project and fuel type.")


def validate_request_destination(db: Session, project_id: uuid.UUID, data: FuelOrderCreate) -> None:
    """Validate a submitted site's destination and its project ownership."""
    destination = (data.destination_type or "").upper()
    allowed = {"VEHICLE", "SITE_STORAGE", "GENERATOR", "PLANT", "OTHER_EQUIPMENT"}
    if destination not in allowed:
        raise ValidationError("Invalid site fuel request destination type.")
    if destination == "VEHICLE":
        if not data.vehicle_id:
            raise ValidationError("Choose the destination vehicle.")
        vehicle = _get(db, Vehicle, data.vehicle_id, "Vehicle")
        if vehicle.assigned_project_id != project_id:
            raise ValidationError("Vehicle does not belong to the selected project.")
        return
    if destination == "SITE_STORAGE":
        if not data.storage_location_id:
            raise ValidationError("Choose the destination site storage location.")
        storage = _get(db, FuelStorageLocation, data.storage_location_id, "Fuel storage")
        if storage.project_id != project_id:
            raise ValidationError("Fuel storage belongs to a different project.")
        return
    if not data.equipment_reference or not data.equipment_reference.strip():
        raise ValidationError("Choose the destination equipment profile.")
    profile = db.query(FuelEquipmentProfile).filter(
        FuelEquipmentProfile.project_id == project_id,
        FuelEquipmentProfile.equipment_reference == data.equipment_reference.strip(),
        FuelEquipmentProfile.destination_type == destination,
        FuelEquipmentProfile.is_active.is_(True),
    ).first()
    if not profile:
        raise ValidationError("The selected equipment profile does not belong to this project or destination type.")


def _evaluate_order_feasibility(db: Session, order: FuelOrder) -> None:
    """Advisory refill estimate from the latest issue and configured asset profile."""
    order.feasibility_status = "NOT_EVALUATED"
    order.feasibility_message = None
    if order.vehicle_id:
        vehicle = _get(db, Vehicle, order.vehicle_id, "Vehicle")
        previous = db.query(FuelIssue).filter(FuelIssue.vehicle_id == vehicle.id,
            FuelIssue.is_reversed.is_(False)).order_by(FuelIssue.issued_at.desc()).first()
        if not previous:
            order.feasibility_status = "INSUFFICIENT_HISTORY"; return
        distance = None
        if vehicle.current_odometer_km is not None and previous.odometer_reading is not None:
            distance = max(float(vehicle.current_odometer_km) - float(previous.odometer_reading), 0)
        consumed = distance * float(vehicle.fuel_consumption_per_100km or 0) / 100 if distance is not None else 0
        remaining = max(float(previous.litres) - consumed, 0)
        order.estimated_remaining_litres = round(remaining, 2)
        allowed = max(float(vehicle.tank_capacity_l or 0) - remaining, 0) if vehicle.tank_capacity_l else None
        elapsed = (_now() - previous.issued_at).total_seconds() / 3600
        warning = ((allowed is not None and float(order.requested_litres) > allowed * (1 + float(vehicle.fuel_tolerance_pct or 0) / 100))
                   or elapsed < float(vehicle.fuel_minimum_issue_interval_hours or 0))
        order.feasibility_status = "OVERRIDE_REQUIRED" if warning and vehicle.fuel_override_required else ("REVIEW" if warning else "OK")
        if warning:
            order.feasibility_message = "Requested refill is outside the configured capacity, consumption or elapsed-time tolerance; review required."
    elif order.equipment_reference:
        profile = db.query(FuelEquipmentProfile).filter(
            FuelEquipmentProfile.project_id == order.project_id,
            FuelEquipmentProfile.equipment_reference == order.equipment_reference,
            FuelEquipmentProfile.is_active.is_(True)).first()
        if not profile:
            order.feasibility_status = "PROFILE_REQUIRED"; return
        previous = db.query(FuelIssue).filter(FuelIssue.project_id == order.project_id,
            FuelIssue.equipment_reference == order.equipment_reference,
            FuelIssue.is_reversed.is_(False)).order_by(FuelIssue.issued_at.desc()).first()
        if not previous:
            order.feasibility_status = "INSUFFICIENT_HISTORY"; return
        elapsed = (_now() - previous.issued_at).total_seconds() / 3600
        remaining = max(float(previous.litres) - elapsed * float(profile.expected_litres_per_hour or 0), 0)
        order.estimated_remaining_litres = round(remaining, 2)
        allowed = max(float(profile.tank_capacity_litres or 0) - remaining, 0) if profile.tank_capacity_litres else None
        warning = ((allowed is not None and float(order.requested_litres) > allowed * (1 + float(profile.tolerance_pct) / 100))
                   or elapsed < float(profile.minimum_issue_interval_hours))
        order.feasibility_status = "OVERRIDE_REQUIRED" if warning and profile.override_required else ("REVIEW" if warning else "OK")
        if warning:
            order.feasibility_message = "Requested refill is outside the configured capacity, consumption or elapsed-time tolerance; review required."


def list_equipment_profiles(db: Session, project_id: uuid.UUID):
    return db.query(FuelEquipmentProfile).filter(FuelEquipmentProfile.project_id == project_id,
        FuelEquipmentProfile.is_active.is_(True)).order_by(FuelEquipmentProfile.equipment_reference).all()


def upsert_equipment_profile(db: Session, project_id: uuid.UUID, data, actor_id: uuid.UUID):
    _validate_scope(db, project_id, data.site_id)
    profile = db.query(FuelEquipmentProfile).filter(FuelEquipmentProfile.project_id == project_id,
        FuelEquipmentProfile.equipment_reference == data.equipment_reference.strip()).first()
    values = data.model_dump()
    values["equipment_reference"] = data.equipment_reference.strip()
    values["destination_type"] = data.destination_type.upper()
    is_new = profile is None
    if profile:
        for key, value in values.items(): setattr(profile, key, value)
    else:
        profile = FuelEquipmentProfile(project_id=project_id, **values); db.add(profile)
    db.flush(); _audit(db, actor_id, AuditAction.CREATE if is_new else AuditAction.UPDATE,
        "FUEL_EQUIPMENT_PROFILE", profile.id, after=data.model_dump(mode="json"))
    db.commit(); db.refresh(profile); return profile


def create_order(db: Session, project_id: uuid.UUID, data: FuelOrderCreate, actor_id: uuid.UUID):
    _validate_order_links(db, project_id, data)
    order = FuelOrder(
        order_number=_number("FUR"), project_id=project_id, site_id=data.site_id,
        fuel_type_id=data.fuel_type_id, supplier_id=data.supplier_id,
        storage_location_id=data.storage_location_id, requested_by=actor_id,
        request_date=data.request_date, requested_litres=data.requested_litres,
        expected_delivery_date=data.expected_delivery_date,
        delivery_location=data.delivery_location.strip(), purpose=data.purpose,
        intended_use=data.intended_use or data.purpose,
        destination_type=data.destination_type.upper() if data.destination_type else None,
        vehicle_id=data.vehicle_id, equipment_reference=data.equipment_reference,
        notes=data.notes, status="DRAFT",
    )
    _evaluate_order_feasibility(db, order)
    db.add(order); db.flush()
    db.add(FuelOrderHistory(order_id=order.id, from_status=None, to_status="DRAFT",
                            actor_id=actor_id, reason="Request created", created_at=_now()))
    _audit(db, actor_id, AuditAction.CREATE, "FUEL_ORDER", order.id,
           after={"order_number": order.order_number, "litres": float(order.requested_litres)})
    db.commit(); db.refresh(order)
    if data.submit_now:
        order = transition_order(db, order.id, "SUBMITTED", actor_id, FuelTransition())
    return order


def get_order(db: Session, order_id: uuid.UUID):
    order = _get(db, FuelOrder, order_id, "Fuel order")
    order.delivered_litres = verified_delivery_total(db, order.id)
    return order


def list_orders(db: Session, project_id: uuid.UUID, status: Optional[str] = None,
                requested_by: Optional[uuid.UUID] = None):
    q = db.query(FuelOrder).filter(FuelOrder.project_id == project_id)
    if status:
        q = q.filter(FuelOrder.status == status.upper())
    if requested_by:
        q = q.filter(FuelOrder.requested_by == requested_by)
    rows = q.order_by(FuelOrder.created_at.desc()).all()
    for row in rows:
        row.delivered_litres = verified_delivery_total(db, row.id)
    return rows


def update_order(db: Session, order_id: uuid.UUID, data: FuelOrderUpdate, actor_id: uuid.UUID):
    order = _get(db, FuelOrder, order_id, "Fuel order")
    if order.status != "DRAFT":
        raise InvalidStateError("Only a DRAFT fuel order can be edited.")
    before = {"requested_litres": float(order.requested_litres), "supplier_id": str(order.supplier_id) if order.supplier_id else None}
    for field in data.model_fields_set:
        setattr(order, field, getattr(data, field))
    _audit(db, actor_id, AuditAction.UPDATE, "FUEL_ORDER", order.id, before=before)
    db.commit(); db.refresh(order)
    return order


def transition_order(db: Session, order_id: uuid.UUID, target: str, actor_id: uuid.UUID,
                     data: FuelTransition):
    order = _get(db, FuelOrder, order_id, "Fuel order")
    target = target.upper()
    if target not in ORDER_TRANSITIONS.get(order.status, set()):
        raise InvalidStateError(f"Fuel order cannot move from {order.status} to {target}.")
    if target == "APPROVED" and order.requested_by == actor_id:
        raise ConflictError("A requester cannot approve their own fuel order.")
    if target == "APPROVED" and order.feasibility_status == "OVERRIDE_REQUIRED":
        if not data.override_reason:
            raise ValidationError("An authorised feasibility override reason is required before approval.")
        order.feasibility_override_reason = data.override_reason.strip()
        order.feasibility_override_by = actor_id
        order.feasibility_override_at = _now()
    if target in {"REJECTED", "CANCELLED"} and not data.reason:
        raise ValidationError(f"A reason is required to mark an order {target}.")
    if target == "ORDERED" and not (data.supplier_reference or order.supplier_reference):
        raise ValidationError("A supplier reference is required before marking the order ORDERED.")
    before = order.status; now = _now(); order.status = target
    if target == "SUBMITTED": order.submitted_at = now
    elif target == "APPROVED": order.approved_by, order.approved_at = actor_id, now
    elif target == "REJECTED":
        order.rejected_by, order.rejected_at, order.rejection_reason = actor_id, now, data.reason
    elif target == "ORDERED":
        order.ordered_at = now
        order.supplier_reference = data.supplier_reference or order.supplier_reference
        order.purchase_order_reference = data.purchase_order_reference or order.purchase_order_reference
    elif target == "CANCELLED": order.cancelled_at, order.cancellation_reason = now, data.reason
    elif target == "CLOSED": order.closed_at = now
    _audit(db, actor_id, AuditAction.UPDATE, "FUEL_ORDER", order.id,
           before={"status": before}, after={"status": target}, notes=data.reason)
    db.add(FuelOrderHistory(order_id=order.id, from_status=before, to_status=target,
                            actor_id=actor_id, reason=data.reason or data.override_reason,
                            created_at=now))
    if target == "SUBMITTED":
        _notify(db, alert_type=AlertType.REQUEST_PENDING_TOO_LONG, severity=AlertSeverity.MEDIUM,
                title="Fuel request awaiting approval", message=f"{order.order_number} requires approval.",
                project_id=order.project_id, entity_type="FUEL_ORDER", entity_id=order.id)
    db.commit(); db.refresh(order)
    if target in {"SUBMITTED", "APPROVED", "REJECTED", "ORDERED"}:
        fuel_email_service.queue_event(db, order, target)
    return order


def verified_delivery_total(db: Session, order_id: uuid.UUID) -> float:
    return float(db.query(func.coalesce(func.sum(FuelDelivery.confirmed_litres), 0)).filter(
        FuelDelivery.order_id == order_id, FuelDelivery.verification_status == "VERIFIED",
    ).scalar() or 0)


def recorded_delivery_total(db: Session, order_id: uuid.UUID) -> float:
    return float(db.query(func.coalesce(func.sum(FuelDelivery.confirmed_litres), 0)).filter(
        FuelDelivery.order_id == order_id, FuelDelivery.verification_status != "REJECTED",
    ).scalar() or 0)


def record_delivery(db: Session, order_id: uuid.UUID, data: FuelDeliveryCreate,
                    actor_id: uuid.UUID, allow_excess_permission: bool):
    order = _get(db, FuelOrder, order_id, "Fuel order")
    if order.status not in {"ORDERED", "PARTIALLY_DELIVERED"}:
        raise InvalidStateError("Deliveries can only be recorded against an ordered fuel request.")
    storage_id = data.storage_location_id or order.storage_location_id
    if not storage_id:
        raise ValidationError("A destination fuel storage location is required.")
    storage = _get(db, FuelStorageLocation, storage_id, "Fuel storage")
    if storage.project_id != order.project_id or storage.fuel_type_id != order.fuel_type_id:
        raise ValidationError("Delivery fuel type or storage location does not match the order.")
    site_id = order.site_id or storage.site_id
    if not site_id:
        raise ValidationError("The delivery must be associated with a site.")
    supplier_id = data.supplier_id or order.supplier_id
    if order.supplier_id and supplier_id != order.supplier_id:
        raise ValidationError("Delivery supplier does not match the order supplier.")
    confirmed = data.confirmed_litres or data.delivered_litres
    after_total = recorded_delivery_total(db, order.id) + confirmed
    excess = after_total > float(order.requested_litres) + 0.001
    if excess and not (data.allow_excess and allow_excess_permission):
        raise ConflictError("Delivery quantity would exceed the ordered litres.")
    calculated = None
    if data.opening_reading is not None:
        calculated = data.closing_reading - data.opening_reading
    variance = confirmed - (calculated if calculated is not None else data.delivered_litres)
    ft = _get(db, FuelTypeDefinition, order.fuel_type_id, "Fuel type")
    delivery = FuelDelivery(
        order_id=order.id, project_id=order.project_id, site_id=site_id,
        supplier_id=supplier_id, fuel_type_id=order.fuel_type_id, storage_location_id=storage.id,
        delivery_date=data.delivered_at.date(), delivered_at=data.delivered_at,
        delivery_note_number=data.delivery_note_number, fuel_type=ft.code[:20],
        litres_delivered=data.delivered_litres, opening_reading=data.opening_reading,
        closing_reading=data.closing_reading, calculated_received_litres=calculated,
        confirmed_litres=confirmed, variance_litres=variance,
        tanker_registration=data.tanker_registration, driver_details=data.driver_details,
        received_by=actor_id, recorded_by=actor_id, verification_status="PENDING",
        excess_override=excess, excess_override_reason=data.excess_reason if excess else None,
        excess_override_by=actor_id if excess else None, notes=data.notes,
    )
    db.add(delivery); db.flush()
    _audit(db, actor_id, AuditAction.CREATE, "FUEL_DELIVERY", delivery.id,
           after={"order_id": str(order.id), "confirmed_litres": confirmed})
    if excess:
        _audit(db, actor_id, AuditAction.OVERRUN_ACCEPTED, "FUEL_DELIVERY", delivery.id,
               before={"recorded_litres": after_total - confirmed,
                       "ordered_litres": float(order.requested_litres)},
               after={"recorded_litres": after_total,
                      "ordered_litres": float(order.requested_litres),
                      "excess_litres": round(after_total - float(order.requested_litres), 2)},
               notes=data.excess_reason)
    if abs(variance) > max(20, confirmed * .02):
        _notify(db, alert_type=AlertType.DELIVERY_DISCREPANCY, severity=AlertSeverity.HIGH,
                title="Fuel delivery variance", message=f"Delivery {data.delivery_note_number} variance is {variance:.2f} L.",
                project_id=order.project_id, entity_type="FUEL_DELIVERY", entity_id=delivery.id)
    db.commit(); db.refresh(delivery)
    return delivery


def receive_delivery_from_procurement(
    db: Session, data: FuelDeliveryFromProcurementCreate, actor_id: uuid.UUID,
):
    """Hand-off from a real procurement DeliveryItem into the Fuel Control
    layer (Phase 5). The item must trace back to a Delivery whose Purchase
    Order originated from a FUEL-category MaterialRequest — this is what
    keeps Fuel out of the BOQ/general-materials procurement pipeline while
    still using the exact same MR -> Quote -> PO -> Delivery machinery.

    Idempotent: the DB-level UNIQUE constraint on
    fuel_deliveries.procurement_delivery_item_id guarantees the same
    DeliveryItem can never be confirmed into stock twice. A retry or
    double-click after a first successful confirmation returns the
    existing FuelDelivery unchanged rather than erroring or double-counting.
    """
    existing = db.query(FuelDelivery).filter(
        FuelDelivery.procurement_delivery_item_id == data.delivery_item_id
    ).first()
    if existing:
        return existing

    delivery_item = _get(db, DeliveryItem, data.delivery_item_id, "Delivery item")
    delivery = _get(db, Delivery, delivery_item.delivery_id, "Delivery")
    if not delivery.purchase_order_id:
        raise ValidationError("This delivery is not linked to a purchase order and cannot be confirmed into Fuel stock.")
    po = _get(db, PurchaseOrder, delivery.purchase_order_id, "Purchase order")
    if not po.material_request_id:
        raise ValidationError("This delivery's purchase order is not linked to a material request.")
    mr = _get(db, MaterialRequest, po.material_request_id, "Material request")
    if mr.procurement_category != "FUEL":
        raise ValidationError("This delivery item did not originate from a Fuel material request.")

    storage = _get(db, FuelStorageLocation, data.storage_location_id, "Fuel storage")
    if storage.project_id != delivery.project_id:
        raise ValidationError("Storage location does not belong to the delivery's project.")
    ft = _get(db, FuelTypeDefinition, storage.fuel_type_id, "Fuel type")

    litres_delivered = float(delivery_item.quantity_received)
    calculated = None
    if data.opening_reading is not None:
        calculated = data.closing_reading - data.opening_reading
    confirmed = data.confirmed_litres
    supplier_variance = round(confirmed - litres_delivered, 2)
    meter_variance = round(confirmed - calculated, 2) if calculated is not None else None

    fuel_delivery = FuelDelivery(
        order_id=None, procurement_delivery_item_id=delivery_item.id,
        project_id=delivery.project_id, site_id=delivery.site_id,
        supplier_id=delivery.supplier_id, fuel_type_id=storage.fuel_type_id,
        storage_location_id=storage.id,
        delivery_date=data.delivered_at.date(), delivered_at=data.delivered_at,
        delivery_note_number=delivery.supplier_delivery_note_number, fuel_type=ft.code[:20],
        litres_delivered=litres_delivered, opening_reading=data.opening_reading,
        closing_reading=data.closing_reading, calculated_received_litres=calculated,
        confirmed_litres=confirmed, variance_litres=supplier_variance,
        supplier_variance_litres=supplier_variance, meter_variance_litres=meter_variance,
        tanker_registration=data.tanker_registration, driver_details=data.driver_details,
        received_by=actor_id, recorded_by=actor_id, verification_status="VERIFIED",
        verified_by=actor_id, verified_at=_now(), notes=data.notes,
    )
    db.add(fuel_delivery)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.query(FuelDelivery).filter(
            FuelDelivery.procurement_delivery_item_id == data.delivery_item_id
        ).first()
        if existing:
            return existing
        raise

    _audit(db, actor_id, AuditAction.CREATE, "FUEL_DELIVERY", fuel_delivery.id,
           after={"delivery_item_id": str(delivery_item.id), "confirmed_litres": confirmed,
                  "supplier_variance_litres": supplier_variance, "meter_variance_litres": meter_variance})

    threshold = max(20, confirmed * .02)
    if abs(supplier_variance) > threshold:
        _notify(db, alert_type=AlertType.DELIVERY_DISCREPANCY, severity=AlertSeverity.HIGH,
                title="Fuel delivery supplier-quantity variance",
                message=f"Confirmed litres differ from the supplier-documented quantity by {supplier_variance:.2f} L.",
                project_id=delivery.project_id, entity_type="FUEL_DELIVERY", entity_id=fuel_delivery.id)
    if meter_variance is not None and abs(meter_variance) > threshold:
        _notify(db, alert_type=AlertType.DELIVERY_DISCREPANCY, severity=AlertSeverity.HIGH,
                title="Fuel delivery meter-reading variance",
                message=f"Confirmed litres differ from the tank meter reading by {meter_variance:.2f} L.",
                project_id=delivery.project_id, entity_type="FUEL_DELIVERY", entity_id=fuel_delivery.id)

    db.commit(); db.refresh(fuel_delivery)
    return fuel_delivery


def list_deliveries(db: Session, project_id: uuid.UUID):
    return db.query(FuelDelivery).filter(FuelDelivery.project_id == project_id).order_by(
        FuelDelivery.delivered_at.desc().nullslast(), FuelDelivery.created_at.desc()
    ).all()


def verify_delivery(db: Session, delivery_id: uuid.UUID, actor_id: uuid.UUID, approve: bool = True):
    delivery = _get(db, FuelDelivery, delivery_id, "Fuel delivery")
    if delivery.verification_status != "PENDING":
        raise InvalidStateError("Only a pending fuel delivery can be verified or rejected.")
    delivery.verification_status = "VERIFIED" if approve else "REJECTED"
    delivery.verified_by, delivery.verified_at = actor_id, _now()
    order = _get(db, FuelOrder, delivery.order_id, "Fuel order") if delivery.order_id else None
    if order and approve:
        db.flush()
        total = verified_delivery_total(db, order.id)
        previous_status = order.status
        next_status = "DELIVERED" if total >= float(order.requested_litres) else "PARTIALLY_DELIVERED"
        order.status = next_status
        if previous_status != next_status:
            db.add(FuelOrderHistory(
                order_id=order.id, from_status=previous_status, to_status=next_status,
                actor_id=actor_id, reason="Delivery verified", created_at=_now(),
            ))
    _audit(db, actor_id, AuditAction.APPROVE if approve else AuditAction.REJECT,
           "FUEL_DELIVERY", delivery.id, after={"verification_status": delivery.verification_status})
    db.commit(); db.refresh(delivery)
    if order and approve:
        fuel_email_service.queue_event(db, order, "DELIVERED", delivery_id=delivery.id)
    return delivery


def _hour_based_issue_metrics(
    litres: float, hour_meter_reading: Optional[float], prev: Optional[FuelIssue],
    expected_lph: float, tolerance_pct: float, tank_capacity: Optional[float],
    minimum_issue_interval_hours: float, issued_at: datetime, no_reading_message: str,
) -> tuple[Optional[float], Optional[float], Optional[float], list[str]]:
    """Shared L/hour anomaly check for any hour-metered destination — a Vehicle
    with uses_hours=True, or a non-Vehicle FuelEquipmentProfile. Returns
    (hours_delta, litres_per_hour, estimated_remaining, anomaly_reasons)."""
    reasons: list[str] = []
    hours_delta = lph = estimated_remaining = None
    if hour_meter_reading is None:
        reasons.append(no_reading_message)
    elif prev and prev.hour_meter_reading is not None:
        hours_delta = float(hour_meter_reading) - float(prev.hour_meter_reading)
        if hours_delta <= 0:
            raise ValidationError("Hour-meter reading must be greater than the previous reading.")
        lph = round(litres / hours_delta, 3)
        tolerance = float(tolerance_pct or 0) / 100
        estimated_remaining = max(float(prev.litres) - hours_delta * expected_lph, 0) if expected_lph else None
        if expected_lph and lph > expected_lph * (1 + tolerance):
            reasons.append(f"High consumption for review ({lph:.2f} L/hour)")
        if tank_capacity and estimated_remaining is not None and litres > (float(tank_capacity) - estimated_remaining) * (1 + tolerance):
            reasons.append("Refill exceeds configured estimated tank space")
        elapsed = (issued_at - prev.issued_at).total_seconds() / 3600
        if elapsed < float(minimum_issue_interval_hours or 0):
            reasons.append("Refill is sooner than the configured minimum interval")
    return hours_delta, lph, estimated_remaining, reasons


def create_issue(db: Session, project_id: uuid.UUID, data: FuelIssueCreate, actor_id: uuid.UUID,
                 *, evidence_types: Optional[set[str]] = None, can_override: bool = False,
                 commit: bool = True):
    _validate_scope(db, project_id, data.site_id)
    storage = _get(db, FuelStorageLocation, data.storage_location_id, "Fuel storage")
    if storage.project_id != project_id or storage.fuel_type_id != data.fuel_type_id:
        raise ValidationError("Issue storage does not match the project and fuel type.")
    destination = data.destination_type.upper()
    allowed = {"VEHICLE", "PLANT", "GENERATOR", "STORAGE_TANK", "OTHER_EQUIPMENT"}
    if destination not in allowed:
        raise ValidationError("Invalid fuel issue destination type.")
    if destination == "VEHICLE" and not data.vehicle_id:
        raise ValidationError("A vehicle is required for a vehicle fuel issue.")
    if destination != "VEHICLE" and not data.equipment_reference:
        raise ValidationError("An equipment reference is required for this destination.")

    # Resolve the vehicle early (if any) so both the evidence requirements below
    # and the consumption-calculation branch further down can key off
    # vehicle.uses_hours — a Vehicle flagged uses_hours=True (TLB, excavator,
    # crane, ...) must be tracked by hour meter / L-per-hour, not odometer /
    # L-per-100km, even though it's issued through destination_type=VEHICLE
    # like any other vehicle. FuelEquipmentProfile remains for destinations
    # with no Vehicle record at all (generators, rented plant, ...).
    vehicle = None
    if data.vehicle_id:
        vehicle = _get(db, Vehicle, data.vehicle_id, "Vehicle")
        if vehicle.assigned_project_id and vehicle.assigned_project_id != project_id:
            raise ValidationError("Vehicle is assigned to a different project.")
    vehicle_uses_hours = bool(vehicle and vehicle.uses_hours)

    required_evidence = {"ASSET_PHOTO", "PUMP_PHOTO"}
    if destination == "VEHICLE":
        if vehicle_uses_hours:
            if vehicle.hour_meter_required:
                required_evidence.add("HOUR_METER_PHOTO")
        else:
            required_evidence.add("ODOMETER_PHOTO")
    profile = None
    if destination != "VEHICLE":
        profile = db.query(FuelEquipmentProfile).filter(
            FuelEquipmentProfile.project_id == project_id,
            FuelEquipmentProfile.equipment_reference == data.equipment_reference,
            FuelEquipmentProfile.is_active.is_(True)).first()
        if profile and profile.hour_meter_required:
            required_evidence.add("HOUR_METER_PHOTO")
    missing = required_evidence - (evidence_types or set())
    if missing:
        if not (can_override and data.evidence_override_reason and data.evidence_override_reason.strip()):
            raise ValidationError("Mandatory fuel evidence missing: " + ", ".join(sorted(missing)) + ". An authorised override reason is required.")
    if stock_balance(db, storage.id, as_of=data.issued_at) + 0.001 < data.litres:
        raise ConflictError("Insufficient verified fuel stock for this issue.")

    anomaly_reasons: list[str] = []
    feasibility_status = "OK"
    estimated_remaining = None
    distance = l100 = hours_delta = lph = None
    if data.vehicle_id and not vehicle_uses_hours:
        prev = db.query(FuelIssue).filter(
            FuelIssue.vehicle_id == data.vehicle_id,
            FuelIssue.is_reversed.is_(False), FuelIssue.issued_at < data.issued_at,
        ).order_by(FuelIssue.issued_at.desc()).first()
        if data.odometer_reading is None:
            anomaly_reasons.append("Vehicle issue has no odometer reading")
        elif prev and prev.odometer_reading is not None:
            distance = float(data.odometer_reading) - float(prev.odometer_reading)
            if distance <= 0:
                raise ValidationError("Odometer reading must be greater than the previous reading.")
            l100 = round(data.litres / distance * 100, 3)
            expected = float(vehicle.fuel_consumption_per_100km or 0)
            tolerance = float(vehicle.fuel_tolerance_pct or 0) / 100
            estimated_remaining = max(float(prev.litres) - distance * expected / 100, 0) if expected else None
            if expected and l100 > expected * (1 + tolerance):
                anomaly_reasons.append(f"High consumption for review ({l100:.2f} L/100km)")
            if vehicle.tank_capacity_l and estimated_remaining is not None and data.litres > (float(vehicle.tank_capacity_l) - estimated_remaining) * (1 + tolerance):
                anomaly_reasons.append("Refill exceeds configured estimated tank space")
            elapsed = (data.issued_at - prev.issued_at).total_seconds() / 3600
            if elapsed < float(vehicle.fuel_minimum_issue_interval_hours or 0):
                anomaly_reasons.append("Refill is sooner than the configured minimum interval")
    elif data.vehicle_id and vehicle_uses_hours:
        prev = db.query(FuelIssue).filter(
            FuelIssue.vehicle_id == data.vehicle_id,
            FuelIssue.is_reversed.is_(False), FuelIssue.issued_at < data.issued_at,
        ).order_by(FuelIssue.issued_at.desc()).first()
        hours_delta, lph, estimated_remaining, hour_reasons = _hour_based_issue_metrics(
            data.litres, data.hour_meter_reading, prev,
            float(vehicle.fuel_consumption_per_hour or 0), float(vehicle.fuel_tolerance_pct or 0),
            float(vehicle.tank_capacity_l) if vehicle.tank_capacity_l else None,
            float(vehicle.fuel_minimum_issue_interval_hours or 0), data.issued_at,
            "Vehicle issue has no hour-meter reading",
        )
        anomaly_reasons.extend(hour_reasons)
    else:
        prev = db.query(FuelIssue).filter(
            FuelIssue.project_id == project_id,
            FuelIssue.destination_type == destination,
            FuelIssue.equipment_reference == data.equipment_reference,
            FuelIssue.is_reversed.is_(False), FuelIssue.issued_at < data.issued_at,
        ).order_by(FuelIssue.issued_at.desc()).first()
        hours_delta, lph, estimated_remaining, hour_reasons = _hour_based_issue_metrics(
            data.litres, data.hour_meter_reading, prev,
            float(profile.expected_litres_per_hour or 0) if profile else 0,
            float(profile.tolerance_pct or 0) if profile else 0,
            float(profile.tank_capacity_litres) if profile and profile.tank_capacity_litres else None,
            float(profile.minimum_issue_interval_hours) if profile else 0, data.issued_at,
            "Equipment issue has no hour-meter reading",
        )
        anomaly_reasons.extend(hour_reasons)

    override_required = bool(anomaly_reasons) and bool(
        (vehicle and vehicle.fuel_override_required) or (profile and profile.override_required))
    if override_required and not (can_override and data.feasibility_override_reason and data.feasibility_override_reason.strip()):
        raise ValidationError("Configured feasibility limits require an authorised override reason.")
    if anomaly_reasons:
        feasibility_status = "OVERRIDDEN" if override_required else "REVIEW"

    issue = FuelIssue(
        issue_number=_number("FUI"), project_id=project_id, site_id=data.site_id or storage.site_id,
        storage_location_id=storage.id, fuel_type_id=data.fuel_type_id,
        vehicle_id=data.vehicle_id, destination_type=destination,
        equipment_reference=data.equipment_reference, issued_at=data.issued_at,
        litres=data.litres, odometer_reading=data.odometer_reading,
        hour_meter_reading=data.hour_meter_reading, issued_by=actor_id,
        received_by=data.received_by, purpose=data.purpose, evidence_url=data.evidence_url,
        notes=data.notes, distance_since_previous_km=distance, litres_per_100km=l100,
        operating_hours_since_previous=hours_delta, litres_per_hour=lph,
        anomaly_flag=bool(anomaly_reasons), anomaly_reason="; ".join(anomaly_reasons) or None,
        reading_source="MANAGER_OVERRIDDEN" if (missing or override_required) else data.reading_source.upper(),
        estimated_remaining_litres=estimated_remaining, feasibility_status=feasibility_status,
        evidence_override_reason=data.evidence_override_reason if missing else None,
        evidence_override_by=actor_id if missing else None,
        evidence_override_at=_now() if missing else None,
        feasibility_override_reason=data.feasibility_override_reason if override_required else None,
        feasibility_override_by=actor_id if override_required else None,
        feasibility_override_at=_now() if override_required else None,
        is_reversed=False,
    )
    db.add(issue); db.flush()
    _audit(db, actor_id, AuditAction.ISSUE, "FUEL_ISSUE", issue.id,
           after={"issue_number": issue.issue_number, "litres": data.litres, "destination": destination})
    if missing:
        _audit(db, actor_id, AuditAction.OVERRUN_ACCEPTED, "FUEL_ISSUE", issue.id,
               before={"evidence_complete": False, "missing_evidence": sorted(missing)},
               after={"evidence_override_accepted": True, "missing_evidence": sorted(missing)},
               notes=data.evidence_override_reason)
    if override_required:
        _audit(db, actor_id, AuditAction.OVERRUN_ACCEPTED, "FUEL_ISSUE", issue.id,
               before={"feasibility_status": "OVERRIDE_REQUIRED"},
               after={"feasibility_status": feasibility_status}, notes=data.feasibility_override_reason)
    if issue.anomaly_flag:
        _notify(db, alert_type=AlertType.FUEL_USAGE_HIGH, severity=AlertSeverity.HIGH,
                title="Fuel usage requires review", message=issue.anomaly_reason,
                project_id=project_id, entity_type="FUEL_ISSUE", entity_id=issue.id)
    balance_after = stock_balance(db, storage.id) - data.litres
    if storage.low_stock_threshold_litres is not None and balance_after <= float(storage.low_stock_threshold_litres):
        _notify(db, alert_type=AlertType.LOW_STOCK, severity=AlertSeverity.HIGH,
                title="Low fuel stock", message=f"{storage.name} balance is {balance_after:.2f} L.",
                project_id=project_id, entity_type="FUEL_STORAGE", entity_id=storage.id)
    if commit:
        db.commit(); db.refresh(issue)
    return issue


def list_issues(db: Session, project_id: uuid.UUID, vehicle_id: Optional[uuid.UUID] = None,
                equipment_reference: Optional[str] = None, anomaly_only: bool = False):
    q = db.query(FuelIssue).filter(FuelIssue.project_id == project_id)
    if vehicle_id: q = q.filter(FuelIssue.vehicle_id == vehicle_id)
    if equipment_reference: q = q.filter(FuelIssue.equipment_reference == equipment_reference)
    if anomaly_only: q = q.filter(FuelIssue.anomaly_flag.is_(True))
    return q.order_by(FuelIssue.issued_at.desc()).all()


def reverse_issue(db: Session, issue_id: uuid.UUID, actor_id: uuid.UUID, reason: str):
    issue = _get(db, FuelIssue, issue_id, "Fuel issue")
    if issue.is_reversed:
        raise ConflictError("Fuel issue has already been reversed.")
    if not reason or len(reason.strip()) < 3:
        raise ValidationError("A reversal reason is required.")
    issue.is_reversed, issue.reversed_at, issue.reversed_by = True, _now(), actor_id
    issue.reversal_reason = reason.strip()
    _audit(db, actor_id, AuditAction.UPDATE, "FUEL_ISSUE", issue.id,
           before={"is_reversed": False}, after={"is_reversed": True}, notes=reason)
    db.commit(); db.refresh(issue)
    return issue


def create_adjustment(db: Session, project_id: uuid.UUID, data: FuelAdjustmentCreate, actor_id: uuid.UUID):
    storage = _get(db, FuelStorageLocation, data.storage_location_id, "Fuel storage")
    if storage.project_id != project_id:
        raise ValidationError("Fuel storage belongs to a different project.")
    adjustment_type = data.adjustment_type.upper()
    if adjustment_type not in {"OPENING", "CORRECTION", "LOSS", "GAIN", "REVERSAL"}:
        raise ValidationError("Invalid fuel adjustment type.")
    if not data.litres_delta:
        raise ValidationError("Fuel adjustment cannot be zero.")
    balance_before = stock_balance(db, storage.id)
    adjustment = FuelStockAdjustment(
        project_id=project_id, site_id=storage.site_id, storage_location_id=storage.id,
        fuel_type_id=storage.fuel_type_id, adjustment_type=adjustment_type,
        litres_delta=data.litres_delta, reason=data.reason.strip(), authorised_by=actor_id,
        reference_reconciliation_id=data.reference_reconciliation_id, created_at=_now(),
    )
    db.add(adjustment); db.flush()
    _audit(db, actor_id, AuditAction.UPDATE, "FUEL_ADJUSTMENT", adjustment.id,
           before={"calculated_balance_litres": balance_before},
           after={"calculated_balance_litres": round(balance_before + data.litres_delta, 2),
                  "litres_delta": data.litres_delta, "type": adjustment_type}, notes=data.reason)
    db.commit(); db.refresh(adjustment)
    return adjustment


def reconcile(db: Session, project_id: uuid.UUID, data: FuelReconciliationCreate, actor_id: uuid.UUID):
    storage = _get(db, FuelStorageLocation, data.storage_location_id, "Fuel storage")
    if storage.project_id != project_id:
        raise ValidationError("Fuel storage belongs to a different project.")
    calculated = stock_balance(db, storage.id, as_of=data.reconciliation_date)
    variance = round(data.physical_balance_litres - calculated, 2)
    variance_pct = round(variance / calculated * 100, 3) if calculated else None
    threshold = max(50.0, abs(calculated) * .02)
    requires_approval = abs(variance) > threshold
    rec = FuelReconciliation(
        reconciliation_number=_number("FRC"), project_id=project_id, site_id=storage.site_id,
        storage_location_id=storage.id, fuel_type_id=storage.fuel_type_id,
        reconciliation_date=data.reconciliation_date, calculated_balance_litres=calculated,
        physical_balance_litres=data.physical_balance_litres, variance_litres=variance,
        variance_pct=variance_pct, explanation=data.explanation.strip(),
        status="PENDING_APPROVAL" if requires_approval else "COMPLETED",
        requires_approval=requires_approval, reconciled_by=actor_id,
    )
    db.add(rec); db.flush()
    _audit(db, actor_id, AuditAction.CREATE, "FUEL_RECONCILIATION", rec.id,
           after={"calculated": calculated, "physical": data.physical_balance_litres, "variance": variance})
    if requires_approval:
        _notify(db, alert_type=AlertType.DELIVERY_DISCREPANCY, severity=AlertSeverity.HIGH,
                title="Fuel reconciliation variance", message=f"{storage.name} variance is {variance:.2f} L and requires approval.",
                project_id=project_id, entity_type="FUEL_RECONCILIATION", entity_id=rec.id)
    db.commit(); db.refresh(rec)
    return rec


def approve_reconciliation(db: Session, rec_id: uuid.UUID, actor_id: uuid.UUID, notes: Optional[str] = None):
    rec = _get(db, FuelReconciliation, rec_id, "Fuel reconciliation")
    if rec.status != "PENDING_APPROVAL":
        raise InvalidStateError("Only a pending reconciliation can be approved.")
    if rec.reconciled_by == actor_id:
        raise ConflictError("The reconciler cannot approve their own large variance.")
    rec.status, rec.approved_by, rec.approved_at, rec.approval_notes = "APPROVED", actor_id, _now(), notes
    _audit(db, actor_id, AuditAction.APPROVE, "FUEL_RECONCILIATION", rec.id,
           before={"status": "PENDING_APPROVAL", "variance_litres": float(rec.variance_litres)},
           after={"status": "APPROVED", "approved_by": str(actor_id),
                  "variance_litres": float(rec.variance_litres)}, notes=notes)
    db.commit(); db.refresh(rec)
    return rec


def list_reconciliations(db: Session, project_id: uuid.UUID):
    return db.query(FuelReconciliation).filter(FuelReconciliation.project_id == project_id).order_by(
        FuelReconciliation.reconciliation_date.desc()
    ).all()


def dashboard(db: Session, project_id: uuid.UUID) -> dict:
    requested = float(db.query(func.coalesce(func.sum(FuelOrder.requested_litres), 0)).filter(
        FuelOrder.project_id == project_id, FuelOrder.status != "CANCELLED", FuelOrder.status != "REJECTED"
    ).scalar() or 0)
    approved = float(db.query(func.coalesce(func.sum(FuelOrder.requested_litres), 0)).filter(
        FuelOrder.project_id == project_id,
        FuelOrder.status.in_(["APPROVED", "ORDERED", "PARTIALLY_DELIVERED", "DELIVERED", "CLOSED"]),
    ).scalar() or 0)
    ordered = float(db.query(func.coalesce(func.sum(FuelOrder.requested_litres), 0)).filter(
        FuelOrder.project_id == project_id,
        FuelOrder.status.in_(["ORDERED", "PARTIALLY_DELIVERED", "DELIVERED", "CLOSED"]),
    ).scalar() or 0)
    delivered = float(db.query(func.coalesce(func.sum(FuelDelivery.confirmed_litres), 0)).filter(
        FuelDelivery.project_id == project_id, FuelDelivery.verification_status == "VERIFIED",
    ).scalar() or 0)
    issued = float(db.query(func.coalesce(func.sum(FuelIssue.litres), 0)).filter(
        FuelIssue.project_id == project_id, FuelIssue.is_reversed.is_(False),
    ).scalar() or 0)
    storage = list_storage(db, project_id)
    current_stock = sum(stock_balance(db, s.id) for s in storage)
    today = date.today()
    overdue = db.query(FuelOrder).filter(
        FuelOrder.project_id == project_id, FuelOrder.expected_delivery_date < today,
        FuelOrder.status.in_(["ORDERED", "PARTIALLY_DELIVERED"]),
    ).count()
    outstanding = db.query(FuelOrder).filter(
        FuelOrder.project_id == project_id,
        FuelOrder.status.in_(["SUBMITTED", "APPROVED", "ORDERED", "PARTIALLY_DELIVERED"]),
    ).count()
    anomalies = db.query(FuelIssue).filter(
        FuelIssue.project_id == project_id, FuelIssue.anomaly_flag.is_(True), FuelIssue.is_reversed.is_(False)
    ).count()
    return {
        "litres_requested": requested, "litres_approved": approved, "litres_ordered": ordered,
        "litres_delivered": delivered, "litres_issued": issued,
        "current_calculated_stock": round(current_stock, 2), "outstanding_orders": outstanding,
        "overdue_deliveries": overdue, "anomalies_for_review": anomalies,
        "storage_locations": [{"id": str(s.id), "name": s.name, "balance_litres": stock_balance(db, s.id)} for s in storage],
    }


def export_orders_csv(db: Session, project_id: uuid.UUID) -> str:
    out = io.StringIO(); writer = csv.writer(out)
    writer.writerow(["Order number", "Request date", "Status", "Requested litres", "Delivered litres", "Expected delivery"])
    for order in list_orders(db, project_id):
        writer.writerow([order.order_number, order.request_date, order.status, order.requested_litres,
                         order.delivered_litres, order.expected_delivery_date or ""])
    return out.getvalue()


def export_usage_csv(db: Session, project_id: uuid.UUID) -> str:
    out = io.StringIO(); writer = csv.writer(out)
    writer.writerow(["Issue number", "Issued at", "Destination", "Reference", "Litres", "L/100km", "L/hour", "Review flag", "Reversed"])
    for issue in list_issues(db, project_id):
        writer.writerow([issue.issue_number, issue.issued_at, issue.destination_type,
                         str(issue.vehicle_id or issue.equipment_reference or ""), issue.litres,
                         issue.litres_per_100km or "", issue.litres_per_hour or "",
                         issue.anomaly_reason or "", issue.is_reversed])
    return out.getvalue()
