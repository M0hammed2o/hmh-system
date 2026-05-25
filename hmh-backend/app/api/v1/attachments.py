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
from app.dependencies import ALL_ROLES, CurrentUser, DbSession, WRITE_ROLES, check_project_access
from app.models.enums import UserRole
from app.schemas.attachment import AttachmentRead
from app.schemas.common import ApiSuccess
from app.services import attachment_service

router = APIRouter(prefix="/attachments", tags=["attachments"])


def _entity_project_id(db, entity_type: str, entity_id: uuid.UUID):
    """Resolve an attachment entity to its project_id. Returns None for non-project entities."""
    t = entity_type.upper()
    if t == "PROJECT":
        return entity_id
    if t == "LOT":
        from app.models.lot import Lot
        obj = db.get(Lot, entity_id)
        return obj.project_id if obj else None
    if t == "MATERIAL_REQUEST":
        from app.models.material_request import MaterialRequest
        obj = db.get(MaterialRequest, entity_id)
        return obj.project_id if obj else None
    if t == "PURCHASE_ORDER":
        from app.models.purchase_order import PurchaseOrder
        obj = db.get(PurchaseOrder, entity_id)
        return obj.project_id if obj else None
    if t == "DELIVERY":
        from app.models.delivery import Delivery
        obj = db.get(Delivery, entity_id)
        return obj.project_id if obj else None
    if t == "INVOICE":
        from app.models.invoice import Invoice
        obj = db.get(Invoice, entity_id)
        return obj.project_id if obj else None
    if t == "PAYMENT":
        from app.models.payment import Payment
        obj = db.get(Payment, entity_id)
        return obj.project_id if obj else None
    if t == "BOQ_HEADER":
        from app.models.boq import BOQHeader
        obj = db.get(BOQHeader, entity_id)
        return obj.project_id if obj else None
    return None


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
    caption: Optional[str] = Form(default=None, description="Optional short caption"),
):
    project_id = _entity_project_id(db, entity_type, uuid.UUID(entity_id))
    if project_id:
        check_project_access(db, current_user, project_id)
    record = attachment_service.save_attachment(
        db=db,
        file=file,
        entity_type=entity_type,
        entity_id=entity_id,
        attachment_type=attachment_type,
        uploaded_by_id=current_user.id,
        caption=caption,
        uploaded_role=current_user.role.value if current_user.role else None,
    )
    read = AttachmentRead.model_validate(record)
    read.uploaded_by_name = current_user.full_name if hasattr(current_user, "full_name") else None
    return ApiSuccess(data=read, message="File uploaded successfully.")


@router.get(
    "/",
    response_model=ApiSuccess[list[AttachmentRead]],
    dependencies=[ALL_ROLES],
)
def list_attachments(
    db: DbSession,
    current_user: CurrentUser,
    entity_type: str = Query(...),
    entity_id: uuid.UUID = Query(...),
    attachment_type: Optional[str] = Query(default=None, description="Filter by attachment type"),
    limit: Optional[int] = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    project_id = _entity_project_id(db, entity_type, entity_id)
    if project_id:
        check_project_access(db, current_user, project_id)
    records = attachment_service.list_attachments(
        db, entity_type, entity_id,
        attachment_type=attachment_type,
        limit=limit,
        offset=offset,
    )

    # Bulk-fetch user names for uploaded_by resolution
    from app.models.user import User
    uploader_ids = {r.uploaded_by for r in records if r.uploaded_by}
    name_map: dict = {}
    if uploader_ids:
        users = db.query(User).filter(User.id.in_(uploader_ids)).all()
        name_map = {str(u.id): u.full_name for u in users}

    result = []
    for r in records:
        read = AttachmentRead.model_validate(r)
        if r.uploaded_by:
            read.uploaded_by_name = name_map.get(str(r.uploaded_by))
        result.append(read)

    return ApiSuccess(data=result)


@router.get(
    "/{attachment_id}/download",
    dependencies=[ALL_ROLES],
)
def download_attachment(attachment_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """Stream local files; redirect to Supabase for cloud-stored files."""
    record = attachment_service.get_attachment(db, attachment_id)
    if not record.is_active:
        raise HTTPException(404, "Attachment is no longer available.")
    project_id = _entity_project_id(db, record.entity_type.value, record.entity_id)
    if project_id:
        check_project_access(db, current_user, project_id)

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
def delete_attachment(attachment_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """Soft-delete an attachment (sets is_active=False).

    SITE_STAFF can only delete their own uploads; office/admin can delete any.
    """
    record = attachment_service.get_attachment(db, attachment_id)
    project_id = _entity_project_id(db, record.entity_type.value, record.entity_id)
    if project_id:
        check_project_access(db, current_user, project_id)

    # SITE_STAFF own-only delete enforcement
    if current_user.role == UserRole.SITE_STAFF:
        if record.uploaded_by != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Site staff can only delete their own uploads.",
            )

    attachment_service.soft_delete_attachment(db, record, deleted_by_id=current_user.id)
    return ApiSuccess(data={"id": str(attachment_id)}, message="Attachment removed.")
