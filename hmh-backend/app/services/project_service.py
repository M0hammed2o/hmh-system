"""Project service — CRUD operations."""

import math
import uuid
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import ProjectStatus, UserRole
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate

_MAX_PAGE_SIZE = 100

# Roles that see ALL projects (no access-table filter needed).
# Site-type roles (SITE_MANAGER, SITE_STAFF, SITE_MANAGER_VIEW) are excluded —
# they must be explicitly assigned to a project.
_UNRESTRICTED_ROLES = {
    UserRole.OWNER,
    UserRole.OFFICE_ADMIN,
    UserRole.OFFICE_USER,
    UserRole.PROCUREMENT_LEAD,
    UserRole.READ_ONLY,
}


def _get_or_404(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")
    return project


def _assert_code_unique(db: Session, code: str, exclude_id: Optional[uuid.UUID] = None) -> None:
    q = db.query(Project).filter(func.lower(Project.code) == code.strip().lower())
    if exclude_id:
        q = q.filter(Project.id != exclude_id)
    if q.first():
        raise ConflictError(f"A project with code '{code.strip().upper()}' already exists.")


# ── Public API ────────────────────────────────────────────────────────────────

def list_projects(
    db: Session,
    page: int,
    limit: int,
    status: Optional[ProjectStatus] = None,
    user_id: Optional[uuid.UUID] = None,
    user_role: Optional[UserRole] = None,
) -> tuple[list[Project], int]:
    limit = min(limit, _MAX_PAGE_SIZE)
    offset = (page - 1) * limit

    q = db.query(Project)
    if status is not None:
        q = q.filter(Project.status == status)

    # Restrict non-admin roles to their explicitly assigned projects
    if user_id and user_role and user_role not in _UNRESTRICTED_ROLES:
        from app.models.access import UserProjectAccess
        q = q.join(
            UserProjectAccess,
            (UserProjectAccess.project_id == Project.id) &
            (UserProjectAccess.user_id == user_id),
        )

    total = q.count()
    projects = q.order_by(Project.created_at.desc()).offset(offset).limit(limit).all()
    return projects, total


def get_project(db: Session, project_id: uuid.UUID) -> Project:
    return _get_or_404(db, project_id)


def create_project(
    db: Session,
    data: ProjectCreate,
    created_by_id: uuid.UUID,
) -> Project:
    _assert_code_unique(db, data.code)

    project = Project(
        name=data.name.strip(),
        code=data.code.strip().upper(),
        description=data.description,
        location=data.location,
        client_name=data.client_name,
        start_date=data.start_date,
        estimated_end_date=data.estimated_end_date,
        go_live_date=data.go_live_date,
        status=data.status,
        created_by=created_by_id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # Auto-create Project Warehouse site so it's always available for stock
    try:
        from app.models.site import Site
        warehouse = Site(
            project_id=project.id,
            name="Project Warehouse",
            code="PW",
            site_type="warehouse",
        )
        db.add(warehouse)
        db.commit()
    except Exception:
        pass  # never crash project creation

    return project


def update_project(
    db: Session,
    project_id: uuid.UUID,
    data: ProjectUpdate,
) -> Project:
    project = _get_or_404(db, project_id)

    # Only update fields explicitly provided in the request body
    update_fields = data.model_fields_set

    if "name" in update_fields and data.name is not None:
        project.name = data.name.strip()
    if "code" in update_fields and data.code is not None:
        new_code = data.code.strip().upper()
        _assert_code_unique(db, new_code, exclude_id=project_id)
        project.code = new_code
    if "description" in update_fields:
        project.description = data.description
    if "location" in update_fields:
        project.location = data.location
    if "client_name" in update_fields:
        project.client_name = data.client_name
    if "start_date" in update_fields:
        project.start_date = data.start_date
    if "estimated_end_date" in update_fields:
        project.estimated_end_date = data.estimated_end_date
    if "go_live_date" in update_fields:
        project.go_live_date = data.go_live_date
    if "status" in update_fields and data.status is not None:
        project.status = data.status

    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project_id: uuid.UUID) -> dict:
    """
    Permanently delete a project and all cascade-linked data.
    FK children (sites, lots, BOQ, deliveries, payments, etc.) cascade via DB FK.
    Returns a summary of what was deleted.
    """
    from app.models.site import Site
    from app.models.lot import Lot

    project = _get_or_404(db, project_id)
    site_count = db.query(Site).filter(Site.project_id == project_id).count()
    lot_count  = db.query(Lot).filter(Lot.project_id == project_id).count()

    db.delete(project)
    db.commit()
    return {
        "deleted_project": project.name,
        "cascade_sites":   site_count,
        "cascade_lots":    lot_count,
    }
