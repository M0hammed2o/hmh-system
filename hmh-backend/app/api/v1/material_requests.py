"""Material Request routes."""

import uuid

from fastapi import APIRouter

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.material_request import (
    MaterialRequestCreate, MaterialRequestRead, MaterialRequestUpdate,
)
from app.services import mr_service

project_mr_router = APIRouter(
    prefix="/projects/{project_id}/material-requests",
    tags=["material-requests"],
)
mr_router = APIRouter(prefix="/material-requests", tags=["material-requests"])


@project_mr_router.get(
    "/",
    response_model=ApiSuccess[list[MaterialRequestRead]],
    dependencies=[ALL_ROLES],
)
def list_material_requests(project_id: uuid.UUID, db: DbSession):
    mrs = mr_service.list_requests(db, project_id)
    return ApiSuccess(data=[MaterialRequestRead.model_validate(m) for m in mrs])


@project_mr_router.post(
    "/",
    response_model=ApiSuccess[MaterialRequestRead],
    status_code=201,
    dependencies=[ALL_ROLES],
)
def create_material_request(
    project_id: uuid.UUID,
    body: MaterialRequestCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    mr = mr_service.create_request(db, project_id, body, current_user.id)
    return ApiSuccess(
        data=MaterialRequestRead.model_validate(mr),
        message="Material request created.",
    )


@mr_router.get(
    "/{mr_id}",
    response_model=ApiSuccess[MaterialRequestRead],
    dependencies=[ALL_ROLES],
)
def get_material_request(mr_id: uuid.UUID, db: DbSession):
    mr = mr_service.get_request(db, mr_id)
    return ApiSuccess(data=MaterialRequestRead.model_validate(mr))


@mr_router.patch(
    "/{mr_id}",
    response_model=ApiSuccess[MaterialRequestRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_material_request(
    mr_id: uuid.UUID,
    body: MaterialRequestUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    mr = mr_service.update_request(db, mr_id, body, current_user.id)
    return ApiSuccess(
        data=MaterialRequestRead.model_validate(mr),
        message="Material request updated.",
    )
