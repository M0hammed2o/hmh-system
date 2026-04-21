"""Delivery routes."""

import uuid

from fastapi import APIRouter

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.delivery import DeliveryCreate, DeliveryRead, DeliveryUpdate
from app.services import delivery_service

project_delivery_router = APIRouter(
    prefix="/projects/{project_id}/deliveries",
    tags=["deliveries"],
)
delivery_router = APIRouter(prefix="/deliveries", tags=["deliveries"])


@project_delivery_router.get(
    "/",
    response_model=ApiSuccess[list[DeliveryRead]],
    dependencies=[ALL_ROLES],
)
def list_deliveries(project_id: uuid.UUID, db: DbSession):
    deliveries = delivery_service.list_deliveries(db, project_id)
    return ApiSuccess(data=[DeliveryRead.model_validate(d) for d in deliveries])


@project_delivery_router.post(
    "/",
    response_model=ApiSuccess[DeliveryRead],
    status_code=201,
    dependencies=[ALL_ROLES],
)
def create_delivery(
    project_id: uuid.UUID,
    body: DeliveryCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    delivery = delivery_service.create_delivery(db, project_id, body, current_user.id)
    return ApiSuccess(
        data=DeliveryRead.model_validate(delivery),
        message="Delivery recorded.",
    )


@delivery_router.get(
    "/{delivery_id}",
    response_model=ApiSuccess[DeliveryRead],
    dependencies=[ALL_ROLES],
)
def get_delivery(delivery_id: uuid.UUID, db: DbSession):
    delivery = delivery_service.get_delivery(db, delivery_id)
    return ApiSuccess(data=DeliveryRead.model_validate(delivery))


@delivery_router.patch(
    "/{delivery_id}",
    response_model=ApiSuccess[DeliveryRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_delivery(delivery_id: uuid.UUID, body: DeliveryUpdate, db: DbSession):
    delivery = delivery_service.update_delivery(db, delivery_id, body)
    return ApiSuccess(data=DeliveryRead.model_validate(delivery), message="Delivery updated.")
