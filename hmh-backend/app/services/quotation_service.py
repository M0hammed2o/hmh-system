"""Quotation service."""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.quotation import Quotation
from app.schemas.quotation import QuotationCreate, QuotationUpdate


def _get_or_404(db: Session, quotation_id: uuid.UUID) -> Quotation:
    q = db.get(Quotation, quotation_id)
    if not q:
        raise NotFoundError(f"Quotation {quotation_id} not found.")
    return q


def list_by_supplier(db: Session, supplier_id: uuid.UUID) -> list[Quotation]:
    return (
        db.query(Quotation)
        .filter(Quotation.supplier_id == supplier_id)
        .order_by(Quotation.created_at.desc())
        .all()
    )


def get_quotation(db: Session, quotation_id: uuid.UUID) -> Quotation:
    return _get_or_404(db, quotation_id)


def create_quotation(db: Session, data: QuotationCreate, created_by: uuid.UUID) -> Quotation:
    existing = db.query(Quotation).filter(Quotation.quote_number == data.quote_number).first()
    if existing:
        raise ConflictError(f"Quotation '{data.quote_number}' already exists.")

    q = Quotation(
        quote_number=data.quote_number,
        supplier_id=data.supplier_id,
        project_id=data.project_id,
        material_request_id=data.material_request_id,
        status=data.status,
        quote_date=data.quote_date,
        expiry_date=data.expiry_date,
        net_amount=data.net_amount,
        vat_amount=data.vat_amount,
        gross_amount=data.gross_amount,
        vat_rate_used=data.vat_rate_used,
        notes=data.notes,
        created_by=created_by,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


def update_quotation(db: Session, quotation_id: uuid.UUID, data: QuotationUpdate) -> Quotation:
    q = _get_or_404(db, quotation_id)
    fields = data.model_fields_set

    if "status" in fields and data.status is not None:
        q.status = data.status
    if "quote_date" in fields:
        q.quote_date = data.quote_date
    if "expiry_date" in fields:
        q.expiry_date = data.expiry_date
    if "net_amount" in fields and data.net_amount is not None:
        q.net_amount = data.net_amount
    if "vat_amount" in fields and data.vat_amount is not None:
        q.vat_amount = data.vat_amount
    if "gross_amount" in fields and data.gross_amount is not None:
        q.gross_amount = data.gross_amount
    if "vat_rate_used" in fields and data.vat_rate_used is not None:
        q.vat_rate_used = data.vat_rate_used
    if "notes" in fields:
        q.notes = data.notes
    if "project_id" in fields:
        q.project_id = data.project_id

    db.commit()
    db.refresh(q)
    return q


def delete_quotation(db: Session, quotation_id: uuid.UUID) -> None:
    q = _get_or_404(db, quotation_id)
    db.delete(q)
    db.commit()
