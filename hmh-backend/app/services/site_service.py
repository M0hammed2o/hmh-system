"""Site service — CRUD operations scoped to a project."""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.project import Project
from app.models.site import Site
from app.schemas.site import SiteCreate, SiteUpdate

_MAX_PAGE_SIZE = 200


def _get_project_or_404(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")
    return project


def _get_site_or_404(db: Session, site_id: uuid.UUID) -> Site:
    site = db.get(Site, site_id)
    if not site:
        raise NotFoundError(f"Site {site_id} not found.")
    return site


def _assert_code_unique_in_project(
    db: Session,
    project_id: uuid.UUID,
    code: str,
    exclude_id: Optional[uuid.UUID] = None,
) -> None:
    """Code must be unique within the project (case-insensitive)."""
    q = (
        db.query(Site)
        .filter(Site.project_id == project_id)
        .filter(Site.code.ilike(code.strip()))
    )
    if exclude_id:
        q = q.filter(Site.id != exclude_id)
    if q.first():
        raise ConflictError(
            f"A site with code '{code.strip().upper()}' already exists in this project."
        )


# ── Public API ─────────────────────────────────────────────────────────────────

def list_sites(
    db: Session,
    project_id: uuid.UUID,
    include_inactive: bool = False,
) -> list[Site]:
    """Return all sites for a project, ordered by name."""
    _get_project_or_404(db, project_id)
    q = db.query(Site).filter(Site.project_id == project_id)
    if not include_inactive:
        q = q.filter(Site.is_active == True)  # noqa: E712
    return q.order_by(Site.name).all()


def get_site(db: Session, site_id: uuid.UUID) -> Site:
    return _get_site_or_404(db, site_id)


def create_site(
    db: Session,
    project_id: uuid.UUID,
    data: SiteCreate,
) -> Site:
    _get_project_or_404(db, project_id)

    if data.code:
        _assert_code_unique_in_project(db, project_id, data.code)

    site = Site(
        project_id=project_id,
        name=data.name.strip(),
        code=data.code.strip().upper() if data.code else None,
        site_type=data.site_type.strip() if data.site_type else "construction_site",
        location_description=data.location_description,
        is_active=True,
    )
    db.add(site)
    db.commit()
    db.refresh(site)
    return site


def update_site(
    db: Session,
    site_id: uuid.UUID,
    data: SiteUpdate,
) -> Site:
    site = _get_site_or_404(db, site_id)
    updated_fields = data.model_fields_set

    if "name" in updated_fields and data.name is not None:
        site.name = data.name.strip()
    if "code" in updated_fields and data.code is not None:
        new_code = data.code.strip().upper()
        _assert_code_unique_in_project(db, site.project_id, new_code, exclude_id=site_id)
        site.code = new_code
    if "site_type" in updated_fields and data.site_type is not None:
        site.site_type = data.site_type.strip()
    if "location_description" in updated_fields:
        site.location_description = data.location_description
    if "is_active" in updated_fields and data.is_active is not None:
        site.is_active = data.is_active

    db.commit()
    db.refresh(site)
    return site
