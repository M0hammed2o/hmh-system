"""
Site capture endpoints — delivery note upload, OCR correction, verification, signature.

POST /site-capture/delivery-note/upload        — upload photo/PDF, triggers OCR
GET  /site-capture/delivery-note/{id}          — get verification + extracted data
POST /site-capture/delivery-note/{id}/correct  — save manual corrections
POST /site-capture/delivery-note/{id}/verify   — run quantity comparison, set status
POST /site-capture/delivery-note/{id}/signature — store signature
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess

router = APIRouter(prefix="/site-capture", tags=["site-capture"])

_DELIVERY_UPLOAD_DIR = os.path.join(settings.UPLOAD_DIR, "site_capture", "delivery_notes")


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/delivery-note/upload", status_code=201, dependencies=[ALL_ROLES])
async def upload_delivery_note(
    db: DbSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    site_id: str = Form(...),
    lot_id: Optional[str] = Form(None),
    purchase_order_id: Optional[str] = Form(None),
    supplier_name: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
):
    """Upload a delivery note photo or PDF. Runs document AI extraction automatically."""
    from app.models.document_extraction import DeliveryVerification, DocumentExtraction

    os.makedirs(_DELIVERY_UPLOAD_DIR, exist_ok=True)

    # Save file
    ext       = os.path.splitext(file.filename or "upload")[1] or ".bin"
    unique    = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(_DELIVERY_UPLOAD_DIR, unique)
    content   = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    now = datetime.now(timezone.utc)

    # Run extraction
    from app.services.document_ai_service import extract_document_data
    extraction_result = extract_document_data(file_path, "DELIVERY_NOTE")

    extraction = DocumentExtraction(
        source_type="SITE_UPLOAD",
        file_path=file_path,
        document_type="DELIVERY_NOTE",
        status=extraction_result["status"],
        raw_text=extraction_result.get("raw_text", ""),
        extracted_json=json.dumps(extraction_result),
        created_at=now,
    )
    db.add(extraction)
    db.flush()

    fields = extraction_result.get("fields", {})
    verification = DeliveryVerification(
        extraction_id=extraction.id,
        site_id=uuid.UUID(site_id),
        lot_id=uuid.UUID(lot_id) if lot_id else None,
        purchase_order_id=uuid.UUID(purchase_order_id) if purchase_order_id else None,
        received_by=current_user.id,
        verification_status="DRAFT",
        supplier_name=supplier_name or fields.get("supplier_name"),
        delivery_note_number=fields.get("delivery_note_number"),
        photo_path=file_path,
        notes=notes,
        created_at=now,
    )
    db.add(verification)
    db.commit()

    print(f"[DELIVERY-CAPTURE] upload created id={verification.id} status={extraction_result['status']}", flush=True)

    return ApiSuccess(
        data={
            "id":              str(verification.id),
            "extraction_id":   str(extraction.id),
            "status":          extraction_result["status"],
            "extracted_fields": fields,
            "items":           extraction_result.get("items", []),
            "warnings":        extraction_result.get("warnings", []),
        },
        message="Delivery note uploaded. Review and correct the extracted data.",
    )


# ── Get ───────────────────────────────────────────────────────────────────────

@router.get("/delivery-note/{verification_id}", dependencies=[ALL_ROLES])
def get_delivery_verification(verification_id: uuid.UUID, db: DbSession):
    from app.models.document_extraction import DeliveryVerification
    from sqlalchemy.orm import joinedload

    v = (
        db.query(DeliveryVerification)
        .options(joinedload(DeliveryVerification.items))
        .filter(DeliveryVerification.id == verification_id)
        .first()
    )
    if not v:
        raise HTTPException(404, "Delivery verification not found.")

    extraction_data = None
    if v.extraction_id:
        from app.models.document_extraction import DocumentExtraction
        ext = db.get(DocumentExtraction, v.extraction_id)
        if ext:
            try:
                extraction_data = json.loads(ext.manually_corrected_json or ext.extracted_json or "{}")
            except Exception:
                extraction_data = {}

    return ApiSuccess(data={
        "id":                   str(v.id),
        "verification_status":  v.verification_status,
        "supplier_name":        v.supplier_name,
        "delivery_note_number": v.delivery_note_number,
        "vehicle_reg":          v.vehicle_reg,
        "driver_name":          v.driver_name,
        "notes":                v.notes,
        "signed_at":            v.signed_at.isoformat() if v.signed_at else None,
        "extraction":           extraction_data,
        "items": [
            {
                "id":                  str(i.id),
                "description":         i.description,
                "unit":                i.unit,
                "expected_qty":        float(i.expected_qty or 0),
                "ocr_qty":             float(i.ocr_qty or 0),
                "actual_received_qty": float(i.actual_received_qty),
                "accepted_qty":        float(i.accepted_qty),
                "rejected_qty":        float(i.rejected_qty),
                "mismatch_reason":     i.mismatch_reason,
            }
            for i in v.items
        ],
    })


# ── Correct ───────────────────────────────────────────────────────────────────

class CorrectionBody(BaseModel):
    supplier_name:        Optional[str] = None
    delivery_note_number: Optional[str] = None
    vehicle_reg:          Optional[str] = None
    driver_name:          Optional[str] = None
    notes:                Optional[str] = None
    items: list[dict] = []       # [{description, unit, actual_received_qty, accepted_qty, rejected_qty, mismatch_reason}]
    corrected_fields: dict = {}  # free-form corrections to extracted fields


@router.post("/delivery-note/{verification_id}/correct", dependencies=[ALL_ROLES])
def correct_delivery_note(
    verification_id: uuid.UUID,
    body: CorrectionBody,
    db: DbSession,
    current_user: CurrentUser,
):
    from app.models.document_extraction import DeliveryVerification, DeliveryVerificationItem, DocumentExtraction

    v = db.query(DeliveryVerification).filter(DeliveryVerification.id == verification_id).first()
    if not v:
        raise HTTPException(404, "Delivery verification not found.")

    now = datetime.now(timezone.utc)

    # Update header fields
    if body.supplier_name is not None:        v.supplier_name        = body.supplier_name
    if body.delivery_note_number is not None: v.delivery_note_number = body.delivery_note_number
    if body.vehicle_reg is not None:          v.vehicle_reg          = body.vehicle_reg
    if body.driver_name is not None:          v.driver_name          = body.driver_name
    if body.notes is not None:                v.notes                = body.notes

    # Replace items
    for old in v.items:
        db.delete(old)
    db.flush()

    for item_data in body.items:
        db.add(DeliveryVerificationItem(
            delivery_verification_id=v.id,
            description=item_data.get("description", ""),
            unit=item_data.get("unit"),
            expected_qty=item_data.get("expected_qty"),
            ocr_qty=item_data.get("ocr_qty"),
            actual_received_qty=item_data.get("actual_received_qty", 0),
            accepted_qty=item_data.get("accepted_qty", 0),
            rejected_qty=item_data.get("rejected_qty", 0),
            mismatch_reason=item_data.get("mismatch_reason"),
        ))

    # Store corrected extraction
    if v.extraction_id and body.corrected_fields:
        ext = db.get(DocumentExtraction, v.extraction_id)
        if ext:
            ext.manually_corrected_json = json.dumps(body.corrected_fields)
            ext.status = "NEEDS_REVIEW"
            ext.corrected_at = now
            ext.corrected_by = current_user.id

    db.commit()
    print(f"[DELIVERY-CAPTURE] correction saved id={v.id}", flush=True)
    return ApiSuccess(data={"id": str(v.id)}, message="Corrections saved.")


# ── Verify ────────────────────────────────────────────────────────────────────

@router.post("/delivery-note/{verification_id}/verify", dependencies=[ALL_ROLES])
def verify_delivery_note(verification_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    Verify a delivery note — accessible by all authenticated roles including
    site staff and site managers (previously restricted to OFFICE_AND_ABOVE).
    """
    from app.models.document_extraction import DeliveryVerification

    v = (
        db.query(DeliveryVerification)
        .filter(DeliveryVerification.id == verification_id)
        .first()
    )
    if not v:
        raise HTTPException(404, "Delivery verification not found.")

    now = datetime.now(timezone.utc)
    has_mismatch = False

    for item in v.items:
        if float(item.rejected_qty or 0) > 0 or (
            item.expected_qty and abs(float(item.actual_received_qty) - float(item.expected_qty)) > 0.01
        ):
            has_mismatch = True
            break

    new_status = "MISMATCH" if has_mismatch else "VERIFIED"
    v.verification_status = new_status
    v.verified_by = current_user.id

    if has_mismatch:
        _create_verification_alert(db, v)

    db.commit()
    print(f"[DELIVERY-CAPTURE] verified successfully id={v.id} status={new_status}", flush=True)
    return ApiSuccess(data={"id": str(v.id), "status": new_status}, message=f"Verification: {new_status}")


# ── Signature ─────────────────────────────────────────────────────────────────

class SignatureBody(BaseModel):
    signature_data: str      # base64 PNG or text placeholder
    signed_by_name: Optional[str] = None


@router.post("/delivery-note/{verification_id}/signature", dependencies=[ALL_ROLES])
def save_signature(
    verification_id: uuid.UUID,
    body: SignatureBody,
    db: DbSession,
    current_user: CurrentUser,
):
    import base64

    from app.models.document_extraction import DeliveryVerification

    v = db.query(DeliveryVerification).filter(DeliveryVerification.id == verification_id).first()
    if not v:
        raise HTTPException(404, "Delivery verification not found.")

    sig_dir  = os.path.join(settings.UPLOAD_DIR, "site_capture", "signatures")
    os.makedirs(sig_dir, exist_ok=True)

    now = datetime.now(timezone.utc)
    sig_path: Optional[str] = None

    # Try to decode base64 image
    try:
        sig_bytes = base64.b64decode(body.signature_data)
        sig_file  = os.path.join(sig_dir, f"{uuid.uuid4().hex}.png")
        with open(sig_file, "wb") as f:
            f.write(sig_bytes)
        sig_path = sig_file
    except Exception:
        # Store as text file (plain name signature)
        sig_file = os.path.join(sig_dir, f"{uuid.uuid4().hex}.txt")
        with open(sig_file, "w") as f:
            f.write(body.signature_data[:500])
        sig_path = sig_file

    v.signature_path = sig_path
    v.signed_at      = now
    db.commit()

    print(f"[DELIVERY-CAPTURE] signature payload received id={v.id} signer={body.signed_by_name}", flush=True)
    return ApiSuccess(data={"id": str(v.id), "signed_at": now.isoformat()}, message="Signature saved.")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _create_verification_alert(db, v) -> None:
    try:
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertSeverity, AlertStatus
        now = datetime.now(timezone.utc)
        db.add(SystemAlert(
            alert_type=AlertType.DELIVERY_MISMATCH,
            severity=AlertSeverity.HIGH,
            title=f"Delivery mismatch — {v.delivery_note_number or str(v.id)[:8]}",
            message="Site verification found quantity discrepancies. Manual review required.",
            status=AlertStatus.OPEN,
            site_id=v.site_id,
            notification_channel="whatsapp",
            created_at=now,
            sent_at=now,
        ))
        db.flush()
    except Exception:
        pass
