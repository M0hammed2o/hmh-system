"""Purchase Order service.

VAT logic (V1): All supplier pricing is VAT-inclusive.
  vat_amount  = ROUND(subtotal * 15 / 115, 2)
  total_amount = subtotal_amount
The DB trigger fn_recalculate_po_totals() handles this automatically
after each INSERT/UPDATE/DELETE on purchase_order_items.
We therefore do NOT manually update totals here — the trigger owns that.
"""

import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import RecordStatus
from app.models.project import Project
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.schemas.purchase_order import (
    POItemCreate, POItemUpdate,
    PurchaseOrderCreate, PurchaseOrderUpdate,
)


def _generate_po_number(db: Session, project_id: uuid.UUID) -> str:
    count = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.project_id == project_id)
        .count()
    )
    return f"PO-{str(project_id)[:8].upper()}-{count + 1:04d}"


def _get_po_or_404(db: Session, po_id: uuid.UUID) -> PurchaseOrder:
    po = (
        db.query(PurchaseOrder)
        .options(joinedload(PurchaseOrder.order_items))
        .filter(PurchaseOrder.id == po_id)
        .first()
    )
    if not po:
        raise NotFoundError(f"Purchase order {po_id} not found.")
    return po


def list_pos(db: Session, project_id: uuid.UUID) -> list[PurchaseOrder]:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")
    return (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.project_id == project_id)
        .order_by(PurchaseOrder.created_at.desc())
        .all()
    )


def get_po(db: Session, po_id: uuid.UUID) -> PurchaseOrder:
    return _get_po_or_404(db, po_id)


def create_po(
    db: Session,
    project_id: uuid.UUID,
    data: PurchaseOrderCreate,
    created_by_id: uuid.UUID,
) -> PurchaseOrder:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")

    po = PurchaseOrder(
        po_number=_generate_po_number(db, project_id),
        project_id=project_id,
        site_id=data.site_id,
        supplier_id=data.supplier_id,
        material_request_id=data.material_request_id,
        status=RecordStatus.DRAFT,
        po_date=datetime.now(timezone.utc),
        expected_delivery_date=data.expected_delivery_date,
        created_by=created_by_id,
        notes=data.notes,
    )
    db.add(po)
    db.flush()  # get po.id

    for item_data in data.items:
        line_total = None
        if item_data.rate is not None:
            line_total = float(
                (Decimal(str(item_data.quantity_ordered)) * Decimal(str(item_data.rate)))
                .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            )
        poi = PurchaseOrderItem(
            purchase_order_id=po.id,
            item_id=item_data.item_id,
            boq_item_id=item_data.boq_item_id,
            lot_id=item_data.lot_id,
            stage_id=item_data.stage_id,
            description=item_data.description,
            quantity_ordered=item_data.quantity_ordered,
            unit=item_data.unit,
            rate=item_data.rate,
            vat_mode=item_data.vat_mode,
            vat_rate=item_data.vat_rate,
            line_total=line_total,
            created_at=datetime.now(timezone.utc),
        )
        db.add(poi)

    db.commit()
    db.refresh(po)

    # Alert: PO created
    try:
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertSeverity, AlertStatus
        db.add(SystemAlert(
            project_id=po.project_id, site_id=po.site_id,
            alert_type=AlertType.REQUEST_PENDING_TOO_LONG,
            severity=AlertSeverity.LOW,
            title=f"PO Created: {po.po_number}",
            message=f"Purchase order {po.po_number} was created and is awaiting approval.",
            status=AlertStatus.OPEN, notification_channel="in_app",
            created_at=datetime.now(timezone.utc),
        ))
        db.commit()
    except Exception:
        pass

    return po


def update_po(db: Session, po_id: uuid.UUID, data: PurchaseOrderUpdate) -> PurchaseOrder:
    po = _get_po_or_404(db, po_id)
    fields = data.model_fields_set

    if "status" in fields and data.status is not None:
        po.status = data.status
    if "expected_delivery_date" in fields:
        po.expected_delivery_date = data.expected_delivery_date
    if "notes" in fields:
        po.notes = data.notes
    if "site_id" in fields:
        po.site_id = data.site_id

    db.commit()
    db.refresh(po)
    return po


def approve_po(db: Session, po_id: uuid.UUID, approver_id: uuid.UUID) -> PurchaseOrder:
    from app.services import audit_service
    from app.models.enums import AuditAction
    po = _get_po_or_404(db, po_id)
    if po.status not in (RecordStatus.DRAFT, RecordStatus.SUBMITTED):
        raise ValidationError("Only DRAFT or SUBMITTED POs can be approved.")
    po.status = RecordStatus.APPROVED
    po.approved_by = approver_id
    audit_service.write_event(db, AuditAction.APPROVE, "purchase_order", approver_id, po_id)
    db.commit()
    db.refresh(po)
    return po


def send_po_email(
    db: Session, po_id: uuid.UUID, sent_by_id: uuid.UUID
):
    from app.services.email_service import send_po_email as _send
    from app.services import audit_service
    from app.models.enums import AuditAction
    po = _get_po_or_404(db, po_id)
    log = _send(db, po, sent_by_id=sent_by_id, mr_id=po.material_request_id)
    po.sent_at = datetime.now(timezone.utc)
    po.status = RecordStatus.SENT
    audit_service.write_event(db, AuditAction.SEND, "purchase_order", sent_by_id, po_id,
                              after_value={"email_status": log.status.value})
    db.commit()
    db.refresh(po)

    # WhatsApp notification: PO sent (fire-and-forget, never blocks email send)
    _notify_po_sent(db, po)
    try:
        db.commit()
    except Exception:
        pass

    return po, log


def _notify_po_sent(db: Session, po: PurchaseOrder) -> None:
    """
    Fire-and-forget WhatsApp notification when a PO transitions to SENT.
    Called by both send_po_email() and the mark-sent API endpoint.
    Never raises — notification failure must not block the business operation.
    """
    try:
        from app.services.notification_service import enqueue_direct
        from app.models.enums import AlertType, AlertSeverity
        total = float(po.total_amount or 0)
        enqueue_direct(
            db,
            alert_type=AlertType.PO_SENT_ALERT,
            severity=AlertSeverity.LOW,
            title=f"PO Sent: {po.po_number}",
            message=(
                f"Purchase order {po.po_number} has been sent to supplier. "
                f"Total: R{total:,.2f}."
            ),
            project_id=po.project_id,
            entity_type="purchase_order",
            entity_id=po.id,
        )
    except Exception:
        pass


def confirm_supplier(db: Session, po_id: uuid.UUID, confirmed_by_id: uuid.UUID) -> PurchaseOrder:
    """Transition PO from SENT → SUPPLIER_CONFIRMED."""
    from app.services import audit_service
    from app.models.enums import AuditAction
    po = _get_po_or_404(db, po_id)
    if po.status != RecordStatus.SENT:
        raise ValidationError(f"Only SENT POs can be confirmed by supplier. Current status: {po.status.value}")
    po.status = RecordStatus.SUPPLIER_CONFIRMED
    audit_service.write_event(db, AuditAction.APPROVE, "purchase_order", confirmed_by_id, po_id,
                              after_value={"status": "SUPPLIER_CONFIRMED"})
    db.commit()
    db.refresh(po)
    return po


def get_po_linked_docs(db: Session, po_id: uuid.UUID) -> dict:
    """Return all linked documents for a PO: quotation, source MR, deliveries, invoices + payment totals."""
    from app.models.delivery import Delivery
    from app.models.invoice import Invoice
    from app.models.material_request import MaterialRequest
    from app.models.payment import Payment
    from app.models.quotation import Quotation
    from app.models.enums import PaymentStatus
    from sqlalchemy import func

    po = db.get(PurchaseOrder, po_id)
    if not po:
        raise NotFoundError(f"Purchase order {po_id} not found.")

    # Linked quotation
    quotation_summary = None
    if po.quotation_id:
        q = db.get(Quotation, po.quotation_id)
        if q:
            quotation_summary = {
                "quotation_id": str(q.id),
                "quote_number": q.quote_number,
                "status": q.status.value,
                "gross_amount": float(q.gross_amount or 0),
                "vat_rate_used": float(q.vat_rate_used or 15.0),
                "expiry_date": q.expiry_date.isoformat() if q.expiry_date else None,
            }

    # Source MR
    mr_summary = None
    if po.material_request_id:
        mr = db.get(MaterialRequest, po.material_request_id)
        if mr:
            mr_summary = {
                "mr_id": str(mr.id),
                "mr_number": mr.request_number,
                "status": mr.status.value,
            }

    # Deliveries linked to this PO
    deliveries = (
        db.query(Delivery)
        .filter(Delivery.purchase_order_id == po_id)
        .order_by(Delivery.delivery_date.desc())
        .all()
    )
    delivery_list = [
        {
            "delivery_id": str(d.id),
            "delivery_number": d.delivery_number or str(d.id)[:8],
            "delivery_date": d.delivery_date.date().isoformat() if d.delivery_date else None,
            "status": d.delivery_status.value if d.delivery_status else None,
        }
        for d in deliveries
    ]

    # Invoices linked to this PO
    invoices = (
        db.query(Invoice)
        .filter(Invoice.purchase_order_id == po_id)
        .order_by(Invoice.created_at.desc())
        .all()
    )
    invoice_ids = [i.id for i in invoices]

    # Payment totals per invoice (single bulk query)
    paid_by_invoice: dict = {}
    if invoice_ids:
        rows = (
            db.query(Payment.invoice_id, func.coalesce(func.sum(Payment.amount_paid), 0).label("total"))
            .filter(Payment.invoice_id.in_(invoice_ids), Payment.status == PaymentStatus.PAID)
            .group_by(Payment.invoice_id)
            .all()
        )
        paid_by_invoice = {str(r.invoice_id): float(r.total) for r in rows}

    invoice_list = [
        {
            "invoice_id": str(i.id),
            "invoice_number": i.invoice_number,
            "total_amount": float(i.total_amount or 0),
            "total_paid": paid_by_invoice.get(str(i.id), 0.0),
            "balance_due": round(float(i.total_amount or 0) - paid_by_invoice.get(str(i.id), 0.0), 2),
            "status": i.status.value if i.status else None,
            "due_date": i.due_date.isoformat() if i.due_date else None,
        }
        for i in invoices
    ]

    return {
        "po_id": str(po_id),
        "po_number": po.po_number,
        "status": po.status.value,
        "quotation": quotation_summary,
        "source_mr": mr_summary,
        "deliveries": delivery_list,
        "invoices": invoice_list,
        "delivery_count": len(delivery_list),
        "invoice_count": len(invoice_list),
        "total_invoiced": round(sum(i["total_amount"] for i in invoice_list), 2),
        "total_paid": round(sum(i["total_paid"] for i in invoice_list), 2),
    }


def add_po_item(db: Session, po_id: uuid.UUID, data: POItemCreate) -> PurchaseOrderItem:
    po = db.get(PurchaseOrder, po_id)
    if not po:
        raise NotFoundError(f"Purchase order {po_id} not found.")

    line_total = None
    if data.rate is not None:
        line_total = float(
            (Decimal(str(data.quantity_ordered)) * Decimal(str(data.rate)))
            .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )

    poi = PurchaseOrderItem(
        purchase_order_id=po_id,
        item_id=data.item_id,
        boq_item_id=data.boq_item_id,
        lot_id=data.lot_id,
        stage_id=data.stage_id,
        description=data.description,
        quantity_ordered=data.quantity_ordered,
        unit=data.unit,
        rate=data.rate,
        vat_mode=data.vat_mode,
        vat_rate=data.vat_rate,
        line_total=line_total,
        created_at=datetime.now(timezone.utc),
    )
    db.add(poi)
    db.commit()
    db.refresh(poi)
    # DB trigger will have updated PO totals
    return poi
