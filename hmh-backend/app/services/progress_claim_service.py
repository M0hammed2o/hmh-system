"""
Municipality Progress Claim service.

Responsibilities:
  - CRUD for MunicipalityProgressClaim
  - Auto-generation of ProgressClaimLine records from canonical operational sources
  - Status transitions with audit events and notifications
  - PDF export of the claim as a structured supporting document
  - Snapshot creation on APPROVED transition (immutable copy)

PRIMARY BUSINESS RULE: No monetary amounts are generated. The claim shows
completed work evidence only. Pricing is a human task performed after the
claim reaches READY_FOR_PRICING status.
"""

from __future__ import annotations

import io
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session, selectinload

from app.models.progress_claim import (
    MunicipalityProgressClaim,
    ProgressClaimLine,
    ProgressClaimEvidence,
)
from app.models.stage import ProjectStageStatus
from app.models.work_done import SubcontractorWorkDone
from app.models.job_card import JobCard
from app.models.lot import Lot
from app.models.stage import StageMaster
from app.models.enums import (
    ProgressClaimStatus,
    ClaimSourceType,
    StageStatus,
    WorkDoneStatus,
    JobCardStatus,
    AuditAction,
    AlertType,
    AlertSeverity,
)
from app.services import audit_service


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Number generation ──────────────────────────────────────────────────────────

def _next_claim_number(db: Session) -> str:
    year = datetime.now().year
    prefix = f"PC-{year}-"
    latest = (
        db.execute(
            select(MunicipalityProgressClaim.claim_number)
            .where(MunicipalityProgressClaim.claim_number.like(f"{prefix}%"))
            .order_by(MunicipalityProgressClaim.claim_number.desc())
        ).scalars().first()
    )
    seq = 1
    if latest:
        try:
            seq = int(latest.split("-")[-1]) + 1
        except (ValueError, IndexError):
            pass
    return f"{prefix}{seq:04d}"


# ── CRUD ───────────────────────────────────────────────────────────────────────

def create_claim(
    db: Session,
    project_id: uuid.UUID,
    data: dict,
    actor_id: Optional[uuid.UUID] = None,
) -> MunicipalityProgressClaim:
    claim_number = _next_claim_number(db)
    period_end = data.get("period_end")
    cutoff = data.get("reporting_cutoff_date") or period_end

    claim = MunicipalityProgressClaim(
        claim_number=claim_number,
        project_id=project_id,
        site_id=data.get("site_id"),
        claim_title=data["claim_title"],
        municipality_name=data.get("municipality_name", "Ethekweni Municipality"),
        cert_number=data.get("cert_number"),
        period_start=data["period_start"],
        period_end=period_end,
        reporting_cutoff_date=cutoff,
        status=ProgressClaimStatus.DRAFT.value,
        notes=data.get("notes"),
        created_by=actor_id,
    )
    db.add(claim)
    db.flush()

    audit_service.write_event(
        db,
        action=AuditAction.CREATE,
        entity_type="MunicipalityProgressClaim",
        actor_id=actor_id,
        entity_id=claim.id,
        after_value={"claim_number": claim_number, "status": claim.status},
    )
    return claim


def get_claim(db: Session, claim_id: uuid.UUID) -> Optional[MunicipalityProgressClaim]:
    return db.execute(
        select(MunicipalityProgressClaim)
        .where(MunicipalityProgressClaim.id == claim_id)
        .options(
            selectinload(MunicipalityProgressClaim.lines).selectinload(ProgressClaimLine.evidence),
            selectinload(MunicipalityProgressClaim.evidence),
        )
    ).scalars().first()


def list_claims(
    db: Session,
    project_id: uuid.UUID,
    site_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
) -> list[MunicipalityProgressClaim]:
    q = select(MunicipalityProgressClaim).where(
        MunicipalityProgressClaim.project_id == project_id
    )
    if site_id:
        q = q.where(MunicipalityProgressClaim.site_id == site_id)
    if status:
        q = q.where(MunicipalityProgressClaim.status == status)
    q = q.order_by(MunicipalityProgressClaim.period_start.desc())
    return list(db.execute(q).scalars().all())


def update_claim(
    db: Session,
    claim: MunicipalityProgressClaim,
    data: dict,
    actor_id: Optional[uuid.UUID] = None,
) -> MunicipalityProgressClaim:
    _assert_editable(claim)
    before = {"status": claim.status, "claim_title": claim.claim_title}

    for field in ["claim_title", "municipality_name", "cert_number", "period_start",
                  "period_end", "reporting_cutoff_date", "notes", "linked_invoice_id"]:
        if field in data and data[field] is not None:
            setattr(claim, field, data[field])

    claim.updated_at = _now()
    db.flush()

    audit_service.write_event(
        db,
        action=AuditAction.UPDATE,
        entity_type="MunicipalityProgressClaim",
        actor_id=actor_id,
        entity_id=claim.id,
        before_value=before,
        after_value={"status": claim.status, "claim_title": claim.claim_title},
    )
    return claim


def delete_claim(
    db: Session,
    claim: MunicipalityProgressClaim,
    actor_id: Optional[uuid.UUID] = None,
) -> None:
    _assert_editable(claim)
    audit_service.write_event(
        db,
        action=AuditAction.DELETE,
        entity_type="MunicipalityProgressClaim",
        actor_id=actor_id,
        entity_id=claim.id,
        before_value={"claim_number": claim.claim_number},
    )
    db.delete(claim)
    db.flush()


def _assert_editable(claim: MunicipalityProgressClaim) -> None:
    if claim.status in (ProgressClaimStatus.APPROVED.value, ProgressClaimStatus.EXPORTED.value):
        raise ValueError(f"Claim {claim.claim_number} is {claim.status} and cannot be modified.")


# ── Claim-line generation ──────────────────────────────────────────────────────

def generate_lines(
    db: Session,
    claim: MunicipalityProgressClaim,
    actor_id: Optional[uuid.UUID] = None,
    include_work_done: bool = True,
    include_job_cards: bool = True,
    include_milestones: bool = True,
    overwrite_existing: bool = False,
) -> dict:
    """
    Auto-generate ProgressClaimLine records from:
      1. ProjectStageStatus records COMPLETED/CERTIFIED with completed_at in period
      2. SubcontractorWorkDone records SITE_APPROVED+ with month in period
      3. JobCard records OWNER_APPROVED+ with work_date in period

    Returns a summary dict with counts.
    Anti-duplicate rule: (claim_id, lot_id, stage_status_id, source_type) is UNIQUE.
    No monetary amounts are generated — this is work evidence only.
    """
    if claim.status in (ProgressClaimStatus.APPROVED.value, ProgressClaimStatus.EXPORTED.value):
        raise ValueError(
            f"Cannot regenerate lines for claim {claim.claim_number} in status {claim.status}."
        )

    if overwrite_existing:
        db.query(ProgressClaimLine).filter(
            ProgressClaimLine.claim_id == claim.id,
            ProgressClaimLine.is_system_generated == True,
        ).delete(synchronize_session="fetch")

    summary = {
        "milestone_lines": 0,
        "work_done_lines": 0,
        "job_card_lines": 0,
        "skipped_duplicates": 0,
    }

    period_start = claim.period_start
    period_end = claim.period_end
    cutoff = claim.reporting_cutoff_date
    sort_counter = [0]

    def _next_sort() -> int:
        sort_counter[0] += 1
        return sort_counter[0]

    def _exists(lot_id, stage_status_id, source_type: str) -> bool:
        return db.execute(
            select(ProgressClaimLine.id).where(
                ProgressClaimLine.claim_id == claim.id,
                ProgressClaimLine.lot_id == lot_id,
                ProgressClaimLine.stage_status_id == stage_status_id,
                ProgressClaimLine.source_type == source_type,
            )
        ).scalars().first() is not None

    # ── 1. Stage milestones ────────────────────────────────────────────────────
    if include_milestones:
        milestones = db.execute(
            select(ProjectStageStatus)
            .where(
                ProjectStageStatus.project_id == claim.project_id,
                ProjectStageStatus.status.in_([StageStatus.COMPLETED.value, StageStatus.CERTIFIED.value]),
                ProjectStageStatus.completed_at >= datetime(period_start.year, period_start.month, period_start.day, tzinfo=timezone.utc),
                ProjectStageStatus.completed_at <= datetime(cutoff.year, cutoff.month, cutoff.day, 23, 59, 59, tzinfo=timezone.utc),
            )
        ).scalars().all()

        if claim.site_id:
            milestones = [m for m in milestones if m.site_id == claim.site_id]

        for m in milestones:
            lot_number = None
            if m.lot_id:
                lot = db.get(Lot, m.lot_id)
                lot_number = lot.lot_number if lot else None

            stage_name = None
            if m.stage_id:
                sm = db.get(StageMaster, m.stage_id)
                stage_name = sm.name if sm else None

            if _exists(m.lot_id, m.id, ClaimSourceType.STAGE_MILESTONE.value):
                summary["skipped_duplicates"] += 1
                continue

            line = ProgressClaimLine(
                claim_id=claim.id,
                source_type=ClaimSourceType.STAGE_MILESTONE.value,
                lot_id=m.lot_id,
                stage_status_id=m.id,
                description=f"Stage {stage_name or 'Unknown'} — {m.status} on lot {lot_number or 'N/A'}",
                stage_name=stage_name,
                lot_number=lot_number,
                work_date=m.completed_at.date() if m.completed_at else period_end,
                progress_pct=m.progress_pct,
                is_system_generated=True,
                sort_order=_next_sort(),
            )
            db.add(line)
            summary["milestone_lines"] += 1

    # ── 2. Subcontractor Work Done ─────────────────────────────────────────────
    if include_work_done:
        work_done_records = db.execute(
            select(SubcontractorWorkDone)
            .where(
                SubcontractorWorkDone.project_id == claim.project_id,
                SubcontractorWorkDone.status.in_([
                    WorkDoneStatus.SITE_APPROVED.value,
                    WorkDoneStatus.OFFICE_APPROVED.value,
                    WorkDoneStatus.PAID.value,
                ]),
                SubcontractorWorkDone.month >= date(period_start.year, period_start.month, 1),
                SubcontractorWorkDone.month <= date(cutoff.year, cutoff.month, 1),
            )
        ).scalars().all()

        if claim.site_id:
            work_done_records = [w for w in work_done_records if w.site_id == claim.site_id]

        for wd in work_done_records:
            lot_number = None
            if wd.lot_id:
                lot = db.get(Lot, wd.lot_id)
                lot_number = lot.lot_number if lot else None

            if _exists(wd.lot_id, wd.stage_status_id, ClaimSourceType.WORK_DONE.value):
                summary["skipped_duplicates"] += 1
                continue

            qty_str = f"{wd.quantity}" if wd.quantity is not None else None

            line = ProgressClaimLine(
                claim_id=claim.id,
                source_type=ClaimSourceType.WORK_DONE.value,
                lot_id=wd.lot_id,
                stage_status_id=wd.stage_status_id,
                work_done_id=wd.id,
                description=wd.work_description or f"Subcontractor work — {wd.work_done_number}",
                lot_number=lot_number,
                work_date=wd.month,
                quantity=qty_str,
                unit=wd.unit,
                is_system_generated=True,
                sort_order=_next_sort(),
            )
            db.add(line)
            summary["work_done_lines"] += 1

    # ── 3. Job Cards ───────────────────────────────────────────────────────────
    if include_job_cards:
        job_cards = db.execute(
            select(JobCard)
            .where(
                JobCard.project_id == claim.project_id,
                JobCard.status.in_([
                    JobCardStatus.OWNER_APPROVED.value,
                    JobCardStatus.PAYMENT_APPROVED.value,
                    JobCardStatus.PAID.value,
                ]),
                JobCard.work_date >= period_start,
                JobCard.work_date <= cutoff,
            )
        ).scalars().all()

        if claim.site_id:
            job_cards = [j for j in job_cards if j.site_id == claim.site_id]

        for jc in job_cards:
            lot_number = None
            if jc.lot_id:
                lot = db.get(Lot, jc.lot_id)
                lot_number = lot.lot_number if lot else None

            if _exists(jc.lot_id, None, ClaimSourceType.JOB_CARD.value):
                summary["skipped_duplicates"] += 1
                continue

            qty_str = f"{jc.quantity}" if jc.quantity is not None else None

            line = ProgressClaimLine(
                claim_id=claim.id,
                source_type=ClaimSourceType.JOB_CARD.value,
                lot_id=jc.lot_id,
                job_card_id=jc.id,
                description=jc.work_description or f"Labour — {jc.job_card_number}",
                lot_number=lot_number,
                work_date=jc.work_date,
                quantity=qty_str,
                unit=jc.unit,
                is_system_generated=True,
                sort_order=_next_sort(),
            )
            db.add(line)
            summary["job_card_lines"] += 1

    db.flush()

    summary["total_lines"] = summary["milestone_lines"] + summary["work_done_lines"] + summary["job_card_lines"]
    summary["generated_at"] = _now().isoformat()

    claim.generation_summary = summary
    claim.generated_at = _now()
    claim.status = ProgressClaimStatus.GENERATED.value
    claim.updated_at = _now()
    db.flush()

    audit_service.write_event(
        db,
        action=AuditAction.UPDATE,
        entity_type="MunicipalityProgressClaim",
        actor_id=actor_id,
        entity_id=claim.id,
        after_value={"status": claim.status, "generation_summary": summary},
        notes=f"Auto-generated {summary['total_lines']} lines",
    )

    return summary


# ── Status transitions ─────────────────────────────────────────────────────────

_ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    ProgressClaimStatus.DRAFT.value: [ProgressClaimStatus.GENERATED.value, ProgressClaimStatus.CANCELLED.value],
    ProgressClaimStatus.GENERATED.value: [ProgressClaimStatus.UNDER_REVIEW.value, ProgressClaimStatus.CANCELLED.value],
    ProgressClaimStatus.UNDER_REVIEW.value: [ProgressClaimStatus.READY_FOR_PRICING.value, ProgressClaimStatus.GENERATED.value, ProgressClaimStatus.CANCELLED.value],
    ProgressClaimStatus.READY_FOR_PRICING.value: [ProgressClaimStatus.APPROVED.value, ProgressClaimStatus.UNDER_REVIEW.value, ProgressClaimStatus.CANCELLED.value],
    ProgressClaimStatus.APPROVED.value: [ProgressClaimStatus.EXPORTED.value],
    ProgressClaimStatus.EXPORTED.value: [],
    ProgressClaimStatus.CANCELLED.value: [],
}


def transition_status(
    db: Session,
    claim: MunicipalityProgressClaim,
    new_status: str,
    actor_id: Optional[uuid.UUID] = None,
    notes: Optional[str] = None,
) -> MunicipalityProgressClaim:
    allowed = _ALLOWED_TRANSITIONS.get(claim.status, [])
    if new_status not in allowed:
        raise ValueError(
            f"Cannot transition claim {claim.claim_number} from {claim.status} to {new_status}. "
            f"Allowed: {allowed}"
        )

    old_status = claim.status
    claim.status = new_status
    claim.updated_at = _now()

    if new_status == ProgressClaimStatus.APPROVED.value:
        claim.approved_at = _now()
        claim.snapshot_json = _build_snapshot(claim)

    if new_status == ProgressClaimStatus.EXPORTED.value:
        claim.exported_at = _now()

    db.flush()

    audit_service.write_event(
        db,
        action=AuditAction.APPROVE if new_status == ProgressClaimStatus.APPROVED.value else AuditAction.UPDATE,
        entity_type="MunicipalityProgressClaim",
        actor_id=actor_id,
        entity_id=claim.id,
        before_value={"status": old_status},
        after_value={"status": new_status},
        notes=notes,
    )

    # Side-effect notifications (non-blocking, per AP-04)
    try:
        from app.services.notification_service import enqueue_direct
        if new_status == ProgressClaimStatus.READY_FOR_PRICING.value:
            enqueue_direct(
                db,
                alert_type=AlertType.CLAIM_READY_FOR_PRICING,
                severity=AlertSeverity.MEDIUM,
                title="Progress Claim Ready for Pricing",
                message=f"Claim {claim.claim_number} is ready for pricing review.",
                project_id=claim.project_id,
                entity_type="MunicipalityProgressClaim",
                entity_id=claim.id,
            )
        elif new_status == ProgressClaimStatus.APPROVED.value:
            enqueue_direct(
                db,
                alert_type=AlertType.CLAIM_APPROVED,
                severity=AlertSeverity.LOW,
                title="Progress Claim Approved",
                message=f"Claim {claim.claim_number} has been approved.",
                project_id=claim.project_id,
                entity_type="MunicipalityProgressClaim",
                entity_id=claim.id,
            )
    except Exception:
        pass

    return claim


def _build_snapshot(claim: MunicipalityProgressClaim) -> dict:
    """Build an immutable snapshot of the claim at approval time."""
    return {
        "claim_number": claim.claim_number,
        "claim_title": claim.claim_title,
        "municipality_name": claim.municipality_name,
        "cert_number": claim.cert_number,
        "period_start": str(claim.period_start),
        "period_end": str(claim.period_end),
        "approved_at": _now().isoformat(),
        "lines": [
            {
                "id": str(line.id),
                "source_type": line.source_type,
                "description": line.description,
                "stage_name": line.stage_name,
                "lot_number": line.lot_number,
                "work_date": str(line.work_date) if line.work_date else None,
                "quantity": line.quantity,
                "unit": line.unit,
                "progress_pct": line.progress_pct,
                "is_included": line.is_included,
            }
            for line in claim.lines
            if line.is_included
        ],
    }


# ── Claim Line CRUD ────────────────────────────────────────────────────────────

def update_line(
    db: Session,
    line: ProgressClaimLine,
    data: dict,
    actor_id: Optional[uuid.UUID] = None,
) -> ProgressClaimLine:
    for field in ["is_included", "reviewer_notes", "description", "sort_order"]:
        if field in data and data[field] is not None:
            setattr(line, field, data[field])
    db.flush()
    return line


def add_manual_line(
    db: Session,
    claim: MunicipalityProgressClaim,
    data: dict,
    actor_id: Optional[uuid.UUID] = None,
) -> ProgressClaimLine:
    _assert_editable(claim)
    line = ProgressClaimLine(
        claim_id=claim.id,
        source_type=data.get("source_type", ClaimSourceType.STAGE_MILESTONE.value),
        lot_id=data.get("lot_id"),
        stage_status_id=data.get("stage_status_id"),
        work_done_id=data.get("work_done_id"),
        job_card_id=data.get("job_card_id"),
        description=data["description"],
        stage_name=data.get("stage_name"),
        lot_number=data.get("lot_number"),
        work_date=data.get("work_date"),
        quantity=data.get("quantity"),
        unit=data.get("unit"),
        progress_pct=data.get("progress_pct"),
        is_system_generated=False,
        sort_order=data.get("sort_order", 0),
    )
    db.add(line)
    db.flush()
    return line


def add_evidence(
    db: Session,
    claim_id: uuid.UUID,
    data: dict,
    actor_id: Optional[uuid.UUID] = None,
) -> ProgressClaimEvidence:
    ev = ProgressClaimEvidence(
        claim_id=claim_id,
        line_id=data.get("line_id"),
        attachment_id=data.get("attachment_id"),
        evidence_type=data.get("evidence_type"),
        caption=data.get("caption"),
        is_included=data.get("is_included", True),
        added_by=actor_id,
    )
    db.add(ev)
    db.flush()
    return ev


# ── PDF Export ─────────────────────────────────────────────────────────────────

def export_pdf(claim: MunicipalityProgressClaim) -> bytes:
    """Generate a PDF supporting document for the progress claim."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=14, spaceAfter=6)
    sub_style = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=9, textColor=colors.grey)
    body_style = styles["Normal"]
    body_style.fontSize = 9

    story = []

    story.append(Paragraph("MUNICIPALITY PROGRESS CLAIM", title_style))
    story.append(Paragraph(f"Claim Number: {claim.claim_number}", sub_style))
    story.append(Paragraph(f"Claim Title: {claim.claim_title}", sub_style))
    story.append(Paragraph(f"Municipality: {claim.municipality_name}", sub_style))
    story.append(Paragraph(f"Period: {claim.period_start} to {claim.period_end}", sub_style))
    story.append(Paragraph(f"Status: {claim.status}", sub_style))
    if claim.cert_number:
        story.append(Paragraph(f"Certificate No: {claim.cert_number}", sub_style))
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph(
        "This document shows completed work evidence for the claim period. "
        "No monetary amounts are included — pricing is added separately by the project team.",
        body_style,
    ))
    story.append(Spacer(1, 0.5*cm))

    included_lines = [l for l in claim.lines if l.is_included]

    if included_lines:
        header = ["#", "Type", "Lot", "Stage / Description", "Date", "Qty", "Unit", "Progress"]
        rows = [header]
        for i, line in enumerate(included_lines, 1):
            rows.append([
                str(i),
                line.source_type,
                line.lot_number or "-",
                line.description[:80],
                str(line.work_date) if line.work_date else "-",
                line.quantity or "-",
                line.unit or "-",
                f"{line.progress_pct}%" if line.progress_pct is not None else "-",
            ])

        col_widths = [1*cm, 3*cm, 2*cm, 6.5*cm, 2.5*cm, 1.5*cm, 1.5*cm, 2*cm]
        t = Table(rows, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7FA")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#C0C8D0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("WORDWRAP", (3, 1), (3, -1), True),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No included lines.", body_style))

    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        f"Total included lines: {len(included_lines)} | Generated: {claim.generated_at or '-'}",
        sub_style,
    ))

    if claim.notes:
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph(f"Notes: {claim.notes}", body_style))

    doc.build(story)
    return buf.getvalue()
