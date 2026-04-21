"""Fuel log routes.

Two-router pattern:
  project_fuel_router  — /projects/{project_id}/fuel/   (list, create)
  fuel_router          — /fuel/{log_id}                  (get, update)
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Query

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.fuel import FuelLogCreate, FuelLogRead, FuelLogUpdate
from app.services import fuel_service

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
