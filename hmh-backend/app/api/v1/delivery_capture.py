"""
Delivery note capture — photo upload + signature + manual correction.

POST /deliveries/{delivery_id}/capture
  Accepts multipart form: delivery_note_image, signature_image, json fields.
  Stores images to local filesystem (swap for R2 in production).
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.dependencies import ALL_ROLES, CurrentUser, DbSession
from app.models.delivery import Delivery
from app.schemas.common import ApiSuccess
from app.services import audit_service
from app.models.enums import AuditAction

router = APIRouter(tags=["delivery-capture"])

_UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")


def _save_file(upload: UploadFile, subfolder: str) -> str:
    """Save uploaded file, return relative URL path."""
    folder = os.path.join(_UPLOAD_DIR, subfolder)
    os.makedirs(folder, exist_ok=True)
    ext = os.path.splitext(upload.filename or "file")[1] or ".bin"
    filename = f"{uuid.uuid4()}{ext}"
    path = os.path.join(folder, filename)
    with open(path, "wb") as f:
        f.write(upload.file.read())
    return f"/uploads/{subfolder}/{filename}"


@router.post(
    "/deliveries/{delivery_id}/capture",
    response_model=ApiSuccess[dict],
    dependencies=[ALL_ROLES],
)
async def capture_delivery(
    delivery_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    delivery_note_image: Optional[UploadFile] = File(None),
    signature_image: Optional[UploadFile] = File(None),
    receiver_name: Optional[str] = Form(None),
    supplier_delivery_note_number: Optional[str] = Form(None),
    gps_lat: Optional[float] = Form(None),
    gps_lng: Optional[float] = Form(None),
    comments: Optional[str] = Form(None),
):
    delivery = db.get(Delivery, delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found.")

    if delivery_note_image:
        delivery.delivery_note_image_url = _save_file(delivery_note_image, "delivery-notes")

    if signature_image:
        delivery.signature_image_url = _save_file(signature_image, "signatures")

    if receiver_name:
        delivery.receiver_name = receiver_name
    if supplier_delivery_note_number:
        delivery.supplier_delivery_note_number = supplier_delivery_note_number
    if gps_lat is not None:
        delivery.gps_lat = gps_lat
    if gps_lng is not None:
        delivery.gps_lng = gps_lng
    if comments:
        delivery.comments = comments

    audit_service.write_event(
        db,
        action=AuditAction.UPLOAD,
        entity_type="delivery",
        actor_id=current_user.id,
        entity_id=delivery_id,
        after_value={
            "has_note_image": delivery.delivery_note_image_url is not None,
            "has_signature": delivery.signature_image_url is not None,
            "receiver_name": delivery.receiver_name,
        },
    )

    db.commit()

    return ApiSuccess(
        data={
            "delivery_id": str(delivery_id),
            "delivery_note_image_url": delivery.delivery_note_image_url,
            "signature_image_url": delivery.signature_image_url,
            "receiver_name": delivery.receiver_name,
        },
        message="Delivery captured.",
    )
