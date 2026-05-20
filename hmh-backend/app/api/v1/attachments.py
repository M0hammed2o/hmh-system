"""Attachment routes — upload, list, download, and delete.

Upload routes through storage.py which uses Supabase Storage when configured,
falling back to local disk otherwise.
"""

import os
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from app.core.exceptions import NotFoundError
from app.dependencies import ALL_ROLES, CurrentUser, DbSession, WRITE_ROLES
from app.schemas.attachment import AttachmentRead
from app.schemas.common import ApiSuccess
from app.services import attachment_service

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.post(
    "/upload",
    response_model=ApiSuccess[AttachmentRead],
    status_code=201,
    dependencies=[WRITE_ROLES],
)
async def upload_attachment(
    db: DbSession,
    current_user: CurrentUser,
    file: UploadFile = File(..., description="File to upload (image, PDF, or spreadsheet)"),
    entity_type: str = Form(..., description="e.g. DELIVERY, PAYMENT, FUEL_LOG"),
    entity_id: str = Form(..., description="UUID of the linked entity"),
    attachment_type: str = Form(default="PHOTO", description="e.g. PHOTO, PDF, PROOF"),
):
    record = attachment_service.save_attachment(
        db=db,
        file=file,
        entity_type=entity_type,
        entity_id=entity_id,
        attachment_type=attachment_type,
        uploaded_by_id=current_user.id,
    )
    return ApiSuccess(
        data=AttachmentRead.model_validate(record),
        message="File uploaded successfully.",
    )


@router.get(
    "/",
    response_model=ApiSuccess[list[AttachmentRead]],
    dependencies=[ALL_ROLES],
)
def list_attachments(
    db: DbSession,
    entity_type: str = Query(...),
    entity_id: uuid.UUID = Query(...),
):
    records = attachment_service.list_attachments(db, entity_type, entity_id)
    return ApiSuccess(data=[AttachmentRead.model_validate(r) for r in records])


@router.get(
    "/{attachment_id}/download",
    dependencies=[ALL_ROLES],
)
def download_attachment(attachment_id: uuid.UUID, db: DbSession):
    """Stream local files; redirect to Supabase for cloud-stored files."""
    record = attachment_service.get_attachment(db, attachment_id)
    if not record.is_active:
        raise HTTPException(404, "Attachment is no longer available.")

    # Supabase Storage or any absolute URL → redirect (no backend proxy needed)
    if record.stored_path.startswith("http"):
        return RedirectResponse(record.stored_path, status_code=302)

    # Local disk
    abs_path = attachment_service.resolve_abs_path(record.stored_path)
    if not os.path.exists(abs_path):
        raise HTTPException(404, "File not found on server. It may have been deleted.")
    return FileResponse(
        path=abs_path,
        media_type=record.mime_type,
        filename=record.file_name,
    )


@router.delete(
    "/{attachment_id}",
    response_model=ApiSuccess[dict],
    dependencies=[WRITE_ROLES],
)
def delete_attachment(attachment_id: uuid.UUID, db: DbSession):
    """Soft-delete an attachment (sets is_active=False)."""
    record = attachment_service.get_attachment(db, attachment_id)
    record.is_active = False
    db.commit()
    return ApiSuccess(data={"id": str(attachment_id)}, message="Attachment removed.")
