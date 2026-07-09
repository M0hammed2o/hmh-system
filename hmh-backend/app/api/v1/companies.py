"""Company CRUD + supplier-link routes."""

import uuid

from fastapi import APIRouter

from app.dependencies import ALL_ROLES, DbSession, OFFICE_ADMIN_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.company import (
    CompanyCreate,
    CompanyRead,
    CompanySupplierLinkRead,
    CompanyUpdate,
    CompanyWithSuppliersRead,
)
from app.schemas.supplier import SupplierRead
from app.services import company_service

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("/", response_model=ApiSuccess[list[CompanyRead]], dependencies=[ALL_ROLES])
def list_companies(db: DbSession):
    companies = company_service.list_companies(db)
    return ApiSuccess(data=[CompanyRead.model_validate(c) for c in companies])


@router.post(
    "/",
    response_model=ApiSuccess[CompanyRead],
    status_code=201,
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def create_company(body: CompanyCreate, db: DbSession):
    company = company_service.create_company(db, body)
    return ApiSuccess(data=CompanyRead.model_validate(company), message="Company created.")


@router.get("/{company_id}", response_model=ApiSuccess[CompanyWithSuppliersRead], dependencies=[ALL_ROLES])
def get_company(company_id: uuid.UUID, db: DbSession):
    company = company_service.get_company(db, company_id)
    suppliers = company_service.get_company_suppliers(db, company_id)
    result = CompanyWithSuppliersRead(
        **CompanyRead.model_validate(company).model_dump(),
        suppliers=[SupplierRead.model_validate(s) for s in suppliers],
    )
    return ApiSuccess(data=result)


@router.patch(
    "/{company_id}",
    response_model=ApiSuccess[CompanyRead],
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def update_company(company_id: uuid.UUID, body: CompanyUpdate, db: DbSession):
    company = company_service.update_company(db, company_id, body)
    return ApiSuccess(data=CompanyRead.model_validate(company), message="Company updated.")


@router.delete(
    "/{company_id}",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def delete_company(company_id: uuid.UUID, db: DbSession):
    result = company_service.delete_company(db, company_id)
    return ApiSuccess(data=result, message=f"Company '{result['deleted_company']}' deleted.")


@router.post(
    "/{company_id}/suppliers/{supplier_id}",
    response_model=ApiSuccess[CompanySupplierLinkRead],
    status_code=201,
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def link_supplier(company_id: uuid.UUID, supplier_id: uuid.UUID, db: DbSession):
    link = company_service.link_supplier(db, company_id, supplier_id)
    return ApiSuccess(
        data=CompanySupplierLinkRead.model_validate(link),
        message="Supplier linked to company.",
    )


@router.delete(
    "/{company_id}/suppliers/{supplier_id}",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def unlink_supplier(company_id: uuid.UUID, supplier_id: uuid.UUID, db: DbSession):
    company_service.unlink_supplier(db, company_id, supplier_id)
    return ApiSuccess(data={}, message="Supplier unlinked.")


@router.get(
    "/project/{project_id}/suppliers",
    response_model=ApiSuccess[list[SupplierRead]],
    dependencies=[ALL_ROLES],
)
def get_project_suppliers(project_id: uuid.UUID, db: DbSession):
    """
    Returns the allowed suppliers for a project.
    If the project has a linked company, returns only that company's suppliers.
    If no company is linked, returns all active suppliers.
    """
    from app.models.supplier import Supplier as SupplierModel

    suppliers = company_service.get_project_suppliers(db, project_id)
    if suppliers is None:
        # No company restriction — return all active suppliers
        suppliers = (
            db.query(SupplierModel)
            .filter(SupplierModel.is_active == True)  # noqa: E712
            .order_by(SupplierModel.name)
            .all()
        )
    return ApiSuccess(data=[SupplierRead.model_validate(s) for s in suppliers])
