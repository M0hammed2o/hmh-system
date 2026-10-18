"""
Tracking what has been paid to mechanics for vehicle repairs.

The one rule everything here follows: **what is owed is derived from the
repair, never stored again.** A repair's cost is already recognised — as
VehicleCost rows, or as the amount quoted or invoiced for the job — and a
second copy on the payment record would be free to drift from it. So the
payable figure is computed on read, the paid figure is the sum of live
payments, and the status is whatever those two say. There is no status field
for someone to set to "Paid" while money is still outstanding.

Nothing here initiates a bank payment. It records payments that have already
been made, so the office can see what is still owed.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.enums import AuditAction
from app.models.mechanic_payment import MechanicPayment
from app.models.vehicle import RepairJob, Vehicle, VehicleCost
from app.services import audit_service

# Money compares to the cent. Anything finer is float noise, and a repair
# left owing R0.004 must read as Paid, not Partially Paid forever.
CENT = 0.005

UNPAID = "UNPAID"
PARTIALLY_PAID = "PARTIALLY_PAID"
PAID = "PAID"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── What is owed ─────────────────────────────────────────────────────────────

# Cost types that represent work the mechanic or workshop performed, and so
# money owed to them.
#
# A repair can carry any VehicleCost type — the capture form offers all seven
# — but most of them are not the mechanic's to be paid for. Tyres bought from
# a tyre dealer, a licence renewal, an insurance premium or fuel are the
# vehicle's costs, settled with whoever supplied them. Summing everything
# booked against the repair would tell the office it owes the mechanic for
# them, which is both wrong and a way to pay the same money twice.
#
# OTHER is excluded deliberately: it is unclassified by definition, and
# overstating what is owed is the worse error. A genuine mechanic cost
# captured as OTHER should be recaptured as REPAIR or SERVICE, or the
# repair's invoiced amount filled in — both of which this honours.
MECHANIC_COST_TYPES = ("REPAIR", "SERVICE")


def amount_payable(db: Session, job: RepairJob) -> tuple[float, str]:
    """
    What is owed to the mechanic for this repair, and where the figure came
    from.

    In order of authority:
      1. the mechanic's invoice — what they actually billed;
      2. the accepted quote, before an invoice arrives;
      3. the repair and service costs booked against the job, when there is
         no paperwork at all.

    Only the third needs filtering. An invoice or a quote comes *from* the
    mechanic, so whatever parts it includes are theirs to be paid for. Loose
    cost rows do not: they are whatever anyone booked against the repair.

    Returning the basis as well as the number matters — an operator looking
    at an outstanding balance needs to know whether it rests on an invoice or
    on a quote that may still change.
    """
    if job.invoice_amount is not None:
        return float(job.invoice_amount), "invoice"
    if job.quote_amount is not None:
        return float(job.quote_amount), "quote"

    booked = (
        db.query(func.coalesce(func.sum(VehicleCost.amount), 0))
        .filter(
            VehicleCost.repair_job_id == job.id,
            VehicleCost.cost_type.in_(MECHANIC_COST_TYPES),
        )
        .scalar()
    ) or 0
    return float(booked), "recorded labour"


def non_mechanic_costs(db: Session, job: RepairJob) -> float:
    """
    Costs booked against the repair that are not the mechanic's to be paid.

    Reported alongside the balance so a payable that is smaller than the
    repair's total spend is explainable rather than looking like a bug. Only
    meaningful where the payable rests on loose cost rows; where the mechanic
    invoiced, their invoice already says what they are owed.
    """
    total = (
        db.query(func.coalesce(func.sum(VehicleCost.amount), 0))
        .filter(
            VehicleCost.repair_job_id == job.id,
            VehicleCost.cost_type.notin_(MECHANIC_COST_TYPES),
        )
        .scalar()
    ) or 0
    return float(total)


def amount_paid(db: Session, repair_job_id: uuid.UUID) -> float:
    """Sum of payments that still stand. Reversed ones do not count."""
    total = (
        db.query(func.coalesce(func.sum(MechanicPayment.amount), 0))
        .filter(
            MechanicPayment.repair_job_id == repair_job_id,
            MechanicPayment.reversed_at.is_(None),
        )
        .scalar()
    ) or 0
    return float(total)


def payment_status(payable: float, paid: float) -> str:
    """
    Derived, never chosen. A status someone can set by hand is a status that
    disagrees with the money sooner or later.
    """
    if paid <= CENT:
        return UNPAID
    if paid >= payable - CENT:
        return PAID
    return PARTIALLY_PAID


def repair_payment_summary(db: Session, job: RepairJob) -> dict:
    """Everything the payments view needs about one repair."""
    payable, basis = amount_payable(db, job)
    paid = amount_paid(db, job.id)
    last = (
        db.query(func.max(MechanicPayment.payment_date))
        .filter(
            MechanicPayment.repair_job_id == job.id,
            MechanicPayment.reversed_at.is_(None),
        )
        .scalar()
    )
    vehicle = db.get(Vehicle, job.vehicle_id)

    other_costs = non_mechanic_costs(db, job)

    return {
        "repair_job_id": str(job.id),
        "repair_title": job.title,
        "repair_date": job.date_opened.isoformat() if job.date_opened else None,
        "repair_status": job.status,
        "vehicle_id": str(job.vehicle_id),
        "vehicle_name": vehicle.name if vehicle else None,
        "vehicle_registration": vehicle.registration if vehicle else None,
        "mechanic_name": job.workshop_name,
        "total_payable": round(payable, 2),
        "payable_basis": basis,
        "total_paid": round(paid, 2),
        # Never negative: an overpayment that slipped in historically should
        # read as nothing outstanding, not as a credit the office can spend.
        "outstanding": round(max(payable - paid, 0.0), 2),
        "payment_status": payment_status(payable, paid),
        "last_payment_date": last.isoformat() if last else None,
        # Parts, tyres, licences and the like booked against this repair but
        # owed to whoever supplied them, not to the mechanic.
        "other_costs_not_payable_to_mechanic": round(other_costs, 2),
    }


# ── Recording a payment ──────────────────────────────────────────────────────

def record_payment(
    db: Session,
    repair_job_id: uuid.UUID,
    *,
    amount: float,
    payment_date: date,
    actor_id: Optional[uuid.UUID],
    supplier_id: Optional[uuid.UUID] = None,
    mechanic_name: Optional[str] = None,
    payment_method: Optional[str] = None,
    payment_reference: Optional[str] = None,
    notes: Optional[str] = None,
    proof_file_url: Optional[str] = None,
) -> MechanicPayment:
    """
    Record money already paid to a mechanic against a repair.

    Refuses anything that would make the balance a lie: a non-positive
    amount, more than is outstanding, or a reference already used on a live
    payment for this repair.
    """
    job = db.get(RepairJob, repair_job_id)
    if job is None:
        raise NotFoundError("Repair job not found.")

    if amount is None or float(amount) <= 0:
        raise ValidationError("A payment must be a positive amount.")
    amount = round(float(amount), 2)

    payable, basis = amount_payable(db, job)
    if payable <= CENT:
        raise ValidationError(
            "Nothing is owed to a mechanic on this repair yet. Capture the "
            "mechanic's quote or invoice, or log the labour as a Repair or "
            "Service cost. Parts, tyres and licences booked here are owed to "
            "whoever supplied them, not to the mechanic."
        )

    already = amount_paid(db, repair_job_id)
    if already + amount > payable + CENT:
        outstanding = max(payable - already, 0.0)
        raise ConflictError(
            f"That would pay {already + amount:.2f} against a repair of "
            f"{payable:.2f} (from the {basis}). Only {outstanding:.2f} is "
            f"outstanding. Correct the repair amount if the mechanic billed "
            f"more than was captured."
        )

    reference = (payment_reference or "").strip() or None
    if reference:
        clash = (
            db.query(MechanicPayment)
            .filter(
                MechanicPayment.repair_job_id == repair_job_id,
                MechanicPayment.reversed_at.is_(None),
                func.lower(func.trim(MechanicPayment.payment_reference)) == reference.lower(),
            )
            .first()
        )
        if clash is not None:
            raise ConflictError(
                f"Payment reference {reference} is already recorded against "
                f"this repair on {clash.payment_date}. Recording it again "
                f"would show the mechanic as paid twice."
            )

    payment = MechanicPayment(
        repair_job_id=repair_job_id,
        supplier_id=supplier_id,
        # Fall back to the workshop already named on the repair, so the
        # payment is attributable even when the form leaves it blank.
        mechanic_name=(mechanic_name or job.workshop_name),
        amount=amount,
        payment_date=payment_date,
        payment_method=payment_method,
        payment_reference=reference,
        notes=notes,
        proof_file_url=proof_file_url,
        recorded_by=actor_id,
    )
    db.add(payment)
    db.flush()

    audit_service.write_event(
        db, AuditAction.CREATE, "mechanic_payment", actor_id, payment.id,
        after_value={
            "repair_job_id": str(repair_job_id),
            "amount": amount,
            "payment_date": payment_date.isoformat(),
            "payment_reference": reference,
            "paid_after": round(already + amount, 2),
            "payable": round(payable, 2),
        },
        notes=f"Mechanic payment of {amount:.2f} recorded against repair {job.title}.",
    )
    return payment


def reverse_payment(
    db: Session,
    payment_id: uuid.UUID,
    *,
    actor_id: Optional[uuid.UUID],
    reason: str,
) -> MechanicPayment:
    """
    Undo a payment without erasing it.

    A payment recorded in error has to stop counting towards the balance, but
    it must not vanish — someone reconciling the account later needs to see
    that it was entered and withdrawn, and by whom.
    """
    payment = db.get(MechanicPayment, payment_id)
    if payment is None:
        raise NotFoundError("Payment not found.")
    if payment.reversed_at is not None:
        raise ConflictError("That payment has already been reversed.")
    if not (reason or "").strip():
        raise ValidationError("A reversal needs a reason.")

    payment.reversed_at = _now()
    payment.reversed_by = actor_id
    payment.reversal_reason = reason.strip()

    audit_service.write_event(
        db, AuditAction.UPDATE, "mechanic_payment", actor_id, payment.id,
        before_value={"reversed": False, "amount": float(payment.amount)},
        after_value={"reversed": True, "reason": reason.strip()},
        notes="Mechanic payment reversed.",
    )
    return payment


def list_payments(db: Session, repair_job_id: uuid.UUID) -> list[MechanicPayment]:
    """Payment history for one repair, newest first, reversals included."""
    return (
        db.query(MechanicPayment)
        .filter(MechanicPayment.repair_job_id == repair_job_id)
        .order_by(MechanicPayment.payment_date.desc(), MechanicPayment.created_at.desc())
        .all()
    )


# ── The overview ─────────────────────────────────────────────────────────────

def _payable_repairs_query(
    db: Session,
    *,
    mechanic: Optional[str] = None,
    vehicle_id: Optional[uuid.UUID] = None,
    company_id: Optional[uuid.UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
):
    """
    Repairs that could owe a mechanic something, with the filters applied in
    the database. Status is not among them — it is derived per repair, so it
    is filtered after the figures are computed.
    """
    from app.models.project import Project

    q = db.query(RepairJob).join(Vehicle, Vehicle.id == RepairJob.vehicle_id)

    if mechanic and mechanic.strip():
        like = f"%{mechanic.strip()}%"
        q = q.filter(func.coalesce(RepairJob.workshop_name, "").ilike(like))
    if vehicle_id:
        q = q.filter(RepairJob.vehicle_id == vehicle_id)
    if company_id:
        # A vehicle belongs to a company through the project it is assigned
        # to; there is no direct link, and inventing one would duplicate it.
        q = q.join(Project, Project.id == Vehicle.assigned_project_id).filter(
            Project.company_id == company_id
        )
    if date_from:
        q = q.filter(RepairJob.date_opened >= date_from)
    if date_to:
        q = q.filter(RepairJob.date_opened <= date_to)

    return q


def overview(
    db: Session,
    *,
    page: int = 1,
    limit: int = 25,
    mechanic: Optional[str] = None,
    vehicle_id: Optional[uuid.UUID] = None,
    company_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    unpaid_only: bool = False,
) -> dict:
    """
    One page of the mechanic payments view, plus totals for everything the
    filters match — not just the page, because "total outstanding" is only
    useful as a whole figure.
    """
    q = _payable_repairs_query(
        db, mechanic=mechanic, vehicle_id=vehicle_id, company_id=company_id,
        date_from=date_from, date_to=date_to,
    )

    rows = [
        repair_payment_summary(db, job)
        for job in q.order_by(RepairJob.date_opened.desc(), RepairJob.id.desc()).all()
    ]

    # Repairs with nothing recognised against them are not payables; showing
    # them would pad the list with jobs nobody can pay.
    rows = [r for r in rows if r["total_payable"] > CENT]

    if unpaid_only:
        rows = [r for r in rows if r["payment_status"] != PAID]
    if status:
        rows = [r for r in rows if r["payment_status"] == status]

    totals = {
        "total_payable": round(sum(r["total_payable"] for r in rows), 2),
        "total_paid": round(sum(r["total_paid"] for r in rows), 2),
        "total_outstanding": round(sum(r["outstanding"] for r in rows), 2),
        "repairs": len(rows),
        "unpaid": sum(1 for r in rows if r["payment_status"] == UNPAID),
        "partially_paid": sum(1 for r in rows if r["payment_status"] == PARTIALLY_PAID),
        "paid": sum(1 for r in rows if r["payment_status"] == PAID),
    }

    total = len(rows)
    start = (page - 1) * limit
    return {
        "items": rows[start:start + limit],
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, -(-total // limit)),
        "totals": totals,
    }
