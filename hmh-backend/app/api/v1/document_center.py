"""Document Center — aggregated attachment listing for a project.

Returns all active attachments linked to a project's procurement entities
(Material Requests, Purchase Orders, Invoices, Deliveries, Payments) enriched
with each entity's human-readable reference number.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, or_
from datetime import datetime

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, check_project_access
from app.models.attachment import Attachment
from app.models.delivery import Delivery
from app.models.enums import AttachmentEntity
from app.models.invoice import Invoice
from app.models.material_request import MaterialRequest
from app.models.payment import Payment
from app.models.purchase_order import PurchaseOrder
from app.schemas.common import ApiSuccess

router = APIRouter(prefix="/api/v1/projects/{project_id}/documents", tags=["document-center"])

_ENTITY_TYPES = {
    AttachmentEntity.MATERIAL_REQUEST,
    AttachmentEntity.PURCHASE_ORDER,
    AttachmentEntity.INVOICE,
    AttachmentEntity.DELIVERY,
    AttachmentEntity.PAYMENT,
}

_ENTITY_LABELS = {
    AttachmentEntity.MATERIAL_REQUEST: "Material Request",
    AttachmentEntity.PURCHASE_ORDER:   "Purchase Order",
    AttachmentEntity.INVOICE:          "Invoice",
    AttachmentEntity.DELIVERY:         "Delivery",
    AttachmentEntity.PAYMENT:          "Payment",
}


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: AttachmentEntity
    entity_id: uuid.UUID
    entity_ref: Optional[str] = None
    entity_label: str
    file_name: str
    mime_type: str
    attachment_type: str
    file_size_bytes: Optional[int] = None
    file_size_display: str
    caption: Optional[str] = None
    uploaded_by_name: Optional[str] = None
    uploaded_role: Optional[str] = None
    uploaded_at: datetime
    download_url: str
    is_image: bool


@router.get("", response_model=ApiSuccess[list[DocumentRead]], dependencies=[ALL_ROLES])
def list_project_documents(
    project_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    entity_type: Optional[str] = Query(default=None, description="Filter by entity type"),
    search: Optional[str] = Query(default=None, description="Search by file name"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    check_project_access(db, current_user, project_id)

    # Resolve entity IDs that belong to this project for each supported type
    mr_ids  = db.query(MaterialRequest.id).filter(MaterialRequest.project_id == project_id).subquery()
    po_ids  = db.query(PurchaseOrder.id).filter(PurchaseOrder.project_id == project_id).subquery()
    inv_ids = db.query(Invoice.id).filter(Invoice.project_id == project_id).subquery()
    del_ids = db.query(Delivery.id).filter(Delivery.project_id == project_id).subquery()
    pay_ids = db.query(Payment.id).filter(Payment.project_id == project_id).subquery()

    conditions = [
        and_(Attachment.entity_type == AttachmentEntity.MATERIAL_REQUEST, Attachment.entity_id.in_(mr_ids)),
        and_(Attachment.entity_type == AttachmentEntity.PURCHASE_ORDER,   Attachment.entity_id.in_(po_ids)),
        and_(Attachment.entity_type == AttachmentEntity.INVOICE,          Attachment.entity_id.in_(inv_ids)),
        and_(Attachment.entity_type == AttachmentEntity.DELIVERY,         Attachment.entity_id.in_(del_ids)),
        and_(Attachment.entity_type == AttachmentEntity.PAYMENT,          Attachment.entity_id.in_(pay_ids)),
    ]

    q = db.query(Attachment).filter(
        Attachment.is_active == True,  # noqa: E712
        or_(*conditions),
    )

    if entity_type:
        try:
            et = AttachmentEntity(entity_type.upper())
            q = q.filter(Attachment.entity_type == et)
        except ValueError:
            pass

    if search:
        q = q.filter(Attachment.file_name.ilike(f"%{search}%"))

    total_q = q.count()
    attachments = q.order_by(Attachment.uploaded_at.desc()).offset(offset).limit(limit).all()

    if not attachments:
        return ApiSuccess(data=[], message=f"0 of {total_q} documents")

    # Build entity reference number lookups (batch, not N+1)
    mr_id_set  = {a.entity_id for a in attachments if a.entity_type == AttachmentEntity.MATERIAL_REQUEST}
    po_id_set  = {a.entity_id for a in attachments if a.entity_type == AttachmentEntity.PURCHASE_ORDER}
    inv_id_set = {a.entity_id for a in attachments if a.entity_type == AttachmentEntity.INVOICE}
    del_id_set = {a.entity_id for a in attachments if a.entity_type == AttachmentEntity.DELIVERY}
    pay_id_set = {a.entity_id for a in attachments if a.entity_type == AttachmentEntity.PAYMENT}

    mr_refs:  dict[uuid.UUID, str] = {}
    po_refs:  dict[uuid.UUID, str] = {}
    inv_refs: dict[uuid.UUID, str] = {}
    del_refs: dict[uuid.UUID, str] = {}
    pay_refs: dict[uuid.UUID, str] = {}

    if mr_id_set:
        rows = db.query(MaterialRequest.id, MaterialRequest.request_number).filter(MaterialRequest.id.in_(mr_id_set)).all()
        mr_refs = {r.id: r.request_number for r in rows}
    if po_id_set:
        rows = db.query(PurchaseOrder.id, PurchaseOrder.po_number).filter(PurchaseOrder.id.in_(po_id_set)).all()
        po_refs = {r.id: r.po_number for r in rows}
    if inv_id_set:
        rows = db.query(Invoice.id, Invoice.invoice_number).filter(Invoice.id.in_(inv_id_set)).all()
        inv_refs = {r.id: r.invoice_number for r in rows}
    if del_id_set:
        rows = db.query(Delivery.id, Delivery.delivery_number).filter(Delivery.id.in_(del_id_set)).all()
        del_refs = {r.id: (r.delivery_number or "") for r in rows}
    if pay_id_set:
        rows = db.query(Payment.id, Payment.payment_reference).filter(Payment.id.in_(pay_id_set)).all()
        pay_refs = {r.id: (r.payment_reference or "") for r in rows}

    ref_lookup: dict[AttachmentEntity, dict] = {
        AttachmentEntity.MATERIAL_REQUEST: mr_refs,
        AttachmentEntity.PURCHASE_ORDER:   po_refs,
        AttachmentEntity.INVOICE:          inv_refs,
        AttachmentEntity.DELIVERY:         del_refs,
        AttachmentEntity.PAYMENT:          pay_refs,
    }

    # Fetch uploader names in a single query
    from app.models.user import User
    uploader_ids = {a.uploaded_by for a in attachments if a.uploaded_by}
    name_map: dict = {}
    if uploader_ids:
        users = db.query(User.id, User.full_name).filter(User.id.in_(uploader_ids)).all()
        name_map = {str(u.id): u.full_name for u in users}

    results: list[DocumentRead] = []
    for a in attachments:
        entity_ref = ref_lookup.get(a.entity_type, {}).get(a.entity_id) or None

        # Compute derived fields (mirrors AttachmentRead computed fields)
        if a.stored_path.startswith("http"):
            download_url = a.stored_path
        else:
            download_url = f"/api/v1/attachments/{a.id}/download"

        file_size_display = "—"
        if a.file_size_bytes:
            kb = a.file_size_bytes / 1024
            file_size_display = f"{kb:.1f} KB" if kb < 1024 else f"{kb / 1024:.1f} MB"

        results.append(DocumentRead(
            id=a.id,
            entity_type=a.entity_type,
            entity_id=a.entity_id,
            entity_ref=entity_ref or None,
            entity_label=_ENTITY_LABELS.get(a.entity_type, str(a.entity_type)),
            file_name=a.file_name,
            mime_type=a.mime_type,
            attachment_type=a.attachment_type.value if hasattr(a.attachment_type, "value") else str(a.attachment_type),
            file_size_bytes=a.file_size_bytes,
            file_size_display=file_size_display,
            caption=a.caption,
            uploaded_by_name=name_map.get(str(a.uploaded_by)) if a.uploaded_by else None,
            uploaded_role=a.uploaded_role,
            uploaded_at=a.uploaded_at,
            download_url=download_url,
            is_image=a.mime_type.startswith("image/"),
        ))

    return ApiSuccess(data=results, message=f"{len(results)} of {total_q} documents")
