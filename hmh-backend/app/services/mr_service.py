"""Material Request service — CRUD + BOQ check + approval flow + convert-to-PO."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import (
    AlertSeverity, AlertStatus, AlertType,
    AuditAction, DeliveryDestination, MRPriority, RecordStatus,
)
from app.models.material_request import MaterialRequest, MaterialRequestItem
from app.models.mr_quote import MRQuote
from app.models.project import Project
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.site import Site
from app.schemas.material_request import (
    MaterialRequestCreate, MaterialRequestUpdate,
)
from app.services import allocation_service, audit_service


def _generate_request_number(db: Session, project_id: uuid.UUID) -> str:
    count = db.query(MaterialRequest).filter(
        MaterialRequest.project_id == project_id
    ).count()
    return f"MR-{str(project_id)[:8].upper()}-{count + 1:04d}"


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
    project_id: uuid.UUID,
    data: MaterialRequestCreate,
    requested_by_id: uuid.UUID,
) -> MaterialRequest:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")

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
            description=getattr(item_data, "description", "") or "",
            requested_quantity=item_data.requested_quantity,
            unit=getattr(item_data, "unit", None),
            over_boq_quantity=over_qty,
            remarks=getattr(item_data, "remarks", None),
        )
        db.add(mr_item)

    mr.over_boq = over_boq
    if over_boq:
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
    return mr


def approve_request(
    db: Session, mr_id: uuid.UUID, approver_id: uuid.UUID,
    over_boq_reason: Optional[str] = None,
) -> MaterialRequest:
    mr = get_request(db, mr_id)
    if mr.status not in (RecordStatus.SUBMITTED, RecordStatus.PENDING_APPROVAL):
        raise ValidationError("Only SUBMITTED or PENDING_APPROVAL requests can be approved.")
    if mr.over_boq and not over_boq_reason:
        raise ValidationError("over_boq_reason is required for over-BOQ requests.")

    now = datetime.now(timezone.utc)
    mr.status = RecordStatus.APPROVED
    mr.approved_by = approver_id
    mr.approved_at = now
    if over_boq_reason:
        mr.over_boq_reason = over_boq_reason

    audit_service.write_event(db, AuditAction.APPROVE, "material_request", approver_id, mr_id,
                              after_value={"over_boq_reason": over_boq_reason})

    # Check each item against lot BOQ and create CRITICAL alert if exceeded
    if mr.lot_id:
        _check_and_alert_mr_boq(db, mr, over_boq_reason)

    db.commit()
    db.refresh(mr)

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
    if mr.status not in (RecordStatus.SUBMITTED, RecordStatus.PENDING_APPROVAL, RecordStatus.DRAFT):
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
    if mr.status != RecordStatus.APPROVED:
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
    for item in items_with_rates:
        qty = Decimal(str(item.get("quantity", 0)))
        rate = Decimal(str(item.get("rate", 0)))
        line_total = (qty * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        subtotal += line_total

        poi = PurchaseOrderItem(
            purchase_order_id=po.id,
            item_id=item.get("item_id"),
            lot_id=mr.lot_id,
            description=item.get("description", ""),
            quantity_ordered=float(qty),
            unit=item.get("unit"),
            rate=float(rate),
            line_total=float(line_total),
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
            if mr.status not in (RecordStatus.SUBMITTED, RecordStatus.PENDING_APPROVAL):
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
