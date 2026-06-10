"""Quotation routes."""

import uuid

from fastapi import APIRouter, Query

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.quotation import QuotationCreate, QuotationRead, QuotationUpdate
from app.services import quotation_service

router = APIRouter(prefix="/quotations", tags=["quotations"])


@router.get(
    "/",
    response_model=ApiSuccess[list[QuotationRead]],
    dependencies=[ALL_ROLES],
)
def list_quotations(
    db: DbSession,
    supplier_id: uuid.UUID = Query(..., description="Filter by supplier"),
):
    qs = quotation_service.list_by_supplier(db, supplier_id)
    return ApiSuccess(data=[QuotationRead.model_validate(q) for q in qs])


@router.get(
    "/{quotation_id}",
    response_model=ApiSuccess[QuotationRead],
    dependencies=[ALL_ROLES],
)
def get_quotation(quotation_id: uuid.UUID, db: DbSession):
    q = quotation_service.get_quotation(db, quotation_id)
    return ApiSuccess(data=QuotationRead.model_validate(q))


@router.post(
    "/",
    response_model=ApiSuccess[QuotationRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_quotation(body: QuotationCreate, db: DbSession, current_user: CurrentUser):
    q = quotation_service.create_quotation(db, body, current_user.id)
    return ApiSuccess(data=QuotationRead.model_validate(q), message="Quotation created.")


@router.patch(
    "/{quotation_id}",
    response_model=ApiSuccess[QuotationRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_quotation(quotation_id: uuid.UUID, body: QuotationUpdate, db: DbSession):
    q = quotation_service.update_quotation(db, quotation_id, body)
    return ApiSuccess(data=QuotationRead.model_validate(q), message="Quotation updated.")


@router.delete(
    "/{quotation_id}",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def delete_quotation(quotation_id: uuid.UUID, db: DbSession):
    quotation_service.delete_quotation(db, quotation_id)
    return ApiSuccess(data={"quotation_id": str(quotation_id)}, message="Quotation deleted.")
