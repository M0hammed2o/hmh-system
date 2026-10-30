"""
Pending supplier charges — money asked for, not money owed.

A pro-forma invoice is a request for payment before supply. The supplier
wants paying now; the liability does not exist until the goods are supplied
and the tax invoice is issued. Accounts Payable must therefore never see it,
and the business must still be able to find it, pay it if it chooses, and
reconcile it when the real invoice turns up.

The reconciliation is the part that matters. `settle_against_invoice` closes
the pending charge and records which invoice superseded it, so the same
purchase appears in exactly one place at a time:

    pro-forma arrives     → PENDING charge, outside Accounts Payable
    tax invoice arrives   → Invoice (the liability) + charge marked INVOICED

Without that step a business holding both documents either pays twice or
drops the charge and loses the record of what was asked for.
"""

import uuid
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.enums import AuditAction, ProvisionalChargeStatus
from app.models.invoice import Invoice
from app.models.provisional_charge import ProvisionalCharge
from app.services import audit_service


def get_charge(db: Session, charge_id: uuid.UUID) -> ProvisionalCharge:
    charge = db.get(ProvisionalCharge, charge_id)
    if charge is None:
        raise NotFoundError("Pending supplier charge not found.")
    return charge


def list_charges(
    db: Session,
    project_id: uuid.UUID,
    *,
    status: Optional[ProvisionalChargeStatus] = None,
) -> list[ProvisionalCharge]:
    """
    Pending charges for a project.

    Deliberately a separate call from the invoice list rather than a filter
    on it: these are not payables, and a screen that can accidentally add
    them to an Accounts Payable total is a screen that will.
    """
    query = db.query(ProvisionalCharge).filter(ProvisionalCharge.project_id == project_id)
    if status is not None:
        query = query.filter(ProvisionalCharge.status == status)
    return query.order_by(ProvisionalCharge.created_at.desc()).all()


def outstanding_total(db: Session, project_id: uuid.UUID) -> float:
    """
    What suppliers have asked for in advance and not yet invoiced.

    Reported next to Accounts Payable and never added to it. The two answer
    different questions: this is "what might we be asked to pay", Accounts
    Payable is "what do we owe".
    """
    charges = list_charges(db, project_id, status=ProvisionalChargeStatus.PENDING)
    return float(sum(float(c.total_amount) for c in charges))


def create_charge(
    db: Session,
    *,
    project_id: uuid.UUID,
    supplier_id: uuid.UUID,
    reference: str,
    total_amount: float,
    actor_id: uuid.UUID,
    subtotal_amount: Optional[float] = None,
    vat_amount: Optional[float] = None,
    issue_date: Optional[date] = None,
    due_date: Optional[date] = None,
    purchase_order_id: Optional[uuid.UUID] = None,
    quotation_id: Optional[uuid.UUID] = None,
    payment_evidence_detected: bool = False,
    payment_evidence_note: Optional[str] = None,
    notes: Optional[str] = None,
) -> ProvisionalCharge:
    """
    Record a supplier's request for payment in advance.

    Refuses a reference already held for that supplier. The database enforces
    the same rule, but raising here gives the caller a sentence worth showing
    a person instead of an integrity error.
    """
    reference = (reference or "").strip()
    if not reference:
        raise ValidationError(
            "A pro-forma needs its document number. Without it the same request for "
            "payment cannot be recognised when it is scanned again."
        )
    if total_amount is None or float(total_amount) <= 0:
        raise ValidationError(
            f"A pending charge of {total_amount} cannot be recorded. Check the total "
            f"read from the document."
        )

    existing = (
        db.query(ProvisionalCharge)
        .filter(
            ProvisionalCharge.supplier_id == supplier_id,
            ProvisionalCharge.reference == reference,
        )
        .first()
    )
    if existing is not None:
        raise ConflictError(
            f"Pro-forma {reference} from this supplier is already recorded as a "
            f"pending charge, so a second one was not created."
        )

    charge = ProvisionalCharge(
        reference=reference,
        supplier_id=supplier_id,
        project_id=project_id,
        purchase_order_id=purchase_order_id,
        quotation_id=quotation_id,
        issue_date=issue_date,
        due_date=due_date,
        subtotal_amount=subtotal_amount,
        vat_amount=vat_amount,
        total_amount=total_amount,
        status=ProvisionalChargeStatus.PENDING,
        payment_evidence_detected=payment_evidence_detected,
        payment_evidence_note=payment_evidence_note,
        notes=notes,
        created_by=actor_id,
    )
    db.add(charge)
    db.flush()

    audit_service.write_event(
        db, AuditAction.CREATE, "provisional_charge", actor_id, charge.id,
        after_value={
            "reference": charge.reference,
            "total_amount": float(charge.total_amount),
            "purchase_order_id": str(purchase_order_id) if purchase_order_id else None,
            "payment_evidence_detected": payment_evidence_detected,
        },
        notes="Supplier request for payment in advance. Not a liability: Accounts "
              "Payable is unchanged until the tax invoice is recorded.",
    )
    return charge


def find_pending_for_invoice(db: Session, invoice: Invoice) -> Optional[ProvisionalCharge]:
    """
    The pending charge this invoice settles, if there is one.

    Matched on the purchase order, which is the only link both documents
    reliably carry: a supplier's pro-forma number and its later tax invoice
    number are unrelated strings, and the amounts routinely differ once
    delivery charges or part-supply are taken into account.

    Amount is deliberately not used as a matching key for that reason, and a
    charge is never matched on supplier alone — a supplier with two open
    pro-formas would have the wrong one closed.
    """
    if invoice.purchase_order_id is None:
        return None

    candidates = (
        db.query(ProvisionalCharge)
        .filter(
            ProvisionalCharge.purchase_order_id == invoice.purchase_order_id,
            ProvisionalCharge.supplier_id == invoice.supplier_id,
            ProvisionalCharge.status == ProvisionalChargeStatus.PENDING,
        )
        .order_by(ProvisionalCharge.created_at.asc())
        .all()
    )
    if len(candidates) != 1:
        # None to close, or more than one and no way to tell which. Closing
        # an arbitrary one would mark a request as invoiced that was not,
        # and leave the real one pending — so both stay open and visible for
        # a person to settle. Under-closing is recoverable; a wrong closure
        # hides itself.
        return None
    return candidates[0]


def settle_against_invoice(
    db: Session,
    charge: ProvisionalCharge,
    invoice: Invoice,
    actor_id: uuid.UUID,
) -> ProvisionalCharge:
    """
    Close a pending charge because the supplier's tax invoice arrived.

    This is the step that prevents the double count. After it the purchase is
    represented once, by the invoice, and the charge remains as the record of
    what was asked for beforehand.
    """
    if charge.status != ProvisionalChargeStatus.PENDING:
        raise ConflictError(
            f"Pro-forma {charge.reference} is already {charge.status.value.lower()}, "
            f"so it was not closed again."
        )

    before = {"status": charge.status.value, "settled_by_invoice_id": None}
    charge.status = ProvisionalChargeStatus.INVOICED
    charge.settled_by_invoice_id = invoice.id
    db.flush()

    audit_service.write_event(
        db, AuditAction.UPDATE, "provisional_charge", actor_id, charge.id,
        before_value=before,
        after_value={
            "status": charge.status.value,
            "settled_by_invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
        },
        notes=f"Closed by tax invoice {invoice.invoice_number}. The purchase is now "
              f"counted once, in Accounts Payable.",
    )
    return charge


def cancel_charge(
    db: Session, charge: ProvisionalCharge, actor_id: uuid.UUID, reason: str,
) -> ProvisionalCharge:
    """Withdraw a request for payment that will not be honoured."""
    if charge.status == ProvisionalChargeStatus.INVOICED:
        raise ConflictError(
            f"Pro-forma {charge.reference} was already invoiced, so it cannot be "
            f"cancelled. Deal with the invoice instead."
        )
    before = {"status": charge.status.value}
    charge.status = ProvisionalChargeStatus.CANCELLED
    charge.notes = f"{charge.notes}\n{reason}" if charge.notes else reason
    db.flush()
    audit_service.write_event(
        db, AuditAction.UPDATE, "provisional_charge", actor_id, charge.id,
        before_value=before,
        after_value={"status": charge.status.value, "reason": reason},
        notes="Pending supplier charge cancelled.",
    )
    return charge
