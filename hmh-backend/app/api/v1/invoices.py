"""Invoice routes."""

import uuid

from fastapi import APIRouter

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.invoice import InvoiceCreate, InvoiceRead, InvoiceUpdate
from app.services import invoice_service

project_invoice_router = APIRouter(
    prefix="/projects/{project_id}/invoices",
    tags=["invoices"],
)
invoice_router = APIRouter(prefix="/invoices", tags=["invoices"])


@project_invoice_router.get(
    "/",
    response_model=ApiSuccess[list[InvoiceRead]],
    dependencies=[ALL_ROLES],
)
def list_invoices(project_id: uuid.UUID, db: DbSession):
    invoices = invoice_service.list_invoices(db, project_id)
    return ApiSuccess(data=[InvoiceRead.model_validate(i) for i in invoices])


@project_invoice_router.post(
    "/",
    response_model=ApiSuccess[InvoiceRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_invoice(
    project_id: uuid.UUID,
    body: InvoiceCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    invoice = invoice_service.create_invoice(db, project_id, body, current_user.id)
    return ApiSuccess(data=InvoiceRead.model_validate(invoice), message="Invoice captured.")


@invoice_router.get(
    "/{invoice_id}",
    response_model=ApiSuccess[InvoiceRead],
    dependencies=[ALL_ROLES],
)
def get_invoice(invoice_id: uuid.UUID, db: DbSession):
    invoice = invoice_service.get_invoice(db, invoice_id)
    return ApiSuccess(data=InvoiceRead.model_validate(invoice))


@invoice_router.patch(
    "/{invoice_id}",
    response_model=ApiSuccess[InvoiceRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_invoice(invoice_id: uuid.UUID, body: InvoiceUpdate, db: DbSession):
    invoice = invoice_service.update_invoice(db, invoice_id, body)
    return ApiSuccess(data=InvoiceRead.model_validate(invoice), message="Invoice updated.")
