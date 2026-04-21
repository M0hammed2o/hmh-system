"""Attachment service — local-disk storage for V1 demo.

Files are saved to:  {UPLOAD_DIR}/{entity_type}/{entity_id}/{uuid4}_{original_name}

Upgrade path for production: swap _save_to_disk() for an S3 upload and update
stored_path to be an S3 key / presigned URL.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.models.attachment import Attachment
from app.models.enums import AttachmentEntity, AttachmentType

# ── Allowed MIME types ────────────────────────────────────────────────────────
ALLOWED_MIME_TYPES = {
    # Images
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    # Documents
    "application/pdf",
    # Spreadsheets
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    # Word documents (for BOQ uploads)
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _save_to_disk(file: UploadFile, entity_type: str, entity_id: str) -> tuple[str, int]:
    """Write the upload to local disk. Returns (relative_path, file_size_bytes)."""
    upload_dir = os.path.join(settings.UPLOAD_DIR, entity_type, entity_id)
    os.makedirs(upload_dir, exist_ok=True)

    # Unique filename avoids collisions even if original names repeat
    safe_name = os.path.basename(file.filename or "upload")
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"
    abs_path = os.path.join(upload_dir, unique_name)

    content = file.file.read()
    with open(abs_path, "wb") as fh:
        fh.write(content)

    # Relative path stored in DB — portable across restarts
    rel_path = os.path.join(entity_type, entity_id, unique_name)
    return rel_path, len(content)


def save_attachment(
    db: Session,
    file: UploadFile,
    entity_type: str,
    entity_id: str,
    attachment_type: str,
    uploaded_by_id: uuid.UUID,
) -> Attachment:
    # Validate enum values
    try:
        ent = AttachmentEntity(entity_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid entity_type: {entity_type}",
        )
    try:
        att = AttachmentType(attachment_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid attachment_type: {attachment_type}",
        )

    # Validate MIME type
    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{mime}' is not supported. Allowed: images, PDF, spreadsheets.",
        )

    # Validate size (re-read check; actual content read happens in _save_to_disk)
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    file.file.seek(0, 2)  # seek to end
    size = file.file.tell()
    file.file.seek(0)     # reset
    if size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )

    rel_path, file_size = _save_to_disk(file, entity_type, str(entity_id))

    record = Attachment(
        entity_type=ent,
        entity_id=uuid.UUID(str(entity_id)),
        file_name=os.path.basename(file.filename or "upload"),
        stored_path=rel_path,
        mime_type=mime,
        file_size_bytes=file_size,
        attachment_type=att,
        uploaded_by=uploaded_by_id,
        uploaded_at=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_attachments(
    db: Session,
    entity_type: str,
    entity_id: uuid.UUID,
    active_only: bool = True,
) -> list[Attachment]:
    try:
        ent = AttachmentEntity(entity_type)
    except ValueError:
        return []

    q = db.query(Attachment).filter(
        Attachment.entity_type == ent,
        Attachment.entity_id == entity_id,
    )
    if active_only:
        q = q.filter(Attachment.is_active == True)  # noqa: E712
    return q.order_by(Attachment.uploaded_at.desc()).all()


def get_attachment(db: Session, attachment_id: uuid.UUID) -> Attachment:
    a = db.get(Attachment, attachment_id)
    if not a:
        raise NotFoundError(f"Attachment {attachment_id} not found.")
    return a


def resolve_abs_path(stored_path: str) -> str:
    """Turn the stored relative path back into an absolute filesystem path."""
    return os.path.join(settings.UPLOAD_DIR, stored_path)
