"""
Document AI endpoints.

POST /document-ai/extract  — extract fields from a file path
POST /document-ai/compare  — compare PO vs invoice vs delivery note
"""

import uuid
from typing import Optional

from fastapi import APIRouter
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
        from fastapi import HTTPException
        raise HTTPException(400, result.get("summary", "Comparison failed"))

    return ApiSuccess(data=result)
