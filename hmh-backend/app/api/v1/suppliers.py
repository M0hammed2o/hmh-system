"""Supplier routes."""

import uuid

from fastapi import APIRouter, Query

from app.dependencies import ALL_ROLES, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.supplier import SupplierCreate, SupplierRead, SupplierUpdate
from app.services import supplier_service

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get(
    "/",
    response_model=ApiSuccess[list[SupplierRead]],
    dependencies=[ALL_ROLES],
)
def list_suppliers(
    db: DbSession,
    include_inactive: bool = Query(False),
):
    suppliers = supplier_service.list_suppliers(db, include_inactive)
    return ApiSuccess(data=[SupplierRead.model_validate(s) for s in suppliers])


@router.get(
    "/{supplier_id}",
    response_model=ApiSuccess[SupplierRead],
    dependencies=[ALL_ROLES],
)
def get_supplier(supplier_id: uuid.UUID, db: DbSession):
    s = supplier_service.get_supplier(db, supplier_id)
    return ApiSuccess(data=SupplierRead.model_validate(s))


@router.post(
    "/",
    response_model=ApiSuccess[SupplierRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_supplier(body: SupplierCreate, db: DbSession):
    s = supplier_service.create_supplier(db, body)
    return ApiSuccess(data=SupplierRead.model_validate(s), message="Supplier created.")


@router.patch(
    "/{supplier_id}",
    response_model=ApiSuccess[SupplierRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_supplier(supplier_id: uuid.UUID, body: SupplierUpdate, db: DbSession):
    s = supplier_service.update_supplier(db, supplier_id, body)
    return ApiSuccess(data=SupplierRead.model_validate(s), message="Supplier updated.")
