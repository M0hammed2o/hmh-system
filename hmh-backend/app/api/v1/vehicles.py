"""Vehicle and fleet cost routes."""

import uuid
from datetime import datetime as dt, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

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
from app.services import vehicle_service

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


# ---------------------------------------------------------------------------
# Vehicle CRUD
# ---------------------------------------------------------------------------

@router.get("/", response_model=ApiSuccess[list[VehicleRead]], dependencies=[ALL_ROLES])
def list_vehicles(
    db: DbSession,
    project_id: Optional[uuid.UUID] = Query(None),
):
    vehicles = vehicle_service.list_vehicles(db, project_id)
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
