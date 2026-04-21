"""Supplier service."""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.supplier import Supplier
from app.schemas.supplier import SupplierCreate, SupplierUpdate


def _get_or_404(db: Session, supplier_id: uuid.UUID) -> Supplier:
    s = db.get(Supplier, supplier_id)
    if not s:
        raise NotFoundError(f"Supplier {supplier_id} not found.")
    return s


def list_suppliers(db: Session, include_inactive: bool = False) -> list[Supplier]:
    q = db.query(Supplier)
    if not include_inactive:
        q = q.filter(Supplier.is_active == True)  # noqa: E712
    return q.order_by(Supplier.name).all()


def get_supplier(db: Session, supplier_id: uuid.UUID) -> Supplier:
    return _get_or_404(db, supplier_id)


def create_supplier(db: Session, data: SupplierCreate) -> Supplier:
    existing = db.query(Supplier).filter(Supplier.name.ilike(data.name.strip())).first()
    if existing:
        raise ConflictError(f"Supplier '{data.name.strip()}' already exists.")

    supplier = Supplier(
        name=data.name.strip(),
        code=data.code.strip().upper() if data.code else None,
        email=data.email,
        phone=data.phone,
        address=data.address,
        contact_person=data.contact_person,
        payment_terms=data.payment_terms,
        notes=data.notes,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def update_supplier(db: Session, supplier_id: uuid.UUID, data: SupplierUpdate) -> Supplier:
    supplier = _get_or_404(db, supplier_id)
    fields = data.model_fields_set

    if "name" in fields and data.name is not None:
        existing = (
            db.query(Supplier)
            .filter(Supplier.name.ilike(data.name.strip()))
            .filter(Supplier.id != supplier_id)
            .first()
        )
        if existing:
            raise ConflictError(f"Supplier name '{data.name.strip()}' is already taken.")
        supplier.name = data.name.strip()
    if "code" in fields:
        supplier.code = data.code.strip().upper() if data.code else None
    if "email" in fields:
        supplier.email = data.email
    if "phone" in fields:
        supplier.phone = data.phone
    if "address" in fields:
        supplier.address = data.address
    if "contact_person" in fields:
        supplier.contact_person = data.contact_person
    if "payment_terms" in fields:
        supplier.payment_terms = data.payment_terms
    if "notes" in fields:
        supplier.notes = data.notes
    if "is_active" in fields and data.is_active is not None:
        supplier.is_active = data.is_active

    db.commit()
    db.refresh(supplier)
    return supplier
