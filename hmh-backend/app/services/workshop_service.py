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
)

WORKSHOP_VOTES_REQUIRED = 3
from app.schemas.workshop import (
    WorkshopCategoryCreate,
    WorkshopIssuanceCreate,
    WorkshopItemCreate,
    WorkshopItemUpdate,
    WorkshopMRCreate,
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
