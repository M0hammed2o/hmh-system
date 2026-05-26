"""Payment service — Phase 3L: partial payments + reconciliation."""

import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.payment import Payment
from app.models.project import Project
from app.schemas.payment import PaymentCreate, PaymentUpdate


def _recalculate_invoice_status(db: Session, invoice_id: uuid.UUID) -> None:
    """
    Recalculate and persist the correct invoice status based on total payments.

    Status transitions:
      total_paid == 0             → leave as-is (keep MATCHED/RECEIVED/etc)
      0 < total_paid < total      → PARTIALLY_PAID
      total_paid == total         → PAID
      total_paid > total          → OVERPAID

    Called after any payment is created, updated, or cancelled.
    Never raises — errors are caught silently so payment operations succeed.
    """
    try:
        from app.models.invoice import Invoice
        from app.models.purchase_order import PurchaseOrder
        from app.models.enums import RecordStatus

        inv = db.get(Invoice, invoice_id)
        if not inv or not inv.total_amount:
            return

        total_paid = float(
            db.query(func.coalesce(func.sum(Payment.amount_paid), 0))
            .filter(
                Payment.invoice_id == invoice_id,
                Payment.status.notin_(["CANCELLED", "FAILED"]),
            )
            .scalar() or 0
        )

        total_required = float(inv.total_amount)

        # Determine new invoice status
        if total_paid <= 0:
            # No active payments — revert to MATCHED if currently in a paid/partial state
            if inv.status in (RecordStatus.PAID, RecordStatus.PARTIALLY_PAID, RecordStatus.OVERPAID):
                inv.status = RecordStatus.MATCHED
            return
        elif total_paid < total_required:
            new_status = RecordStatus.PARTIALLY_PAID
        elif total_paid > total_required:
            new_status = RecordStatus.OVERPAID
        else:
            new_status = RecordStatus.PAID

        inv.status = new_status

        # Also advance PO status when invoice is fully paid
        if new_status == RecordStatus.PAID and inv.purchase_order_id:
            po = db.get(PurchaseOrder, inv.purchase_order_id)
            if po and po.status in (
                RecordStatus.MATCHED, RecordStatus.APPROVED,
                RecordStatus.PARTIALLY_PAID,
            ):
                po.status = RecordStatus.PAID

    except Exception:
        pass  # never block payment operations


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
        amount_paid=data.amount_paid,   # ORM column
        amount=data.amount_paid,        # legacy NOT NULL column (migration 0001)
        captured_by=captured_by_id,
        notes=data.notes,
        # Phase 3L new fields
        payment_method=getattr(data, "payment_method", None),
        lot_id=getattr(data, "lot_id", None),
    )
    db.add(payment)
    db.flush()

    # Recalculate invoice status using the helper (PARTIALLY_PAID / PAID / OVERPAID)
    if data.invoice_id:
        _recalculate_invoice_status(db, data.invoice_id)

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

    # Phase 3Q.3: WhatsApp operational alerts — fire-and-forget after commit
    if data.invoice_id:
        try:
            from app.models.invoice import Invoice
            from app.models.supplier import Supplier
            from app.models.enums import (
                AlertType, AlertSeverity, RecordStatus,
            )
            from app.services.notification_service import enqueue_direct

            inv = db.get(Invoice, data.invoice_id)
            if inv:
                _sup_name = "Unknown supplier"
                if inv.supplier_id:
                    _s = db.get(Supplier, inv.supplier_id)
                    if _s:
                        _sup_name = _s.name

                _amount = float(data.amount_paid)
                _total = float(inv.total_amount) if inv.total_amount else 0.0
                _total_paid = float(
                    db.query(func.coalesce(func.sum(Payment.amount_paid), 0))
                    .filter(
                        Payment.invoice_id == data.invoice_id,
                        Payment.status.notin_(["CANCELLED", "FAILED"]),
                    )
                    .scalar() or 0
                )
                _outstanding = max(0.0, _total - _total_paid)

                if inv.status == RecordStatus.PAID:
                    enqueue_direct(
                        db,
                        alert_type=AlertType.PAYMENT_COMPLETED,
                        severity=AlertSeverity.LOW,
                        title=f"Payment Completed: {inv.invoice_number}",
                        message=(
                            f"R{_amount:,.2f} paid to {_sup_name}. "
                            f"Invoice {inv.invoice_number} is fully settled."
                        ),
                        project_id=project_id,
                        entity_type="invoice",
                        entity_id=data.invoice_id,
                    )
                    db.commit()
                elif inv.status == RecordStatus.PARTIALLY_PAID:
                    enqueue_direct(
                        db,
                        alert_type=AlertType.PARTIAL_PAYMENT_RECORDED,
                        severity=AlertSeverity.LOW,
                        title=f"Partial Payment: {inv.invoice_number}",
                        message=(
                            f"R{_amount:,.2f} paid to {_sup_name}. "
                            f"Outstanding balance: R{_outstanding:,.2f} on invoice {inv.invoice_number}."
                        ),
                        project_id=project_id,
                        entity_type="invoice",
                        entity_id=data.invoice_id,
                    )
                    db.commit()
        except Exception:
            pass  # never block payment operations

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
    if "payment_method" in fields:
        payment.payment_method = data.payment_method

    db.commit()
    db.refresh(payment)

    # If payment was cancelled, recalculate invoice status
    if "status" in fields and data.status is not None:
        from app.models.enums import PaymentStatus
        if data.status in (PaymentStatus.CANCELLED, PaymentStatus.FAILED):
            if payment.invoice_id:
                _recalculate_invoice_status(db, payment.invoice_id)
                db.commit()

    return payment


def get_invoice_reconciliation(db: Session, invoice_id: uuid.UUID) -> dict:
    """
    Return a full reconciliation view for an invoice:
      - invoice totals
      - all payments (sorted by date)
      - total paid
      - outstanding balance
      - status

    Accessible to office users. Site users must not call this.
    """
    from app.models.invoice import Invoice
    from app.models.enums import PaymentStatus

    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise NotFoundError(f"Invoice {invoice_id} not found.")

    payments = (
        db.query(Payment)
        .filter(
            Payment.invoice_id == invoice_id,
            Payment.status.notin_(["CANCELLED", "FAILED"]),
        )
        .order_by(Payment.payment_date.asc().nullslast(), Payment.created_at.asc())
        .all()
    )

    total_amount = float(inv.total_amount or 0)
    total_paid   = sum(float(p.amount_paid) for p in payments)
    outstanding  = max(0.0, total_amount - total_paid)
    is_overpaid  = total_paid > total_amount

    # Resolve captured_by names
    captured_names: dict = {}
    capture_ids = {p.captured_by for p in payments if p.captured_by}
    if capture_ids:
        from app.models.user import User
        for u in db.query(User).filter(User.id.in_(capture_ids)).all():
            captured_names[str(u.id)] = u.full_name

    return {
        "invoice_id":      str(invoice_id),
        "invoice_number":  inv.invoice_number,
        "invoice_date":    inv.invoice_date.isoformat() if inv.invoice_date else None,
        "due_date":        inv.due_date.isoformat() if inv.due_date else None,
        "total_amount":    total_amount,
        "total_paid":      total_paid,
        "outstanding":     outstanding,
        "is_overpaid":     is_overpaid,
        "status":          inv.status.value if hasattr(inv.status, "value") else str(inv.status),
        "payments": [
            {
                "id":               str(p.id),
                "amount_paid":      float(p.amount_paid),
                "payment_date":     p.payment_date.isoformat() if p.payment_date else None,
                "payment_method":   p.payment_method,
                "payment_reference": p.payment_reference,
                "payment_type":     p.payment_type.value if hasattr(p.payment_type, "value") else str(p.payment_type),
                "status":           p.status.value if hasattr(p.status, "value") else str(p.status),
                "notes":            p.notes,
                "captured_by_name": captured_names.get(str(p.captured_by)) if p.captured_by else None,
                "created_at":       p.created_at.isoformat(),
            }
            for p in payments
        ],
    }
