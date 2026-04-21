"""Attachment routes — upload, list, and download.

Upload uses multipart/form-data so a file and metadata arrive together.
Download streams the file from local disk via FileResponse.

For production: swap the FileResponse for a presigned S3 URL redirect.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from app.core.exceptions import NotFoundError
from app.dependencies import ALL_ROLES, CurrentUser, DbSession
from app.schemas.attachment import AttachmentRead
from app.schemas.common import ApiSuccess
from app.services import attachment_service

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.post(
    "/upload",
    response_model=ApiSuccess[AttachmentRead],
    status_code=201,
    dependencies=[ALL_ROLES],
)
async def upload_attachment(
    db: DbSession,
    current_user: CurrentUser,
    file: UploadFile = File(..., description="File to upload (image, PDF, or spreadsheet)"),
    entity_type: str = Form(..., description="e.g. DELIVERY, PURCHASE_ORDER, INVOICE"),
    entity_id: str = Form(..., description="UUID of the linked entity"),
    attachment_type: str = Form(..., description="e.g. PHOTO, PDF, DELIVERY_NOTE"),
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
    # Response is a file stream — not an ApiSuccess envelope
)
def download_attachment(attachment_id: uuid.UUID, db: DbSession):
    record = attachment_service.get_attachment(db, attachment_id)
    if not record.is_active:
        raise NotFoundError("Attachment is no longer available.")

    abs_path = attachment_service.resolve_abs_path(record.stored_path)
    return FileResponse(
        path=abs_path,
        media_type=record.mime_type,
        filename=record.file_name,
    )
