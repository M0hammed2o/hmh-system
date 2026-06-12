"""Municipality Invoice routes — manual capture + Excel export."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE, WRITE_ROLES, check_project_access
from app.models.municipality_invoice import MunicipalityInvoice, MunicipalityInvoiceItem
from app.schemas.common import ApiSuccess
from app.services import muni_invoice_service

project_muni_router = APIRouter(
    prefix="/projects/{project_id}/municipality-invoices",
    tags=["municipality-invoices"],
)
muni_router = APIRouter(prefix="/municipality-invoices", tags=["municipality-invoices"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class InvoiceItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:          uuid.UUID
    sort_order:  int
    line_number: Optional[str] = None
    description: str
    quantity:    Optional[float] = None
    unit_price:  Optional[float] = None
    total:       Optional[float] = None
    disc_pct:    Optional[float] = None
    comments:    Optional[str]   = None


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             uuid.UUID
    invoice_number: str
    cert_number:    Optional[str]  = None
    project_id:     uuid.UUID
    invoice_date:   date
    due_date:       Optional[date] = None
    client_name:    str
    client_vat_no:  Optional[str]  = None
    client_address: Optional[str]  = None
    company_email:  Optional[str]  = None
    project_description: Optional[str] = None
    contract_reference:  Optional[str] = None
    subtotal:        float
    previously_paid: Optional[float] = None
    vat_rate:        float
    vat_amount:      float
    total_due:       float
    notes:          Optional[str] = None
    bank_name:      Optional[str] = None
    account_number: Optional[str] = None
    branch_name:    Optional[str] = None
    branch_code:    Optional[str] = None
    status:         str
    created_by:     Optional[uuid.UUID] = None
    created_at:     Optional[str]       = None
    items:          list[InvoiceItemRead] = []

    @classmethod
    def from_orm_full(cls, inv: MunicipalityInvoice) -> "InvoiceRead":
        return cls(
            id=inv.id,
            invoice_number=inv.invoice_number,
            cert_number=inv.cert_number,
            project_id=inv.project_id,
            invoice_date=inv.invoice_date,
            due_date=inv.due_date,
            client_name=inv.client_name,
            client_vat_no=inv.client_vat_no,
            client_address=inv.client_address,
            company_email=inv.company_email,
            project_description=inv.project_description,
            contract_reference=inv.contract_reference,
            subtotal=float(inv.subtotal or 0),
            previously_paid=float(inv.previously_paid) if inv.previously_paid is not None else None,
            vat_rate=float(inv.vat_rate or 15),
            vat_amount=float(inv.vat_amount or 0),
            total_due=float(inv.total_due or 0),
            notes=inv.notes,
            bank_name=inv.bank_name,
            account_number=inv.account_number,
            branch_name=inv.branch_name,
            branch_code=inv.branch_code,
            status=inv.status,
            created_by=inv.created_by,
            created_at=inv.created_at.isoformat() if inv.created_at else None,
            items=[InvoiceItemRead.model_validate(i) for i in (inv.items or [])],
        )


class InvoiceItemWrite(BaseModel):
    sort_order:  int = 0
    line_number: Optional[str]   = None
    description: str
    quantity:    Optional[float] = None
    unit_price:  Optional[float] = None
    total:       Optional[float] = None
    disc_pct:    Optional[float] = None
    comments:    Optional[str]   = None


class InvoiceCreate(BaseModel):
    invoice_number: Optional[str]  = None
    cert_number:    Optional[str]  = None
    invoice_date:   Optional[date] = None
    due_date:       Optional[date] = None
    client_name:    str = "Ethekweni Municipality"
    client_vat_no:  Optional[str]  = None
    client_address: Optional[str]  = None
    company_email:  Optional[str]  = None
    project_description: Optional[str] = None
    contract_reference:  Optional[str] = None
    previously_paid: Optional[float] = None
    vat_rate:        float = 15.0
    notes:          Optional[str] = None
    bank_name:      Optional[str] = None
    account_number: Optional[str] = None
    branch_name:    Optional[str] = None
    branch_code:    Optional[str] = None
    items:          list[InvoiceItemWrite] = []


class InvoiceUpdate(BaseModel):
    cert_number:    Optional[str]  = None
    invoice_date:   Optional[date] = None
    due_date:       Optional[date] = None
    client_name:    Optional[str]  = None
    client_vat_no:  Optional[str]  = None
    client_address: Optional[str]  = None
    company_email:  Optional[str]  = None
    project_description: Optional[str] = None
    contract_reference:  Optional[str] = None
    previously_paid: Optional[float] = None
    vat_rate:        Optional[float] = None
    notes:          Optional[str]  = None
    bank_name:      Optional[str]  = None
    account_number: Optional[str]  = None
    branch_name:    Optional[str]  = None
    branch_code:    Optional[str]  = None
    status:         Optional[str]  = None
    items:          Optional[list[InvoiceItemWrite]] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@project_muni_router.get("/", response_model=ApiSuccess[list[InvoiceRead]], dependencies=[ALL_ROLES])
def list_invoices(
    project_id: uuid.UUID, db: DbSession, current_user: CurrentUser,
    status: Optional[str] = None,
):
    check_project_access(db, current_user, project_id)
    invoices = muni_invoice_service.list_invoices(db, project_id, status=status)
    return ApiSuccess(data=[InvoiceRead.from_orm_full(i) for i in invoices])


@project_muni_router.post(
    "/", response_model=ApiSuccess[InvoiceRead], status_code=201, dependencies=[WRITE_ROLES]
)
def create_invoice(
    project_id: uuid.UUID, body: InvoiceCreate, db: DbSession, current_user: CurrentUser,
):
    check_project_access(db, current_user, project_id)
    inv = muni_invoice_service.create_invoice(
        db, project_id, current_user.id,
        invoice_number=body.invoice_number,
        cert_number=body.cert_number,
        invoice_date=body.invoice_date,
        due_date=body.due_date,
        client_name=body.client_name,
        client_vat_no=body.client_vat_no,
        client_address=body.client_address,
        company_email=body.company_email,
        project_description=body.project_description,
        contract_reference=body.contract_reference,
        previously_paid=Decimal(str(body.previously_paid)) if body.previously_paid is not None else None,
        vat_rate=Decimal(str(body.vat_rate)),
        notes=body.notes,
        bank_name=body.bank_name,
        account_number=body.account_number,
        branch_name=body.branch_name,
        branch_code=body.branch_code,
        items=[i.model_dump() for i in body.items],
    )
    return ApiSuccess(data=InvoiceRead.from_orm_full(inv), message="Municipality invoice created.")


@muni_router.get("/{invoice_id}", response_model=ApiSuccess[InvoiceRead], dependencies=[ALL_ROLES])
def get_invoice(invoice_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    inv = muni_invoice_service.get_invoice(db, invoice_id)
    check_project_access(db, current_user, inv.project_id)
    return ApiSuccess(data=InvoiceRead.from_orm_full(inv))


@muni_router.patch("/{invoice_id}", response_model=ApiSuccess[InvoiceRead], dependencies=[WRITE_ROLES])
def update_invoice(invoice_id: uuid.UUID, body: InvoiceUpdate, db: DbSession, current_user: CurrentUser):
    inv = muni_invoice_service.get_invoice(db, invoice_id)
    check_project_access(db, current_user, inv.project_id)
    fields = body.model_dump(exclude_none=True)
    if "items" in fields:
        fields["items"] = [i.model_dump() for i in body.items] if body.items is not None else None
    if "previously_paid" in fields and fields["previously_paid"] is not None:
        fields["previously_paid"] = Decimal(str(fields["previously_paid"]))
    if "vat_rate" in fields and fields["vat_rate"] is not None:
        fields["vat_rate"] = Decimal(str(fields["vat_rate"]))
    inv = muni_invoice_service.update_invoice(db, invoice_id, **fields)
    return ApiSuccess(data=InvoiceRead.from_orm_full(inv), message="Invoice updated.")


@muni_router.delete("/{invoice_id}", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def delete_invoice(invoice_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    inv = muni_invoice_service.get_invoice(db, invoice_id)
    check_project_access(db, current_user, inv.project_id)
    muni_invoice_service.delete_invoice(db, invoice_id)
    return ApiSuccess(data={}, message="Invoice deleted.")


@muni_router.get(
    "/{invoice_id}/export/excel",
    dependencies=[ALL_ROLES],
    response_class=Response,
)
def export_excel(invoice_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """Download the invoice as an Excel file matching the municipality template."""
    inv = muni_invoice_service.get_invoice(db, invoice_id)
    check_project_access(db, current_user, inv.project_id)
    xlsx_bytes = muni_invoice_service.export_excel(db, invoice_id)
    filename   = f"Invoice_{inv.invoice_number}_Cert{inv.cert_number or 'NA'}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
