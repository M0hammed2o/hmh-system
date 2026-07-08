"""Workshop API routes — parts catalog, stock, MRs, and issuances."""

import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.core.exceptions import ConflictError, NotFoundError
from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE, OFFICE_ADMIN_AND_ABOVE, WRITE_ROLES
from app.models.enums import RecordStatus
from app.schemas.common import ApiSuccess
from app.schemas.workshop import (
    WorkshopCategoryCreate,
    WorkshopCategoryRead,
    WorkshopIssuanceCreate,
    WorkshopIssuanceRead,
    WorkshopItemCreate,
    WorkshopItemRead,
    WorkshopItemUpdate,
    WorkshopMRApprovalRead,
    WorkshopMRCreate,
    WorkshopMREmailLogRead,
    WorkshopMRRead,
    WorkshopQuoteCreate,
    WorkshopQuoteRead,
    WorkshopSupplierLinkCreate,
    WorkshopSupplierLinkRead,
)
from app.services import workshop_service

router = APIRouter(prefix="/workshop", tags=["workshop"])


def _404(e: Exception) -> HTTPException:
    return HTTPException(status_code=404, detail=str(e))


def _409(e: Exception) -> HTTPException:
    return HTTPException(status_code=409, detail=str(e))


def _error(e: Exception) -> HTTPException:
    return _409(e) if isinstance(e, ConflictError) else _404(e)


# ── Categories ────────────────────────────────────────────────────────────────

@router.get("/categories/", response_model=ApiSuccess[list[WorkshopCategoryRead]], dependencies=[ALL_ROLES])
def list_categories(db: DbSession):
    cats = workshop_service.list_categories(db)
    return ApiSuccess(data=[WorkshopCategoryRead.model_validate(c) for c in cats])


@router.post(
    "/categories/",
    response_model=ApiSuccess[WorkshopCategoryRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_category(body: WorkshopCategoryCreate, db: DbSession):
    try:
        cat = workshop_service.create_category(db, body)
        return ApiSuccess(data=WorkshopCategoryRead.model_validate(cat), message="Category created.")
    except (NotFoundError, ConflictError) as e:
        raise _error(e)


@router.patch(
    "/categories/{category_id}",
    response_model=ApiSuccess[WorkshopCategoryRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_category(category_id: uuid.UUID, body: WorkshopCategoryCreate, db: DbSession):
    try:
        cat = workshop_service.update_category(db, category_id, body)
        return ApiSuccess(data=WorkshopCategoryRead.model_validate(cat), message="Category updated.")
    except (NotFoundError, ConflictError) as e:
        raise _error(e)


# ── Items ─────────────────────────────────────────────────────────────────────

@router.get("/items/", response_model=ApiSuccess[list[WorkshopItemRead]], dependencies=[ALL_ROLES])
def list_items(
    db: DbSession,
    category_id: Optional[uuid.UUID] = Query(None),
    active_only: bool = Query(True),
):
    items = workshop_service.list_items(db, category_id=category_id, active_only=active_only)
    return ApiSuccess(data=[WorkshopItemRead.model_validate(i) for i in items])


@router.post(
    "/items/",
    response_model=ApiSuccess[WorkshopItemRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_item(body: WorkshopItemCreate, db: DbSession):
    try:
        item = workshop_service.create_item(db, body)
        return ApiSuccess(data=WorkshopItemRead.model_validate(item), message="Item created.")
    except (NotFoundError, ConflictError) as e:
        raise _error(e)


@router.patch(
    "/items/{item_id}",
    response_model=ApiSuccess[WorkshopItemRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_item(item_id: uuid.UUID, body: WorkshopItemUpdate, db: DbSession):
    try:
        item = workshop_service.update_item(db, item_id, body)
        return ApiSuccess(data=WorkshopItemRead.model_validate(item), message="Item updated.")
    except (NotFoundError, ConflictError) as e:
        raise _error(e)


class StockAdjustBody(BaseModel):
    quantity_delta: float
    notes: Optional[str] = None


@router.post(
    "/items/{item_id}/adjust-stock",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def adjust_stock(item_id: uuid.UUID, body: StockAdjustBody, db: DbSession, current_user: CurrentUser):
    try:
        stock = workshop_service.adjust_stock(db, item_id, body.quantity_delta, current_user.id)
        return ApiSuccess(
            data={"quantity_on_hand": float(stock.quantity_on_hand)},
            message="Stock adjusted.",
        )
    except (NotFoundError, ConflictError) as e:
        raise _error(e)


# ── Supplier links ─────────────────────────────────────────────────────────────

@router.get(
    "/supplier-links/",
    response_model=ApiSuccess[list[WorkshopSupplierLinkRead]],
    dependencies=[ALL_ROLES],
)
def list_supplier_links(db: DbSession, category_id: Optional[uuid.UUID] = Query(None)):
    links = workshop_service.list_supplier_links(db, category_id=category_id)
    return ApiSuccess(data=[WorkshopSupplierLinkRead.model_validate(l) for l in links])


@router.post(
    "/supplier-links/",
    response_model=ApiSuccess[WorkshopSupplierLinkRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_supplier_link(body: WorkshopSupplierLinkCreate, db: DbSession):
    try:
        link = workshop_service.create_supplier_link(db, body)
        return ApiSuccess(data=WorkshopSupplierLinkRead.model_validate(link), message="Supplier linked to category.")
    except (NotFoundError, ConflictError) as e:
        raise _error(e)


@router.delete(
    "/supplier-links/{link_id}",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def delete_supplier_link(link_id: uuid.UUID, db: DbSession):
    try:
        workshop_service.delete_supplier_link(db, link_id)
        return ApiSuccess(data={}, message="Supplier link removed.")
    except NotFoundError as e:
        raise _404(e)


# ── Workshop MRs ──────────────────────────────────────────────────────────────

@router.get("/mrs/", response_model=ApiSuccess[list[WorkshopMRRead]], dependencies=[ALL_ROLES])
def list_mrs(
    db: DbSession,
    site_id: Optional[uuid.UUID] = Query(None),
    vehicle_id: Optional[uuid.UUID] = Query(None),
    status: Optional[RecordStatus] = Query(None),
):
    mrs = workshop_service.list_mrs(db, site_id=site_id, vehicle_id=vehicle_id, status=status)
    return ApiSuccess(data=[WorkshopMRRead.model_validate(m) for m in mrs])


@router.post(
    "/mrs/",
    response_model=ApiSuccess[WorkshopMRRead],
    status_code=201,
    dependencies=[WRITE_ROLES],
)
def create_mr(body: WorkshopMRCreate, db: DbSession, current_user: CurrentUser):
    mr = workshop_service.create_mr(db, body, current_user.id)
    return ApiSuccess(
        data=WorkshopMRRead.model_validate(mr),
        message=f"Workshop MR {mr.mr_number} created.",
    )


@router.get("/mrs/{mr_id}", response_model=ApiSuccess[WorkshopMRRead], dependencies=[ALL_ROLES])
def get_mr(mr_id: uuid.UUID, db: DbSession):
    try:
        mr = workshop_service.get_mr(db, mr_id)
        return ApiSuccess(data=WorkshopMRRead.model_validate(mr))
    except NotFoundError as e:
        raise _404(e)


@router.post(
    "/mrs/{mr_id}/submit",
    response_model=ApiSuccess[WorkshopMRRead],
    dependencies=[WRITE_ROLES],
)
def submit_mr(mr_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    try:
        mr = workshop_service.submit_mr(db, mr_id, current_user.id)
        return ApiSuccess(data=WorkshopMRRead.model_validate(mr), message="MR submitted for approval.")
    except (NotFoundError, ConflictError) as e:
        raise _error(e)


class VoteBody(BaseModel):
    notes: Optional[str] = None


@router.post(
    "/mrs/{mr_id}/vote",
    response_model=ApiSuccess[WorkshopMRRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def cast_vote(mr_id: uuid.UUID, body: VoteBody, db: DbSession, current_user: CurrentUser):
    try:
        mr = workshop_service.cast_mr_vote(db, mr_id, current_user.id, body.notes)
        return ApiSuccess(data=WorkshopMRRead.model_validate(mr), message="Vote cast.")
    except (NotFoundError, ConflictError) as e:
        raise _error(e)


@router.get(
    "/mrs/{mr_id}/votes",
    response_model=ApiSuccess[list[WorkshopMRApprovalRead]],
    dependencies=[OFFICE_AND_ABOVE],
)
def list_votes(mr_id: uuid.UUID, db: DbSession):
    votes = workshop_service.list_mr_votes(db, mr_id)
    return ApiSuccess(data=[WorkshopMRApprovalRead.model_validate(v) for v in votes])


@router.post(
    "/mrs/{mr_id}/approve",
    response_model=ApiSuccess[WorkshopMRRead],
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def approve_mr(mr_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """Admin override — approve directly without requiring 3 votes."""
    try:
        mr = workshop_service.approve_mr(db, mr_id, current_user.id)
        return ApiSuccess(data=WorkshopMRRead.model_validate(mr), message="MR approved (admin override).")
    except (NotFoundError, ConflictError) as e:
        raise _error(e)


class SendEmailBody(BaseModel):
    force_resend: bool = False


@router.post(
    "/mrs/{mr_id}/send-to-suppliers",
    response_model=ApiSuccess[list[WorkshopMREmailLogRead]],
    dependencies=[OFFICE_AND_ABOVE],
)
def send_to_suppliers(mr_id: uuid.UUID, body: SendEmailBody, db: DbSession, current_user: CurrentUser):
    """Send quote-request emails to suppliers for an approved Workshop MR."""
    from app.services.email_service import send_workshop_mr_email
    try:
        mr = workshop_service.get_mr(db, mr_id)
    except NotFoundError as e:
        raise _404(e)
    if mr.status.value != "APPROVED":
        raise HTTPException(status_code=400, detail="MR must be APPROVED before sending to suppliers.")
    logs = send_workshop_mr_email(db, mr, sent_by_id=current_user.id, force_resend=body.force_resend)
    return ApiSuccess(
        data=[WorkshopMREmailLogRead.model_validate(l) for l in logs],
        message=f"{len(logs)} email(s) processed.",
    )


class RejectBody(BaseModel):
    reason: Optional[str] = None


@router.post(
    "/mrs/{mr_id}/reject",
    response_model=ApiSuccess[WorkshopMRRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def reject_mr(mr_id: uuid.UUID, body: RejectBody, db: DbSession, current_user: CurrentUser):
    try:
        mr = workshop_service.reject_mr(db, mr_id, current_user.id, body.reason)
        return ApiSuccess(data=WorkshopMRRead.model_validate(mr), message="MR rejected.")
    except (NotFoundError, ConflictError) as e:
        raise _error(e)


# ── Issuances ─────────────────────────────────────────────────────────────────

@router.get("/issuances/", response_model=ApiSuccess[list[WorkshopIssuanceRead]], dependencies=[ALL_ROLES])
def list_issuances(
    db: DbSession,
    vehicle_id: Optional[uuid.UUID] = Query(None),
    item_id: Optional[uuid.UUID] = Query(None),
):
    issuances = workshop_service.list_issuances(db, vehicle_id=vehicle_id, item_id=item_id)
    return ApiSuccess(data=[WorkshopIssuanceRead.model_validate(i) for i in issuances])


@router.post(
    "/issuances/",
    response_model=ApiSuccess[WorkshopIssuanceRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def issue_parts(body: WorkshopIssuanceCreate, db: DbSession, current_user: CurrentUser):
    try:
        issuance = workshop_service.issue_parts(db, body, current_user.id)
        return ApiSuccess(
            data=WorkshopIssuanceRead.model_validate(issuance),
            message="Parts issued to vehicle.",
        )
    except (NotFoundError, ConflictError) as e:
        raise _error(e)


# ── Workshop Quotes ────────────────────────────────────────────────────────────

@router.get(
    "/quotes/",
    response_model=ApiSuccess[list[WorkshopQuoteRead]],
    dependencies=[ALL_ROLES],
)
def list_quotes(db: DbSession, mr_id: uuid.UUID = Query(...)):
    quotes = workshop_service.list_quotes(db, mr_id)
    return ApiSuccess(data=[WorkshopQuoteRead.model_validate(q) for q in quotes])


@router.post(
    "/quotes/",
    response_model=ApiSuccess[WorkshopQuoteRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_quote(body: WorkshopQuoteCreate, db: DbSession, current_user: CurrentUser):
    try:
        q = workshop_service.create_quote(db, body, current_user.id)
        return ApiSuccess(data=WorkshopQuoteRead.model_validate(q), message="Quote created.")
    except (NotFoundError, ConflictError) as e:
        raise _error(e)


@router.post(
    "/quotes/{quote_id}/upload-file",
    response_model=ApiSuccess[WorkshopQuoteRead],
    dependencies=[OFFICE_AND_ABOVE],
)
async def upload_quote_file(
    quote_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
):
    from app.storage import save_upload

    try:
        workshop_service.get_quote(db, quote_id)
    except NotFoundError as e:
        raise _404(e)

    content = await file.read()
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() or "pdf"
    relative_path = f"workshop/quotes/{quote_id}/quote.{ext}"
    file_url = save_upload(content, relative_path)

    q = workshop_service.attach_quote_file(db, quote_id, file_url)
    return ApiSuccess(data=WorkshopQuoteRead.model_validate(q), message="Quote file uploaded.")


class QuoteVoteBody(BaseModel):
    notes: Optional[str] = None


@router.post(
    "/quotes/{quote_id}/vote",
    response_model=ApiSuccess[WorkshopQuoteRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def cast_quote_vote(quote_id: uuid.UUID, body: QuoteVoteBody, db: DbSession, current_user: CurrentUser):
    try:
        q = workshop_service.cast_quote_vote(db, quote_id, current_user.id, body.notes)
        return ApiSuccess(data=WorkshopQuoteRead.model_validate(q), message="Vote cast on quote.")
    except (NotFoundError, ConflictError) as e:
        raise _error(e)


@router.post(
    "/quotes/{quote_id}/approve",
    response_model=ApiSuccess[WorkshopQuoteRead],
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def approve_quote(quote_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """Admin override — approve quote without 3 votes."""
    try:
        q = workshop_service.approve_quote(db, quote_id, current_user.id)
        return ApiSuccess(data=WorkshopQuoteRead.model_validate(q), message="Quote approved (admin override).")
    except (NotFoundError, ConflictError) as e:
        raise _error(e)


class QuoteRejectBody(BaseModel):
    reason: Optional[str] = None


@router.post(
    "/quotes/{quote_id}/reject",
    response_model=ApiSuccess[WorkshopQuoteRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def reject_quote(quote_id: uuid.UUID, body: QuoteRejectBody, db: DbSession, current_user: CurrentUser):
    try:
        q = workshop_service.reject_quote(db, quote_id, current_user.id, body.reason)
        return ApiSuccess(data=WorkshopQuoteRead.model_validate(q), message="Quote rejected.")
    except (NotFoundError, ConflictError) as e:
        raise _error(e)
