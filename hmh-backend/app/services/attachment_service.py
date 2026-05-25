"""Attachment service.

Files are saved via save_upload() which routes to:
  - Supabase Storage when SUPABASE_URL + SUPABASE_SERVICE_KEY are configured
  - Local disk (UPLOAD_DIR) otherwise

stored_path is always the public-accessible URL (Supabase) or /uploads/... path (local).
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.storage import save_upload
from app.core.upload_validation import _check_extension
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


def _save_via_storage(file: UploadFile, entity_type: str, entity_id: str) -> tuple[str, int]:
    """
    Read file bytes, route through save_upload() (Supabase or local disk).
    Returns (stored_url_or_path, file_size_bytes).
    """
    content = file.file.read()
    ext = os.path.splitext(file.filename or "upload")[1].lower() or ".bin"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    relative = f"attachments/{entity_type}/{entity_id}/{unique_name}"
    stored = save_upload(content, relative)
    return stored, len(content)


def _log_audit(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    attachment_id: uuid.UUID,
    user_id: Optional[uuid.UUID],
    description: str,
) -> None:
    """Write an audit log entry for attachment upload/delete events."""
    try:
        from app.models.audit import AuditEvent
        db.add(AuditEvent(
            actor_id=user_id,
            action=action,
            entity_type="attachments",
            entity_id=attachment_id,
            after_value={"entity_type": entity_type, "entity_id": str(entity_id)},
            notes=description,
            created_at=datetime.now(timezone.utc),
        ))
        db.flush()
    except Exception:
        pass  # Audit failures must never break the primary operation


def save_attachment(
    db: Session,
    file: UploadFile,
    entity_type: str,
    entity_id: str,
    attachment_type: str,
    uploaded_by_id: uuid.UUID,
    caption: Optional[str] = None,
    uploaded_role: Optional[str] = None,
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

    # Validate extension (independent of client-declared MIME type)
    _check_extension(file.filename)

    # Validate MIME type
    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{mime}' is not supported. Allowed: images, PDF, spreadsheets.",
        )

    # Validate size before reading
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )

    stored_path, file_size = _save_via_storage(file, entity_type, str(entity_id))

    record = Attachment(
        entity_type     = ent,
        entity_id       = uuid.UUID(str(entity_id)),
        file_name       = os.path.basename(file.filename or "upload"),
        stored_path     = stored_path,
        file_url        = stored_path,   # legacy column kept in sync
        mime_type       = mime,
        file_size_bytes = file_size,
        attachment_type = att,
        uploaded_by     = uploaded_by_id,
        uploaded_at     = datetime.now(timezone.utc),
        is_active       = True,
        caption         = caption.strip() if caption else None,
        uploaded_role   = uploaded_role,
    )
    db.add(record)
    db.flush()

    _log_audit(
        db, "UPLOAD", entity_type, uuid.UUID(str(entity_id)),
        record.id, uploaded_by_id,
        f"Uploaded {record.file_name} ({attachment_type})",
    )

    db.commit()
    db.refresh(record)
    return record


def list_attachments(
    db: Session,
    entity_type: str,
    entity_id: uuid.UUID,
    active_only: bool = True,
    attachment_type: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
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
    if attachment_type:
        try:
            att_enum = AttachmentType(attachment_type)
            q = q.filter(Attachment.attachment_type == att_enum)
        except ValueError:
            pass

    q = q.order_by(Attachment.uploaded_at.desc())

    if offset:
        q = q.offset(offset)
    if limit:
        q = q.limit(limit)

    return q.all()


def get_attachment(db: Session, attachment_id: uuid.UUID) -> Attachment:
    a = db.get(Attachment, attachment_id)
    if not a:
        raise NotFoundError(f"Attachment {attachment_id} not found.")
    return a


def soft_delete_attachment(
    db: Session,
    record: Attachment,
    deleted_by_id: Optional[uuid.UUID] = None,
) -> None:
    """Soft-delete and write audit log."""
    record.is_active = False
    _log_audit(
        db, "DELETE", record.entity_type.value, record.entity_id,
        record.id, deleted_by_id,
        f"Deleted attachment {record.file_name}",
    )
    db.commit()


def resolve_abs_path(stored_path: str) -> str:
    """Turn a stored path into an absolute filesystem path.

    Handles three formats produced by save_upload() or legacy code:
      https://...        → caller should redirect, not call this function
      /uploads/...       → strip the prefix, join with UPLOAD_DIR
      relative/path.ext  → join directly with UPLOAD_DIR (legacy format)
    """
    if stored_path.startswith("http"):
        # Caller should redirect; this is a safety guard
        return stored_path
    if stored_path.startswith("/uploads/"):
        return os.path.join(settings.UPLOAD_DIR, stored_path[len("/uploads/"):])
    return os.path.join(settings.UPLOAD_DIR, stored_path)
