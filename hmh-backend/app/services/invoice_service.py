"""Invoice service."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.invoice import Invoice
from app.models.project import Project
from app.schemas.invoice import InvoiceCreate, InvoiceUpdate
from app.services import audit_service
from app.models.enums import AuditAction


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
    db.flush()

    audit_service.write_event(
        db, AuditAction.CREATE, "invoice", captured_by_id, invoice.id,
        after_value={"invoice_number": data.invoice_number, "total": float(data.total_amount)},
    )
    # Note: auto-reconciliation is available via POST /alerts/scan and
    # the procurement_matching_service. It is intentionally NOT triggered
    # automatically here to prevent overwriting manual match records.

    # Reactive alert: invoice captured but not yet matched
    try:
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertSeverity, AlertStatus
        from app.models.supplier import Supplier
        supplier = db.get(Supplier, data.supplier_id)
        db.add(SystemAlert(
            project_id=project_id,
            reference_type="invoice",
            reference_id=invoice.id,
            alert_type=AlertType.INVOICE_UNMATCHED,
            severity=AlertSeverity.LOW,
            title=f"Invoice captured — not yet matched: {data.invoice_number}",
            message=(
                f"Invoice {data.invoice_number} from {supplier.name if supplier else 'supplier'} "
                f"(R{float(data.total_amount):,.2f}) has been captured and awaits reconciliation."
            ),
            status=AlertStatus.OPEN,
            notification_channel="in_app",
            created_at=now,
        ))
    except Exception:
        pass  # never block invoice creation due to alert failure

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
