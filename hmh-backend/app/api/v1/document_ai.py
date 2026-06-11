"""
Document AI endpoints.

POST /document-ai/extract                  — extract fields from a file path (regex)
POST /document-ai/compare                  — compare PO vs invoice vs delivery note
POST /document-ai/ai-extract/{att_id}      — AI-powered field extraction via Claude (Phase 6A)
GET  /document-ai/ai-extract/{att_id}      — retrieve stored AI extraction result
"""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.dependencies import OFFICE_AND_ABOVE, DbSession
from app.schemas.common import ApiSuccess

router = APIRouter(prefix="/document-ai", tags=["document-ai"])


class ExtractBody(BaseModel):
    file_path:     str
    document_type: str = "OTHER"   # INVOICE | DELIVERY_NOTE | QUOTE | OTHER
    source_id:     Optional[str] = None
    source_type:   Optional[str] = None


@router.post("/extract", dependencies=[OFFICE_AND_ABOVE])
def extract_document(body: ExtractBody, db: DbSession):
    """Run document AI extraction on a file and store the result."""
    import json
    from datetime import datetime, timezone

    from app.models.document_extraction import DocumentExtraction
    from app.services.document_ai_service import extract_document_data

    result = extract_document_data(body.file_path, body.document_type)

    now = datetime.now(timezone.utc)
    extraction = DocumentExtraction(
        source_type=body.source_type or "OTHER",
        source_id=uuid.UUID(body.source_id) if body.source_id else None,
        file_path=body.file_path,
        document_type=body.document_type,
        status=result["status"],
        raw_text=result.get("raw_text", ""),
        extracted_json=json.dumps(result),
        created_at=now,
    )
    db.add(extraction)
    db.commit()

    return ApiSuccess(data={"extraction_id": str(extraction.id), **result})


class CompareBody(BaseModel):
    purchase_order_id:  str
    invoice_id:         Optional[str] = None
    delivery_note_id:   Optional[str] = None


@router.post("/compare", dependencies=[OFFICE_AND_ABOVE])
def compare_documents(body: CompareBody, db: DbSession):
    """Compare PO vs invoice vs delivery note quantities and amounts."""
    from app.services.document_ai_service import compare_po_invoice_delivery

    result = compare_po_invoice_delivery(
        po_id=body.purchase_order_id,
        invoice_id=body.invoice_id,
        delivery_note_id=body.delivery_note_id,
        db=db,
    )
    if result.get("status") == "FAILED":
        raise HTTPException(400, result.get("summary", "Comparison failed"))

    return ApiSuccess(data=result)


# ── AI extraction endpoints (Phase 6A) ────────────────────────────────────────

@router.post("/ai-extract/{attachment_id}", dependencies=[OFFICE_AND_ABOVE])
def ai_extract_attachment(attachment_id: uuid.UUID, db: DbSession):
    """
    Run Claude AI field extraction on a Gmail attachment.

    Retrieves the attachment's DocumentExtraction record (created by the Gmail
    inbox processor), runs Claude Haiku on the raw OCR text, stores the result
    in ai_extraction_json, and returns per-field confidence scores.

    Human approval is ALWAYS required before creating an invoice — this endpoint
    only produces a draft suggestion, never an actual invoice.
    """
    import json
    from datetime import datetime, timezone

    from app.models.document_extraction import DocumentExtraction
    from app.services.ai_ocr_service import extract_invoice_fields_with_ai

    # Find the extraction record by source_id (attachment_id is the source_id for Gmail attachments)
    extraction = (
        db.query(DocumentExtraction)
        .filter(
            DocumentExtraction.source_id == attachment_id,
            DocumentExtraction.source_type == "gmail_attachment",
        )
        .order_by(DocumentExtraction.created_at.desc())
        .first()
    )

    if not extraction:
        raise HTTPException(
            404,
            f"No extraction record found for attachment {attachment_id}. "
            "The Gmail inbox processor must run first to create an extraction record.",
        )

    raw_text = extraction.raw_text or ""

    ai_result = extract_invoice_fields_with_ai(raw_text)

    # Persist the AI extraction result
    extraction.ai_extraction_json = json.dumps(ai_result)
    # Update overall confidence score with AI result if it improved
    ai_conf = ai_result.get("overall_confidence", 0.0)
    if ai_conf > 0:
        extraction.confidence_score = ai_conf
    db.commit()

    return ApiSuccess(data={
        "extraction_id":     str(extraction.id),
        "attachment_id":     str(attachment_id),
        "status":            ai_result.get("status"),
        "model":             ai_result.get("model"),
        "overall_confidence": ai_result.get("overall_confidence"),
        "low_confidence_fields": ai_result.get("low_confidence_fields", []),
        "header":            ai_result.get("header", {}),
        "line_items":        ai_result.get("line_items", []),
        "warnings":          ai_result.get("warnings", []),
    })


@router.get("/ai-extract/{attachment_id}", dependencies=[OFFICE_AND_ABOVE])
def get_ai_extraction(attachment_id: uuid.UUID, db: DbSession):
    """
    Retrieve a previously stored AI extraction result for a Gmail attachment.
    Returns 404 if no AI extraction has been run yet.
    """
    import json
    from app.models.document_extraction import DocumentExtraction

    extraction = (
        db.query(DocumentExtraction)
        .filter(
            DocumentExtraction.source_id == attachment_id,
            DocumentExtraction.source_type == "gmail_attachment",
        )
        .order_by(DocumentExtraction.created_at.desc())
        .first()
    )

    if not extraction:
        raise HTTPException(404, f"No extraction record found for attachment {attachment_id}.")

    if not extraction.ai_extraction_json:
        raise HTTPException(
            404,
            "AI extraction has not been run for this attachment yet. "
            "Call POST /document-ai/ai-extract/{attachment_id} first.",
        )

    ai_result = json.loads(extraction.ai_extraction_json)

    return ApiSuccess(data={
        "extraction_id":      str(extraction.id),
        "attachment_id":      str(attachment_id),
        "status":             ai_result.get("status"),
        "model":              ai_result.get("model"),
        "overall_confidence": ai_result.get("overall_confidence"),
        "low_confidence_fields": ai_result.get("low_confidence_fields", []),
        "header":             ai_result.get("header", {}),
        "line_items":         ai_result.get("line_items", []),
        "warnings":           ai_result.get("warnings", []),
    })
