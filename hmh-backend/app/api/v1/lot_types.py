"""LotType routes — Phase 3D.2 + 3D.3."""

import uuid
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.schemas.common import ApiSuccess
from app.schemas.lot_type import (
    AssignLotsRequest,
    LotTypeCreate,
    LotTypeRead,
    LotTypeUpdate,
    LotTypeWithLots,
    RemoveLotsRequest,
)
from app.services import lot_type_service


class PropagateRequest(BaseModel):
    mode:               str           = "SAFE"      # SAFE | FORCE
    lot_ids:            Optional[list[uuid.UUID]] = None  # None = all linked lots
    generate_milestones: bool         = True

project_lot_types_router = APIRouter(
    prefix="/projects/{project_id}/lot-types",
    tags=["lot-types"],
)
lot_types_router = APIRouter(prefix="/lot-types", tags=["lot-types"])


@project_lot_types_router.get(
    "/",
    response_model=ApiSuccess[list[LotTypeRead]],
    dependencies=[ALL_ROLES],
)
def list_lot_types(project_id: uuid.UUID, db: DbSession):
    """List all lot types for a project with lot counts."""
    types = lot_type_service.list_lot_types(db, project_id)
    return ApiSuccess(data=types)


@project_lot_types_router.post(
    "/",
    response_model=ApiSuccess[LotTypeRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def create_lot_type(
    project_id: uuid.UUID,
    body: LotTypeCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    lt = lot_type_service.create_lot_type(db, project_id, body, actor_id=current_user.id)
    return ApiSuccess(data=lt, message=f"Lot type '{lt.name}' created.")


@lot_types_router.get(
    "/{lot_type_id}",
    response_model=ApiSuccess[LotTypeWithLots],
    dependencies=[ALL_ROLES],
)
def get_lot_type(lot_type_id: uuid.UUID, db: DbSession):
    """Get a lot type with its linked lots."""
    lt = lot_type_service.get_lot_type(db, lot_type_id)
    return ApiSuccess(data=lt)


@lot_types_router.patch(
    "/{lot_type_id}",
    response_model=ApiSuccess[LotTypeRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_lot_type(lot_type_id: uuid.UUID, body: LotTypeUpdate, db: DbSession):
    lt = lot_type_service.update_lot_type(db, lot_type_id, body)
    return ApiSuccess(data=lt, message=f"Lot type '{lt.name}' updated.")


@lot_types_router.delete(
    "/{lot_type_id}",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def delete_lot_type(lot_type_id: uuid.UUID, db: DbSession):
    """
    Delete a lot type. Blocked if any lots are still assigned.
    Unassign all lots first, or use the force query param.
    """
    from app.models.lot_type import LotType
    lt = db.get(LotType, lot_type_id)
    name = lt.name if lt else str(lot_type_id)
    lot_type_service.delete_lot_type(db, lot_type_id)
    return ApiSuccess(data={"id": str(lot_type_id)}, message=f"Lot type '{name}' deleted.")


# ── Lot assignment ────────────────────────────────────────────────────────────

@lot_types_router.post(
    "/{lot_type_id}/assign-lots",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def assign_lots(lot_type_id: uuid.UUID, body: AssignLotsRequest, db: DbSession):
    """
    Assign lots to this type (bulk).
    Lots from other types are reassigned here.
    Returns: { assigned, reassigned, already_set, total }
    """
    result = lot_type_service.assign_lots(db, lot_type_id, body.lot_ids)
    return ApiSuccess(
        data=result,
        message=(
            f"{result['assigned']} lot(s) assigned, "
            f"{result['reassigned']} reassigned, "
            f"{result['already_set']} already in type."
        ),
    )


@lot_types_router.post(
    "/{lot_type_id}/remove-lots",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def remove_lots(lot_type_id: uuid.UUID, body: RemoveLotsRequest, db: DbSession):
    """Remove lots from this type (sets lot_type_id = NULL)."""
    result = lot_type_service.remove_lots(db, lot_type_id, body.lot_ids)
    return ApiSuccess(data=result, message=f"{result['removed']} lot(s) removed from type.")


# ── Propagation (Phase 3D.3) ──────────────────────────────────────────────────

@lot_types_router.post(
    "/{lot_type_id}/preview-propagate",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def preview_propagate(lot_type_id: uuid.UUID, body: PropagateRequest, db: DbSession):
    """
    Dry-run: show which lots would receive the BOQ changes and which would be
    skipped, without writing anything to the database.
    """
    result = lot_type_service.preview_propagate(
        db,
        lot_type_id = lot_type_id,
        lot_ids     = body.lot_ids,
        mode        = body.mode,
    )
    return ApiSuccess(data=result)


@lot_types_router.post(
    "/{lot_type_id}/propagate",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def propagate_to_lots(
    lot_type_id: uuid.UUID,
    body: PropagateRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Propagate the LotType's default template to linked lots.

    mode=SAFE  — skip lots where boq_customized_at IS NOT NULL (user edited the BOQ)
    mode=FORCE — overwrite all lots regardless of customization state
    """
    result = lot_type_service.propagate_to_lots(
        db,
        lot_type_id         = lot_type_id,
        actor_id            = current_user.id,
        lot_ids             = body.lot_ids,
        mode                = body.mode,
        generate_milestones = body.generate_milestones,
    )
    return ApiSuccess(data=result, message=result.get("message", "Propagation complete."))
