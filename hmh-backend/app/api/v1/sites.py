"""Sites routes — scoped to a project."""

import uuid

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, field_validator

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_ADMIN_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.site import SiteCreate, SiteRead, SiteUpdate
from app.services import site_service

# Two routers:
#   project_sites_router  — mounted at /projects/{project_id}/sites
#   sites_router          — mounted at /sites  (for individual-site operations)
project_sites_router = APIRouter(
    prefix="/projects/{project_id}/sites",
    tags=["sites"],
)
sites_router = APIRouter(prefix="/sites", tags=["sites"])


@project_sites_router.get(
    "/",
    response_model=ApiSuccess[list[SiteRead]],
    dependencies=[ALL_ROLES],
)
def list_sites(
    project_id: uuid.UUID,
    db: DbSession,
    include_inactive: bool = Query(False, description="Include inactive sites"),
):
    """List all sites for a project. Active only by default."""
    sites = site_service.list_sites(db, project_id, include_inactive)
    return ApiSuccess(data=[SiteRead.model_validate(s) for s in sites])


@project_sites_router.post(
    "/",
    response_model=ApiSuccess[SiteRead],
    status_code=201,
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def create_site(
    project_id: uuid.UUID,
    body: SiteCreate,
    db: DbSession,
    _current_user: CurrentUser,
):
    """Create a new site within the project. Requires Office Admin or above."""
    site = site_service.create_site(db, project_id, body)
    return ApiSuccess(
        data=SiteRead.model_validate(site),
        message="Site created successfully.",
    )


@sites_router.patch(
    "/{site_id}",
    response_model=ApiSuccess[SiteRead],
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def update_site(site_id: uuid.UUID, body: SiteUpdate, db: DbSession):
    """Partially update a site (name, code, type, location, active status)."""
    site = site_service.update_site(db, site_id, body)
    return ApiSuccess(
        data=SiteRead.model_validate(site),
        message="Site updated successfully.",
    )


@sites_router.get(
    "/{site_id}",
    response_model=ApiSuccess[SiteRead],
    dependencies=[ALL_ROLES],
)
def get_site(site_id: uuid.UUID, db: DbSession):
    """Get a single site by ID."""
    site = site_service.get_site(db, site_id)
    return ApiSuccess(data=SiteRead.model_validate(site))


# ── Bulk create ───────────────────────────────────────────────────────────────

class SiteBulkCreate(BaseModel):
    prefix: str
    count: int
    site_type: str = "construction_site"
    location_description: Optional[str] = None

    @field_validator("count")
    @classmethod
    def sane_count(cls, v: int) -> int:
        if v < 1 or v > 50:
            raise ValueError("count must be between 1 and 50")
        return v

    @field_validator("prefix")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("prefix cannot be blank")
        return v.strip()


@project_sites_router.post(
    "/bulk",
    response_model=ApiSuccess[list[SiteRead]],
    status_code=201,
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def bulk_create_sites(project_id: uuid.UUID, body: SiteBulkCreate, db: DbSession):
    """Create multiple sites with auto-numbered names: '{prefix} 1', '{prefix} 2', …"""
    created = []
    for i in range(1, body.count + 1):
        site = site_service.create_site(db, project_id, SiteCreate(
            name=f"{body.prefix} {i}",
            site_type=body.site_type,
            location_description=body.location_description,
        ))
        created.append(site)
    return ApiSuccess(
        data=[SiteRead.model_validate(s) for s in created],
        message=f"{body.count} sites created.",
    )
