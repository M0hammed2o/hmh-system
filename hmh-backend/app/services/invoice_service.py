"""Invoice service."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.invoice import Invoice
from app.models.project import Project
from app.schemas.invoice import InvoiceCreate, InvoiceUpdate


def _get_or_404(db: Session, invoice_id: uuid.UUID) -> Invoice:
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise NotFoundError(f"Invoice {invoice_id} not found.")
    return inv


def list_invoices(db: Session, project_id: uuid.UUID) -> list[Invoice]:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")
    return (
        db.query(Invoice)
        .filter(Invoice.project_id == project_id)
        .order_by(Invoice.captured_at.desc())
        .all()
    )


def get_invoice(db: Session, invoice_id: uuid.UUID) -> Invoice:
    return _get_or_404(db, invoice_id)


def create_invoice(
    db: Session,
    project_id: uuid.UUID,
    data: InvoiceCreate,
    captured_by_id: uuid.UUID,
) -> Invoice:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")

    # Uniqueness: (supplier_id, invoice_number)
    existing = (
        db.query(Invoice)
        .filter(
            Invoice.supplier_id == data.supplier_id,
            Invoice.invoice_number == data.invoice_number,
        )
        .first()
    )
    if existing:
        raise ConflictError(
            f"Invoice '{data.invoice_number}' already exists for this supplier."
        )

    now = datetime.now(timezone.utc)
    invoice = Invoice(
        invoice_number=data.invoice_number,
        supplier_id=data.supplier_id,
        project_id=project_id,
        site_id=data.site_id,
        purchase_order_id=data.purchase_order_id,
        invoice_date=data.invoice_date,
        due_date=data.due_date,
        subtotal_amount=data.subtotal_amount,
        vat_amount=data.vat_amount,
        total_amount=data.total_amount,
        status="DRAFT",
        captured_by=captured_by_id,
        captured_at=now,
        notes=data.notes,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def update_invoice(
    db: Session, invoice_id: uuid.UUID, data: InvoiceUpdate
) -> Invoice:
    invoice = _get_or_404(db, invoice_id)
    fields = data.model_fields_set

    if "status" in fields and data.status is not None:
        invoice.status = data.status
    if "due_date" in fields:
        invoice.due_date = data.due_date
    if "total_amount" in fields and data.total_amount is not None:
        invoice.total_amount = data.total_amount
    if "subtotal_amount" in fields:
        invoice.subtotal_amount = data.subtotal_amount
    if "vat_amount" in fields:
        invoice.vat_amount = data.vat_amount
    if "notes" in fields:
        invoice.notes = data.notes

    db.commit()
    db.refresh(invoice)
    return invoice
