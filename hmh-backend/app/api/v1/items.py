"""Item catalogue routes."""

import uuid

from fastapi import APIRouter, Query

from app.dependencies import ALL_ROLES, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.item import ItemCategoryRead, ItemCreate, ItemRead, ItemUpdate
from app.services import item_service

router = APIRouter(prefix="/items", tags=["items"])
categories_router = APIRouter(prefix="/item-categories", tags=["items"])


@categories_router.get(
    "/",
    response_model=ApiSuccess[list[ItemCategoryRead]],
    dependencies=[ALL_ROLES],
)
def list_categories(db: DbSession):
    cats = item_service.list_categories(db)
    return ApiSuccess(data=[ItemCategoryRead.model_validate(c) for c in cats])


@router.get(
    "/",
    response_model=ApiSuccess[list[ItemRead]],
    dependencies=[ALL_ROLES],
)
def list_items(
    db: DbSession,
    include_inactive: bool = Query(False),
):
    items = item_service.list_items(db, include_inactive)
    return ApiSuccess(data=[ItemRead.model_validate(i) for i in items])


@router.get(
    "/{item_id}",
    response_model=ApiSuccess[ItemRead],
    dependencies=[ALL_ROLES],
)
def get_item(item_id: uuid.UUID, db: DbSession):
    item = item_service.get_item(db, item_id)
    return ApiSuccess(data=ItemRead.model_validate(item))


@router.post(
    "/",
    response_model=ApiSuccess[ItemRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_item(body: ItemCreate, db: DbSession):
    item = item_service.create_item(db, body)
    return ApiSuccess(data=ItemRead.model_validate(item), message="Item created.")


@router.patch(
    "/{item_id}",
    response_model=ApiSuccess[ItemRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_item(item_id: uuid.UUID, body: ItemUpdate, db: DbSession):
    item = item_service.update_item(db, item_id, body)
    return ApiSuccess(data=ItemRead.model_validate(item), message="Item updated.")
