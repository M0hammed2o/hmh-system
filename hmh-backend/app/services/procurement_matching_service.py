"""
Procurement matching service.

Matches incoming Gmail attachments (invoices, delivery notes) to purchase orders
using PO number, supplier email, and document number heuristics.

Creates WhatsApp alerts on mismatches or failed matches.
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session, joinedload

logger = logging.getLogger(__name__)

_PO_RE = re.compile(r"\bPO[-/\s]?([A-Z0-9\-]+)\b", re.IGNORECASE)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_name(name: str) -> str:
    """Lowercase, strip punctuation/whitespace for fuzzy comparison."""
    return re.sub(r"\W+", " ", (name or "").lower()).strip()


def _amount_match(a: float, b: float) -> bool:
    """
    Returns True if amounts are within tolerance.
    Uses 2% relative tolerance OR R50 absolute, whichever is larger.
    Handles both zero and non-zero base amounts safely.
    """
    if a == 0 and b == 0:
        return True
    tolerance = max(max(a, b) * 0.02, 50.0)
    return abs(a - b) <= tolerance


# ── PO number extraction ──────────────────────────────────────────────────────

def _find_po_by_number(db, po_number: str):
    """
    Find a PurchaseOrder by PO number with normalized lookup.

    Search order:
      1. Exact case-insensitive match ("PO-F6EF3D9A-0001")
      2. With "PO-" prefix added (OCR often strips the prefix, yielding "F6EF3D9A-0001")
      3. Suffix search on the full value minus leading "PO-" — only when the
         remaining fragment is longer than 6 chars to avoid false positives
         (old code split on the first "-" which turned "F6EF3D9A-0001" into
         just "0001" and matched the wrong PO).
    """
    try:
        from app.models.purchase_order import PurchaseOrder

        po_num = (po_number or "").strip().upper()
        if not po_num:
            return None

        # 1. Exact match
        po = db.query(PurchaseOrder).filter(
            PurchaseOrder.po_number.ilike(po_num)
        ).first()
        if po:
            return po

        # 2. Try with "PO-" prefix added (OCR strips it)
        if not re.match(r"^PO[-]", po_num):
            po = db.query(PurchaseOrder).filter(
                PurchaseOrder.po_number.ilike(f"PO-{po_num}")
            ).first()
            if po:
                return po

        # 3. Suffix search — strip only the "PO-" prefix, keep the rest intact
        if re.match(r"^PO[-]", po_num):
            suffix = po_num[3:]
        else:
            suffix = po_num

        if len(suffix) > 6:
            return db.query(PurchaseOrder).filter(
                PurchaseOrder.po_number.ilike(f"%{suffix}%")
            ).first()

        return None
    except Exception:
        return None


def _find_po_number(text: str) -> Optional[str]:
    m = _PO_RE.search(text or "")
    if not m:
        return None
    raw = m.group(0).upper()
    return re.sub(r"\s+", "-", raw).replace("/", "-")


# ── Alert helper ──────────────────────────────────────────────────────────────

def _create_match_alert(
    db: Session,
    title: str,
    message: str,
    project_id: Optional[uuid.UUID] = None,
    severity: str = "HIGH",
) -> None:
    try:
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertSeverity, AlertStatus
        now = datetime.now(timezone.utc)
        sev = AlertSeverity(severity) if severity in AlertSeverity._value2member_map_ else AlertSeverity.HIGH
        db.add(SystemAlert(
            alert_type=AlertType.INVOICE_MISMATCH,
            severity=sev,
            title=title,
            message=message,
            status=AlertStatus.OPEN,
            project_id=project_id,
            notification_channel="whatsapp",
            created_at=now,
            sent_at=now,
        ))
        db.flush()
    except Exception:
        logger.exception("Failed to create match alert: %s", title)


# ── Match invoice to PO ───────────────────────────────────────────────────────

def match_invoice_to_po(invoice_id: uuid.UUID, db: Session) -> dict:
    """
    Attempt to match an Invoice to a PurchaseOrder.

    Strategy (in order):
    1. PO number found in invoice notes/number
    2. Supplier email match (incoming email → supplier)
    3. Flag as UNMATCHED and create alert

    Returns dict with match result.
    """
    from app.models.invoice import Invoice, InvoiceMatchingResult
    from app.models.purchase_order import PurchaseOrder
    from app.models.enums import InvoiceMatchStatus, RecordStatus

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        return {"matched": False, "reason": "Invoice not found"}

    po: Optional[PurchaseOrder] = None

    # 1. Try PO number from invoice notes or number fields
    for text in [invoice.invoice_number or "", invoice.notes or ""]:
        po_num = _find_po_number(text)
        if po_num:
            po = db.query(PurchaseOrder).filter(
                PurchaseOrder.po_number.ilike(f"%{po_num.split('-', 1)[-1]}%")
            ).first()
            if po:
                break

    # 2. Try match via supplier
    if not po and invoice.supplier_id:
        po = (
            db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.supplier_id == invoice.supplier_id,
                PurchaseOrder.status.notin_(["CANCELLED", "RECEIVED"]),
            )
            .order_by(PurchaseOrder.po_date.desc())
            .first()
        )

    now = datetime.now(timezone.utc)

    if not po:
        # No match — flag and alert
        existing = db.query(InvoiceMatchingResult).filter(
            InvoiceMatchingResult.invoice_id == invoice_id
        ).first()
        match_status = InvoiceMatchStatus.MISSING_DELIVERY_NOTE
        if not existing:
            db.add(InvoiceMatchingResult(
                invoice_id=invoice_id,
                match_status=InvoiceMatchStatus.UNLINKED,
                quantity_match=False, amount_match=False, supplier_match=False,
                notes="No matching PO found. Manual review required.",
                created_at=now,
            ))
        _create_match_alert(
            db,
            title=f"Unmatched invoice — {invoice.invoice_number or str(invoice.id)[:8]}",
            message=(
                f"Invoice {invoice.invoice_number} could not be automatically matched "
                "to any purchase order. Manual review required."
            ),
            project_id=invoice.project_id,
        )
        db.commit()
        return {"matched": False, "reason": "No matching PO", "invoice_id": str(invoice_id)}

    # Link the invoice to the PO
    invoice.purchase_order_id = po.id

    # Compare amounts using tolerance (2% relative or R50 absolute)
    po_total = float(po.total_amount or 0)
    inv_total = float(invoice.total_amount or 0)
    amount_ok = _amount_match(po_total, inv_total)

    # Supplier match
    supplier_match = (po.supplier_id == invoice.supplier_id)

    # Determine overall match status
    if amount_ok and supplier_match:
        match_status = InvoiceMatchStatus.MATCHED
    elif not amount_ok:
        match_status = InvoiceMatchStatus.QUANTITY_MISMATCH
        _create_match_alert(
            db,
            title=f"Invoice mismatch — {invoice.invoice_number}",
            message=(
                f"Invoice {invoice.invoice_number} total R{inv_total:,.2f} does not match "
                f"PO {po.po_number} total R{po_total:,.2f}. Difference: R{abs(po_total - inv_total):,.2f}."
            ),
            project_id=po.project_id,
        )
    elif not supplier_match:
        match_status = InvoiceMatchStatus.MISMATCH
    amount_match = amount_ok

    existing = db.query(InvoiceMatchingResult).filter(
        InvoiceMatchingResult.invoice_id == invoice_id
    ).first()

    if existing:
        existing.purchase_order_id = po.id
        existing.match_status = match_status
        existing.amount_match = amount_match
        existing.supplier_match = supplier_match
        existing.checked_at = now
    else:
        db.add(InvoiceMatchingResult(
            invoice_id=invoice_id,
            purchase_order_id=po.id,
            match_status=match_status,
            quantity_match=True,
            amount_match=amount_match,
            supplier_match=supplier_match,
            notes=f"Auto-matched to {po.po_number}",
            checked_at=now,
            created_at=now,
        ))

    db.commit()
    return {
        "matched": True,
        "po_number": po.po_number,
        "match_status": match_status.value,
        "amount_match": amount_match,
        "invoice_id": str(invoice_id),
    }


# ── Match delivery note to PO ─────────────────────────────────────────────────

def match_delivery_note_to_po(delivery_id: uuid.UUID, db: Session) -> dict:
    """
    Attempt to match a Delivery to a PurchaseOrder.

    Strategy:
    1. Supplier delivery note number in PO items
    2. Supplier match on most-recent open PO
    3. Flag as UNMATCHED (DELIVERY_WITHOUT_PO alert)
    """
    from app.models.delivery import Delivery
    from app.models.purchase_order import PurchaseOrder
    from app.models.enums import AlertType

    delivery = db.query(Delivery).filter(Delivery.id == delivery_id).first()
    if not delivery:
        return {"matched": False, "reason": "Delivery not found"}

    po: Optional[PurchaseOrder] = None

    # 1. PO number embedded in delivery number or comments
    for text_field in [delivery.delivery_number or "", getattr(delivery, "comments", "") or ""]:
        po_num = _find_po_number(text_field)
        if po_num:
            po = _find_po_by_number(db, po_num)
            if po:
                break

    # 2. Supplier match on most-recent open PO
    if not po and delivery.supplier_id:
        po = (
            db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.supplier_id == delivery.supplier_id,
                PurchaseOrder.status.notin_(["CANCELLED", "RECEIVED"]),
            )
            .order_by(PurchaseOrder.po_date.desc())
            .first()
        )

    if not po:
        # No match
        now = datetime.now(timezone.utc)
        try:
            from app.models.alert import SystemAlert
            from app.models.enums import AlertSeverity, AlertStatus
            db.add(SystemAlert(
                alert_type=AlertType.DELIVERY_WITHOUT_PO,
                severity=AlertSeverity.HIGH,
                title=f"Delivery without PO — {delivery.delivery_number or str(delivery.id)[:8]}",
                message=(
                    f"Delivery {delivery.delivery_number or str(delivery.id)[:8]} "
                    "could not be matched to any purchase order."
                ),
                status=AlertStatus.OPEN,
                project_id=delivery.project_id,
                site_id=delivery.site_id,
                notification_channel="whatsapp",
                created_at=now,
                sent_at=now,
            ))
            db.commit()
        except Exception:
            logger.exception("Could not create delivery-without-PO alert")
        return {"matched": False, "reason": "No matching PO"}

    # Link
    delivery.purchase_order_id = po.id
    db.commit()
    return {"matched": True, "po_number": po.po_number, "delivery_id": str(delivery_id)}


# ── Build proof pack ──────────────────────────────────────────────────────────

def build_proof_pack(invoice_id: uuid.UUID, db: Session) -> dict:
    """
    Assemble the full proof pack for accounting review.

    Returns a dict containing:
    - Invoice details
    - Linked PO + items
    - Supplier outgoing email log
    - Incoming supplier reply email (from incoming_emails)
    - Delivery note details + images
    - Matching result
    - Accounting flags (missing docs, match status)
    """
    import json as _json
    from app.models.invoice import Invoice, InvoiceMatchingResult
    from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem, PoEmailLog
    from app.models.delivery import Delivery
    from app.models.supplier import Supplier
    from app.models.incoming_email import IncomingEmail, IncomingEmailAttachment
    from app.models.document_extraction import DocumentExtraction
    from app.models.user import User

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        return {}

    supplier = db.get(Supplier, invoice.supplier_id) if invoice.supplier_id else None

    # PO
    po = db.get(PurchaseOrder, invoice.purchase_order_id) if invoice.purchase_order_id else None
    po_items = []
    if po:
        po_items = db.query(PurchaseOrderItem).filter(
            PurchaseOrderItem.purchase_order_id == po.id
        ).all()

    # Outgoing email log (supplier PO email)
    email_logs = []
    if po:
        email_logs = db.query(PoEmailLog).filter(
            PoEmailLog.purchase_order_id == po.id
        ).all()

    # Incoming supplier reply email (match by supplier email domain or PO number)
    incoming_email = None
    if supplier and supplier.email:
        domain = supplier.email.split("@")[-1]
        incoming_email = (
            db.query(IncomingEmail)
            .filter(IncomingEmail.from_email.ilike(f"%{domain}"))
            .order_by(IncomingEmail.received_at.desc())
            .first()
        )
        if not incoming_email and po:
            incoming_email = (
                db.query(IncomingEmail)
                .filter(IncomingEmail.matched_po_number.ilike(f"%{po.po_number.split('-', 1)[-1]}%"))
                .order_by(IncomingEmail.received_at.desc())
                .first()
            )

    # OCR extraction — most recent DocumentExtraction for any attachment on the incoming email
    extraction = None
    if incoming_email:
        att = (
            db.query(IncomingEmailAttachment)
            .filter(IncomingEmailAttachment.incoming_email_id == incoming_email.id)
            .order_by(IncomingEmailAttachment.id.desc())
            .first()
        )
        if att:
            extraction = (
                db.query(DocumentExtraction)
                .filter(
                    DocumentExtraction.source_type == "GMAIL_ATTACHMENT",
                    DocumentExtraction.source_id   == att.id,
                )
                .order_by(DocumentExtraction.created_at.desc())
                .first()
            )

    # Delivery
    match_result = db.query(InvoiceMatchingResult).filter(
        InvoiceMatchingResult.invoice_id == invoice_id
    ).first()

    delivery = None
    if match_result and match_result.delivery_id:
        delivery = db.get(Delivery, match_result.delivery_id)
    elif po:
        delivery = db.query(Delivery).filter(
            Delivery.purchase_order_id == po.id
        ).order_by(Delivery.delivery_date.desc()).first()

    match_status = match_result.match_status.value if match_result else "UNLINKED"
    is_matched   = match_status == "MATCHED"

    return {
        "invoice": {
            "id":             str(invoice.id),
            "number":         invoice.invoice_number,
            "date":           invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            "due_date":       invoice.due_date.isoformat() if invoice.due_date else None,
            "total":          float(invoice.total_amount or 0),
            "vat":            float(invoice.vat_amount or 0),
            "subtotal":       float(invoice.subtotal_amount or 0),
            "status":         invoice.status.value if invoice.status else None,
            "notes":          invoice.notes,
        },
        "supplier": {
            "name":       supplier.name if supplier else None,
            "email":      supplier.email if supplier else None,
            "vat_number": supplier.vat_number if supplier else None,
        } if supplier else None,
        "purchase_order": {
            "id":       str(po.id),
            "number":   po.po_number,
            "date":     po.po_date.isoformat() if po.po_date else None,
            "total":    float(po.total_amount or 0),
            "status":   po.status.value if po.status else None,
            "items": [
                {
                    "description":         i.description,
                    "quantity_ordered":    float(i.quantity_ordered),
                    "quantity_received":   float(i.quantity_received or 0),
                    "unit":                i.unit,
                    "rate":                float(i.rate or 0),
                    "line_total":          float(i.line_total or 0),
                }
                for i in po_items
            ],
        } if po else None,
        "outgoing_emails": [
            {
                "to":       l.sent_to_email,
                "subject":  l.email_subject,
                "status":   l.status.value if l.status else None,
                "sent_at":  l.sent_at.isoformat() if l.sent_at else None,
                "has_body": bool(l.email_body),
            }
            for l in email_logs
        ],
        "incoming_supplier_email": {
            "from":      incoming_email.from_email,
            "subject":   incoming_email.subject,
            "received":  incoming_email.received_at.isoformat() if incoming_email.received_at else None,
            "snippet":   incoming_email.body_snippet,
            "has_attachments": incoming_email.has_attachments,
        } if incoming_email else None,
        "delivery": {
            "id":               str(delivery.id),
            "number":           delivery.delivery_number,
            "date":             delivery.delivery_date.isoformat() if delivery.delivery_date else None,
            "note_image_url":   delivery.delivery_note_image_url,
            "signature_url":    delivery.signature_image_url,
            "receiver_name":    delivery.receiver_name,
            "comments":         delivery.comments,
            "status":           delivery.delivery_status.value if delivery.delivery_status else None,
        } if delivery else None,
        "match_result": {
            "status":         match_status,
            "quantity_match": match_result.quantity_match if match_result else False,
            "amount_match":   match_result.amount_match if match_result else False,
            "supplier_match": match_result.supplier_match if match_result else False,
            "notes":          match_result.notes if match_result else None,
        },
        "accounting_flags": {
            "is_matched":            is_matched,
            "missing_delivery_note": delivery is None,
            "missing_signature":     not (delivery and delivery.signature_image_url),
            "missing_po":            po is None,
            "missing_supplier_reply": incoming_email is None,
            "ready_for_payment":     (
                is_matched
                and delivery is not None
                and delivery.signature_image_url is not None
            ),
        },
        "ocr_extraction": {
            "status":        extraction.status,
            "document_type": extraction.document_type,
            "fields":        _json.loads(extraction.extracted_json or "{}").get("fields"),
            "created_at":    extraction.created_at.isoformat() if extraction.created_at else None,
        } if extraction else None,
    }
