"""
Vision API — upload a file and extract structured data using OCR.

POST /vision/extract
  Accepts a file upload + document_type.
  Uses Google Cloud Vision if GOOGLE_APPLICATION_CREDENTIALS is set and OCR_PROVIDER=google_vision.
  Falls back to local pytesseract/pdfplumber if available.
  Returns extracted fields for user review — does NOT auto-save business records.
  User must confirm extracted data before it is used.

document_type values:
  delivery_note  — extracts: delivery_note_number, supplier_name, date, items, quantities
  invoice        — extracts: invoice_number, supplier, date, vat, total, line_items
  payment_proof  — extracts: amount, date, payee/reference

If Vision is not configured, returns:
  {"status": "OCR_NOT_AVAILABLE", "message": "Vision service not configured."}
"""

import os
import uuid as _uuid_module
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile

from app.core.config import settings
from app.dependencies import ALL_ROLES, CurrentUser, DbSession
from app.schemas.common import ApiSuccess

router = APIRouter(prefix="/vision", tags=["vision"])


@router.post("/extract", dependencies=[ALL_ROLES])
async def vision_extract(
    db:             DbSession,
    current_user:   CurrentUser,
    document_type:  str           = Form("delivery_note"),
    file:           UploadFile    = File(...),
):
    """
    Upload a file and extract structured fields using the configured OCR provider.

    Returns extracted fields for USER REVIEW — nothing is auto-saved.
    The caller must confirm the data before creating any business record.

    document_type:
      - delivery_note  → delivery_note_number, supplier_name, date, items[]
      - invoice        → invoice_number, supplier_name, date, vat_amount, total_amount, line_items[]
      - payment_proof  → amount, date, reference

    Status values:
      EXTRACTED          — data was extracted (review recommended)
      NEEDS_REVIEW       — extracted but key fields missing
      OCR_NOT_AVAILABLE  — no OCR provider configured
      FAILED             — file could not be processed
    """
    import json
    from datetime import datetime, timezone
    from app.services.document_ai_service import extract_document_data

    # ── Save uploaded file to a temp location ─────────────────────────────────
    upload_dir = os.path.join(settings.UPLOAD_DIR, "vision_uploads")
    os.makedirs(upload_dir, exist_ok=True)

    ext      = os.path.splitext(file.filename or "upload")[1] or ".bin"
    fname    = f"{_uuid_module.uuid4().hex}{ext}"
    fpath    = os.path.join(upload_dir, fname)
    content  = await file.read()

    with open(fpath, "wb") as fh:
        fh.write(content)

    file_size_bytes = len(content)

    # ── Run extraction ─────────────────────────────────────────────────────────
    doc_type = document_type.upper()
    result   = extract_document_data(fpath, doc_type)

    status    = result.get("status", "FAILED")
    raw_text  = result.get("raw_text", "")
    fields    = result.get("fields", {})
    items     = result.get("items", [])
    warnings  = result.get("warnings", [])

    # Build a structured preview for the UI to display in an editable form
    preview: dict = {}

    if doc_type == "INVOICE":
        preview = {
            "invoice_number": fields.get("invoice_number"),
            "supplier_name":  fields.get("supplier_name"),
            "supplier_email": fields.get("supplier_email"),
            "date":           fields.get("date"),
            "total_amount":   fields.get("total_amount"),
            "line_items":     [
                {
                    "description": i.get("description"),
                    "quantity":    i.get("quantity"),
                    "unit_price":  i.get("unit_price"),
                    "line_total":  i.get("line_total"),
                    "unit":        i.get("unit"),
                }
                for i in items
            ],
        }
    elif doc_type == "DELIVERY_NOTE":
        preview = {
            "delivery_note_number": fields.get("delivery_note_number"),
            "supplier_name":        fields.get("supplier_name"),
            "date":                 fields.get("date"),
            "po_number":            fields.get("po_number"),
            "items":                [
                {
                    "description": i.get("description"),
                    "quantity":    i.get("quantity"),
                    "unit":        i.get("unit"),
                }
                for i in items
            ],
        }
    elif doc_type == "PAYMENT_PROOF":
        preview = {
            "amount":    fields.get("total_amount"),
            "date":      fields.get("date"),
            "reference": fields.get("invoice_number") or fields.get("po_number"),
            "supplier":  fields.get("supplier_name"),
        }
    else:
        preview = fields

    # ── Store extraction record for audit (optional, best-effort) ──────────────
    try:
        from app.models.document_extraction import DocumentExtraction
        now = datetime.now(timezone.utc)
        extraction = DocumentExtraction(
            source_type="SITE_UPLOAD",
            file_path=fpath,
            document_type=doc_type,
            status=status,
            raw_text=raw_text[:10000] if raw_text else "",
            extracted_json=json.dumps(result)[:50000],
            created_at=now,
        )
        db.add(extraction)
        db.commit()
        extraction_id = str(extraction.id)
    except Exception:
        extraction_id = None

    return ApiSuccess(data={
        "status":          status,
        "document_type":   doc_type,
        "file_name":       file.filename,
        "file_size_bytes": file_size_bytes,
        "extraction_id":   extraction_id,
        "preview":         preview,           # editable fields for UI confirmation
        "raw_fields":      fields,            # full extracted fields
        "items":           items,             # line items if any
        "warnings":        warnings,
        "provider":        settings.OCR_PROVIDER,
        "note": (
            "Review and confirm all extracted data before saving. "
            "Data is NOT automatically saved to any business record."
        ),
    })
