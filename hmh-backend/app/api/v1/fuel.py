"""Fuel log routes.

Two-router pattern:
  project_fuel_router  — /projects/{project_id}/fuel/   (list, create)
  fuel_router          — /fuel/{log_id}                  (get, update)
"""

import os
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.core.config import settings
from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.fuel import FuelLogCreate, FuelLogRead, FuelLogUpdate
from app.services import fuel_service


def _save_fuel_photo(file: Optional[UploadFile], subfolder: str) -> Optional[str]:
    """Save a fuel evidence photo and return the relative URL path."""
    if not file or not file.filename:
        return None
    import asyncio, inspect
    save_dir = os.path.join(settings.UPLOAD_DIR, "fuel_evidence", subfolder)
    os.makedirs(save_dir, exist_ok=True)
    ext  = os.path.splitext(file.filename)[1] or ".jpg"
    fname = f"{uuid.uuid4().hex}{ext}"
    content = file.file.read()
    with open(os.path.join(save_dir, fname), "wb") as fh:
        fh.write(content)
    return f"/uploads/fuel_evidence/{subfolder}/{fname}"

project_fuel_router = APIRouter(
    prefix="/projects/{project_id}/fuel",
    tags=["fuel"],
)
fuel_router = APIRouter(prefix="/fuel", tags=["fuel"])


@project_fuel_router.get(
    "/",
    response_model=ApiSuccess[list[FuelLogRead]],
    dependencies=[ALL_ROLES],
)
def list_fuel_logs(
    project_id: uuid.UUID,
    db: DbSession,
    site_id: Optional[uuid.UUID] = Query(default=None),
    limit: int = Query(default=200, le=500),
):
    logs = fuel_service.list_fuel_logs(db, project_id, site_id=site_id, limit=limit)
    return ApiSuccess(data=[FuelLogRead.model_validate(l) for l in logs])


@project_fuel_router.post(
    "/",
    response_model=ApiSuccess[FuelLogRead],
    status_code=201,
    dependencies=[ALL_ROLES],
)
def create_fuel_log(
    project_id: uuid.UUID,
    body: FuelLogCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    log = fuel_service.create_fuel_log(db, project_id, body, current_user.id)
    return ApiSuccess(data=FuelLogRead.model_validate(log), message="Fuel log recorded.")


@project_fuel_router.post(
    "/with-evidence",
    response_model=ApiSuccess[FuelLogRead],
    status_code=201,
    dependencies=[ALL_ROLES],
)
async def create_fuel_log_with_evidence(
    project_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    # Core fields as form
    fuel_type:        str   = Form(...),
    usage_type:       str   = Form(...),
    litres:           float = Form(...),
    cost_per_litre:   Optional[float] = Form(None),
    equipment_ref:    Optional[str]   = Form(None),
    fuelled_by:       Optional[str]   = Form(None),
    site_id:          Optional[str]   = Form(None),
    vehicle_id:       Optional[str]   = Form(None),
    fuel_date:        Optional[str]   = Form(None),
    odometer_reading: Optional[float] = Form(None),
    notes:            Optional[str]   = Form(None),
    # Evidence photos
    photo_odometer: Optional[UploadFile] = File(None),
    photo_pump:     Optional[UploadFile] = File(None),
    photo_invoice:  Optional[UploadFile] = File(None),
):
    """Create a fuel log with optional evidence photos (multipart form)."""
    from datetime import datetime, timezone
    from app.models.enums import FuelType, FuelUsageType

    body = FuelLogCreate(
        fuel_type        = FuelType(fuel_type),
        usage_type       = FuelUsageType(usage_type),
        litres           = litres,
        cost_per_litre   = cost_per_litre,
        equipment_ref    = equipment_ref,
        fuelled_by       = fuelled_by,
        site_id          = uuid.UUID(site_id)  if site_id   else None,
        vehicle_id       = uuid.UUID(vehicle_id) if vehicle_id else None,
        fuel_date        = datetime.fromisoformat(fuel_date) if fuel_date else None,
        odometer_reading = odometer_reading,
        notes            = notes,
    )
    log = fuel_service.create_fuel_log(db, project_id, body, current_user.id)

    # Save photos and attach URLs
    if photo_odometer and photo_odometer.filename:
        log.photo_odometer = _save_fuel_photo(photo_odometer, "odometer")
    if photo_pump and photo_pump.filename:
        log.photo_pump = _save_fuel_photo(photo_pump, "pump")
    if photo_invoice and photo_invoice.filename:
        log.photo_invoice = _save_fuel_photo(photo_invoice, "invoice")

    db.commit()
    db.refresh(log)
    return ApiSuccess(data=FuelLogRead.model_validate(log), message="Fuel log with evidence recorded.")


@project_fuel_router.get(
    "/vehicle/{vehicle_id}",
    response_model=ApiSuccess[list[FuelLogRead]],
    dependencies=[ALL_ROLES],
)
def list_fuel_logs_for_vehicle(project_id: uuid.UUID, vehicle_id: uuid.UUID, db: DbSession):
    """List all fuel logs for a specific vehicle within a project."""
    from app.models.fuel import FuelLog
    logs = (
        db.query(FuelLog)
        .filter(FuelLog.project_id == project_id, FuelLog.vehicle_id == vehicle_id)
        .order_by(FuelLog.fuel_date.desc())
        .all()
    )
    return ApiSuccess(data=[FuelLogRead.model_validate(l) for l in logs])


@fuel_router.get(
    "/{log_id}",
    response_model=ApiSuccess[FuelLogRead],
    dependencies=[ALL_ROLES],
)
def get_fuel_log(log_id: uuid.UUID, db: DbSession):
    log = fuel_service.get_fuel_log(db, log_id)
    return ApiSuccess(data=FuelLogRead.model_validate(log))


@fuel_router.patch(
    "/{log_id}",
    response_model=ApiSuccess[FuelLogRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_fuel_log(log_id: uuid.UUID, body: FuelLogUpdate, db: DbSession):
    log = fuel_service.update_fuel_log(db, log_id, body)
    return ApiSuccess(data=FuelLogRead.model_validate(log), message="Fuel log updated.")


@fuel_router.delete("/{log_id}", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def delete_fuel_log(log_id: uuid.UUID, db: DbSession):
    """Hard-delete a fuel log entry."""
    from app.models.fuel import FuelLog
    log = db.get(FuelLog, log_id)
    if not log:
        raise HTTPException(404, "Fuel log not found.")
    db.delete(log)
    db.commit()
    return ApiSuccess(data={"log_id": str(log_id)}, message="Fuel log deleted.")
