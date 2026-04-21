"""Material Request service."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import RecordStatus
from app.models.material_request import MaterialRequest, MaterialRequestItem
from app.models.project import Project
from app.models.site import Site
from app.schemas.material_request import MaterialRequestCreate, MaterialRequestUpdate


def _generate_request_number(db: Session, project_id: uuid.UUID) -> str:
    count = (
        db.query(MaterialRequest)
        .filter(MaterialRequest.project_id == project_id)
        .count()
    )
    return f"MR-{str(project_id)[:8].upper()}-{count + 1:04d}"


def list_requests(
    db: Session, project_id: uuid.UUID, site_id: uuid.UUID = None
) -> list[MaterialRequest]:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")
    q = (
        db.query(MaterialRequest)
        .options(joinedload(MaterialRequest.items))
        .filter(MaterialRequest.project_id == project_id)
    )
    if site_id:
        q = q.filter(MaterialRequest.site_id == site_id)
    return q.order_by(MaterialRequest.created_at.desc()).all()


def get_request(db: Session, mr_id: uuid.UUID) -> MaterialRequest:
    mr = (
        db.query(MaterialRequest)
        .options(joinedload(MaterialRequest.items))
        .filter(MaterialRequest.id == mr_id)
        .first()
    )
    if not mr:
        raise NotFoundError(f"Material request {mr_id} not found.")
    return mr


def create_request(
    db: Session,
    project_id: uuid.UUID,
    data: MaterialRequestCreate,
    requested_by_id: uuid.UUID,
) -> MaterialRequest:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")

    site = db.get(Site, data.site_id)
    if not site or site.project_id != project_id:
        raise NotFoundError(f"Site {data.site_id} not found in this project.")

    mr = MaterialRequest(
        request_number=_generate_request_number(db, project_id),
        project_id=project_id,
        site_id=data.site_id,
        lot_id=data.lot_id,
        stage_id=data.stage_id,
        requested_by=requested_by_id,
        preferred_supplier_id=data.preferred_supplier_id,
        status=RecordStatus.DRAFT,
        requested_date=datetime.now(timezone.utc),
        needed_by_date=data.needed_by_date,
        notes=data.notes,
    )
    db.add(mr)
    db.flush()  # get mr.id

    for item_data in data.items:
        mr_item = MaterialRequestItem(
            material_request_id=mr.id,
            item_id=item_data.item_id,
            boq_item_id=item_data.boq_item_id,
            requested_quantity=item_data.requested_quantity,
            unit=item_data.unit,
            remarks=item_data.remarks,
        )
        db.add(mr_item)

    db.commit()
    db.refresh(mr)
    return mr


def update_request(
    db: Session,
    mr_id: uuid.UUID,
    data: MaterialRequestUpdate,
    reviewed_by_id: uuid.UUID,
) -> MaterialRequest:
    mr = get_request(db, mr_id)
    fields = data.model_fields_set

    if "status" in fields and data.status is not None:
        # Validate allowed transitions
        if data.status in (RecordStatus.APPROVED, RecordStatus.REJECTED):
            if mr.status != RecordStatus.SUBMITTED:
                raise ValidationError("Only SUBMITTED requests can be approved or rejected.")
            mr.reviewed_by = reviewed_by_id
            mr.reviewed_at = datetime.now(timezone.utc)
        mr.status = data.status

    if "rejection_reason" in fields:
        mr.rejection_reason = data.rejection_reason
    if "preferred_supplier_id" in fields:
        mr.preferred_supplier_id = data.preferred_supplier_id
    if "needed_by_date" in fields:
        mr.needed_by_date = data.needed_by_date
    if "notes" in fields:
        mr.notes = data.notes

    db.commit()
    db.refresh(mr)
    return mr
