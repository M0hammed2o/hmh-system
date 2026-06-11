"""Subcontractor Work Done service — CRUD, approval chain, duplicate check, monthly summary."""

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import AuditAction, WorkDoneStatus
from app.models.work_done import SubcontractorWorkDone
from app.models.project import Project
from app.services import audit_service


def _get_or_404(db: Session, wd_id: uuid.UUID) -> SubcontractorWorkDone:
    wd = db.get(SubcontractorWorkDone, wd_id)
    if not wd:
        raise NotFoundError(f"Work done record {wd_id} not found.")
    return wd


def _next_number(db: Session, project_id: uuid.UUID) -> str:
    count = db.query(SubcontractorWorkDone).filter(
        SubcontractorWorkDone.project_id == project_id
    ).count()
    return f"WD-{str(project_id)[:6].upper()}-{count + 1:04d}"


def _check_duplicate(
    db: Session,
    supplier_id: uuid.UUID,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    lot_id: Optional[uuid.UUID],
    stage_status_id: Optional[uuid.UUID],
    month: date,
    exclude_id: Optional[uuid.UUID] = None,
) -> bool:
    """Return True if a PAID work done record exists for the same combination."""
    q = db.query(SubcontractorWorkDone).filter(
        SubcontractorWorkDone.status == WorkDoneStatus.PAID,
        SubcontractorWorkDone.supplier_id == supplier_id,
        SubcontractorWorkDone.project_id == project_id,
        SubcontractorWorkDone.site_id == site_id,
        SubcontractorWorkDone.month == month,
    )
    if lot_id:
        q = q.filter(SubcontractorWorkDone.lot_id == lot_id)
    else:
        q = q.filter(SubcontractorWorkDone.lot_id.is_(None))
    if stage_status_id:
        q = q.filter(SubcontractorWorkDone.stage_status_id == stage_status_id)
    else:
        q = q.filter(SubcontractorWorkDone.stage_status_id.is_(None))
    if exclude_id:
        q = q.filter(SubcontractorWorkDone.id != exclude_id)
    return q.first() is not None


def list_work_done(
    db: Session,
    project_id: uuid.UUID,
    status: Optional[WorkDoneStatus] = None,
    site_id: Optional[uuid.UUID] = None,
    lot_id: Optional[uuid.UUID] = None,
    supplier_id: Optional[uuid.UUID] = None,
    month: Optional[date] = None,
) -> list[SubcontractorWorkDone]:
    if not db.get(Project, project_id):
        raise NotFoundError(f"Project {project_id} not found.")
    q = db.query(SubcontractorWorkDone).filter(
        SubcontractorWorkDone.project_id == project_id
    )
    if status:
        q = q.filter(SubcontractorWorkDone.status == status)
    if site_id:
        q = q.filter(SubcontractorWorkDone.site_id == site_id)
    if lot_id:
        q = q.filter(SubcontractorWorkDone.lot_id == lot_id)
    if supplier_id:
        q = q.filter(SubcontractorWorkDone.supplier_id == supplier_id)
    if month:
        q = q.filter(SubcontractorWorkDone.month == month)
    return q.order_by(SubcontractorWorkDone.created_at.desc()).all()


def create_work_done(
    db: Session,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    supplier_id: uuid.UUID,
    work_description: str,
    quantity: float,
    unit: Optional[str],
    rate: float,
    month: date,
    created_by: uuid.UUID,
    lot_id: Optional[uuid.UUID] = None,
    stage_status_id: Optional[uuid.UUID] = None,
    job_card_id: Optional[uuid.UUID] = None,
    comments: Optional[str] = None,
) -> SubcontractorWorkDone:
    if not db.get(Project, project_id):
        raise NotFoundError(f"Project {project_id} not found.")

    # Normalise month to first of month
    month = month.replace(day=1)

    # Duplicate payment guard
    if _check_duplicate(db, supplier_id, project_id, site_id, lot_id, stage_status_id, month):
        raise ValidationError(
            "A PAID claim already exists for this subcontractor, project, site, "
            "lot, milestone and month. Cannot create a duplicate."
        )

    amount = round(float(quantity) * float(rate), 2)
    now = datetime.now(timezone.utc)

    wd = SubcontractorWorkDone(
        work_done_number=_next_number(db, project_id),
        project_id=project_id,
        site_id=site_id,
        lot_id=lot_id,
        stage_status_id=stage_status_id,
        supplier_id=supplier_id,
        job_card_id=job_card_id,
        work_description=work_description,
        quantity=quantity,
        unit=unit,
        rate=rate,
        amount=amount,
        month=month,
        comments=comments,
        status=WorkDoneStatus.DRAFT,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    db.add(wd)
    audit_service.write_event(db, AuditAction.CREATE, "work_done", created_by, wd.id,
                              after_value={"number": wd.work_done_number, "amount": amount})
    db.commit()
    db.refresh(wd)
    return wd


def update_work_done(
    db: Session,
    wd_id: uuid.UUID,
    actor_id: uuid.UUID,
    work_description: Optional[str] = None,
    quantity: Optional[float] = None,
    unit: Optional[str] = None,
    rate: Optional[float] = None,
    month: Optional[date] = None,
    comments: Optional[str] = None,
    lot_id: Optional[uuid.UUID] = None,
    stage_status_id: Optional[uuid.UUID] = None,
    job_card_id: Optional[uuid.UUID] = None,
) -> SubcontractorWorkDone:
    wd = _get_or_404(db, wd_id)
    if wd.status not in (WorkDoneStatus.DRAFT, WorkDoneStatus.REJECTED):
        raise ValidationError("Only DRAFT or REJECTED records can be edited.")

    if work_description is not None:
        wd.work_description = work_description
    if comments is not None:
        wd.comments = comments
    if lot_id is not None:
        wd.lot_id = lot_id
    if stage_status_id is not None:
        wd.stage_status_id = stage_status_id
    if job_card_id is not None:
        wd.job_card_id = job_card_id
    if unit is not None:
        wd.unit = unit

    qty = quantity if quantity is not None else float(wd.quantity)
    rt  = rate     if rate     is not None else float(wd.rate)
    if quantity is not None:
        wd.quantity = qty
    if rate is not None:
        wd.rate = rt
    wd.amount = round(qty * rt, 2)

    if month is not None:
        wd.month = month.replace(day=1)

    wd.updated_at = datetime.now(timezone.utc)
    audit_service.write_event(db, AuditAction.UPDATE, "work_done", actor_id, wd.id,
                              after_value={"amount": float(wd.amount)})
    db.commit()
    db.refresh(wd)
    return wd


def _transition(
    db: Session,
    wd: SubcontractorWorkDone,
    new_status: WorkDoneStatus,
    actor_id: uuid.UUID,
    **kwargs,
) -> SubcontractorWorkDone:
    now = datetime.now(timezone.utc)
    wd.status = new_status
    wd.updated_at = now
    for k, v in kwargs.items():
        setattr(wd, k, v)
    audit_service.write_event(db, AuditAction.UPDATE, "work_done", actor_id, wd.id,
                              after_value={"status": new_status.value})
    db.commit()
    db.refresh(wd)
    return wd


def submit(db: Session, wd_id: uuid.UUID, actor_id: uuid.UUID) -> SubcontractorWorkDone:
    wd = _get_or_404(db, wd_id)
    if wd.status not in (WorkDoneStatus.DRAFT, WorkDoneStatus.REJECTED):
        raise ValidationError("Only DRAFT or REJECTED records can be submitted.")
    now = datetime.now(timezone.utc)
    return _transition(db, wd, WorkDoneStatus.SUBMITTED, actor_id,
                       submitted_by=actor_id, submitted_at=now)


def site_approve(db: Session, wd_id: uuid.UUID, actor_id: uuid.UUID) -> SubcontractorWorkDone:
    wd = _get_or_404(db, wd_id)
    if wd.status != WorkDoneStatus.SUBMITTED:
        raise ValidationError("Record must be SUBMITTED before site approval.")
    now = datetime.now(timezone.utc)
    return _transition(db, wd, WorkDoneStatus.SITE_APPROVED, actor_id,
                       site_approved_by=actor_id, site_approved_at=now)


def office_approve(db: Session, wd_id: uuid.UUID, actor_id: uuid.UUID) -> SubcontractorWorkDone:
    wd = _get_or_404(db, wd_id)
    if wd.status != WorkDoneStatus.SITE_APPROVED:
        raise ValidationError("Record must have site approval before office approval.")
    now = datetime.now(timezone.utc)
    return _transition(db, wd, WorkDoneStatus.OFFICE_APPROVED, actor_id,
                       office_approved_by=actor_id, office_approved_at=now)


def mark_paid(db: Session, wd_id: uuid.UUID, actor_id: uuid.UUID) -> SubcontractorWorkDone:
    from app.models.payment import Payment
    from app.models.enums import PaymentStatus, PaymentType

    wd = _get_or_404(db, wd_id)
    if wd.status != WorkDoneStatus.OFFICE_APPROVED:
        raise ValidationError("Record must be OFFICE_APPROVED before marking paid.")

    amount = float(wd.amount or 0)
    if amount > 0:
        db.add(Payment(
            project_id=wd.project_id,
            payment_type=PaymentType.LABOUR,
            amount_paid=amount,
            status=PaymentStatus.PAID,
            payment_reference=wd.work_done_number,
            payment_date=datetime.now(timezone.utc).date(),
            notes=f"Subcontractor: {(wd.work_description or wd.work_done_number or '')[:200]}",
            captured_by=actor_id,
            approved_by=actor_id,
        ))

    # Update milestone progress if linked
    if wd.stage_status_id:
        _update_milestone_progress(db, wd.stage_status_id, actor_id)

    now = datetime.now(timezone.utc)
    return _transition(db, wd, WorkDoneStatus.PAID, actor_id,
                       paid_by=actor_id, paid_at=now)


def reject(
    db: Session, wd_id: uuid.UUID, actor_id: uuid.UUID, reason: str
) -> SubcontractorWorkDone:
    wd = _get_or_404(db, wd_id)
    if wd.status == WorkDoneStatus.PAID:
        raise ValidationError("Cannot reject a paid record.")
    return _transition(db, wd, WorkDoneStatus.REJECTED, actor_id,
                       rejection_reason=reason)


def _update_milestone_progress(
    db: Session, stage_status_id: uuid.UUID, actor_id: uuid.UUID
) -> None:
    """Mark the linked milestone as IN_PROGRESS when a payment is made."""
    from app.models.stage import ProjectStageStatus
    from app.models.enums import StageStatus
    pss = db.get(ProjectStageStatus, stage_status_id)
    if pss and pss.status == StageStatus.NOT_STARTED:
        pss.status = StageStatus.IN_PROGRESS
        pss.updated_at = datetime.now(timezone.utc)
        db.flush()


def get_monthly_summary(
    db: Session,
    project_id: uuid.UUID,
    month: Optional[date] = None,
    site_id: Optional[uuid.UUID] = None,
    supplier_id: Optional[uuid.UUID] = None,
) -> dict:
    """Return aggregated summary of work done claims for a given month/project/filter."""
    from app.models.supplier import Supplier
    from app.models.site import Site

    q = db.query(SubcontractorWorkDone).filter(
        SubcontractorWorkDone.project_id == project_id
    )
    if month:
        q = q.filter(SubcontractorWorkDone.month == month.replace(day=1))
    if site_id:
        q = q.filter(SubcontractorWorkDone.site_id == site_id)
    if supplier_id:
        q = q.filter(SubcontractorWorkDone.supplier_id == supplier_id)

    records = q.order_by(SubcontractorWorkDone.month, SubcontractorWorkDone.supplier_id).all()

    # Build per-supplier summary
    by_supplier: dict = {}
    total_amount = 0.0
    paid_amount  = 0.0

    for r in records:
        sid = str(r.supplier_id)
        if sid not in by_supplier:
            sup = db.get(Supplier, r.supplier_id)
            by_supplier[sid] = {
                "supplier_id": sid,
                "supplier_name": sup.name if sup else "Unknown",
                "count": 0,
                "total_amount": 0.0,
                "paid_amount": 0.0,
                "statuses": {},
            }
        entry = by_supplier[sid]
        entry["count"] += 1
        entry["total_amount"] += float(r.amount or 0)
        total_amount += float(r.amount or 0)
        status_key = r.status.value
        entry["statuses"][status_key] = entry["statuses"].get(status_key, 0) + 1
        if r.status == WorkDoneStatus.PAID:
            entry["paid_amount"] += float(r.amount or 0)
            paid_amount += float(r.amount or 0)

    return {
        "project_id": str(project_id),
        "month": month.isoformat() if month else None,
        "total_records": len(records),
        "total_amount": round(total_amount, 2),
        "paid_amount": round(paid_amount, 2),
        "pending_amount": round(total_amount - paid_amount, 2),
        "by_supplier": list(by_supplier.values()),
    }


def get_summary(db: Session, project_id: uuid.UUID) -> dict:
    """Quick status count breakdown for the project dashboard."""
    rows = (
        db.query(SubcontractorWorkDone.status, func.count(SubcontractorWorkDone.id),
                 func.sum(SubcontractorWorkDone.amount))
        .filter(SubcontractorWorkDone.project_id == project_id)
        .group_by(SubcontractorWorkDone.status)
        .all()
    )
    counts = {r[0].value: {"count": r[1], "total": float(r[2] or 0)} for r in rows}
    pending = sum(
        v["count"] for k, v in counts.items()
        if k in ("SUBMITTED", "SITE_APPROVED", "OFFICE_APPROVED")
    )
    return {
        "by_status": counts,
        "pending_payment_count": pending,
        "pending_payment_amount": sum(
            v["total"] for k, v in counts.items()
            if k in ("SUBMITTED", "SITE_APPROVED", "OFFICE_APPROVED")
        ),
    }
