"""BOQ routes — three-level hierarchy."""

import uuid

from fastapi import APIRouter, Form, HTTPException, UploadFile

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.boq import (
    BOQHeaderCreate, BOQHeaderRead, BOQHeaderUpdate,
    BOQItemCreate, BOQItemRead, BOQItemUpdate,
    BOQSectionCreate, BOQSectionRead, BOQSectionUpdate,
)
from app.schemas.common import ApiSuccess
from app.services import boq_service

# Three routers for three levels
project_boq_router = APIRouter(
    prefix="/projects/{project_id}/boq",
    tags=["boq"],
)
boq_sections_router = APIRouter(prefix="/boq/{header_id}/sections", tags=["boq"])
boq_items_router = APIRouter(prefix="/boq/sections/{section_id}/items", tags=["boq"])
boq_item_router = APIRouter(prefix="/boq/items", tags=["boq"])


# ── Headers ───────────────────────────────────────────────────────────────────

@project_boq_router.get(
    "/",
    response_model=ApiSuccess[list[BOQHeaderRead]],
    dependencies=[ALL_ROLES],
)
def list_boq_headers(project_id: uuid.UUID, db: DbSession):
    headers = boq_service.list_headers(db, project_id)
    return ApiSuccess(data=[BOQHeaderRead.model_validate(h) for h in headers])


@project_boq_router.post(
    "/",
    response_model=ApiSuccess[BOQHeaderRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_boq_header(
    project_id: uuid.UUID,
    body: BOQHeaderCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    header = boq_service.create_header(db, project_id, body, current_user.id)
    return ApiSuccess(data=BOQHeaderRead.model_validate(header), message="BOQ header created.")


@project_boq_router.get(
    "/{header_id}",
    response_model=ApiSuccess[BOQHeaderRead],
    dependencies=[ALL_ROLES],
)
def get_boq_header(project_id: uuid.UUID, header_id: uuid.UUID, db: DbSession):
    header = boq_service.get_header(db, header_id)
    return ApiSuccess(data=BOQHeaderRead.model_validate(header))


@project_boq_router.patch(
    "/{header_id}",
    response_model=ApiSuccess[BOQHeaderRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_boq_header(
    project_id: uuid.UUID, header_id: uuid.UUID, body: BOQHeaderUpdate, db: DbSession
):
    header = boq_service.update_header(db, header_id, body)
    return ApiSuccess(data=BOQHeaderRead.model_validate(header), message="BOQ header updated.")


@project_boq_router.post(
    "/import-csv",
    response_model=ApiSuccess[BOQHeaderRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
async def import_boq_csv(
    project_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    file: UploadFile,
    version_name: str = Form(...),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")
    raw = await file.read()
    try:
        csv_text = raw.decode("utf-8-sig")  # strip BOM if present
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded.")
    header = boq_service.import_csv(db, project_id, csv_text, version_name, current_user.id)
    return ApiSuccess(
        data=BOQHeaderRead.model_validate(header),
        message=f"BOQ imported from CSV ({version_name}).",
    )


# ── Sections ──────────────────────────────────────────────────────────────────

@boq_sections_router.get(
    "/",
    response_model=ApiSuccess[list[BOQSectionRead]],
    dependencies=[ALL_ROLES],
)
def list_sections(header_id: uuid.UUID, db: DbSession):
    sections = boq_service.list_sections(db, header_id)
    return ApiSuccess(data=[BOQSectionRead.model_validate(s) for s in sections])


@boq_sections_router.post(
    "/",
    response_model=ApiSuccess[BOQSectionRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_section(header_id: uuid.UUID, body: BOQSectionCreate, db: DbSession):
    section = boq_service.create_section(db, header_id, body)
    return ApiSuccess(data=BOQSectionRead.model_validate(section), message="Section created.")


# ── Items ─────────────────────────────────────────────────────────────────────

@boq_items_router.get(
    "/",
    response_model=ApiSuccess[list[BOQItemRead]],
    dependencies=[ALL_ROLES],
)
def list_boq_items(section_id: uuid.UUID, db: DbSession):
    items = boq_service.list_items(db, section_id)
    return ApiSuccess(data=[BOQItemRead.model_validate(i) for i in items])


@boq_items_router.post(
    "/",
    response_model=ApiSuccess[BOQItemRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_boq_item(section_id: uuid.UUID, body: BOQItemCreate, db: DbSession):
    item = boq_service.create_item(db, section_id, body)
    return ApiSuccess(data=BOQItemRead.model_validate(item), message="BOQ item created.")


@boq_item_router.patch(
    "/{item_id}",
    response_model=ApiSuccess[BOQItemRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_boq_item(item_id: uuid.UUID, body: BOQItemUpdate, db: DbSession):
    item = boq_service.update_item(db, item_id, body)
    return ApiSuccess(data=BOQItemRead.model_validate(item), message="BOQ item updated.")
