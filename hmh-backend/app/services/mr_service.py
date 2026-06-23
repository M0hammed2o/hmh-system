"""Material Request service — CRUD + BOQ check + approval flow + convert-to-PO."""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.core.logging_config import get_logger

logger = get_logger(__name__)

from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import (
    AlertSeverity, AlertStatus, AlertType,
    AuditAction, DeliveryDestination, MRPriority, RecordStatus, VatMode,
)
from app.models.material_request import MaterialRequest, MaterialRequestItem, MRApproval
from app.models.mr_quote import MRQuote
from app.models.project import Project
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.site import Site
from app.schemas.material_request import (
    MaterialRequestCreate, MaterialRequestUpdate,
)
from app.services import allocation_service, audit_service


def _generate_request_number(db: Session, project_id: Optional[uuid.UUID]) -> str:
    if project_id:
        count = db.query(MaterialRequest).filter(
            MaterialRequest.project_id == project_id
        ).count()
        return f"MR-{str(project_id)[:8].upper()}-{count + 1:04d}"
    count = db.query(MaterialRequest).filter(MaterialRequest.project_id.is_(None)).count()
    return f"MR-WH-{count + 1:04d}"


def _generate_po_number(db: Session, project_id: uuid.UUID) -> str:
    count = db.query(PurchaseOrder).filter(PurchaseOrder.project_id == project_id).count()
    return f"PO-{str(project_id)[:8].upper()}-{count + 1:04d}"


def list_requests(
    db: Session,
    project_id: uuid.UUID,
    site_id: Optional[uuid.UUID] = None,
    status: Optional[RecordStatus] = None,
) -> list[MaterialRequest]:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")
    q = (
        db.query(MaterialRequest)
        .options(joinedload(MaterialRequest.items))
        .filter(MaterialRequest.project_id == project_id)
    )
    if site_id:
        q = q.filter(MaterialRequest.site_id == site_id)
    if status:
        q = q.filter(MaterialRequest.status == status)
    return q.order_by(MaterialRequest.created_at.desc()).all()


def get_request(db: Session, mr_id: uuid.UUID) -> MaterialRequest:
    mr = (
        db.query(MaterialRequest)
        .options(joinedload(MaterialRequest.items))
        .filter(MaterialRequest.id == mr_id)
        .first()
    )
    if not mr:
        raise NotFoundError(f"Material request {mr_id} not found.")
    _attach_email_log(db, mr)
    return mr


def _attach_email_log(db: Session, mr: MaterialRequest) -> None:
    """Attach the latest MREmailLog to mr.email_log (non-ORM transient attribute)."""
    try:
        from app.models.mr_email_log import MREmailLog
        log = (
            db.query(MREmailLog)
            .filter(MREmailLog.material_request_id == mr.id)
            .order_by(MREmailLog.created_at.desc())
            .first()
        )
        mr.email_log = log  # type: ignore[attr-defined]
    except Exception:
        mr.email_log = None  # type: ignore[attr-defined]


def create_request(
    db: Session,
    project_id: Optional[uuid.UUID],
    data: MaterialRequestCreate,
    requested_by_id: uuid.UUID,
) -> MaterialRequest:
    if project_id is not None:
        project = db.get(Project, project_id)
        if not project:
            raise NotFoundError(f"Project {project_id} not found.")
        if data.site_id:
            site = db.get(Site, data.site_id)
            if not site or site.project_id != project_id:
                raise NotFoundError(f"Site {data.site_id} not found in this project.")

    now = datetime.now(timezone.utc)
    mr = MaterialRequest(
        request_number=_generate_request_number(db, project_id),
        project_id=project_id,
        site_id=data.site_id,
        lot_id=getattr(data, "lot_id", None),
        stage_id=getattr(data, "stage_id", None),
        requested_by=requested_by_id,
        preferred_supplier_id=getattr(data, "preferred_supplier_id", None),
        priority=getattr(data, "priority", MRPriority.NORMAL),
        delivery_destination=getattr(data, "delivery_destination", DeliveryDestination.SITE_STORE),
        status=RecordStatus.DRAFT,
        requested_date=now,
        needed_by_date=getattr(data, "needed_by_date", None),
        notes=getattr(data, "notes", None),
    )
    db.add(mr)
    db.flush()

    over_boq = False
    for item_data in data.items:
        over_qty = None
        if getattr(data, "lot_id", None) and getattr(item_data, "item_id", None):
            warning = allocation_service.check_before_issue(
                db, data.lot_id, item_data.item_id, item_data.requested_quantity
            )
            if warning:
                over_boq = True
                over_qty = warning.over_amount

        mr_item = MaterialRequestItem(
            material_request_id=mr.id,
            item_id=getattr(item_data, "item_id", None),
            boq_item_id=getattr(item_data, "boq_item_id", None),
            preferred_supplier_id=getattr(item_data, "preferred_supplier_id", None),
            description=getattr(item_data, "description", "") or "",
            requested_quantity=item_data.requested_quantity,
            unit=getattr(item_data, "unit", None),
            over_boq_quantity=over_qty,
            remarks=getattr(item_data, "remarks", None),
        )
        db.add(mr_item)

    mr.over_boq = over_boq
    if over_boq and project_id is not None:
        from app.models.alert import SystemAlert
        alert = SystemAlert(
            project_id=project_id,
            site_id=data.site_id,
            lot_id=getattr(data, "lot_id", None),
            alert_type=AlertType.BOQ_ALLOCATION_EXCEEDED,
            severity=AlertSeverity.HIGH,
            title=f"MR over BOQ: {mr.request_number}",
            message=f"Material request {mr.request_number} exceeds BOQ allocation.",
            status=AlertStatus.OPEN,
            notification_channel="in_app",
            created_at=now,
        )
        db.add(alert)

    audit_service.write_event(
        db, AuditAction.CREATE, "material_request", requested_by_id, mr.id,
        after_value={"request_number": mr.request_number, "over_boq": over_boq},
    )

    db.commit()
    db.refresh(mr)
    return mr


def submit_request(db: Session, mr_id: uuid.UUID, actor_id: uuid.UUID) -> MaterialRequest:
    mr = get_request(db, mr_id)
    if mr.status != RecordStatus.DRAFT:
        raise ValidationError("Only DRAFT requests can be submitted.")
    mr.status = RecordStatus.PENDING_APPROVAL if mr.over_boq else RecordStatus.SUBMITTED
    audit_service.write_event(db, AuditAction.UPDATE, "material_request", actor_id, mr_id,
                              after_value={"status": mr.status.value})
    db.commit()
    db.refresh(mr)

    # Create a SystemAlert so office/admin sees the MR on the Alerts page immediately.
    # The MR status was committed above. Alert creation is best-effort: any failure
    # is caught and logged without rolling back the main session (which would undo
    # the MR commit in the test context where a single connection is shared).
    try:
        _create_mr_submitted_alert(db, mr)   # flushes only; we commit below
        db.commit()
    except Exception:
        # Expire all objects so the session is in a usable state, but do NOT call
        # db.rollback() which would wipe the connection-level transaction in tests.
        try:
            db.expire_all()
        except Exception:
            pass
        import logging as _log
        _log.getLogger(__name__).exception(
            "MR submission alert failed for %s — submission still stands.", mr.request_number
        )

    return mr


def _create_mr_submitted_alert(db: Session, mr: "MaterialRequest") -> None:
    """Create a SystemAlert for a submitted MR and enqueue WhatsApp notifications."""
    from app.models.alert import SystemAlert
    from app.models.enums import AlertSeverity, AlertStatus
    from app.services import notification_service

    now = datetime.now(timezone.utc)
    priority_label = mr.priority.value if hasattr(mr.priority, "value") else str(mr.priority)

    alert = SystemAlert(
        project_id=mr.project_id,
        site_id=mr.site_id,
        alert_type=AlertType.REQUEST_PENDING_TOO_LONG,   # closest standard type for "MR needs review"
        severity=AlertSeverity.MEDIUM,
        title=f"MR Submitted: {mr.request_number}",
        message=(
            f"Material request {mr.request_number} has been submitted and is awaiting approval. "
            f"Priority: {priority_label}. "
            f"Items: {len(mr.items)}."
        ),
        status=AlertStatus.OPEN,
        notification_channel="whatsapp",
        created_at=now,
    )
    db.add(alert)
    db.flush()  # get alert.id — caller commits

    logger.info("mr alert created alert_id=%s mr=%s", alert.id, mr.request_number)

    # Enqueue WhatsApp notifications for matching active recipients
    queued = notification_service.enqueue_for_alert(db, alert)
    logger.info("mr alert queued notifications=%d mr=%s", len(queued), mr.request_number)


def approve_request(
    db: Session, mr_id: uuid.UUID, approver_id: uuid.UUID,
    over_boq_reason: Optional[str] = None,
    issuing_company: Optional[str] = "HMH_GROUP",
) -> MaterialRequest:
    mr = get_request(db, mr_id)
    if mr.status not in (RecordStatus.SUBMITTED, RecordStatus.PENDING_APPROVAL, RecordStatus.STAFF_APPROVED):
        raise ValidationError("Only SUBMITTED, PENDING_APPROVAL, or STAFF_APPROVED requests can be approved.")
    if mr.over_boq and not over_boq_reason:
        raise ValidationError("over_boq_reason is required for over-BOQ requests.")

    now = datetime.now(timezone.utc)
    mr.status = RecordStatus.APPROVED
    mr.approved_by = approver_id
    mr.approved_at = now
    mr.issuing_company = issuing_company or "HMH_GROUP"
    if over_boq_reason:
        mr.over_boq_reason = over_boq_reason

    audit_service.write_event(db, AuditAction.APPROVE, "material_request", approver_id, mr_id,
                              after_value={"over_boq_reason": over_boq_reason})

    # Check each item against lot BOQ and create CRITICAL alert if exceeded
    if mr.lot_id:
        _check_and_alert_mr_boq(db, mr, over_boq_reason)

    db.commit()
    db.refresh(mr)

    # Alert: MR approved — WhatsApp notification via enqueue_direct (never blocks approval)
    try:
        from app.services.notification_service import enqueue_direct
        from app.models.enums import AlertSeverity
        item_count = len(mr.items) if mr.items else 0
        enqueue_direct(
            db,
            alert_type=AlertType.MR_APPROVED,
            severity=AlertSeverity.LOW,
            title=f"MR Approved: {mr.request_number}",
            message=(
                f"Material request {mr.request_number} has been approved. "
                f"{item_count} item{'s' if item_count != 1 else ''}."
            ),
            project_id=mr.project_id,
            entity_type="material_request",
            entity_id=mr.id,
        )
        db.commit()
    except Exception:
        pass

    # Send approval email to preferred supplier (best-effort, never crashes approval)
    if mr.preferred_supplier_id:
        try:
            from app.services.email_service import send_mr_approval_email
            send_mr_approval_email(db, mr, sent_by_id=approver_id, force_resend=False)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "MR approval email failed for %s — approval still stands.", mr.request_number
            )

    return mr


def resend_mr_email(db: Session, mr_id: uuid.UUID, sent_by_id: uuid.UUID):
    """Manually (re)send the approval email. Always creates a new log entry."""
    from app.services.email_service import send_mr_approval_email
    mr = get_request(db, mr_id)
    if mr.status != RecordStatus.APPROVED:
        raise ValidationError("Only APPROVED requests can have their email (re)sent.")
    return send_mr_approval_email(db, mr, sent_by_id=sent_by_id, force_resend=True)


def _check_and_alert_mr_boq(db: Session, mr: "MaterialRequest", reason: Optional[str]) -> None:
    """Create a SystemAlert if any MR item exceeds the lot's BOQ allocation."""
    try:
        from app.services.allocation_service import check_before_issue
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertSeverity, AlertStatus

        now = datetime.now(timezone.utc)
        for item in mr.items:
            if not item.item_id or not item.requested_quantity:
                continue
            warning = check_before_issue(
                db, mr.lot_id, item.item_id, float(item.requested_quantity)
            )
            if warning:
                db.add(SystemAlert(
                    alert_type=AlertType.BOQ_ALLOCATION_EXCEEDED,
                    severity=AlertSeverity.CRITICAL,
                    title=f"MR BOQ overrun: {warning.item_name} on Lot {warning.lot_number}",
                    message=(
                        f"Material request {mr.request_number} requests {warning.new_issue_quantity} "
                        f"{warning.item_unit or ''} of {warning.item_name} but only "
                        f"{warning.remaining_quantity:.1f} remaining in lot BOQ "
                        f"(allocated {warning.allocated_quantity}). "
                        + (f"Reason: {reason}" if reason else "")
                    ),
                    status=AlertStatus.OPEN,
                    project_id=mr.project_id,
                    site_id=mr.site_id,
                    lot_id=mr.lot_id,
                    notification_channel="whatsapp",
                    created_at=now,
                    sent_at=now,
                ))
    except Exception:
        pass  # never crash the approval


def reject_request(
    db: Session, mr_id: uuid.UUID, reviewer_id: uuid.UUID, reason: str
) -> MaterialRequest:
    mr = get_request(db, mr_id)
    if mr.status not in (RecordStatus.SUBMITTED, RecordStatus.PENDING_APPROVAL, RecordStatus.STAFF_APPROVED, RecordStatus.DRAFT):
        raise ValidationError("Cannot reject a request in this status.")
    now = datetime.now(timezone.utc)
    mr.status = RecordStatus.REJECTED
    mr.reviewed_by = reviewer_id
    mr.reviewed_at = now
    mr.rejection_reason = reason
    audit_service.write_event(db, AuditAction.REJECT, "material_request", reviewer_id, mr_id,
                              after_value={"reason": reason})
    db.commit()
    db.refresh(mr)

    try:
        from app.models.alert import SystemAlert
        from app.models.enums import AlertSeverity, AlertStatus
        db.add(SystemAlert(
            project_id=mr.project_id, site_id=mr.site_id,
            alert_type=AlertType.REQUEST_PENDING_TOO_LONG,
            severity=AlertSeverity.HIGH,
            title=f"MR Rejected: {mr.request_number}",
            message=f"Material request {mr.request_number} was rejected. Reason: {reason}",
            status=AlertStatus.OPEN, notification_channel="in_app",
            created_at=now,
        ))
        db.commit()
    except Exception:
        pass

    return mr


def cancel_request(
    db: Session,
    mr_id: uuid.UUID,
    actor_id: uuid.UUID,
    reason: str,
    force: bool = False,
) -> MaterialRequest:
    """
    Cancel a material request.
    - Before ORDERED: any WRITE_ROLES member may cancel directly.
    - ORDERED or beyond: requires force=True (only OFFICE_AND_ABOVE callers pass this).
    """
    mr = get_request(db, mr_id)

    # Already terminal
    if mr.status in (RecordStatus.CANCELLED, RecordStatus.CLOSED, RecordStatus.RECEIVED):
        raise ValidationError(f"Cannot cancel a request with status {mr.status.value}.")

    # After ORDERED a supervisor must explicitly authorise
    ordered_or_beyond = {
        RecordStatus.ORDERED, RecordStatus.CONVERTED_TO_PO,
        RecordStatus.PARTIALLY_RECEIVED, RecordStatus.INVOICED,
        RecordStatus.PARTIALLY_PAID, RecordStatus.PAID,
    }
    if mr.status in ordered_or_beyond and not force:
        raise ValidationError(
            "Request is ORDERED or beyond — office approval is required to cancel."
        )

    now = datetime.now(timezone.utc)
    mr.status = RecordStatus.CANCELLED
    mr.rejection_reason = reason

    audit_service.write_event(
        db, AuditAction.UPDATE, "material_request", actor_id, mr_id,
        after_value={"status": RecordStatus.CANCELLED.value, "cancel_reason": reason},
    )
    db.commit()
    db.refresh(mr)
    return mr


def convert_to_po(
    db: Session,
    mr_id: uuid.UUID,
    actor_id: uuid.UUID,
    supplier_id: uuid.UUID,
    items_with_rates: list[dict],
    expected_delivery_date=None,
    notes: Optional[str] = None,
) -> PurchaseOrder:
    mr = get_request(db, mr_id)
    if mr.status not in (RecordStatus.APPROVED, RecordStatus.CONVERTED_TO_PO):
        raise ValidationError("Only APPROVED requests can be converted to PO.")

    now = datetime.now(timezone.utc)
    po = PurchaseOrder(
        po_number=_generate_po_number(db, mr.project_id),
        project_id=mr.project_id,
        site_id=mr.site_id,
        lot_id=mr.lot_id,
        supplier_id=supplier_id,
        material_request_id=mr_id,
        delivery_destination=mr.delivery_destination,
        issuing_company=mr.issuing_company or "HMH_GROUP",
        status=RecordStatus.APPROVED,
        po_date=now,
        expected_delivery_date=expected_delivery_date,
        created_by=actor_id,
        notes=notes,
        subtotal_amount=0,
        vat_amount=0,
        total_amount=0,
    )
    db.add(po)
    db.flush()

    subtotal = Decimal("0")
    for idx, item in enumerate(items_with_rates, 1):
        raw_qty  = item.get("quantity", 0) or 0
        raw_rate = item.get("rate", 0) or 0
        desc     = item.get("description") or f"Item {idx}"

        qty  = Decimal(str(raw_qty))
        rate = Decimal(str(raw_rate))

        if qty <= 0:
            raise ValidationError(
                f"Item '{desc}': quantity must be greater than 0 (got {raw_qty})."
            )
        if rate <= 0:
            raise ValidationError(
                f"Item '{desc}': rate must be greater than 0 (got {raw_rate}). "
                "Add a unit price before converting to PO."
            )

        line_total = (qty * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        subtotal  += line_total

        poi = PurchaseOrderItem(
            purchase_order_id=po.id,
            item_id=item.get("item_id"),
            boq_item_id=item.get("boq_item_id"),
            lot_id=mr.lot_id,
            stage_id=item.get("stage_id"),
            description=desc,
            quantity_ordered=float(qty),
            unit=item.get("unit"),
            rate=float(rate),
            vat_mode=VatMode.EXCLUSIVE,
            vat_rate=float(item.get("vat_rate", 15.0)),
            line_total=float(line_total),
            quantity_received=0.0,
            created_at=now,
        )
        db.add(poi)

    vat = (subtotal * Decimal("15") / Decimal("115")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    po.subtotal_amount = float(subtotal)
    po.vat_amount = float(vat)
    po.total_amount = float(subtotal)

    mr.status = RecordStatus.CONVERTED_TO_PO
    mr.converted_to_po_at = now

    audit_service.write_event(db, AuditAction.CREATE, "purchase_order", actor_id, po.id,
                              after_value={"po_number": po.po_number, "from_mr": str(mr_id)})
    db.commit()
    db.refresh(po)
    return po


def update_request(
    db: Session, mr_id: uuid.UUID, data: MaterialRequestUpdate, reviewed_by_id: uuid.UUID,
) -> MaterialRequest:
    mr = get_request(db, mr_id)
    fields = data.model_fields_set

    if "status" in fields and data.status is not None:
        if data.status in (RecordStatus.APPROVED, RecordStatus.REJECTED):
            if mr.status not in (RecordStatus.SUBMITTED, RecordStatus.PENDING_APPROVAL, RecordStatus.STAFF_APPROVED):
                raise ValidationError("Cannot approve/reject from this status.")
            mr.reviewed_by = reviewed_by_id
            mr.reviewed_at = datetime.now(timezone.utc)
        mr.status = data.status

    if "rejection_reason" in fields:
        mr.rejection_reason = data.rejection_reason
    if "preferred_supplier_id" in fields:
        mr.preferred_supplier_id = data.preferred_supplier_id
    if "needed_by_date" in fields:
        mr.needed_by_date = data.needed_by_date
    if "notes" in fields:
        mr.notes = data.notes

    db.commit()
    db.refresh(mr)
    return mr


# ── 4-way approval system ─────────────────────────────────────────────────────

STAFF_VOTES_REQUIRED = 3


def list_mr_approvals(db: Session, mr_id: uuid.UUID) -> list[MRApproval]:
    return (
        db.query(MRApproval)
        .filter(MRApproval.mr_id == mr_id)
        .order_by(MRApproval.approved_at.asc())
        .all()
    )


def cast_staff_vote(
    db: Session,
    mr_id: uuid.UUID,
    voter_id: uuid.UUID,
    notes: Optional[str] = None,
) -> MaterialRequest:
    """Cast a staff approval vote on an MR.

    Allowed statuses: SUBMITTED or PENDING_APPROVAL.
    Each user may vote only once.  When vote count reaches STAFF_VOTES_REQUIRED
    the MR moves to STAFF_APPROVED, awaiting PROCUREMENT_LEAD final approval.
    """
    mr = get_request(db, mr_id)
    if mr.status not in (RecordStatus.SUBMITTED, RecordStatus.PENDING_APPROVAL):
        raise ValidationError("Can only vote on SUBMITTED or PENDING_APPROVAL requests.")

    existing = db.query(MRApproval).filter(
        MRApproval.mr_id == mr_id,
        MRApproval.approved_by == voter_id,
    ).first()
    if existing:
        raise ValidationError("You have already voted on this request.")

    now = datetime.now(timezone.utc)
    db.add(MRApproval(
        mr_id=mr_id,
        approved_by=voter_id,
        approved_at=now,
        is_override=False,
        notes=notes,
    ))
    db.flush()

    staff_votes = db.query(MRApproval).filter(
        MRApproval.mr_id == mr_id,
        MRApproval.is_override.is_(False),
    ).count()

    if staff_votes >= STAFF_VOTES_REQUIRED:
        mr.status = RecordStatus.STAFF_APPROVED

    audit_service.write_event(
        db, AuditAction.APPROVE, "material_request", voter_id, mr_id,
        after_value={"staff_vote": True, "vote_count": staff_votes},
    )
    db.commit()
    db.refresh(mr)
    return mr


def procurement_lead_approve(
    db: Session,
    mr_id: uuid.UUID,
    approver_id: uuid.UUID,
    over_boq_reason: Optional[str] = None,
    issuing_company: Optional[str] = "HMH_GROUP",
) -> MaterialRequest:
    """Final procurement-lead approval — also works as an override when staff vote count is below threshold.

    Records the approval in mr_approvals with is_override=True when bypassing
    the staff vote requirement, then calls the standard approval flow.
    """
    mr = get_request(db, mr_id)
    allowed = (RecordStatus.SUBMITTED, RecordStatus.PENDING_APPROVAL, RecordStatus.STAFF_APPROVED)
    if mr.status not in allowed:
        raise ValidationError(
            "MR must be SUBMITTED, PENDING_APPROVAL, or STAFF_APPROVED to receive procurement approval."
        )
    if mr.over_boq and not over_boq_reason:
        raise ValidationError("over_boq_reason is required for over-BOQ requests.")

    staff_votes = db.query(MRApproval).filter(
        MRApproval.mr_id == mr_id,
        MRApproval.is_override.is_(False),
    ).count()
    is_override = staff_votes < STAFF_VOTES_REQUIRED

    # Avoid duplicate procurement lead entry if somehow called twice
    existing = db.query(MRApproval).filter(
        MRApproval.mr_id == mr_id,
        MRApproval.approved_by == approver_id,
    ).first()
    if not existing:
        db.add(MRApproval(
            mr_id=mr_id,
            approved_by=approver_id,
            approved_at=datetime.now(timezone.utc),
            is_override=is_override,
            notes=over_boq_reason,
        ))

    # Delegate to the standard approval function for notifications/email/audit
    return approve_request(db, mr_id, approver_id, over_boq_reason, issuing_company)


# ── Quotes ────────────────────────────────────────────────────────────────────

def list_quotes(db: Session, mr_id: uuid.UUID) -> list[MRQuote]:
    get_request(db, mr_id)
    return (
        db.query(MRQuote)
        .filter(MRQuote.material_request_id == mr_id)
        .order_by(MRQuote.unit_price)
        .all()
    )


def add_quote(
    db: Session,
    mr_id: uuid.UUID,
    supplier_id: uuid.UUID,
    description: str,
    quoted_quantity: float,
    unit_price: float,
    unit: Optional[str] = None,
    delivery_date=None,
    validity_date=None,
    notes: Optional[str] = None,
    item_id: Optional[uuid.UUID] = None,
    actor_id: Optional[uuid.UUID] = None,
) -> MRQuote:
    get_request(db, mr_id)
    now = datetime.now(timezone.utc)
    quote = MRQuote(
        material_request_id=mr_id,
        supplier_id=supplier_id,
        item_id=item_id,
        description=description,
        quoted_quantity=quoted_quantity,
        unit=unit,
        unit_price=unit_price,
        total_price=quoted_quantity * unit_price,
        delivery_date=delivery_date,
        validity_date=validity_date,
        notes=notes,
        is_selected=False,
        created_by=actor_id,
        created_at=now,
    )
    db.add(quote)
    db.commit()
    db.refresh(quote)
    return quote


def select_quote(
    db: Session, mr_id: uuid.UUID, quote_id: uuid.UUID, actor_id: uuid.UUID
) -> MRQuote:
    get_request(db, mr_id)
    db.query(MRQuote).filter(MRQuote.material_request_id == mr_id).update({"is_selected": False})
    quote = db.get(MRQuote, quote_id)
    if not quote or quote.material_request_id != mr_id:
        raise NotFoundError("Quote not found for this MR.")
    quote.is_selected = True
    db.commit()
    db.refresh(quote)
    return quote
