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
