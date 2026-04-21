"""Payment routes."""

import uuid

from fastapi import APIRouter

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.payment import PaymentCreate, PaymentRead, PaymentUpdate
from app.services import payment_service

project_payment_router = APIRouter(
    prefix="/projects/{project_id}/payments",
    tags=["payments"],
)
payment_router = APIRouter(prefix="/payments", tags=["payments"])


@project_payment_router.get(
    "/",
    response_model=ApiSuccess[list[PaymentRead]],
    dependencies=[ALL_ROLES],
)
def list_payments(project_id: uuid.UUID, db: DbSession):
    payments = payment_service.list_payments(db, project_id)
    return ApiSuccess(data=[PaymentRead.model_validate(p) for p in payments])


@project_payment_router.post(
    "/",
    response_model=ApiSuccess[PaymentRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_payment(
    project_id: uuid.UUID,
    body: PaymentCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    payment = payment_service.create_payment(db, project_id, body, current_user.id)
    return ApiSuccess(data=PaymentRead.model_validate(payment), message="Payment captured.")


@payment_router.get(
    "/{payment_id}",
    response_model=ApiSuccess[PaymentRead],
    dependencies=[ALL_ROLES],
)
def get_payment(payment_id: uuid.UUID, db: DbSession):
    payment = payment_service.get_payment(db, payment_id)
    return ApiSuccess(data=PaymentRead.model_validate(payment))


@payment_router.patch(
    "/{payment_id}",
    response_model=ApiSuccess[PaymentRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_payment(
    payment_id: uuid.UUID, body: PaymentUpdate, db: DbSession, current_user: CurrentUser
):
    payment = payment_service.update_payment(db, payment_id, body, current_user.id)
    return ApiSuccess(data=PaymentRead.model_validate(payment), message="Payment updated.")
