"""Vehicle and fleet cost routes."""

import os
import uuid
from datetime import date, datetime as dt, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func

from app.core.storage import save_upload
from app.core.upload_validation import DOCUMENT_MIMES, validate_upload
from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.vehicle import (
    RepairJobCreate,
    RepairJobUpdate,
    VehicleCostCreate,
    VehicleCostRead,
    VehicleCreate,
    VehicleRead,
    VehicleUpdate,
)
from app.services import fuel_service, vehicle_service

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


# ---------------------------------------------------------------------------
# Vehicle CRUD
# ---------------------------------------------------------------------------

@router.get("/", response_model=ApiSuccess[list[VehicleRead]], dependencies=[ALL_ROLES])
def list_vehicles(
    db: DbSession,
    project_id: Optional[uuid.UUID] = Query(None),
    site_id: Optional[uuid.UUID] = Query(None),
):
    vehicles = vehicle_service.list_vehicles(db, project_id, site_id)
    return ApiSuccess(data=[VehicleRead.model_validate(v) for v in vehicles])


@router.post("/", response_model=ApiSuccess[VehicleRead], status_code=201, dependencies=[OFFICE_AND_ABOVE])
def create_vehicle(body: VehicleCreate, db: DbSession, current_user: CurrentUser):
    vehicle = vehicle_service.create_vehicle(db, body, actor_id=current_user.id)
    return ApiSuccess(data=VehicleRead.model_validate(vehicle), message="Vehicle created.")


@router.get("/{vehicle_id}", response_model=ApiSuccess[VehicleRead], dependencies=[ALL_ROLES])
def get_vehicle(vehicle_id: uuid.UUID, db: DbSession):
    vehicle = vehicle_service.get_vehicle(db, vehicle_id)
    return ApiSuccess(data=VehicleRead.model_validate(vehicle))


@router.patch("/{vehicle_id}", response_model=ApiSuccess[VehicleRead], dependencies=[OFFICE_AND_ABOVE])
def update_vehicle(vehicle_id: uuid.UUID, body: VehicleUpdate, db: DbSession, current_user: CurrentUser):
    vehicle = vehicle_service.update_vehicle(db, vehicle_id, body, actor_id=current_user.id)
    return ApiSuccess(data=VehicleRead.model_validate(vehicle))


@router.delete("/{vehicle_id}", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def delete_vehicle(vehicle_id: uuid.UUID, db: DbSession):
    """
    Hard-delete a vehicle if it has no fuel logs or cost records.
    If records exist, blocks deletion to preserve audit trail.
    """
    from app.models.vehicle import Vehicle, VehicleCost
    from app.models.fuel import FuelLog

    v = db.get(Vehicle, vehicle_id)
    if not v:
        raise HTTPException(404, "Vehicle not found.")

    cost_count = db.query(VehicleCost).filter(VehicleCost.vehicle_id == vehicle_id).count()
    fuel_count = db.query(FuelLog).filter(FuelLog.equipment_ref == v.registration).count()

    if cost_count > 0 or fuel_count > 0:
        raise HTTPException(
            409,
            f"Cannot delete '{v.registration}': it has {cost_count} cost record(s) and "
            f"{fuel_count} fuel log(s). Set the vehicle to RETIRED status instead."
        )
    db.delete(v)
    db.commit()
    return ApiSuccess(data={"vehicle_id": str(vehicle_id), "registration": v.registration},
                      message=f"Vehicle '{v.registration}' deleted.")


# ---------------------------------------------------------------------------
# Vehicle costs (standalone — not tied to a repair job)
# ---------------------------------------------------------------------------

@router.post(
    "/{vehicle_id}/costs",
    response_model=ApiSuccess[VehicleCostRead],
    status_code=201,
    dependencies=[ALL_ROLES],
)
def log_cost(vehicle_id: uuid.UUID, body: VehicleCostCreate, db: DbSession, current_user: CurrentUser):
    cost = vehicle_service.log_cost(db, vehicle_id, body, actor_id=current_user.id)
    return ApiSuccess(data=VehicleCostRead.model_validate(cost), message="Cost logged.")


@router.get(
    "/{vehicle_id}/costs",
    response_model=ApiSuccess[list[VehicleCostRead]],
    dependencies=[ALL_ROLES],
)
def list_costs(vehicle_id: uuid.UUID, db: DbSession):
    costs = vehicle_service.list_costs(db, vehicle_id)
    return ApiSuccess(data=[VehicleCostRead.model_validate(c) for c in costs])


# ---------------------------------------------------------------------------
# Repair jobs
# ---------------------------------------------------------------------------

def _build_repair_job_dict(job, labour_costs, mrs) -> dict:
    """Serialize a RepairJob ORM object plus pre-fetched related collections."""
    return {
        "id": str(job.id),
        "vehicle_id": str(job.vehicle_id),
        "title": job.title,
        "description": job.description,
        "status": job.status,
        "workshop_name": job.workshop_name,
        "date_opened": job.date_opened.isoformat() if job.date_opened else None,
        "date_closed": job.date_closed.isoformat() if job.date_closed else None,
        "odometer_at_repair": float(job.odometer_at_repair) if job.odometer_at_repair is not None else None,
        "notes": job.notes,
        "created_by": str(job.created_by) if job.created_by else None,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        # Quotation / approval / invoice
        "quote_amount": float(job.quote_amount) if job.quote_amount is not None else None,
        "quote_file_url": job.quote_file_url,
        "invoice_amount": float(job.invoice_amount) if job.invoice_amount is not None else None,
        "invoice_file_url": job.invoice_file_url,
        "approval_stage": job.approval_stage or 0,
        "approval_1_by": str(job.approval_1_by) if job.approval_1_by else None,
        "approval_1_at": job.approval_1_at.isoformat() if job.approval_1_at else None,
        "approval_2_by": str(job.approval_2_by) if job.approval_2_by else None,
        "approval_2_at": job.approval_2_at.isoformat() if job.approval_2_at else None,
        "approval_3_by": str(job.approval_3_by) if job.approval_3_by else None,
        "approval_3_at": job.approval_3_at.isoformat() if job.approval_3_at else None,
        # Costs
        "total_labour_cost": float(sum(c.amount for c in labour_costs)),
        "total_parts_cost": 0.0,
        "labour_cost_count": len(labour_costs),
        "labour_costs": [
            {
                "id": str(c.id),
                "cost_type": c.cost_type.value if hasattr(c.cost_type, "value") else c.cost_type,
                "amount": float(c.amount),
                "description": c.description,
                "cost_date": c.cost_date.isoformat(),
                "notes": c.notes,
            }
            for c in sorted(labour_costs, key=lambda x: x.cost_date, reverse=True)
        ],
        "mr_count": len(mrs),
        "material_requests": [
            {
                "id": str(mr.id),
                "mr_number": mr.request_number,
                "status": mr.status.value if hasattr(mr.status, "value") else str(mr.status),
                "requested_date": mr.requested_date.isoformat() if mr.requested_date else None,
            }
            for mr in mrs
        ],
    }


@router.get(
    "/{vehicle_id}/repairs",
    response_model=ApiSuccess[list],
    dependencies=[ALL_ROLES],
)
def list_repairs(vehicle_id: uuid.UUID, db: DbSession):
    """List all repair jobs for a vehicle, newest first, with cost totals."""
    from app.models.vehicle import RepairJob, VehicleCost
    from app.models.material_request import MaterialRequest

    # Verify vehicle exists
    from app.models.vehicle import Vehicle
    v = db.get(Vehicle, vehicle_id)
    if not v:
        raise HTTPException(404, "Vehicle not found.")

    jobs = (
        db.query(RepairJob)
        .filter(RepairJob.vehicle_id == vehicle_id)
        .order_by(RepairJob.date_opened.desc())
        .all()
    )

    result = []
    for job in jobs:
        labour_costs = db.query(VehicleCost).filter(VehicleCost.repair_job_id == job.id).all()
        mrs = db.query(MaterialRequest).filter(MaterialRequest.repair_job_id == job.id).all()
        result.append(_build_repair_job_dict(job, labour_costs, mrs))

    return ApiSuccess(data=result)


@router.post(
    "/{vehicle_id}/repairs",
    response_model=ApiSuccess[dict],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_repair(vehicle_id: uuid.UUID, body: RepairJobCreate, db: DbSession, current_user: CurrentUser):
    """Create a new repair job for a vehicle."""
    from app.models.vehicle import Vehicle, RepairJob

    v = db.get(Vehicle, vehicle_id)
    if not v:
        raise HTTPException(404, "Vehicle not found.")

    job = RepairJob(
        vehicle_id=vehicle_id,
        title=body.title,
        description=body.description,
        status=body.status or "OPEN",
        workshop_name=body.workshop_name,
        date_opened=body.date_opened,
        date_closed=body.date_closed,
        odometer_at_repair=body.odometer_at_repair,
        notes=body.notes,
        created_by=current_user.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    return ApiSuccess(
        data=_build_repair_job_dict(job, [], []),
        message="Repair job created.",
        status_code=201,
    )


@router.patch(
    "/repairs/{repair_job_id}",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_repair(repair_job_id: uuid.UUID, body: RepairJobUpdate, db: DbSession, current_user: CurrentUser):
    """Update fields on a repair job."""
    from app.models.vehicle import RepairJob, VehicleCost
    from app.models.material_request import MaterialRequest

    job = db.get(RepairJob, repair_job_id)
    if not job:
        raise HTTPException(404, "Repair job not found.")

    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(job, field, val)

    db.commit()
    db.refresh(job)

    labour_costs = db.query(VehicleCost).filter(VehicleCost.repair_job_id == job.id).all()
    mrs = db.query(MaterialRequest).filter(MaterialRequest.repair_job_id == job.id).all()

    return ApiSuccess(data=_build_repair_job_dict(job, labour_costs, mrs))


@router.post(
    "/repairs/{repair_job_id}/costs",
    response_model=ApiSuccess[VehicleCostRead],
    status_code=201,
    dependencies=[ALL_ROLES],
)
def log_repair_cost(repair_job_id: uuid.UUID, body: VehicleCostCreate, db: DbSession, current_user: CurrentUser):
    """Log a labour/workshop cost directly against a repair job."""
    from app.models.vehicle import RepairJob, VehicleCost

    job = db.get(RepairJob, repair_job_id)
    if not job:
        raise HTTPException(404, "Repair job not found.")

    cost = VehicleCost(
        vehicle_id=job.vehicle_id,
        repair_job_id=repair_job_id,
        cost_type=body.cost_type,
        amount=body.amount,
        description=body.description,
        project_id=body.project_id,
        site_id=body.site_id,
        lot_id=body.lot_id,
        proof_image_url=body.proof_image_url,
        cost_date=body.cost_date,
        notes=body.notes,
        recorded_by=current_user.id,
        created_at=dt.now(timezone.utc),
    )
    db.add(cost)
    db.commit()
    db.refresh(cost)

    return ApiSuccess(
        data=VehicleCostRead.model_validate(cost).model_dump(),
        message="Cost logged against repair job.",
        status_code=201,
    )


# ---------------------------------------------------------------------------
# Repair job quotation / approval / invoice workflow
# ---------------------------------------------------------------------------

def _save_repair_file(file: Optional[UploadFile], subfolder: str) -> Optional[str]:
    """Save a repair quote or invoice file to storage."""
    if not file or not file.filename:
        return None
    validate_upload(file, allowed=DOCUMENT_MIMES)
    ext = os.path.splitext(file.filename)[1] or ".pdf"
    fname = f"{uuid.uuid4().hex}{ext}"
    content = file.file.read()
    return save_upload(content, f"repair_docs/{subfolder}/{fname}")


@router.post(
    "/repairs/{repair_job_id}/submit-quote",
    response_model=ApiSuccess[dict],
    dependencies=[ALL_ROLES],
)
def submit_repair_quote(
    repair_job_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    quote_amount: float = Form(...),
    workshop_name: Optional[str] = Form(None),
    quote_file: Optional[UploadFile] = File(None),
):
    """Upload a quotation for a repair job. Sets status to QUOTE_SUBMITTED."""
    from app.models.vehicle import RepairJob, VehicleCost
    from app.models.material_request import MaterialRequest

    job = db.get(RepairJob, repair_job_id)
    if not job:
        raise HTTPException(404, "Repair job not found.")

    file_url = _save_repair_file(quote_file, "quotes")
    job.quote_amount = quote_amount
    if file_url:
        job.quote_file_url = file_url
    if workshop_name:
        job.workshop_name = workshop_name
    job.status = "QUOTE_SUBMITTED"
    job.approval_stage = 0
    db.commit()
    db.refresh(job)

    labour_costs = db.query(VehicleCost).filter(VehicleCost.repair_job_id == job.id).all()
    mrs = db.query(MaterialRequest).filter(MaterialRequest.repair_job_id == job.id).all()
    return ApiSuccess(data=_build_repair_job_dict(job, labour_costs, mrs), message="Quote submitted.")


@router.post(
    "/repairs/{repair_job_id}/approve",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def approve_repair_quote(repair_job_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """Advance the approval stage of a repair job (stages 1 → 2 → 3 = fully approved)."""
    from app.models.vehicle import RepairJob, VehicleCost
    from app.models.material_request import MaterialRequest

    job = db.get(RepairJob, repair_job_id)
    if not job:
        raise HTTPException(404, "Repair job not found.")
    if job.status not in ("QUOTE_SUBMITTED", "QUOTE_APPROVED_1", "QUOTE_APPROVED_2"):
        raise HTTPException(400, f"Cannot approve: current status is '{job.status}'.")

    now = dt.now(timezone.utc)
    stage = (job.approval_stage or 0) + 1
    job.approval_stage = stage

    if stage == 1:
        job.approval_1_by = current_user.id
        job.approval_1_at = now
        job.status = "QUOTE_APPROVED_1"
    elif stage == 2:
        job.approval_2_by = current_user.id
        job.approval_2_at = now
        job.status = "QUOTE_APPROVED_2"
    elif stage >= 3:
        job.approval_3_by = current_user.id
        job.approval_3_at = now
        job.approval_stage = 3
        job.status = "APPROVED"

    db.commit()
    db.refresh(job)

    labour_costs = db.query(VehicleCost).filter(VehicleCost.repair_job_id == job.id).all()
    mrs = db.query(MaterialRequest).filter(MaterialRequest.repair_job_id == job.id).all()
    return ApiSuccess(data=_build_repair_job_dict(job, labour_costs, mrs), message=f"Stage {stage} approved.")


@router.post(
    "/repairs/{repair_job_id}/upload-invoice",
    response_model=ApiSuccess[dict],
    dependencies=[ALL_ROLES],
)
def upload_repair_invoice(
    repair_job_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    invoice_amount: float = Form(...),
    invoice_file: Optional[UploadFile] = File(None),
):
    """Upload the final invoice for a repair job. Sets status to INVOICE_UPLOADED."""
    from app.models.vehicle import RepairJob, VehicleCost
    from app.models.material_request import MaterialRequest

    job = db.get(RepairJob, repair_job_id)
    if not job:
        raise HTTPException(404, "Repair job not found.")
    if job.status not in ("APPROVED", "INVOICE_UPLOADED", "OPEN", "QUOTE_SUBMITTED", "QUOTE_APPROVED_1", "QUOTE_APPROVED_2"):
        raise HTTPException(400, f"Cannot upload invoice: current status is '{job.status}'.")

    file_url = _save_repair_file(invoice_file, "invoices")
    job.invoice_amount = invoice_amount
    if file_url:
        job.invoice_file_url = file_url
    job.status = "INVOICE_UPLOADED"
    db.commit()
    db.refresh(job)

    labour_costs = db.query(VehicleCost).filter(VehicleCost.repair_job_id == job.id).all()
    mrs = db.query(MaterialRequest).filter(MaterialRequest.repair_job_id == job.id).all()
    return ApiSuccess(data=_build_repair_job_dict(job, labour_costs, mrs), message="Invoice uploaded.")


# ---------------------------------------------------------------------------
# Fuel deliveries (bulk site diesel tank)
# ---------------------------------------------------------------------------

def _delivery_dict(delivery, dispensed_litres: float) -> dict:
    return {
        "id": str(delivery.id),
        "site_id": str(delivery.site_id),
        "project_id": str(delivery.project_id) if delivery.project_id else None,
        "delivery_date": delivery.delivery_date.isoformat(),
        "fuel_type": delivery.fuel_type,
        "litres_delivered": float(delivery.litres_delivered),
        "litres_dispensed": round(dispensed_litres, 2),
        "litres_remaining": round(float(delivery.litres_delivered) - dispensed_litres, 2),
        "cost_per_litre": float(delivery.cost_per_litre) if delivery.cost_per_litre else None,
        "supplier_name": delivery.supplier_name,
        "invoice_number": delivery.invoice_number,
        "notes": delivery.notes,
        "recorded_by": str(delivery.recorded_by) if delivery.recorded_by else None,
        "created_at": delivery.created_at.isoformat(),
    }


@router.get("/fuel-deliveries/", response_model=ApiSuccess[list], dependencies=[ALL_ROLES])
def list_fuel_deliveries(
    db: DbSession,
    site_id: uuid.UUID = Query(...),
):
    """List all bulk fuel deliveries for a site, newest first, with running balance."""
    from app.models.vehicle import FuelDelivery
    from app.models.fuel import FuelLog

    deliveries = (
        db.query(FuelDelivery)
        .filter(FuelDelivery.site_id == site_id)
        .order_by(FuelDelivery.delivery_date.desc(), FuelDelivery.created_at.desc())
        .all()
    )

    result = []
    for d in deliveries:
        dispensed = db.query(func.coalesce(func.sum(FuelLog.litres), 0)).filter(
            FuelLog.fuel_delivery_id == d.id
        ).scalar() or 0.0
        result.append(_delivery_dict(d, float(dispensed)))
    return ApiSuccess(data=result)


@router.post("/fuel-deliveries/", response_model=ApiSuccess[dict], status_code=201, dependencies=[OFFICE_AND_ABOVE])
def create_fuel_delivery(
    db: DbSession,
    current_user: CurrentUser,
    site_id: uuid.UUID = Form(...),
    project_id: Optional[uuid.UUID] = Form(None),
    delivery_date: str = Form(...),
    fuel_type: str = Form("DIESEL"),
    litres_delivered: float = Form(...),
    cost_per_litre: Optional[float] = Form(None),
    supplier_name: Optional[str] = Form(None),
    invoice_number: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
):
    """Record a new bulk diesel delivery to a site."""
    from app.models.vehicle import FuelDelivery

    if project_id and fuel_service._fuel_management_is_live(db, project_id):
        raise HTTPException(
            422,
            "This project has moved to Fuel Management for fuel tracking. "
            "Record deliveries via Fuel Management instead of the legacy vehicle fuel delivery flow.",
        )

    d = FuelDelivery(
        site_id=site_id,
        project_id=project_id,
        delivery_date=date.fromisoformat(delivery_date),
        fuel_type=fuel_type,
        litres_delivered=litres_delivered,
        cost_per_litre=cost_per_litre,
        supplier_name=supplier_name,
        invoice_number=invoice_number,
        notes=notes,
        recorded_by=current_user.id,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return ApiSuccess(data=_delivery_dict(d, 0.0), message="Fuel delivery recorded.", status_code=201)


@router.post(
    "/{vehicle_id}/fill-from-delivery",
    response_model=ApiSuccess[dict],
    status_code=201,
    dependencies=[ALL_ROLES],
)
def fill_vehicle_from_delivery(
    vehicle_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    delivery_id: uuid.UUID = Form(...),
    litres: float = Form(...),
    hours_reading: Optional[float] = Form(None),
    odometer_reading: Optional[float] = Form(None),
    fuelled_by: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
):
    """Fill a vehicle from a bulk delivery. Creates a fuel log linked to the delivery."""
    from app.models.vehicle import Vehicle, FuelDelivery
    from app.models.fuel import FuelLog

    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(404, "Vehicle not found.")

    delivery = db.get(FuelDelivery, delivery_id)
    if not delivery:
        raise HTTPException(404, "Fuel delivery not found.")

    project_id = delivery.project_id or vehicle.assigned_project_id
    if not project_id:
        raise HTTPException(400, "Vehicle must be assigned to a project before logging fuel.")
    if fuel_service._fuel_management_is_live(db, project_id):
        raise HTTPException(
            422,
            "This project has moved to Fuel Management for fuel tracking. "
            "Record new fuel fills via Fuel Management > Issue Fuel instead of the legacy vehicle fuel delivery flow.",
        )

    # Check remaining balance
    from sqlalchemy import func as sqlfunc
    from app.models.enums import FuelType as FuelTypeEnum, FuelUsageType
    dispensed = db.query(sqlfunc.coalesce(sqlfunc.sum(FuelLog.litres), 0)).filter(
        FuelLog.fuel_delivery_id == delivery_id
    ).scalar() or 0.0
    remaining = float(delivery.litres_delivered) - float(dispensed)
    if litres > remaining + 0.01:
        raise HTTPException(400, f"Only {remaining:.1f}L remaining in this delivery.")

    # Update hours / odometer on vehicle
    if hours_reading is not None:
        vehicle.current_hours_reading = hours_reading
    if odometer_reading is not None:
        vehicle.current_odometer_km = odometer_reading

    now = dt.now(timezone.utc)
    fuel_type_val = FuelTypeEnum(delivery.fuel_type) if delivery.fuel_type in [e.value for e in FuelTypeEnum] else FuelTypeEnum.DIESEL
    log = FuelLog(
        project_id=project_id,
        site_id=delivery.site_id,
        vehicle_id=vehicle_id,
        fuel_delivery_id=delivery_id,
        fuel_type=fuel_type_val,
        usage_type=FuelUsageType.EQUIPMENT,
        equipment_ref=vehicle.registration,
        litres=litres,
        cost_per_litre=delivery.cost_per_litre,
        fuelled_by=fuelled_by,
        recorded_by=current_user.id,
        fuel_date=now,
        odometer_reading=odometer_reading,
        hours_reading=hours_reading,
        notes=notes,
    )
    db.add(log)
    db.commit()
    db.refresh(delivery)

    new_dispensed = float(dispensed) + litres
    return ApiSuccess(
        data=_delivery_dict(delivery, new_dispensed),
        message=f"{litres:.1f}L logged for {vehicle.registration}.",
        status_code=201,
    )


# ---------------------------------------------------------------------------
# Vehicle transfer requests
# ---------------------------------------------------------------------------

@router.post(
    "/{vehicle_id}/request-transfer",
    response_model=ApiSuccess[dict],
    status_code=201,
    dependencies=[ALL_ROLES],
)
def request_vehicle_transfer(
    vehicle_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    to_site_id: uuid.UUID = Form(...),
    reason: Optional[str] = Form(None),
):
    """Request to move a vehicle to a different site (requires office approval)."""
    from app.models.vehicle import Vehicle, VehicleTransferRequest

    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(404, "Vehicle not found.")

    req = VehicleTransferRequest(
        vehicle_id=vehicle_id,
        from_site_id=vehicle.assigned_site_id,
        to_site_id=to_site_id,
        reason=reason,
        status="PENDING",
        requested_by=current_user.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return ApiSuccess(data=_transfer_dict(req), message="Transfer request submitted.", status_code=201)


@router.get("/transfer-requests/", response_model=ApiSuccess[list], dependencies=[ALL_ROLES])
def list_transfer_requests(
    db: DbSession,
    vehicle_id: Optional[uuid.UUID] = Query(None),
    site_id: Optional[uuid.UUID] = Query(None),
):
    """List transfer requests, optionally filtered by vehicle or site."""
    from app.models.vehicle import VehicleTransferRequest

    q = db.query(VehicleTransferRequest)
    if vehicle_id:
        q = q.filter(VehicleTransferRequest.vehicle_id == vehicle_id)
    if site_id:
        q = q.filter(
            (VehicleTransferRequest.from_site_id == site_id) |
            (VehicleTransferRequest.to_site_id == site_id)
        )
    reqs = q.order_by(VehicleTransferRequest.created_at.desc()).all()
    return ApiSuccess(data=[_transfer_dict(r) for r in reqs])


@router.post(
    "/transfer-requests/{request_id}/approve",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def approve_transfer_request(request_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """Approve a vehicle transfer request and move the vehicle to the new site."""
    from app.models.vehicle import Vehicle, VehicleTransferRequest

    req = db.get(VehicleTransferRequest, request_id)
    if not req:
        raise HTTPException(404, "Transfer request not found.")
    if req.status != "PENDING":
        raise HTTPException(400, f"Request is already '{req.status}'.")

    vehicle = db.get(Vehicle, req.vehicle_id)
    if vehicle:
        vehicle.assigned_site_id = req.to_site_id

    now = dt.now(timezone.utc)
    req.status = "APPROVED"
    req.approved_by = current_user.id
    req.approved_at = now
    db.commit()
    db.refresh(req)
    return ApiSuccess(data=_transfer_dict(req), message="Transfer approved. Vehicle moved.")


@router.post(
    "/transfer-requests/{request_id}/reject",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def reject_transfer_request(
    request_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    rejected_reason: Optional[str] = Form(None),
):
    """Reject a vehicle transfer request."""
    from app.models.vehicle import VehicleTransferRequest

    req = db.get(VehicleTransferRequest, request_id)
    if not req:
        raise HTTPException(404, "Transfer request not found.")
    if req.status != "PENDING":
        raise HTTPException(400, f"Request is already '{req.status}'.")

    req.status = "REJECTED"
    req.rejected_reason = rejected_reason
    db.commit()
    db.refresh(req)
    return ApiSuccess(data=_transfer_dict(req), message="Transfer request rejected.")


def _transfer_dict(req) -> dict:
    return {
        "id": str(req.id),
        "vehicle_id": str(req.vehicle_id),
        "from_site_id": str(req.from_site_id) if req.from_site_id else None,
        "to_site_id": str(req.to_site_id),
        "reason": req.reason,
        "status": req.status,
        "requested_by": str(req.requested_by) if req.requested_by else None,
        "approved_by": str(req.approved_by) if req.approved_by else None,
        "approved_at": req.approved_at.isoformat() if req.approved_at else None,
        "rejected_reason": req.rejected_reason,
        "created_at": req.created_at.isoformat(),
    }
