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
    # Auto-calculate due_date from supplier payment_due_days when not provided
    computed_due_date = data.due_date
    if not computed_due_date and data.invoice_date:
        from app.models.supplier import Supplier as _SupModel
        from datetime import timedelta
        _sup = db.get(_SupModel, data.supplier_id)
        if _sup and _sup.payment_due_days:
            computed_due_date = data.invoice_date + timedelta(days=_sup.payment_due_days)

    invoice = Invoice(
        invoice_number=data.invoice_number,
        supplier_id=data.supplier_id,
        project_id=project_id,
        site_id=data.site_id,
        purchase_order_id=data.purchase_order_id,
        invoice_date=data.invoice_date,
        due_date=computed_due_date,
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

    # Resolve supplier name once — used by both the in-app and WhatsApp alerts below
    _supplier_name = "Unknown supplier"
    try:
        from app.models.supplier import Supplier as _Sup
        _s = db.get(_Sup, data.supplier_id)
        if _s:
            _supplier_name = _s.name
    except Exception:
        pass

    # Reactive alert: invoice captured but not yet matched (in-app, existing behaviour)
    try:
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertSeverity, AlertStatus
        db.add(SystemAlert(
            project_id=project_id,
            reference_type="invoice",
            reference_id=invoice.id,
            alert_type=AlertType.INVOICE_UNMATCHED,
            severity=AlertSeverity.LOW,
            title=f"Invoice captured — not yet matched: {data.invoice_number}",
            message=(
                f"Invoice {data.invoice_number} from {_supplier_name} "
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

    # Phase 3Q.3: WhatsApp notification — invoice captured (fire-and-forget)
    try:
        from app.services.notification_service import enqueue_direct
        from app.models.enums import AlertSeverity
        enqueue_direct(
            db,
            alert_type=AlertType.INVOICE_CAPTURED,
            severity=AlertSeverity.LOW,
            title=f"Invoice Captured: {invoice.invoice_number}",
            message=(
                f"Invoice {invoice.invoice_number} from {_supplier_name} "
                f"(R{float(invoice.total_amount):,.2f}) has been captured."
            ),
            project_id=project_id,
            entity_type="invoice",
            entity_id=invoice.id,
        )
        db.commit()
    except Exception:
        pass

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
