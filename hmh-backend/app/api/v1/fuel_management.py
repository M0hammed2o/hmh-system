"""Fuel Management API: orders, deliveries, issues, stock, reconciliation, reports."""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError as PydanticValidationError

from app.core.fuel_permissions import has_fuel_permission, require_fuel_permission
from app.core.exceptions import HMHException
from app.dependencies import CurrentUser, DbSession, check_project_access
from app.models.fuel_management import FuelEmailLog, FuelIssue, FuelIssueEvidence, FuelOrderHistory, FuelReconciliation
from app.models.user import User
from app.models.vehicle import FuelDelivery
from app.schemas.common import ApiSuccess
from app.schemas.fuel_management import (
    FuelAdjustmentCreate, FuelAdjustmentRead, FuelDeliveryCreate, FuelDeliveryRead, FuelEmailLogRead,
    FuelEquipmentProfileCreate, FuelEquipmentProfileRead,
    FuelIssueCreate, FuelIssueRead, FuelOrderCreate, FuelOrderHistoryRead, FuelOrderRead, FuelOrderUpdate,
    FuelReconciliationCreate, FuelReconciliationRead, FuelStorageCreate, FuelStorageRead,
    FuelTransition, FuelTypeRead,
)
from app.services import fuel_management_service as service
from app.services import attachment_service, fuel_email_service

router = APIRouter(prefix="/fuel-management", tags=["fuel-management"])
project_router = APIRouter(prefix="/projects/{project_id}/fuel-management", tags=["fuel-management"])


def _access(db, user, project_id):
    check_project_access(db, user, project_id)


def _order_read(db, obj):
    read = FuelOrderRead.model_validate(obj)
    requester = db.get(User, obj.requested_by)
    read.requester_name = requester.full_name if requester else None
    read.next_approver = {"DRAFT": "Requester submission", "SUBMITTED": "Fuel approver",
                          "APPROVED": "Procurement ordering", "ORDERED": "Delivery receiver",
                          "PARTIALLY_DELIVERED": "Delivery receiver", "DELIVERED": "Order closure"}.get(obj.status)
    rows = db.query(FuelOrderHistory).filter(FuelOrderHistory.order_id == obj.id).order_by(FuelOrderHistory.created_at).all()
    users = {u.id: u.full_name for u in db.query(User).filter(User.id.in_({r.actor_id for r in rows})).all()} if rows else {}
    read.history = [FuelOrderHistoryRead(id=r.id, from_status=r.from_status, to_status=r.to_status,
                     actor_id=r.actor_id, actor_name=users.get(r.actor_id),
                     reason=r.reason, created_at=r.created_at) for r in rows]
    return read


def _issue_read(db, obj):
    read = FuelIssueRead.model_validate(obj)
    evidence = db.query(FuelIssueEvidence).filter(FuelIssueEvidence.issue_id == obj.id).all()
    read.evidence = [{"type": e.evidence_type, "attachment_id": str(e.attachment_id)} for e in evidence]
    return read


@router.get("/fuel-types", response_model=ApiSuccess[list[FuelTypeRead]],
            dependencies=[require_fuel_permission("fuel.view")])
def fuel_types(db: DbSession):
    return ApiSuccess(data=[FuelTypeRead.model_validate(x) for x in service.list_fuel_types(db)])


@project_router.get("/dashboard", response_model=ApiSuccess[dict],
                    dependencies=[require_fuel_permission("fuel.view")])
def dashboard(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    _access(db, current_user, project_id)
    return ApiSuccess(data=service.dashboard(db, project_id))


@project_router.post("/storage", response_model=ApiSuccess[FuelStorageRead], status_code=201,
                     dependencies=[require_fuel_permission("fuel.admin")])
def create_storage(project_id: uuid.UUID, body: FuelStorageCreate, db: DbSession, current_user: CurrentUser):
    _access(db, current_user, project_id)
    obj = service.create_storage(db, project_id, body, current_user.id)
    read = FuelStorageRead.model_validate(obj)
    read.calculated_balance_litres = service.stock_balance(db, obj.id)
    return ApiSuccess(data=read, message="Fuel storage location created.")


@project_router.get("/storage", response_model=ApiSuccess[list[FuelStorageRead]],
                    dependencies=[require_fuel_permission("fuel.view")])
def list_storage(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    _access(db, current_user, project_id)
    result = []
    for obj in service.list_storage(db, project_id):
        read = FuelStorageRead.model_validate(obj)
        read.calculated_balance_litres = service.stock_balance(db, obj.id)
        result.append(read)
    return ApiSuccess(data=result)


@project_router.post("/orders", response_model=ApiSuccess[FuelOrderRead], status_code=201,
                     dependencies=[require_fuel_permission("fuel.request")])
def create_order(project_id: uuid.UUID, body: FuelOrderCreate, db: DbSession, current_user: CurrentUser):
    _access(db, current_user, project_id)
    obj = service.create_order(db, project_id, body, current_user.id)
    return ApiSuccess(data=_order_read(db, obj), message="Fuel request created.")


@project_router.post("/requests", response_model=ApiSuccess[FuelOrderRead], status_code=201,
                     dependencies=[require_fuel_permission("fuel.request")])
def create_submitted_request(project_id: uuid.UUID, body: FuelOrderCreate, db: DbSession, current_user: CurrentUser):
    """Mobile clerk flow: create and submit in one operation."""
    _access(db, current_user, project_id)
    if not body.site_id:
        from fastapi import HTTPException
        raise HTTPException(422, "A site is required for a site fuel request.")
    if not body.intended_use or not body.expected_delivery_date or not body.destination_type:
        from fastapi import HTTPException
        raise HTTPException(422, "Intended use, required date and destination are required.")
    service.validate_request_destination(db, project_id, body)
    body.submit_now = True
    obj = service.create_order(db, project_id, body, current_user.id)
    return ApiSuccess(data=_order_read(db, obj), message="Fuel request submitted for approval.")


@project_router.get("/orders", response_model=ApiSuccess[list[FuelOrderRead]],
                    dependencies=[require_fuel_permission("fuel.view")])
def list_orders(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser,
                status: Optional[str] = Query(default=None), mine: bool = Query(default=False)):
    _access(db, current_user, project_id)
    rows = service.list_orders(db, project_id, status, current_user.id if mine else None)
    return ApiSuccess(data=[_order_read(db, x) for x in rows])


@router.get("/orders/{order_id}", response_model=ApiSuccess[FuelOrderRead],
            dependencies=[require_fuel_permission("fuel.view")])
def get_order(order_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    obj = service.get_order(db, order_id); _access(db, current_user, obj.project_id)
    return ApiSuccess(data=_order_read(db, obj))


@router.patch("/orders/{order_id}", response_model=ApiSuccess[FuelOrderRead],
              dependencies=[require_fuel_permission("fuel.request")])
def update_order(order_id: uuid.UUID, body: FuelOrderUpdate, db: DbSession, current_user: CurrentUser):
    obj = service.get_order(db, order_id); _access(db, current_user, obj.project_id)
    obj = service.update_order(db, order_id, body, current_user.id)
    return ApiSuccess(data=_order_read(db, obj), message="Fuel request updated.")


def _transition(order_id, target, body, db, user):
    obj = service.get_order(db, order_id); _access(db, user, obj.project_id)
    return service.transition_order(db, order_id, target, user.id, body)


@router.post("/orders/{order_id}/submit", response_model=ApiSuccess[FuelOrderRead],
             dependencies=[require_fuel_permission("fuel.submit")])
def submit_order(order_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    return ApiSuccess(data=_order_read(db, _transition(order_id, "SUBMITTED", FuelTransition(), db, current_user)))


@router.post("/orders/{order_id}/approve", response_model=ApiSuccess[FuelOrderRead],
             dependencies=[require_fuel_permission("fuel.approve")])
def approve_order(order_id: uuid.UUID, db: DbSession, current_user: CurrentUser,
                  body: FuelTransition = FuelTransition()):
    return ApiSuccess(data=_order_read(db, _transition(order_id, "APPROVED", body, db, current_user)))


@router.post("/orders/{order_id}/reject", response_model=ApiSuccess[FuelOrderRead],
             dependencies=[require_fuel_permission("fuel.approve")])
def reject_order(order_id: uuid.UUID, body: FuelTransition, db: DbSession, current_user: CurrentUser):
    return ApiSuccess(data=_order_read(db, _transition(order_id, "REJECTED", body, db, current_user)))


@router.post("/orders/{order_id}/mark-ordered", response_model=ApiSuccess[FuelOrderRead],
             dependencies=[require_fuel_permission("fuel.order")])
def mark_ordered(order_id: uuid.UUID, body: FuelTransition, db: DbSession, current_user: CurrentUser):
    return ApiSuccess(data=_order_read(db, _transition(order_id, "ORDERED", body, db, current_user)))


@router.post("/orders/{order_id}/cancel", response_model=ApiSuccess[FuelOrderRead],
             dependencies=[require_fuel_permission("fuel.submit")])
def cancel_order(order_id: uuid.UUID, body: FuelTransition, db: DbSession, current_user: CurrentUser):
    return ApiSuccess(data=_order_read(db, _transition(order_id, "CANCELLED", body, db, current_user)))


@router.post("/orders/{order_id}/close", response_model=ApiSuccess[FuelOrderRead],
             dependencies=[require_fuel_permission("fuel.order")])
def close_order(order_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    return ApiSuccess(data=_order_read(db, _transition(order_id, "CLOSED", FuelTransition(), db, current_user)))


@router.post("/orders/{order_id}/deliveries", response_model=ApiSuccess[FuelDeliveryRead], status_code=201,
             dependencies=[require_fuel_permission("fuel.receive")])
def record_delivery(order_id: uuid.UUID, body: FuelDeliveryCreate, db: DbSession, current_user: CurrentUser):
    order = service.get_order(db, order_id); _access(db, current_user, order.project_id)
    can_override = has_fuel_permission(current_user.role, "fuel.admin")
    obj = service.record_delivery(db, order_id, body, current_user.id, can_override)
    return ApiSuccess(data=FuelDeliveryRead.model_validate(obj), message="Fuel delivery recorded pending verification.")


@project_router.get("/deliveries", response_model=ApiSuccess[list[FuelDeliveryRead]],
                    dependencies=[require_fuel_permission("fuel.view")])
def list_deliveries(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    _access(db, current_user, project_id)
    return ApiSuccess(data=[FuelDeliveryRead.model_validate(x) for x in service.list_deliveries(db, project_id)])


@router.post("/deliveries/{delivery_id}/verify", response_model=ApiSuccess[FuelDeliveryRead],
             dependencies=[require_fuel_permission("fuel.receive")])
def verify_delivery(delivery_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    obj = service._get(db, FuelDelivery, delivery_id, "Fuel delivery")
    _access(db, current_user, obj.project_id)
    return ApiSuccess(data=FuelDeliveryRead.model_validate(service.verify_delivery(db, delivery_id, current_user.id, True)))


@router.post("/deliveries/{delivery_id}/reject", response_model=ApiSuccess[FuelDeliveryRead],
             dependencies=[require_fuel_permission("fuel.receive")])
def reject_delivery(delivery_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    obj = service._get(db, FuelDelivery, delivery_id, "Fuel delivery")
    _access(db, current_user, obj.project_id)
    return ApiSuccess(data=FuelDeliveryRead.model_validate(service.verify_delivery(db, delivery_id, current_user.id, False)))


@project_router.post("/issues", response_model=ApiSuccess[FuelIssueRead], status_code=201,
                     dependencies=[require_fuel_permission("fuel.issue")])
def create_issue(project_id: uuid.UUID, body: FuelIssueCreate, db: DbSession, current_user: CurrentUser):
    _access(db, current_user, project_id)
    can_override = has_fuel_permission(current_user.role, "fuel.admin")
    return ApiSuccess(data=_issue_read(db, service.create_issue(db, project_id, body, current_user.id,
                      evidence_types=set(), can_override=can_override)),
                      message="Fuel issued from calculated stock.")


@project_router.post("/issues-with-evidence", response_model=ApiSuccess[FuelIssueRead], status_code=201,
                     dependencies=[require_fuel_permission("fuel.issue")])
def create_issue_with_evidence(
    project_id: uuid.UUID, db: DbSession, current_user: CurrentUser,
    payload: str = Form(...), asset_photo: Optional[UploadFile] = File(None),
    pump_photo: Optional[UploadFile] = File(None), odometer_photo: Optional[UploadFile] = File(None),
    hour_meter_photo: Optional[UploadFile] = File(None),
):
    """Stage evidence and commit issue, metadata, and audit rows only after every upload succeeds."""
    _access(db, current_user, project_id)
    try:
        decoded = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(422, f"Invalid Fuel issue payload: malformed JSON ({exc.msg if hasattr(exc, 'msg') else 'invalid input'}).")
    try:
        body = FuelIssueCreate.model_validate(decoded)
    except PydanticValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'payload'}: {error['msg']}"
            for error in exc.errors(include_url=False)
        )
        raise HTTPException(422, f"Invalid Fuel issue payload: {details}")
    files = {"ASSET_PHOTO": asset_photo, "PUMP_PHOTO": pump_photo,
             "ODOMETER_PHOTO": odometer_photo, "HOUR_METER_PHOTO": hour_meter_photo}
    supplied = {kind for kind, file in files.items() if file is not None}
    can_override = has_fuel_permission(current_user.role, "fuel.admin")
    staged_paths: list[str] = []
    staging_complete = False
    try:
        with db.begin_nested():
            obj = service.create_issue(db, project_id, body, current_user.id,
                                       evidence_types=supplied, can_override=can_override, commit=False)
            for kind, file in files.items():
                if file is None: continue
                attachment = attachment_service.save_attachment(
                    db, file, "FUEL_ISSUE", str(obj.id), "PHOTO", current_user.id,
                    caption=kind, uploaded_role=current_user.role.value, commit=False,
                    staged_paths=staged_paths,
                )
                db.add(FuelIssueEvidence(issue_id=obj.id, attachment_id=attachment.id,
                                         evidence_type=kind, created_at=datetime.now(timezone.utc)))
            if not obj.evidence_override_by and not obj.feasibility_override_by:
                obj.reading_source = "PHOTOGRAPH_VERIFIED" if supplied else body.reading_source.upper()
            db.flush()
        staging_complete = True
        db.commit(); db.refresh(obj)
    except Exception as exc:
        if staging_complete:
            db.rollback()
        attachment_service.cleanup_staged_uploads(staged_paths)
        if isinstance(exc, (HTTPException, HMHException)):
            raise
        raise HTTPException(
            503,
            "Fuel evidence capture did not complete. No fuel issue was recorded; retry the capture.",
        ) from exc
    return ApiSuccess(data=_issue_read(db, obj), message="Fuel issued with required evidence.")


@project_router.get("/issues", response_model=ApiSuccess[list[FuelIssueRead]],
                    dependencies=[require_fuel_permission("fuel.view")])
def list_issues(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser,
                vehicle_id: Optional[uuid.UUID] = None, equipment_reference: Optional[str] = None,
                anomaly_only: bool = False):
    _access(db, current_user, project_id)
    return ApiSuccess(data=[_issue_read(db, x) for x in service.list_issues(
        db, project_id, vehicle_id, equipment_reference, anomaly_only
    )])


@project_router.get("/equipment-profiles", response_model=ApiSuccess[list[FuelEquipmentProfileRead]],
                    dependencies=[require_fuel_permission("fuel.view")])
def equipment_profiles(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    _access(db, current_user, project_id)
    return ApiSuccess(data=[FuelEquipmentProfileRead.model_validate(x) for x in service.list_equipment_profiles(db, project_id)])


@project_router.put("/equipment-profiles", response_model=ApiSuccess[FuelEquipmentProfileRead],
                    dependencies=[require_fuel_permission("fuel.admin")])
def save_equipment_profile(project_id: uuid.UUID, body: FuelEquipmentProfileCreate,
                           db: DbSession, current_user: CurrentUser):
    _access(db, current_user, project_id)
    return ApiSuccess(data=FuelEquipmentProfileRead.model_validate(
        service.upsert_equipment_profile(db, project_id, body, current_user.id)))


@router.get("/orders/{order_id}/emails", response_model=ApiSuccess[list[FuelEmailLogRead]],
            dependencies=[require_fuel_permission("fuel.view")])
def fuel_email_history(order_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    order = service.get_order(db, order_id); _access(db, current_user, order.project_id)
    rows = db.query(FuelEmailLog).filter(FuelEmailLog.order_id == order_id).order_by(FuelEmailLog.created_at).all()
    return ApiSuccess(data=[FuelEmailLogRead.model_validate(x) for x in rows])


@router.post("/email-queue/retry", response_model=ApiSuccess[dict],
             dependencies=[require_fuel_permission("fuel.admin")])
def retry_fuel_emails(db: DbSession):
    return ApiSuccess(data=fuel_email_service.retry_failed(db), message="Fuel email queue processed.")


@router.post("/issues/{issue_id}/reverse", response_model=ApiSuccess[FuelIssueRead],
             dependencies=[require_fuel_permission("fuel.adjust")])
def reverse_issue(issue_id: uuid.UUID, body: FuelTransition, db: DbSession, current_user: CurrentUser):
    obj = service._get(db, FuelIssue, issue_id, "Fuel issue")
    _access(db, current_user, obj.project_id)
    return ApiSuccess(data=FuelIssueRead.model_validate(service.reverse_issue(db, issue_id, current_user.id, body.reason or "")))


@project_router.post("/adjustments", response_model=ApiSuccess[FuelAdjustmentRead], status_code=201,
                     dependencies=[require_fuel_permission("fuel.adjust")])
def create_adjustment(project_id: uuid.UUID, body: FuelAdjustmentCreate, db: DbSession, current_user: CurrentUser):
    _access(db, current_user, project_id)
    return ApiSuccess(data=FuelAdjustmentRead.model_validate(service.create_adjustment(db, project_id, body, current_user.id)))


@project_router.post("/reconciliations", response_model=ApiSuccess[FuelReconciliationRead], status_code=201,
                     dependencies=[require_fuel_permission("fuel.reconcile")])
def reconcile(project_id: uuid.UUID, body: FuelReconciliationCreate, db: DbSession, current_user: CurrentUser):
    _access(db, current_user, project_id)
    return ApiSuccess(data=FuelReconciliationRead.model_validate(service.reconcile(db, project_id, body, current_user.id)))


@project_router.get("/reconciliations", response_model=ApiSuccess[list[FuelReconciliationRead]],
                    dependencies=[require_fuel_permission("fuel.view")])
def list_reconciliations(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    _access(db, current_user, project_id)
    return ApiSuccess(data=[FuelReconciliationRead.model_validate(x) for x in service.list_reconciliations(db, project_id)])


@router.post("/reconciliations/{rec_id}/approve", response_model=ApiSuccess[FuelReconciliationRead],
             dependencies=[require_fuel_permission("fuel.adjust")])
def approve_reconciliation(rec_id: uuid.UUID, body: FuelTransition, db: DbSession, current_user: CurrentUser):
    obj = service._get(db, FuelReconciliation, rec_id, "Fuel reconciliation")
    _access(db, current_user, obj.project_id)
    return ApiSuccess(data=FuelReconciliationRead.model_validate(service.approve_reconciliation(db, rec_id, current_user.id, body.reason)))


@project_router.get("/reports/orders.csv", dependencies=[require_fuel_permission("fuel.export")])
def orders_csv(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    _access(db, current_user, project_id)
    return Response(service.export_orders_csv(db, project_id), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=fuel-orders.csv"})


@project_router.get("/reports/usage.csv", dependencies=[require_fuel_permission("fuel.export")])
def usage_csv(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    _access(db, current_user, project_id)
    return Response(service.export_usage_csv(db, project_id), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=fuel-usage.csv"})
