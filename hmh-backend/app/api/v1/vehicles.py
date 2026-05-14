"""Vehicle and fleet cost routes."""

import uuid
from typing import Optional

from fastapi import APIRouter, Query

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.vehicle import VehicleCostCreate, VehicleCostRead, VehicleCreate, VehicleRead, VehicleUpdate
from app.services import vehicle_service

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


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
