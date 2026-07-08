"""Workshop service — parts catalog, stock, MRs, and issuances."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import MRPriority, RecordStatus
from app.models.workshop import (
    WorkshopCategory,
    WorkshopIssuance,
    WorkshopItem,
    WorkshopMR,
    WorkshopMRApproval,
    WorkshopMRLine,
    WorkshopStock,
    WorkshopSupplierLink,
    WorkshopQuote,
    WorkshopQuoteApproval,
    WorkshopPurchaseOrder,
    WorkshopInvoice,
    WorkshopDeliveryNote,
)

WORKSHOP_VOTES_REQUIRED = 3
from app.schemas.workshop import (
    WorkshopCategoryCreate,
    WorkshopDeliveryNoteCreate,
    WorkshopInvoiceCreate,
    WorkshopIssuanceCreate,
    WorkshopItemCreate,
    WorkshopItemUpdate,
    WorkshopMRCreate,
    WorkshopPurchaseOrderCreate,
    WorkshopQuoteCreate,
    WorkshopSupplierLinkCreate,
)


def _next_mr_number(db: Session) -> str:
    count = db.query(func.count(WorkshopMR.id)).scalar() or 0
    return f"WMR-{count + 1:04d}"


# ── Categories ────────────────────────────────────────────────────────────────

def list_categories(db: Session) -> list[WorkshopCategory]:
    return db.query(WorkshopCategory).order_by(WorkshopCategory.name).all()


def get_category(db: Session, category_id: uuid.UUID) -> WorkshopCategory:
    cat = db.get(WorkshopCategory, category_id)
    if not cat:
        raise NotFoundError(f"Workshop category {category_id} not found.")
    return cat


def create_category(db: Session, data: WorkshopCategoryCreate) -> WorkshopCategory:
    existing = db.query(WorkshopCategory).filter(WorkshopCategory.name == data.name).first()
    if existing:
        raise ConflictError(f"Category '{data.name}' already exists.")
    cat = WorkshopCategory(name=data.name, description=data.description)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def update_category(db: Session, category_id: uuid.UUID, data: WorkshopCategoryCreate) -> WorkshopCategory:
    cat = get_category(db, category_id)
    if data.name != cat.name:
        existing = db.query(WorkshopCategory).filter(WorkshopCategory.name == data.name).first()
        if existing:
            raise ConflictError(f"Category '{data.name}' already exists.")
    cat.name = data.name
    cat.description = data.description
    db.commit()
    db.refresh(cat)
    return cat


# ── Items ─────────────────────────────────────────────────────────────────────

def list_items(
    db: Session,
    category_id: Optional[uuid.UUID] = None,
    active_only: bool = True,
) -> list[WorkshopItem]:
    q = db.query(WorkshopItem)
    if active_only:
        q = q.filter(WorkshopItem.is_active == True)  # noqa: E712
    if category_id:
        q = q.filter(WorkshopItem.category_id == category_id)
    return q.order_by(WorkshopItem.name).all()


def get_item(db: Session, item_id: uuid.UUID) -> WorkshopItem:
    item = db.get(WorkshopItem, item_id)
    if not item:
        raise NotFoundError(f"Workshop item {item_id} not found.")
    return item


def create_item(db: Session, data: WorkshopItemCreate) -> WorkshopItem:
    get_category(db, data.category_id)  # validates category exists
    item = WorkshopItem(
        category_id=data.category_id,
        name=data.name,
        part_number=data.part_number,
        unit=data.unit,
        description=data.description,
        reorder_level=data.reorder_level,
    )
    db.add(item)
    db.flush()
    # Immediately create a stock record at zero
    stock = WorkshopStock(item_id=item.id, quantity_on_hand=0)
    db.add(stock)
    db.commit()
    db.refresh(item)
    return item


def update_item(db: Session, item_id: uuid.UUID, data: WorkshopItemUpdate) -> WorkshopItem:
    item = get_item(db, item_id)
    if data.name is not None:
        item.name = data.name
    if data.part_number is not None:
        item.part_number = data.part_number
    if data.unit is not None:
        item.unit = data.unit
    if data.description is not None:
        item.description = data.description
    if data.reorder_level is not None:
        item.reorder_level = data.reorder_level
    if data.is_active is not None:
        item.is_active = data.is_active
    db.commit()
    db.refresh(item)
    return item


def adjust_stock(
    db: Session,
    item_id: uuid.UUID,
    quantity_delta: float,
    actor_id: Optional[uuid.UUID] = None,
) -> WorkshopStock:
    """Add (positive) or subtract (negative) from workshop stock."""
    stock = db.query(WorkshopStock).filter(WorkshopStock.item_id == item_id).first()
    if not stock:
        raise NotFoundError(f"Stock record for item {item_id} not found.")
    new_qty = float(stock.quantity_on_hand) + quantity_delta
    stock.quantity_on_hand = new_qty
    stock.last_updated = datetime.now(timezone.utc)
    db.commit()
    db.refresh(stock)
    return stock


# ── Supplier links ─────────────────────────────────────────────────────────────

def list_supplier_links(
    db: Session,
    category_id: Optional[uuid.UUID] = None,
) -> list[WorkshopSupplierLink]:
    q = db.query(WorkshopSupplierLink)
    if category_id:
        q = q.filter(WorkshopSupplierLink.category_id == category_id)
    return q.all()


def create_supplier_link(db: Session, data: WorkshopSupplierLinkCreate) -> WorkshopSupplierLink:
    existing = (
        db.query(WorkshopSupplierLink)
        .filter(
            WorkshopSupplierLink.category_id == data.category_id,
            WorkshopSupplierLink.supplier_id == data.supplier_id,
        )
        .first()
    )
    if existing:
        raise ConflictError("Supplier is already linked to this category.")
    link = WorkshopSupplierLink(
        category_id=data.category_id,
        supplier_id=data.supplier_id,
        is_preferred=data.is_preferred,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def delete_supplier_link(db: Session, link_id: uuid.UUID) -> None:
    link = db.get(WorkshopSupplierLink, link_id)
    if not link:
        raise NotFoundError(f"Supplier link {link_id} not found.")
    db.delete(link)
    db.commit()


# ── Workshop MRs ──────────────────────────────────────────────────────────────

def list_mrs(
    db: Session,
    site_id: Optional[uuid.UUID] = None,
    vehicle_id: Optional[uuid.UUID] = None,
    status: Optional[RecordStatus] = None,
) -> list[WorkshopMR]:
    q = db.query(WorkshopMR)
    if site_id:
        q = q.filter(WorkshopMR.site_id == site_id)
    if vehicle_id:
        q = q.filter(WorkshopMR.vehicle_id == vehicle_id)
    if status:
        q = q.filter(WorkshopMR.status == status)
    return q.order_by(WorkshopMR.created_at.desc()).all()


def get_mr(db: Session, mr_id: uuid.UUID) -> WorkshopMR:
    mr = db.get(WorkshopMR, mr_id)
    if not mr:
        raise NotFoundError(f"Workshop MR {mr_id} not found.")
    return mr


def create_mr(db: Session, data: WorkshopMRCreate, actor_id: uuid.UUID) -> WorkshopMR:
    mr = WorkshopMR(
        mr_number=_next_mr_number(db),
        site_id=data.site_id,
        vehicle_id=data.vehicle_id,
        reason=data.reason,
        status=RecordStatus.DRAFT,
        priority=data.priority,
        needed_by_date=data.needed_by_date,
        notes=data.notes,
        requested_by=actor_id,
    )
    db.add(mr)
    db.flush()
    for line_data in data.lines:
        line = WorkshopMRLine(
            workshop_mr_id=mr.id,
            item_id=line_data.item_id,
            quantity_requested=line_data.quantity_requested,
            preferred_supplier_id=line_data.preferred_supplier_id,
            remarks=line_data.remarks,
        )
        db.add(line)
    db.commit()
    db.refresh(mr)
    return mr


def submit_mr(db: Session, mr_id: uuid.UUID, actor_id: uuid.UUID) -> WorkshopMR:
    mr = get_mr(db, mr_id)
    if mr.status != RecordStatus.DRAFT:
        raise ConflictError(f"MR {mr.mr_number} cannot be submitted from status '{mr.status.value}'.")
    if mr.requested_by != actor_id:
        # office roles bypass this, handled at route level via role check
        pass
    mr.status = RecordStatus.SUBMITTED
    db.commit()
    db.refresh(mr)
    return mr


def list_mr_votes(db: Session, mr_id: uuid.UUID) -> list[WorkshopMRApproval]:
    return (
        db.query(WorkshopMRApproval)
        .filter(WorkshopMRApproval.mr_id == mr_id)
        .order_by(WorkshopMRApproval.approved_at.asc())
        .all()
    )


def cast_mr_vote(
    db: Session,
    mr_id: uuid.UUID,
    voter_id: uuid.UUID,
    notes: Optional[str] = None,
) -> WorkshopMR:
    """Cast one approval vote on a SUBMITTED WorkshopMR.

    Each office user may vote only once. After WORKSHOP_VOTES_REQUIRED
    non-override votes the MR automatically moves to APPROVED.
    """
    mr = get_mr(db, mr_id)
    if mr.status != RecordStatus.SUBMITTED:
        raise ConflictError(f"MR {mr.mr_number} must be SUBMITTED to vote on (currently '{mr.status.value}').")

    existing = db.query(WorkshopMRApproval).filter(
        WorkshopMRApproval.mr_id == mr_id,
        WorkshopMRApproval.approved_by == voter_id,
    ).first()
    if existing:
        raise ConflictError("You have already voted on this request.")

    now = datetime.now(timezone.utc)
    db.add(WorkshopMRApproval(
        mr_id=mr_id,
        approved_by=voter_id,
        approved_at=now,
        is_override=False,
        notes=notes,
    ))
    db.flush()

    vote_count = db.query(WorkshopMRApproval).filter(
        WorkshopMRApproval.mr_id == mr_id,
        WorkshopMRApproval.is_override.is_(False),
    ).count()

    if vote_count >= WORKSHOP_VOTES_REQUIRED:
        mr.status = RecordStatus.APPROVED
        mr.approved_by = voter_id
        mr.approved_at = now

    db.commit()
    db.refresh(mr)
    return mr


def approve_mr(db: Session, mr_id: uuid.UUID, actor_id: uuid.UUID) -> WorkshopMR:
    """Admin override — approves the MR directly regardless of vote count."""
    mr = get_mr(db, mr_id)
    if mr.status != RecordStatus.SUBMITTED:
        raise ConflictError(f"MR {mr.mr_number} must be SUBMITTED to approve (currently '{mr.status.value}').")

    existing = db.query(WorkshopMRApproval).filter(
        WorkshopMRApproval.mr_id == mr_id,
        WorkshopMRApproval.approved_by == actor_id,
    ).first()
    if not existing:
        db.add(WorkshopMRApproval(
            mr_id=mr_id,
            approved_by=actor_id,
            approved_at=datetime.now(timezone.utc),
            is_override=True,
        ))

    mr.status = RecordStatus.APPROVED
    mr.approved_by = actor_id
    mr.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(mr)
    return mr


def reject_mr(
    db: Session,
    mr_id: uuid.UUID,
    actor_id: uuid.UUID,
    reason: Optional[str] = None,
) -> WorkshopMR:
    mr = get_mr(db, mr_id)
    if mr.status not in (RecordStatus.SUBMITTED, RecordStatus.DRAFT):
        raise ConflictError(f"MR {mr.mr_number} cannot be rejected from status '{mr.status.value}'.")
    mr.status = RecordStatus.REJECTED
    mr.rejection_reason = reason
    db.commit()
    db.refresh(mr)
    return mr


# ── Issuances ─────────────────────────────────────────────────────────────────

def list_issuances(
    db: Session,
    vehicle_id: Optional[uuid.UUID] = None,
    item_id: Optional[uuid.UUID] = None,
) -> list[WorkshopIssuance]:
    q = db.query(WorkshopIssuance)
    if vehicle_id:
        q = q.filter(WorkshopIssuance.vehicle_id == vehicle_id)
    if item_id:
        q = q.filter(WorkshopIssuance.item_id == item_id)
    return q.order_by(WorkshopIssuance.issued_at.desc()).all()


def issue_parts(
    db: Session,
    data: WorkshopIssuanceCreate,
    actor_id: uuid.UUID,
) -> WorkshopIssuance:
    """Deduct from workshop stock and record issuance against a vehicle."""
    stock = db.query(WorkshopStock).filter(WorkshopStock.item_id == data.item_id).first()
    if not stock:
        raise NotFoundError("Stock record not found for this item.")
    available = float(stock.quantity_on_hand)
    if available < data.quantity_issued:
        raise ConflictError(
            f"Insufficient stock. Available: {available}, requested: {data.quantity_issued}."
        )
    stock.quantity_on_hand = available - data.quantity_issued
    stock.last_updated = datetime.now(timezone.utc)

    issuance = WorkshopIssuance(
        item_id=data.item_id,
        vehicle_id=data.vehicle_id,
        workshop_mr_id=data.workshop_mr_id,
        quantity_issued=data.quantity_issued,
        issued_by=actor_id,
        issued_at=datetime.now(timezone.utc),
        notes=data.notes,
    )
    db.add(issuance)
    db.commit()
    db.refresh(issuance)
    return issuance


# ── Workshop Quotes ────────────────────────────────────────────────────────────

def list_quotes(db: Session, mr_id: uuid.UUID) -> list[WorkshopQuote]:
    return (
        db.query(WorkshopQuote)
        .filter(WorkshopQuote.workshop_mr_id == mr_id)
        .order_by(WorkshopQuote.created_at)
        .all()
    )


def get_quote(db: Session, quote_id: uuid.UUID) -> WorkshopQuote:
    q = db.query(WorkshopQuote).filter(WorkshopQuote.id == quote_id).first()
    if not q:
        raise NotFoundError(f"Quote {quote_id} not found.")
    return q


def create_quote(
    db: Session,
    data: WorkshopQuoteCreate,
    actor_id: uuid.UUID,
) -> WorkshopQuote:
    mr = db.query(WorkshopMR).filter(WorkshopMR.id == data.workshop_mr_id).first()
    if not mr:
        raise NotFoundError("Workshop MR not found.")
    if mr.status.value != "APPROVED":
        raise ConflictError("Quotes can only be submitted for APPROVED MRs.")

    quote = WorkshopQuote(
        workshop_mr_id=data.workshop_mr_id,
        supplier_id=data.supplier_id,
        supplier_name=data.supplier_name,
        total_amount=data.total_amount,
        currency=data.currency or "ZAR",
        notes=data.notes,
        status="PENDING",
        submitted_at=datetime.now(timezone.utc),
        created_by=actor_id,
    )
    db.add(quote)
    db.commit()
    db.refresh(quote)
    return quote


def attach_quote_file(
    db: Session,
    quote_id: uuid.UUID,
    file_url: str,
) -> WorkshopQuote:
    q = get_quote(db, quote_id)
    q.quote_file_url = file_url
    q.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(q)
    return q


def cast_quote_vote(
    db: Session,
    quote_id: uuid.UUID,
    voter_id: uuid.UUID,
    notes: Optional[str] = None,
) -> WorkshopQuote:
    q = get_quote(db, quote_id)
    if q.status != "PENDING":
        raise ConflictError(f"Quote is already {q.status}.")

    existing = (
        db.query(WorkshopQuoteApproval)
        .filter(
            WorkshopQuoteApproval.quote_id == quote_id,
            WorkshopQuoteApproval.approved_by == voter_id,
        )
        .first()
    )
    if existing:
        raise ConflictError("You have already voted on this quote.")

    vote = WorkshopQuoteApproval(
        quote_id=quote_id,
        approved_by=voter_id,
        approved_at=datetime.now(timezone.utc),
        is_override=False,
        notes=notes,
    )
    db.add(vote)
    db.flush()

    non_override_count = (
        db.query(func.count(WorkshopQuoteApproval.id))
        .filter(
            WorkshopQuoteApproval.quote_id == quote_id,
            WorkshopQuoteApproval.is_override.is_(False),
        )
        .scalar()
        or 0
    )
    if non_override_count >= WORKSHOP_VOTES_REQUIRED:
        q.status = "APPROVED"
        q.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(q)
    return q


def approve_quote(
    db: Session,
    quote_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> WorkshopQuote:
    """Admin override — approve quote directly."""
    q = get_quote(db, quote_id)
    if q.status not in ("PENDING",):
        raise ConflictError(f"Quote is already {q.status}.")

    vote = WorkshopQuoteApproval(
        quote_id=quote_id,
        approved_by=actor_id,
        approved_at=datetime.now(timezone.utc),
        is_override=True,
        notes="Admin override",
    )
    db.add(vote)
    q.status = "APPROVED"
    q.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(q)
    return q


def reject_quote(
    db: Session,
    quote_id: uuid.UUID,
    actor_id: uuid.UUID,
    reason: Optional[str] = None,
) -> WorkshopQuote:
    q = get_quote(db, quote_id)
    if q.status not in ("PENDING",):
        raise ConflictError(f"Quote is already {q.status}.")
    q.status = "REJECTED"
    q.rejection_reason = reason
    q.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(q)
    return q


# ── Workshop Purchase Orders ───────────────────────────────────────────────────

def _next_po_number(db: Session) -> str:
    count = db.query(func.count(WorkshopPurchaseOrder.id)).scalar() or 0
    return f"WPO-{count + 1:04d}"


def list_pos(db: Session, mr_id: uuid.UUID) -> list[WorkshopPurchaseOrder]:
    return (
        db.query(WorkshopPurchaseOrder)
        .filter(WorkshopPurchaseOrder.workshop_mr_id == mr_id)
        .order_by(WorkshopPurchaseOrder.created_at)
        .all()
    )


def get_po(db: Session, po_id: uuid.UUID) -> WorkshopPurchaseOrder:
    po = db.query(WorkshopPurchaseOrder).filter(WorkshopPurchaseOrder.id == po_id).first()
    if not po:
        raise NotFoundError(f"Purchase order {po_id} not found.")
    return po


def generate_po(
    db: Session,
    data: WorkshopPurchaseOrderCreate,
    actor_id: uuid.UUID,
) -> WorkshopPurchaseOrder:
    mr = db.query(WorkshopMR).filter(WorkshopMR.id == data.workshop_mr_id).first()
    if not mr:
        raise NotFoundError("Workshop MR not found.")
    if mr.status.value != "APPROVED":
        raise ConflictError("POs can only be generated for APPROVED MRs.")

    # Pre-fill from approved quote if provided
    supplier_id   = data.supplier_id
    supplier_name = data.supplier_name
    total_amount  = data.total_amount
    currency      = data.currency or "ZAR"

    if data.quote_id:
        q = db.query(WorkshopQuote).filter(WorkshopQuote.id == data.quote_id).first()
        if q:
            supplier_id   = supplier_id   or q.supplier_id
            supplier_name = supplier_name or q.supplier_name
            total_amount  = total_amount  if total_amount is not None else q.total_amount
            currency      = q.currency or currency

    po = WorkshopPurchaseOrder(
        workshop_mr_id=data.workshop_mr_id,
        quote_id=data.quote_id,
        po_number=_next_po_number(db),
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        total_amount=total_amount,
        currency=currency,
        notes=data.notes,
        status="DRAFT",
        created_by=actor_id,
    )
    db.add(po)
    db.commit()
    db.refresh(po)
    return po


def attach_po_file(db: Session, po_id: uuid.UUID, file_url: str) -> WorkshopPurchaseOrder:
    po = get_po(db, po_id)
    po.po_file_url = file_url
    po.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(po)
    return po


def send_po(
    db: Session,
    po_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> tuple[WorkshopPurchaseOrder, Optional[str]]:
    """Email PO to supplier. Returns (po, error_message_or_None)."""
    from app.services.email_service import send_workshop_po_email

    po = get_po(db, po_id)
    mr = db.query(WorkshopMR).filter(WorkshopMR.id == po.workshop_mr_id).first()
    if not mr:
        raise NotFoundError("Associated MR not found.")

    error = send_workshop_po_email(db, po, mr, sent_by_id=actor_id)
    db.refresh(po)
    return po, error


# ── Workshop Invoices ─────────────────────────────────────────────────────────

def list_invoices(db: Session, mr_id: uuid.UUID) -> list[WorkshopInvoice]:
    return (
        db.query(WorkshopInvoice)
        .filter(WorkshopInvoice.workshop_mr_id == mr_id)
        .order_by(WorkshopInvoice.created_at)
        .all()
    )


def get_invoice(db: Session, invoice_id: uuid.UUID) -> WorkshopInvoice:
    inv = db.query(WorkshopInvoice).filter(WorkshopInvoice.id == invoice_id).first()
    if not inv:
        raise NotFoundError(f"Invoice {invoice_id} not found.")
    return inv


def create_invoice(
    db: Session,
    data: WorkshopInvoiceCreate,
    actor_id: uuid.UUID,
) -> WorkshopInvoice:
    mr = db.query(WorkshopMR).filter(WorkshopMR.id == data.workshop_mr_id).first()
    if not mr:
        raise NotFoundError("Workshop MR not found.")

    inv = WorkshopInvoice(
        workshop_mr_id=data.workshop_mr_id,
        po_id=data.po_id,
        invoice_number=data.invoice_number,
        supplier_id=data.supplier_id,
        supplier_name=data.supplier_name,
        total_amount=data.total_amount,
        currency=data.currency or "ZAR",
        invoice_date=data.invoice_date,
        notes=data.notes,
        created_by=actor_id,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def attach_invoice_file(db: Session, invoice_id: uuid.UUID, file_url: str) -> WorkshopInvoice:
    inv = get_invoice(db, invoice_id)
    inv.invoice_file_url = file_url
    inv.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(inv)
    return inv


# ── Workshop Delivery Notes ───────────────────────────────────────────────────

def list_delivery_notes(db: Session, mr_id: uuid.UUID) -> list[WorkshopDeliveryNote]:
    return (
        db.query(WorkshopDeliveryNote)
        .filter(WorkshopDeliveryNote.workshop_mr_id == mr_id)
        .order_by(WorkshopDeliveryNote.created_at)
        .all()
    )


def get_delivery_note(db: Session, note_id: uuid.UUID) -> WorkshopDeliveryNote:
    dn = db.query(WorkshopDeliveryNote).filter(WorkshopDeliveryNote.id == note_id).first()
    if not dn:
        raise NotFoundError(f"Delivery note {note_id} not found.")
    return dn


def create_delivery_note(
    db: Session,
    data: WorkshopDeliveryNoteCreate,
    actor_id: uuid.UUID,
) -> WorkshopDeliveryNote:
    mr = db.query(WorkshopMR).filter(WorkshopMR.id == data.workshop_mr_id).first()
    if not mr:
        raise NotFoundError("Workshop MR not found.")

    dn = WorkshopDeliveryNote(
        workshop_mr_id=data.workshop_mr_id,
        po_id=data.po_id,
        delivery_number=data.delivery_number,
        delivery_date=data.delivery_date,
        received_by_name=data.received_by_name,
        notes=data.notes,
        created_by=actor_id,
    )
    db.add(dn)
    db.commit()
    db.refresh(dn)
    return dn


def attach_delivery_file(db: Session, note_id: uuid.UUID, file_url: str) -> WorkshopDeliveryNote:
    dn = get_delivery_note(db, note_id)
    dn.delivery_file_url = file_url
    dn.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(dn)
    return dn
