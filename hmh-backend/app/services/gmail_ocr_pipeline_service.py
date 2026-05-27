"""
Gmail → OCR → PO matching pipeline service.

Orchestrates: attachment extraction → PO candidate search → reconciliation suggestion.

Design principles:
  - NEVER creates Invoice, Delivery, Payment, or any business record automatically.
  - NEVER auto-approves, auto-certifies, or auto-closes procurement flows.
  - All output is labelled requires_review=True — human confirmation is always required.
  - Never raises — returns structured result dicts on all error paths.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Confidence contribution per matching signal
_CONF_PO_NUMBER_EXACT = 0.55
_CONF_AMOUNT_WITHIN_TOLERANCE = 0.25
_CONF_SUPPLIER_FUZZY = 0.20


# ── Public API ────────────────────────────────────────────────────────────────

def build_reconciliation_suggestion(db: Session, att_id: uuid.UUID) -> dict:
    """
    Run the full extraction → PO match pipeline for one Gmail attachment.

    Returns a structured reconciliation suggestion dict for human review.
    NEVER creates business records.

    Return shape:
    {
        "attachment_id": str,
        "filename": str,
        "document_type": str,
        "extraction_status": str,
        "invoice_number": str | None,
        "delivery_note_number": str | None,
        "po_number_from_doc": str | None,
        "supplier_name": str | None,
        "supplier_email": str | None,
        "total_amount": float | None,
        "date": str | None,
        "matched_po": str | None,
        "matched_po_id": str | None,
        "match_confidence": float,          # 0.0 – 1.0
        "issues": list[str],
        "requires_review": True,            # ALWAYS True — never omit
        "extraction_warnings": list[str],
    }
    """
    from app.models.incoming_email import IncomingEmailAttachment
    from app.models.document_extraction import DocumentExtraction
    from app.services.document_ai_service import extract_document_data

    att = db.get(IncomingEmailAttachment, att_id)
    if not att:
        return {"error": "Attachment not found", "requires_review": True, "issues": ["attachment_not_found"]}

    # ── 1. Use cached extraction or run OCR ──────────────────────────────────
    extraction = (
        db.query(DocumentExtraction)
        .filter(
            DocumentExtraction.source_type == "GMAIL_ATTACHMENT",
            DocumentExtraction.source_id   == att.id,
        )
        .order_by(DocumentExtraction.created_at.desc())
        .first()
    )

    if extraction and extraction.status in ("EXTRACTED", "OCR_EXTRACTED", "NEEDS_REVIEW"):
        try:
            result = json.loads(extraction.extracted_json or "{}")
        except Exception:
            result = {"status": extraction.status, "fields": {}, "items": [], "warnings": []}
    else:
        try:
            result = extract_document_data(att.file_path or "", att.detected_type or "OTHER")
            _upsert_extraction(db, att, result, extraction)
        except Exception:
            logger.exception("build_reconciliation_suggestion: extraction failed att_id=%s", att_id)
            result = {"status": "FAILED", "fields": {}, "items": [], "warnings": ["extraction_error"]}

    fields     = result.get("fields") or {}
    doc_type   = att.detected_type or "OTHER"
    ext_status = result.get("status", "FAILED")

    # ── 2. Duplicate invoice check ───────────────────────────────────────────
    duplicate_warning: Optional[str] = None
    if doc_type == "INVOICE" and fields.get("invoice_number"):
        if detect_duplicate_invoice(db, fields["invoice_number"]):
            duplicate_warning = f"duplicate_invoice_number:{fields['invoice_number']}"

    # ── 3. Best PO candidate ─────────────────────────────────────────────────
    matched_po = None
    try:
        matched_po = _find_best_po_match(db, fields, doc_type)
    except Exception:
        logger.exception("build_reconciliation_suggestion: PO match failed att_id=%s", att_id)

    # ── 4. Score and collect issues ──────────────────────────────────────────
    confidence, issues = _score_match(fields, doc_type, matched_po)

    if duplicate_warning:
        issues.insert(0, duplicate_warning)
    if ext_status in ("EXTRACTION_FAILED", "FAILED", "OCR_NOT_AVAILABLE"):
        issues.append(f"extraction_status:{ext_status.lower()}")

    return {
        "attachment_id":        str(att_id),
        "filename":             att.filename,
        "document_type":        doc_type,
        "extraction_status":    ext_status,
        "invoice_number":       fields.get("invoice_number"),
        "delivery_note_number": fields.get("delivery_note_number"),
        "po_number_from_doc":   fields.get("po_number"),
        "supplier_name":        fields.get("supplier_name"),
        "supplier_email":       fields.get("supplier_email"),
        "total_amount":         fields.get("total_amount"),
        "date":                 fields.get("date"),
        "matched_po":           matched_po.po_number if matched_po else None,
        "matched_po_id":        str(matched_po.id)   if matched_po else None,
        "match_confidence":     round(confidence, 2),
        "issues":               issues,
        "requires_review":      True,   # NEVER omit — human confirmation always required
        "extraction_warnings":  result.get("warnings", []),
    }


def detect_duplicate_invoice(
    db: Session,
    invoice_number: str,
    supplier_id: Optional[uuid.UUID] = None,
) -> bool:
    """
    Return True if an invoice with this number already exists in the system.
    Optionally scoped to a specific supplier.
    Never raises.
    """
    try:
        from app.models.invoice import Invoice
        q = db.query(Invoice).filter(Invoice.invoice_number == invoice_number)
        if supplier_id:
            q = q.filter(Invoice.supplier_id == supplier_id)
        return q.first() is not None
    except Exception:
        logger.exception("detect_duplicate_invoice failed for %s", invoice_number)
        return False


def create_duplicate_invoice_alert(
    db: Session,
    invoice_number: str,
    from_email: str,
    now: Optional[datetime] = None,
) -> None:
    """
    Create a DUPLICATE_INVOICE alert in the system_alerts table.
    Never raises — alert failures must not block the pipeline.
    """
    try:
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertSeverity, AlertStatus
        now = now or datetime.now(timezone.utc)
        db.add(SystemAlert(
            alert_type=AlertType.DUPLICATE_INVOICE,
            severity=AlertSeverity.HIGH,
            title=f"Duplicate invoice — {invoice_number}",
            message=(
                f"Invoice number '{invoice_number}' received from {from_email} "
                "already exists in the system. Manual review required before creating a record."
            ),
            status=AlertStatus.OPEN,
            notification_channel="in_app",
            created_at=now,
        ))
        db.flush()
    except Exception:
        logger.exception("create_duplicate_invoice_alert failed for %s", invoice_number)


def create_supplier_mismatch_alert(
    db: Session,
    doc_supplier: str,
    po_supplier: str,
    po_number: str,
    now: Optional[datetime] = None,
) -> None:
    """
    Create a SUPPLIER_MISMATCH alert when the supplier in the document differs
    from the supplier on the matched PO. Never raises.
    """
    try:
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertSeverity, AlertStatus
        now = now or datetime.now(timezone.utc)
        db.add(SystemAlert(
            alert_type=AlertType.SUPPLIER_MISMATCH,
            severity=AlertSeverity.HIGH,
            title=f"Supplier mismatch — {po_number}",
            message=(
                f"Document supplier '{doc_supplier}' does not match "
                f"PO {po_number} supplier '{po_supplier}'. Verify before proceeding."
            ),
            status=AlertStatus.OPEN,
            notification_channel="in_app",
            created_at=now,
        ))
        db.flush()
    except Exception:
        logger.exception("create_supplier_mismatch_alert failed for po=%s", po_number)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _upsert_extraction(db: Session, att, result: dict, existing=None) -> None:
    """Store or update a DocumentExtraction row. Never raises."""
    try:
        from app.models.document_extraction import DocumentExtraction
        now = datetime.now(timezone.utc)
        if existing:
            existing.status         = result["status"]
            existing.raw_text       = result.get("raw_text", "")
            existing.extracted_json = json.dumps(result)
        else:
            db.add(DocumentExtraction(
                source_type    = "GMAIL_ATTACHMENT",
                source_id      = att.id,
                file_path      = att.file_path or "",
                document_type  = att.detected_type or "OTHER",
                status         = result["status"],
                raw_text       = result.get("raw_text", ""),
                extracted_json = json.dumps(result),
                created_at     = now,
            ))
        db.flush()
    except Exception:
        logger.exception("_upsert_extraction failed att_id=%s", getattr(att, "id", "?"))


def _find_best_po_match(db: Session, fields: dict, doc_type: str):
    """
    Find the most likely PurchaseOrder for the extracted fields.
    Search order: exact PO number → supplier email → fuzzy supplier name.
    Returns PO object or None.  Never raises.
    """
    try:
        from app.models.purchase_order import PurchaseOrder
        from app.services.procurement_matching_service import _find_po_by_number

        # 1. Exact PO number match (highest signal)
        po_num = fields.get("po_number")
        if po_num:
            po = _find_po_by_number(db, po_num)
            if po:
                return po

        # 2. Supplier email → most recent open PO for that supplier
        supplier_email = fields.get("supplier_email")
        if supplier_email:
            from app.models.supplier import Supplier
            supplier = db.query(Supplier).filter(
                Supplier.email.ilike(supplier_email)
            ).first()
            if supplier:
                return (
                    db.query(PurchaseOrder)
                    .filter(
                        PurchaseOrder.supplier_id == supplier.id,
                        PurchaseOrder.status.notin_(["CANCELLED", "RECEIVED"]),
                    )
                    .order_by(PurchaseOrder.po_date.desc())
                    .first()
                )

        # 3. Fuzzy supplier name match
        supplier_name = fields.get("supplier_name")
        if supplier_name:
            from app.services.document_ai_service import fuzzy_match_supplier
            supplier = fuzzy_match_supplier(supplier_name, db)
            if supplier:
                return (
                    db.query(PurchaseOrder)
                    .filter(
                        PurchaseOrder.supplier_id == supplier.id,
                        PurchaseOrder.status.notin_(["CANCELLED", "RECEIVED"]),
                    )
                    .order_by(PurchaseOrder.po_date.desc())
                    .first()
                )
    except Exception:
        logger.exception("_find_best_po_match failed fields=%s", list(fields.keys()))
    return None


def _score_match(fields: dict, doc_type: str, matched_po) -> tuple:
    """
    Calculate (confidence: float, issues: list[str]).
    confidence is in [0.0, 1.0]. Never raises.
    """
    issues: list = []

    if matched_po is None:
        issues.append("no_po_match_found")
        return 0.0, issues

    confidence = 0.0

    # Signal 1: PO number in document matches the candidate PO
    po_num_in_doc = (fields.get("po_number") or "").upper().strip()
    candidate_po_num = (matched_po.po_number or "").upper().strip()
    if po_num_in_doc and po_num_in_doc in candidate_po_num:
        confidence += _CONF_PO_NUMBER_EXACT
    elif po_num_in_doc:
        issues.append("po_number_partial_match")
    else:
        issues.append("no_po_number_in_document")

    # Signal 2: Amount within tolerance (2% relative or R50 absolute)
    doc_amount = fields.get("total_amount")
    if doc_amount is not None:
        try:
            po_total  = float(matched_po.total_amount or 0)
            doc_total = float(doc_amount)
            tolerance = max(max(po_total, doc_total) * 0.02, 50.0) if (po_total or doc_total) else 50.0
            if abs(po_total - doc_total) <= tolerance:
                confidence += _CONF_AMOUNT_WITHIN_TOLERANCE
            else:
                diff = abs(po_total - doc_total)
                issues.append(f"invoice_total_differs_by_R{diff:.0f}")
        except (TypeError, ValueError):
            pass

    # Signal 3: Supplier name fuzzy match
    supplier_name = (fields.get("supplier_name") or "").strip()
    if supplier_name:
        try:
            from app.services.document_ai_service import _similar
            po_supplier_name = ""
            if matched_po.supplier:
                po_supplier_name = matched_po.supplier.name or ""
            if po_supplier_name and _similar(supplier_name, po_supplier_name):
                confidence += _CONF_SUPPLIER_FUZZY
            elif po_supplier_name:
                issues.append("supplier_name_mismatch")
        except Exception:
            pass

    return min(confidence, 1.0), issues
