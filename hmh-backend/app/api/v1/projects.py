"""Projects CRUD routes."""

import math
import uuid
from typing import Optional

from fastapi import APIRouter, Query

from app.dependencies import (
    ALL_ROLES,
    CurrentUser,
    DbSession,
    OFFICE_ADMIN_AND_ABOVE,
)
from app.models.enums import ProjectStatus
from app.schemas.common import ApiSuccess, PaginatedResult
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get(
    "/",
    response_model=ApiSuccess[PaginatedResult[ProjectRead]],
    dependencies=[ALL_ROLES],
)
def list_projects(
    db: DbSession,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[ProjectStatus] = Query(None, description="Filter by project status"),
):
    """List all projects. Optionally filter by status."""
    projects, total = project_service.list_projects(db, page, limit, status)
    return ApiSuccess(
        data=PaginatedResult(
            items=[ProjectRead.model_validate(p) for p in projects],
            total=total,
            page=page,
            limit=limit,
            total_pages=math.ceil(total / limit) if total else 1,
        )
    )


@router.post(
    "/",
    response_model=ApiSuccess[ProjectRead],
    status_code=201,
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def create_project(
    body: ProjectCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new project. Requires Office Admin or above."""
    project = project_service.create_project(db, body, current_user.id)
    return ApiSuccess(
        data=ProjectRead.model_validate(project),
        message="Project created successfully.",
    )


@router.get(
    "/{project_id}",
    response_model=ApiSuccess[ProjectRead],
    dependencies=[ALL_ROLES],
)
def get_project(project_id: uuid.UUID, db: DbSession):
    """Get a single project by ID."""
    project = project_service.get_project(db, project_id)
    return ApiSuccess(data=ProjectRead.model_validate(project))


@router.patch(
    "/{project_id}",
    response_model=ApiSuccess[ProjectRead],
    dependencies=[OFFICE_ADMIN_AND_ABOVE],
)
def update_project(project_id: uuid.UUID, body: ProjectUpdate, db: DbSession):
    """Partially update a project. Requires Office Admin or above."""
    project = project_service.update_project(db, project_id, body)
    return ApiSuccess(
        data=ProjectRead.model_validate(project),
        message="Project updated successfully.",
    )
