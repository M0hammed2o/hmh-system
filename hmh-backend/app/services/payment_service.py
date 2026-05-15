"""Payment service."""

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.payment import Payment
from app.models.project import Project
from app.schemas.payment import PaymentCreate, PaymentUpdate


def _get_or_404(db: Session, payment_id: uuid.UUID) -> Payment:
    p = db.get(Payment, payment_id)
    if not p:
        raise NotFoundError(f"Payment {payment_id} not found.")
    return p


def list_payments(db: Session, project_id: uuid.UUID) -> list[Payment]:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")
    return (
        db.query(Payment)
        .filter(Payment.project_id == project_id)
        .order_by(Payment.created_at.desc())
        .all()
    )


def get_payment(db: Session, payment_id: uuid.UUID) -> Payment:
    return _get_or_404(db, payment_id)


def create_payment(
    db: Session,
    project_id: uuid.UUID,
    data: PaymentCreate,
    captured_by_id: uuid.UUID,
) -> Payment:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")

    # Check payment_reference uniqueness per project
    if data.payment_reference:
        exists = (
            db.query(Payment)
            .filter(
                Payment.project_id == project_id,
                Payment.payment_reference == data.payment_reference,
            )
            .first()
        )
        if exists:
            raise ConflictError(
                f"Payment reference '{data.payment_reference}' already exists in this project."
            )

    payment = Payment(
        invoice_id=data.invoice_id,
        supplier_id=data.supplier_id,
        project_id=project_id,
        payment_type=data.payment_type,
        payment_reference=data.payment_reference,
        payment_date=data.payment_date,
        amount_paid=data.amount_paid,
        captured_by=captured_by_id,
        notes=data.notes,
    )
    db.add(payment)
    db.flush()

    # PO lifecycle: when a payment is recorded against an invoice, advance PO to PAID
    # if the full invoice amount is now covered.
    if data.invoice_id:
        try:
            from app.models.invoice import Invoice
            from app.models.purchase_order import PurchaseOrder
            from app.models.enums import RecordStatus
            from sqlalchemy import func
            inv = db.get(Invoice, data.invoice_id)
            if inv and inv.purchase_order_id:
                total_paid = float(
                    db.query(func.coalesce(func.sum(Payment.amount_paid), 0))
                    .filter(Payment.invoice_id == data.invoice_id)
                    .scalar() or 0
                ) + float(data.amount_paid)
                if total_paid >= float(inv.total_amount or 0):
                    po = db.get(PurchaseOrder, inv.purchase_order_id)
                    if po and po.status in (RecordStatus.MATCHED, RecordStatus.APPROVED):
                        po.status = RecordStatus.PAID
                    inv.status = RecordStatus.PAID
        except Exception:
            pass  # never block payment creation

    from app.services import audit_service
    from app.models.enums import AuditAction
    audit_service.write_event(
        db, AuditAction.CREATE, "payment", captured_by_id, payment.id,
        after_value={
            "payment_type":      data.payment_type.value if hasattr(data.payment_type, "value") else str(data.payment_type),
            "amount_paid":       float(data.amount_paid),
            "payment_reference": data.payment_reference,
        },
    )

    db.commit()
    db.refresh(payment)
    return payment


def update_payment(
    db: Session, payment_id: uuid.UUID, data: PaymentUpdate, approved_by_id: uuid.UUID
) -> Payment:
    payment = _get_or_404(db, payment_id)
    fields = data.model_fields_set

    if "status" in fields and data.status is not None:
        payment.status = data.status
        from app.models.enums import PaymentStatus
        if data.status == PaymentStatus.APPROVED:
            payment.approved_by = approved_by_id
    if "payment_reference" in fields:
        payment.payment_reference = data.payment_reference
    if "payment_date" in fields:
        payment.payment_date = data.payment_date
    if "notes" in fields:
        payment.notes = data.notes

    db.commit()
    db.refresh(payment)
    return payment
