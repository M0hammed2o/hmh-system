"""Lots routes."""

import uuid

from fastapi import APIRouter

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.lot import LotCreate, LotRead, LotUpdate
from app.services import lot_service

project_lots_router = APIRouter(
    prefix="/projects/{project_id}/lots",
    tags=["lots"],
)
lots_router = APIRouter(prefix="/lots", tags=["lots"])


@project_lots_router.get(
    "/",
    response_model=ApiSuccess[list[LotRead]],
    dependencies=[ALL_ROLES],
)
def list_lots(project_id: uuid.UUID, db: DbSession):
    lots = lot_service.list_lots(db, project_id)
    return ApiSuccess(data=[LotRead.model_validate(l) for l in lots])


@project_lots_router.post(
    "/",
    response_model=ApiSuccess[LotRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_lot(project_id: uuid.UUID, body: LotCreate, db: DbSession):
    lot = lot_service.create_lot(db, project_id, body)
    return ApiSuccess(data=LotRead.model_validate(lot), message="Lot created successfully.")


@lots_router.get(
    "/{lot_id}",
    response_model=ApiSuccess[LotRead],
    dependencies=[ALL_ROLES],
)
def get_lot(lot_id: uuid.UUID, db: DbSession):
    lot = lot_service.get_lot(db, lot_id)
    return ApiSuccess(data=LotRead.model_validate(lot))


@lots_router.patch(
    "/{lot_id}",
    response_model=ApiSuccess[LotRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_lot(lot_id: uuid.UUID, body: LotUpdate, db: DbSession):
    lot = lot_service.update_lot(db, lot_id, body)
    return ApiSuccess(data=LotRead.model_validate(lot), message="Lot updated successfully.")
