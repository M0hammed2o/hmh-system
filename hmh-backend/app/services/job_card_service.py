"""Job Card service — labour approval chain."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import AuditAction, JobCardStatus, JobCardWorkType
from app.models.job_card import JobCard, OWNER_APPROVAL_THRESHOLD
from app.models.project import Project
from app.services import audit_service


def _get_or_404(db: Session, jc_id: uuid.UUID) -> JobCard:
    jc = db.get(JobCard, jc_id)
    if not jc:
        raise NotFoundError(f"Job card {jc_id} not found.")
    return jc


def _next_number(db: Session, project_id: uuid.UUID) -> str:
    count = db.query(JobCard).filter(JobCard.project_id == project_id).count()
    return f"JC-{str(project_id)[:6].upper()}-{count + 1:03d}"


def list_job_cards(
    db: Session,
    project_id: uuid.UUID,
    status: Optional[JobCardStatus] = None,
    site_id: Optional[uuid.UUID] = None,
    lot_id: Optional[uuid.UUID] = None,
) -> list[JobCard]:
    if not db.get(Project, project_id):
        raise NotFoundError(f"Project {project_id} not found.")
    q = db.query(JobCard).filter(JobCard.project_id == project_id)
    if status:
        q = q.filter(JobCard.status == status)
    if site_id:
        q = q.filter(JobCard.site_id == site_id)
    if lot_id:
        q = q.filter(JobCard.lot_id == lot_id)
    return q.order_by(JobCard.created_at.desc()).all()


def create_job_card(
    db: Session,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    work_description: str,
    work_type: JobCardWorkType,
    quantity: float,
    unit: Optional[str],
    rate: float,
    created_by: uuid.UUID,
    lot_id: Optional[uuid.UUID] = None,
    stage_id: Optional[uuid.UUID] = None,
    worker_name: Optional[str] = None,
    team_name: Optional[str] = None,
    work_date=None,
    notes: Optional[str] = None,
) -> JobCard:
    if not db.get(Project, project_id):
        raise NotFoundError(f"Project {project_id} not found.")

    total = round(quantity * rate, 2)
    now = datetime.now(timezone.utc)

    jc = JobCard(
        job_card_number=_next_number(db, project_id),
        project_id=project_id,
        site_id=site_id,
        lot_id=lot_id,
        stage_id=stage_id,
        work_description=work_description,
        work_type=work_type,
        worker_name=worker_name,
        team_name=team_name,
        quantity=quantity,
        unit=unit,
        rate=rate,
        total_amount=total,
        owner_approval_required=total >= OWNER_APPROVAL_THRESHOLD,
        status=JobCardStatus.DRAFT,
        work_date=work_date,
        notes=notes,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    db.add(jc)
    audit_service.write_event(db, AuditAction.CREATE, "job_card", created_by, jc.id,
                              after_value={"number": jc.job_card_number, "total": total})
    db.commit()
    db.refresh(jc)
    return jc


def _transition(db: Session, jc: JobCard, new_status: JobCardStatus, actor_id: uuid.UUID, **kwargs) -> JobCard:
    now = datetime.now(timezone.utc)
    jc.status = new_status
    jc.updated_at = now
    for k, v in kwargs.items():
        setattr(jc, k, v)
    audit_service.write_event(db, AuditAction.UPDATE, "job_card", actor_id, jc.id,
                              after_value={"status": new_status.value})
    db.commit()
    db.refresh(jc)
    return jc


def submit(db: Session, jc_id: uuid.UUID, actor_id: uuid.UUID) -> JobCard:
    jc = _get_or_404(db, jc_id)
    if jc.status != JobCardStatus.DRAFT:
        raise ValidationError("Only DRAFT job cards can be submitted.")
    now = datetime.now(timezone.utc)
    return _transition(db, jc, JobCardStatus.SUBMITTED, actor_id,
                       submitted_by=actor_id, submitted_at=now)


def site_approve(db: Session, jc_id: uuid.UUID, actor_id: uuid.UUID) -> JobCard:
    jc = _get_or_404(db, jc_id)
    if jc.status != JobCardStatus.SUBMITTED:
        raise ValidationError("Job card must be SUBMITTED before site approval.")
    now = datetime.now(timezone.utc)
    return _transition(db, jc, JobCardStatus.SITE_APPROVED, actor_id,
                       site_approved_by=actor_id, site_approved_at=now)


def office_approve(db: Session, jc_id: uuid.UUID, actor_id: uuid.UUID) -> JobCard:
    jc = _get_or_404(db, jc_id)
    if jc.status != JobCardStatus.SITE_APPROVED:
        raise ValidationError("Job card must have site approval first.")
    now = datetime.now(timezone.utc)
    next_status = JobCardStatus.OWNER_APPROVED if not jc.owner_approval_required else JobCardStatus.OFFICE_APPROVED
    # If owner not required, skip straight to OFFICE_APPROVED which is payment-ready
    return _transition(db, jc, JobCardStatus.OFFICE_APPROVED, actor_id,
                       office_approved_by=actor_id, office_approved_at=now)


def owner_approve(db: Session, jc_id: uuid.UUID, actor_id: uuid.UUID) -> JobCard:
    jc = _get_or_404(db, jc_id)
    if jc.status != JobCardStatus.OFFICE_APPROVED:
        raise ValidationError("Job card must have office approval before owner approval.")
    now = datetime.now(timezone.utc)
    return _transition(db, jc, JobCardStatus.OWNER_APPROVED, actor_id,
                       owner_approved_by=actor_id, owner_approved_at=now)


def approve_payment(db: Session, jc_id: uuid.UUID, actor_id: uuid.UUID) -> JobCard:
    jc = _get_or_404(db, jc_id)
    required = JobCardStatus.OWNER_APPROVED if jc.owner_approval_required else JobCardStatus.OFFICE_APPROVED
    if jc.status != required:
        raise ValidationError(f"Job card must be {required.value} before payment approval.")
    now = datetime.now(timezone.utc)
    return _transition(db, jc, JobCardStatus.PAYMENT_APPROVED, actor_id,
                       payment_approved_by=actor_id, payment_approved_at=now)


def mark_paid(db: Session, jc_id: uuid.UUID, actor_id: uuid.UUID) -> JobCard:
    from datetime import datetime, timezone
    from app.models.payment import Payment
    from app.models.enums import PaymentStatus, PaymentType

    jc = _get_or_404(db, jc_id)
    if jc.status != JobCardStatus.PAYMENT_APPROVED:
        raise ValidationError("Job card must be PAYMENT_APPROVED before marking paid.")

    # Create a Payment record so labour payments appear on the Payments page.
    amount = float(jc.total_amount or 0)
    if amount > 0:
        db.add(Payment(
            project_id=jc.project_id,
            payment_type=PaymentType.LABOUR,
            amount_paid=amount,
            status=PaymentStatus.PAID,
            payment_reference=jc.job_card_number,
            payment_date=datetime.now(timezone.utc).date(),
            notes=f"Labour: {(jc.work_description or jc.job_card_number or '')[:200]}",
            captured_by=actor_id,
            approved_by=actor_id,
        ))

    return _transition(db, jc, JobCardStatus.PAID, actor_id)


def reject(db: Session, jc_id: uuid.UUID, actor_id: uuid.UUID, reason: str) -> JobCard:
    jc = _get_or_404(db, jc_id)
    if jc.status in (JobCardStatus.PAID,):
        raise ValidationError("Cannot reject a paid job card.")
    return _transition(db, jc, JobCardStatus.REJECTED, actor_id,
                       rejection_reason=reason)


def get_summary(db: Session, project_id: uuid.UUID) -> dict:
    """Count job cards by status for the owner dashboard."""
    from sqlalchemy import func
    rows = (
        db.query(JobCard.status, func.count(JobCard.id), func.sum(JobCard.total_amount))
        .filter(JobCard.project_id == project_id)
        .group_by(JobCard.status)
        .all()
    )
    counts = {r[0].value: {"count": r[1], "total": float(r[2] or 0)} for r in rows}
    pending_payment = sum(
        v["count"] for k, v in counts.items()
        if k in ("OFFICE_APPROVED", "OWNER_APPROVED", "PAYMENT_APPROVED")
    )
    return {
        "by_status": counts,
        "pending_payment_count": pending_payment,
        "pending_payment_amount": sum(
            v["total"] for k, v in counts.items()
            if k in ("OFFICE_APPROVED", "OWNER_APPROVED", "PAYMENT_APPROVED")
        ),
    }
