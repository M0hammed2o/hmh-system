"""Invoice routes."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE, check_project_access
from app.models.invoice import Invoice
from app.schemas.common import ApiSuccess
from app.schemas.invoice import InvoiceCreate, InvoiceRead, InvoiceUpdate
from app.services import invoice_service

project_invoice_router = APIRouter(
    prefix="/projects/{project_id}/invoices",
    tags=["invoices"],
)
invoice_router = APIRouter(prefix="/invoices", tags=["invoices"])


@project_invoice_router.get(
    "/",
    response_model=ApiSuccess[list[InvoiceRead]],
    dependencies=[ALL_ROLES],
)
def list_invoices(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    check_project_access(db, current_user, project_id)
    invoices = invoice_service.list_invoices(db, project_id)
    return ApiSuccess(data=[InvoiceRead.model_validate(i) for i in invoices])


@project_invoice_router.get(
    "/enriched",
    response_model=ApiSuccess[list[dict]],
    dependencies=[ALL_ROLES],
)
def list_invoices_enriched(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    Enriched invoice list for the Payments page.
    Returns supplier name, PO number, match status, outstanding amount,
    overdue flag — everything needed for the Invoices tab and Outstanding view.
    """
    check_project_access(db, current_user, project_id)
    from datetime import date
    from sqlalchemy import func
    from app.models.invoice import Invoice, InvoiceMatchingResult
    from app.models.purchase_order import PurchaseOrder
    from app.models.supplier import Supplier
    from app.models.payment import Payment
    from app.models.enums import PaymentStatus

    invoices = (
        db.query(Invoice)
        .filter(Invoice.project_id == project_id)
        .order_by(Invoice.captured_at.desc())
        .all()
    )

    today = date.today()
    result = []
    for inv in invoices:
        supplier = db.get(Supplier, inv.supplier_id) if inv.supplier_id else None
        po       = db.get(PurchaseOrder, inv.purchase_order_id) if inv.purchase_order_id else None

        match = (
            db.query(InvoiceMatchingResult)
            .filter(InvoiceMatchingResult.invoice_id == inv.id)
            .first()
        )

        paid_total = float(
            db.query(func.coalesce(func.sum(Payment.amount_paid), 0))
            .filter(Payment.invoice_id == inv.id, Payment.status == PaymentStatus.PAID)
            .scalar() or 0
        )
        outstanding = max(0.0, float(inv.total_amount or 0) - paid_total)
        is_overdue  = inv.due_date is not None and inv.due_date < today

        result.append({
            "invoice_id":         str(inv.id),
            "invoice_number":     inv.invoice_number,
            "supplier_id":        str(inv.supplier_id)         if inv.supplier_id         else None,
            "supplier_name":      supplier.name                if supplier                else None,
            "purchase_order_id":  str(inv.purchase_order_id)  if inv.purchase_order_id   else None,
            "po_number":          po.po_number                 if po                      else None,
            "invoice_date":       inv.invoice_date.isoformat() if inv.invoice_date        else None,
            "due_date":           inv.due_date.isoformat()     if inv.due_date            else None,
            "total_amount":       float(inv.total_amount or 0),
            "paid_amount":        paid_total,
            "outstanding_amount": outstanding,
            "status":             inv.status.value,
            "match_status":       match.match_status.value     if match                   else "UNLINKED",
            "is_overdue":         is_overdue,
            "notes":              inv.notes,
            "captured_at":        inv.captured_at.isoformat()  if inv.captured_at         else None,
        })

    return ApiSuccess(data=result)


@project_invoice_router.post(
    "/",
    response_model=ApiSuccess[InvoiceRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_invoice(
    project_id: uuid.UUID,
    body: InvoiceCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    check_project_access(db, current_user, project_id)
    invoice = invoice_service.create_invoice(db, project_id, body, current_user.id)
    return ApiSuccess(data=InvoiceRead.model_validate(invoice), message="Invoice captured.")


@invoice_router.get(
    "/",
    response_model=ApiSuccess[list[InvoiceRead]],
    dependencies=[ALL_ROLES],
)
def list_all_invoices(
    db: DbSession,
    limit: int = Query(100, le=500),
    status: Optional[str] = Query(None),
):
    """List invoices across all projects (for reconciliation page)."""
    from app.models.invoice import Invoice
    from app.models.enums import RecordStatus

    q = db.query(Invoice)
    if status:
        # Support comma-separated statuses
        statuses = [s.strip() for s in status.split(",")]
        valid = [RecordStatus(s) for s in statuses if s in [r.value for r in RecordStatus]]
        if valid:
            q = q.filter(Invoice.status.in_(valid))
    return ApiSuccess(data=[InvoiceRead.model_validate(i) for i in
                            q.order_by(Invoice.captured_at.desc()).limit(limit).all()])


@invoice_router.get(
    "/{invoice_id}",
    response_model=ApiSuccess[InvoiceRead],
    dependencies=[ALL_ROLES],
)
def get_invoice(invoice_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    invoice = invoice_service.get_invoice(db, invoice_id)
    check_project_access(db, current_user, invoice.project_id)
    return ApiSuccess(data=InvoiceRead.model_validate(invoice))


@invoice_router.patch(
    "/{invoice_id}",
    response_model=ApiSuccess[InvoiceRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_invoice(invoice_id: uuid.UUID, body: InvoiceUpdate, db: DbSession, current_user: CurrentUser):
    _inv = db.get(Invoice, invoice_id)
    if not _inv:
        raise HTTPException(404, "Invoice not found.")
    check_project_access(db, current_user, _inv.project_id)
    invoice = invoice_service.update_invoice(db, invoice_id, body)
    return ApiSuccess(data=InvoiceRead.model_validate(invoice), message="Invoice updated.")


@invoice_router.get(
    "/{invoice_id}/reconciliation",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def get_invoice_reconciliation(invoice_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    Full reconciliation view: invoice totals, all payments, balance, status.
    Office-only — site users must not see pricing or payment amounts.
    """
    _inv = db.get(Invoice, invoice_id)
    if not _inv:
        raise HTTPException(404, "Invoice not found.")
    check_project_access(db, current_user, _inv.project_id)
    from app.services import payment_service
    data = payment_service.get_invoice_reconciliation(db, invoice_id)
    return ApiSuccess(data=data)


@invoice_router.get(
    "/{invoice_id}/proof",
    response_model=ApiSuccess[dict],
    dependencies=[ALL_ROLES],
)
def get_invoice_proof(invoice_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    Return the full proof pack for one invoice:
    invoice + PO + delivery note + signature + email log + match result.
    Everything accounting needs on one screen.
    """
    from app.models.delivery import Delivery, DeliveryItem
    from app.models.invoice import InvoiceMatchingResult
    from app.models.purchase_order import PoEmailLog, PurchaseOrder, PurchaseOrderItem
    from app.models.supplier import Supplier

    invoice = invoice_service.get_invoice(db, invoice_id)
    check_project_access(db, current_user, invoice.project_id)
    supplier = db.get(Supplier, invoice.supplier_id)

    # PO
    po = db.get(PurchaseOrder, invoice.purchase_order_id) if invoice.purchase_order_id else None
    po_items = []
    if po:
        po_items = (
            db.query(PurchaseOrderItem)
            .filter(PurchaseOrderItem.purchase_order_id == po.id)
            .all()
        )

    # Email log for this PO
    email_logs = []
    if po:
        email_logs = (
            db.query(PoEmailLog)
            .filter(PoEmailLog.purchase_order_id == po.id)
            .order_by(PoEmailLog.sent_at.desc())
            .all()
        )

    # Match results
    match_results = (
        db.query(InvoiceMatchingResult)
        .filter(InvoiceMatchingResult.invoice_id == invoice_id)
        .all()
    )
    primary_match = match_results[0] if match_results else None

    # Delivery
    delivery = None
    if primary_match and primary_match.delivery_id:
        delivery = db.get(Delivery, primary_match.delivery_id)

    def _dt(val) -> str | None:
        return val.isoformat() if val else None

    return ApiSuccess(data={
        # Invoice
        "invoice_id": str(invoice.id),
        "project_id": str(invoice.project_id) if invoice.project_id else None,
        "invoice_number": invoice.invoice_number,
        "invoice_date": _dt(invoice.invoice_date),
        "due_date": _dt(invoice.due_date),
        "total_amount": float(invoice.total_amount),
        "vat_amount": float(invoice.vat_amount or 0),
        "subtotal_amount": float(invoice.subtotal_amount or 0),
        "invoice_status": invoice.status.value,
        "invoice_notes": invoice.notes,

        # Supplier
        "supplier_name": supplier.name if supplier else None,
        "supplier_email": supplier.email if supplier else None,
        "supplier_vat": supplier.vat_number if supplier else None,

        # Purchase Order
        "po_number": po.po_number if po else None,
        "po_id": str(po.id) if po else None,
        "po_date": _dt(po.po_date) if po else None,
        "po_expected_delivery": _dt(po.expected_delivery_date) if po else None,
        "po_items": [
            {
                "description": i.description,
                "quantity_ordered": float(i.quantity_ordered),
                "quantity_received": float(i.quantity_received or 0),
                "unit": i.unit,
                "rate": float(i.rate or 0),
                "line_total": float(i.line_total or 0),
            }
            for i in po_items
        ],

        # Supplier email
        "email_logs": [
            {
                "sent_to": el.sent_to_email,
                "subject": el.email_subject,
                "status": el.status.value,
                "sent_at": _dt(el.sent_at),
                "has_body": bool(el.email_body),
            }
            for el in email_logs
        ],

        # Delivery + signatures
        "delivery_number":          delivery.delivery_number if delivery else None,
        "delivery_id":              str(delivery.id) if delivery else None,
        "delivery_date":            _dt(delivery.delivery_date) if delivery else None,
        "delivery_note_image_url":  delivery.delivery_note_image_url if delivery else None,
        "delivery_note_download_url": delivery.delivery_note_image_url if delivery else None,
        "signature_image_url":      delivery.signature_image_url if delivery else None,
        "receiver_name":            delivery.receiver_name if delivery else None,
        "delivery_comments":        delivery.comments if delivery else None,
        # Driver signature (path stored in ocr_raw_data JSON under driver_signature_path)
        "driver_name":              (delivery.ocr_raw_data or {}).get("driver_name") if delivery else None,
        "driver_signature_url":     (delivery.ocr_raw_data or {}).get("driver_signature_path") if delivery else None,
        "signed_at":                (delivery.ocr_raw_data or {}).get("signed_at") if delivery else None,

        # Match result
        "match_status": primary_match.match_status.value if primary_match else "UNLINKED",
        "quantity_match": primary_match.quantity_match if primary_match else None,
        "amount_match": primary_match.amount_match if primary_match else None,
        "supplier_match": primary_match.supplier_match if primary_match else None,
        "match_notes": primary_match.notes if primary_match else None,

        # Reconciliation comparison — PO vs Invoice vs Delivery
        "reconciliation": {
            "po_total":       float(po.total_amount) if po else None,
            "invoice_total":  float(invoice.total_amount),
            "delivery_items": [
                {
                    "description":       di.description,
                    "quantity_expected": float(di.quantity_expected or 0),
                    "quantity_received": float(di.quantity_received or 0),
                }
                for di in (
                    db.query(DeliveryItem)
                    .filter(DeliveryItem.delivery_id == delivery.id)
                    .all()
                )
            ] if delivery else [],
            "amount_variance": (
                abs(float(invoice.total_amount) - float(po.total_amount)) if po else None
            ),
            "match_label": (
                "Matched" if (primary_match and primary_match.match_status.value == "MATCHED")
                else "Partial Match" if (primary_match and primary_match.match_status.value in ("PARTIALLY_MATCHED", "MISSING_DELIVERY_NOTE", "MISSING_SIGNATURE", "MISSING_INVOICE"))
                else "Variance" if primary_match
                else "Unlinked"
            ),
        },

        # Reviewer info (from manual match)
        "checked_by":  str(primary_match.checked_by)           if primary_match and primary_match.checked_by else None,
        "checked_at":  primary_match.checked_at.isoformat()    if primary_match and primary_match.checked_at else None,

        # Flags for accounting
        "missing_delivery_note": delivery is None or not delivery.delivery_note_image_url,
        "missing_signature": delivery is None or not delivery.signature_image_url,
        "is_matched": primary_match.match_status.value == "MATCHED" if primary_match else False,
    })


@invoice_router.post(
    "/{invoice_id}/approve-payment",
    response_model=ApiSuccess[InvoiceRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def approve_for_payment(invoice_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    from app.models.enums import RecordStatus, AuditAction
    from app.services import audit_service
    invoice = invoice_service.get_invoice(db, invoice_id)
    check_project_access(db, current_user, invoice.project_id)
    invoice.status = RecordStatus.APPROVED
    audit_service.write_event(
        db, AuditAction.APPROVE, "invoice", current_user.id, invoice_id,
        after_value={"status": "APPROVED", "invoice_number": invoice.invoice_number},
    )
    db.commit()
    db.refresh(invoice)
    return ApiSuccess(data=InvoiceRead.model_validate(invoice), message="Approved for payment.")


# ── Manual reconciliation matching ───────────────────────────────────────────

class ManualMatchBody(BaseModel):
    delivery_id:       Optional[uuid.UUID] = None
    purchase_order_id: Optional[uuid.UUID] = None
    match_status:      Optional[str]       = "MATCHED"   # InvoiceMatchStatus value
    notes:             Optional[str]       = None


@invoice_router.patch(
    "/{invoice_id}/match",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def manual_match_invoice(
    invoice_id: uuid.UUID,
    body: ManualMatchBody,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Manually link an invoice to a delivery and/or PO and set the match status.
    Creates or updates the InvoiceMatchingResult record.
    Reviewed_by and reviewed_at are set automatically.
    """
    from app.models.invoice import InvoiceMatchingResult
    from app.models.enums import InvoiceMatchStatus

    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "Invoice not found.")
    check_project_access(db, current_user, invoice.project_id)

    # Validate match_status
    try:
        ms = InvoiceMatchStatus(body.match_status or "MATCHED")
    except ValueError:
        raise HTTPException(422, f"Invalid match_status: {body.match_status}")

    now = datetime.now(timezone.utc)

    # Find existing match record or create new
    match = (
        db.query(InvoiceMatchingResult)
        .filter(InvoiceMatchingResult.invoice_id == invoice_id)
        .first()
    )
    if match:
        if body.delivery_id is not None:
            match.delivery_id = body.delivery_id
        if body.purchase_order_id is not None:
            match.purchase_order_id = body.purchase_order_id
        match.match_status  = ms
        match.quantity_match = ms == InvoiceMatchStatus.MATCHED
        match.amount_match   = ms == InvoiceMatchStatus.MATCHED
        match.supplier_match = ms == InvoiceMatchStatus.MATCHED
        if body.notes:
            match.notes = body.notes
        match.checked_by = current_user.id
        match.checked_at = now
    else:
        match = InvoiceMatchingResult(
            invoice_id        = invoice_id,
            purchase_order_id = body.purchase_order_id or invoice.purchase_order_id,
            delivery_id       = body.delivery_id,
            match_status      = ms,
            quantity_match    = ms == InvoiceMatchStatus.MATCHED,
            amount_match      = ms == InvoiceMatchStatus.MATCHED,
            supplier_match    = ms == InvoiceMatchStatus.MATCHED,
            notes             = body.notes,
            checked_by        = current_user.id,
            checked_at        = now,
            created_at        = now,
        )
        db.add(match)

    # Update invoice status when matched
    if ms in (InvoiceMatchStatus.MATCHED, InvoiceMatchStatus.APPROVED_FOR_PAYMENT):
        from app.models.enums import RecordStatus
        from app.models.purchase_order import PurchaseOrder
        if invoice.status not in (
            RecordStatus.MATCHED, RecordStatus.APPROVED, RecordStatus.PAID
        ):
            invoice.status = RecordStatus.MATCHED

        # PO lifecycle: when invoice is MATCHED, advance PO to MATCHED
        po_id = match.purchase_order_id or invoice.purchase_order_id
        if po_id:
            po = db.get(PurchaseOrder, po_id)
            if po and po.status in (RecordStatus.RECEIVED, RecordStatus.PARTIALLY_RECEIVED):
                po.status = RecordStatus.MATCHED

    db.commit()
    db.refresh(match)

    return ApiSuccess(data={
        "invoice_id":       str(invoice_id),
        "match_id":         str(match.id),
        "match_status":     match.match_status.value,
        "delivery_id":      str(match.delivery_id) if match.delivery_id else None,
        "purchase_order_id": str(match.purchase_order_id) if match.purchase_order_id else None,
        "checked_by":       str(match.checked_by) if match.checked_by else None,
        "checked_at":       match.checked_at.isoformat() if match.checked_at else None,
        "notes":            match.notes,
    }, message="Match record updated.")
