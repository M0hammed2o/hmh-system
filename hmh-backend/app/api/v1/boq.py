"""BOQ routes — three-level hierarchy."""

import uuid

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from typing import Literal

from app.core.logging_config import get_logger
from app.core.upload_validation import SPREADSHEET_MIMES, validate_upload
from app.core.resource_access import get_and_check_project_resource
from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE, check_project_access
from app.models.boq import BOQItem

_boq_log = get_logger(__name__)
from app.schemas.boq import (
    BOQHeaderCreate, BOQHeaderRead, BOQHeaderUpdate,
    BOQItemCreate, BOQItemRead, BOQItemUpdate,
    BOQSectionCreate, BOQSectionRead, BOQSectionUpdate,
    SectionDeleteResult,
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
def list_boq_headers(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    check_project_access(db, current_user, project_id)
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
    check_project_access(db, current_user, project_id)
    header = boq_service.create_header(db, project_id, body, current_user.id)
    return ApiSuccess(data=BOQHeaderRead.model_validate(header), message="BOQ header created.")


@project_boq_router.get(
    "/items/search",
    response_model=ApiSuccess[list[dict]],
    dependencies=[ALL_ROLES],
)
def search_boq_items(
    project_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    q: str = Query("", description="Search term"),
):
    """
    Search MATERIAL BOQ items for a project by description.
    Deduplicates by raw_description+unit and returns up to 20 results.
    Used by the MR creation modal to look up BOQ allocations and assigned suppliers.
    """
    from app.models.enums import ItemType
    from app.models.supplier import Supplier as SupplierModel
    from sqlalchemy import true as _true

    check_project_access(db, current_user, project_id)

    q_stripped = q.strip()
    q_clause = BOQItem.raw_description.ilike(f"%{q_stripped}%") if q_stripped else _true()

    rows = (
        db.query(BOQItem)
        .filter(
            BOQItem.project_id == project_id,
            BOQItem.is_active.is_(True),
            BOQItem.item_type == ItemType.MATERIAL,
            q_clause,
        )
        .order_by(BOQItem.raw_description)
        .limit(100)
        .all()
    )

    # Pre-compute total_planned_quantity for each (description, unit) key across all lots
    from sqlalchemy import func as _func, case as _case, String as _String
    from sqlalchemy.orm import aliased as _alias

    _bi = _alias(BOQItem)
    total_qty_rows = (
        db.query(
            _func.lower(_func.trim(_bi.raw_description)).label("desc_key"),
            _func.coalesce(_func.lower(_func.trim(_func.cast(_bi.unit, _String))), "").label("unit_key"),
            _func.sum(_bi.planned_quantity).label("total_qty"),
        )
        .filter(
            _bi.project_id == project_id,
            _bi.is_active.is_(True),
            _bi.item_type == ItemType.MATERIAL,
        )
        .group_by(
            _func.lower(_func.trim(_bi.raw_description)),
            _func.coalesce(_func.lower(_func.trim(_func.cast(_bi.unit, _String))), ""),
        )
        .all()
    )
    total_qty_map: dict[tuple, float] = {
        (r.desc_key, r.unit_key): float(r.total_qty or 0)
        for r in total_qty_rows
    }

    seen: set[tuple] = set()
    results: list[dict] = []
    for item in rows:
        key = (item.raw_description.lower().strip(), (item.unit or "").lower())
        if key in seen:
            continue
        seen.add(key)

        supplier_name: str | None = None
        if item.supplier_id:
            sup = db.get(SupplierModel, item.supplier_id)
            if sup:
                supplier_name = sup.name

        total_planned = total_qty_map.get(key)

        results.append({
            "id":                     str(item.id),
            "description":            item.raw_description,
            "unit":                   item.unit,
            "planned_quantity":       float(item.planned_quantity) if item.planned_quantity is not None else None,
            "total_planned_quantity": round(total_planned, 3) if total_planned is not None else None,
            "preferred_supplier_id":  str(item.supplier_id) if item.supplier_id else None,
            "supplier_name":          supplier_name,
            "lot_id":                 str(item.lot_id) if item.lot_id else None,
            "site_id":                str(item.site_id) if item.site_id else None,
            "item_id":                str(item.item_id) if item.item_id else None,
        })

        if len(results) >= 20:
            break

    return ApiSuccess(data=results)


@project_boq_router.get(
    "/{header_id}",
    response_model=ApiSuccess[BOQHeaderRead],
    dependencies=[ALL_ROLES],
)
def get_boq_header(project_id: uuid.UUID, header_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    check_project_access(db, current_user, project_id)
    header = boq_service.get_header(db, header_id)
    return ApiSuccess(data=BOQHeaderRead.model_validate(header))


@project_boq_router.patch(
    "/{header_id}",
    response_model=ApiSuccess[BOQHeaderRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_boq_header(
    project_id: uuid.UUID, header_id: uuid.UUID, body: BOQHeaderUpdate, db: DbSession, current_user: CurrentUser
):
    check_project_access(db, current_user, project_id)
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
    check_project_access(db, current_user, project_id)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")
    validate_upload(file, SPREADSHEET_MIMES)
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
def update_boq_item(item_id: uuid.UUID, body: BOQItemUpdate, db: DbSession, current_user: CurrentUser):
    get_and_check_project_resource(db, current_user, BOQItem, item_id, "BOQ item not found.")
    item = boq_service.update_item(db, item_id, body)
    return ApiSuccess(data=BOQItemRead.model_validate(item), message="BOQ item updated.")


@boq_item_router.post(
    "/{item_id}/apply-to-all-site-lots",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def apply_item_to_all_site_lots(item_id: uuid.UUID, body: BOQItemUpdate, db: DbSession, current_user: CurrentUser):
    """
    Update this BOQ item and propagate the same changes to all lot-specific copies
    of this item within the same site.

    Peer matching key: raw_description + unit + item_type
    We intentionally do NOT filter by boq_section_id because lots generated via
    different BOQ headers (site-specific vs project-level fallback) have different
    section UUIDs even if structurally identical.

    Lot scope resolution:
    1. Lots with site_id == effective_site_id  (preferred — properly assigned)
    2. If that yields ≤1 lot, also include lots with site_id IS NULL in the same
       project (common when lots were created before the site-assignment fix).

    Returns the number of peer items updated and the number of distinct lots affected.
    """
    from app.models.lot import Lot

    get_and_check_project_resource(db, current_user, BOQItem, item_id, "BOQ item not found.")

    # Apply to the source item first
    updated = boq_service.update_item(db, item_id, body)

    # ── Resolve source lot and project ────────────────────────────────────────
    source_lot: Lot | None = None
    if updated.lot_id:
        source_lot = db.get(Lot, updated.lot_id)

    effective_site_id = updated.site_id or (source_lot.site_id if source_lot else None)
    project_id        = updated.project_id

    if not project_id:
        return ApiSuccess(
            data={"updated": 1, "lots_affected": 0, "warning": "No project context found."},
            message="Item updated. Cannot propagate without project context.",
        )

    # ── Build candidate lot ID pool ───────────────────────────────────────────
    # Start with lots that are properly assigned to the same site.
    site_lot_ids: list = []
    if effective_site_id:
        site_lot_ids = [
            row[0] for row in (
                db.query(Lot.id)
                .filter(Lot.site_id == effective_site_id, Lot.project_id == project_id)
                .all()
            )
        ]

    # If we found ≤1 lot (just the source lot or none), the other lots are likely
    # still unassigned (site_id=NULL).  Include them so the user's edit propagates.
    used_unassigned_fallback = False
    if len(site_lot_ids) <= 1:
        extra = [
            row[0] for row in (
                db.query(Lot.id)
                .filter(Lot.project_id == project_id, Lot.site_id.is_(None))
                .all()
            )
        ]
        if extra:
            # Merge, deduplicate, keep order stable
            combined = list(dict.fromkeys(site_lot_ids + extra))
            site_lot_ids = combined
            used_unassigned_fallback = True

    if len(site_lot_ids) <= 1:
        # Only the source lot — nothing else to propagate to
        return ApiSuccess(
            data={"updated": 1, "lots_affected": 0,
                  "warning": "No other lots found for this site. Assign lots to a site first."},
            message="Item updated. No other lots found in this site to propagate to.",
        )

    # ── Find peers: same content (description + unit + item_type), any site lot ─
    # Exclude the source item and exclude site-level items (lot_id IS NULL).
    desc      = updated.raw_description
    unit      = updated.unit
    item_type = updated.item_type

    peer_q = (
        db.query(BOQItem)
        .filter(
            BOQItem.lot_id.in_(site_lot_ids),
            BOQItem.raw_description == desc,
            BOQItem.is_active == True,
            BOQItem.id != item_id,
        )
    )
    # Add unit/item_type filters only when they are set, to avoid missing
    # items that have NULL unit (treat NULL == NULL as a match).
    if unit is not None:
        peer_q = peer_q.filter(BOQItem.unit == unit)
    if item_type is not None:
        peer_q = peer_q.filter(BOQItem.item_type == item_type)

    peers = peer_q.all()

    if not peers:
        reason = (
            f"No items matching description='{desc}', unit='{unit}', "
            f"type='{item_type.value if hasattr(item_type,'value') else item_type}' "
            f"were found in {len(site_lot_ids)} lot(s)."
        )
        if used_unassigned_fallback:
            reason += " (Lots are unassigned — assign lots to a site to enable site-scoped propagation.)"
        return ApiSuccess(
            data={"updated": 1, "lots_affected": 0, "warning": reason},
            message=f"Item updated. {reason}",
        )

    affected_lot_ids = {str(p.lot_id) for p in peers}
    for peer in peers:
        boq_service.update_item(db, peer.id, body)

    # Also push non-quantity fields to the site-level template item in the same header.
    # Build a body that excludes planned_quantity so individual lot quantities are preserved.
    from app.schemas.boq import BOQItemUpdate as _ItemUpd
    site_body_data = {
        k: v for k, v in body.model_dump(exclude_unset=True).items()
        if k != "planned_quantity"
    }
    if site_body_data:
        # Find the site-level template item (lot_id IS NULL) matched by
        # description + unit + item_type, scoped to the same site/project.
        if unit is not None:
            site_template_q = (
                db.query(BOQItem)
                .filter(
                    BOQItem.lot_id.is_(None),
                    BOQItem.is_active == True,
                    BOQItem.raw_description == desc,
                    BOQItem.unit == unit,
                )
            )
        else:
            site_template_q = (
                db.query(BOQItem)
                .filter(
                    BOQItem.lot_id.is_(None),
                    BOQItem.is_active == True,
                    BOQItem.raw_description == desc,
                )
            )
        if item_type is not None:
            site_template_q = site_template_q.filter(BOQItem.item_type == item_type)
        if effective_site_id:
            site_template_q = site_template_q.filter(BOQItem.site_id == effective_site_id)
        else:
            site_template_q = site_template_q.filter(BOQItem.project_id == project_id)

        site_template = site_template_q.first()
        if site_template and site_template.id != item_id:
            boq_service.update_item(db, site_template.id, _ItemUpd(**site_body_data))

    db.commit()

    warning = (
        "Some lots are still unassigned. Assign them to a site to restrict "
        "propagation to the correct site only."
    ) if used_unassigned_fallback else None

    return ApiSuccess(
        data={
            "updated":      len(peers) + 1,
            "lots_affected": len(affected_lot_ids),
            "warning":       warning,
        },
        message=(
            f"Applied to {len(peers) + 1} item(s) across {len(affected_lot_ids)} lot(s)."
            + (f" Warning: {warning}" if warning else "")
        ),
    )


@boq_item_router.post(
    "/{item_id}/push-to-lots",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
def push_site_item_to_lots(item_id: uuid.UUID, body: BOQItemUpdate, db: DbSession, current_user: CurrentUser):
    """
    For a site-level BOQ item (lot_id IS NULL), push the update to all lot-specific
    copies in the same site. Quantity is NOT pushed — each lot keeps its own quantity.
    Rate, supplier, description, unit, item_type, specification, notes are propagated.
    """
    from app.models.lot import Lot

    get_and_check_project_resource(db, current_user, BOQItem, item_id, "BOQ item not found.")

    # Update the site item itself first
    updated = boq_service.update_item(db, item_id, body)

    if updated.lot_id is not None:
        return ApiSuccess(
            data={"updated": 1, "lots_affected": 0, "warning": "Item belongs to a lot, not a site template. Use apply-to-all-site-lots instead."},
            message="Item is lot-specific. Use apply-to-all-site-lots for lot items.",
        )

    site_id    = updated.site_id
    project_id = updated.project_id

    if not project_id:
        return ApiSuccess(
            data={"updated": 1, "lots_affected": 0, "warning": "No project context found."},
            message="Site item updated. Cannot propagate without project context.",
        )

    # Collect lot IDs for this site
    if site_id:
        lot_ids = [
            row[0] for row in (
                db.query(Lot.id)
                .filter(Lot.site_id == site_id, Lot.project_id == project_id)
                .all()
            )
        ]
    else:
        lot_ids = []

    # Fallback: unassigned lots
    if not lot_ids:
        lot_ids = [
            row[0] for row in (
                db.query(Lot.id)
                .filter(Lot.project_id == project_id, Lot.site_id.is_(None))
                .all()
            )
        ]

    if not lot_ids:
        return ApiSuccess(
            data={"updated": 1, "lots_affected": 0, "warning": "No lots found for this site."},
            message="Site item updated. No lots found to propagate to.",
        )

    desc      = updated.raw_description
    unit      = updated.unit
    item_type = updated.item_type

    # Build patch without quantity — preserve lot-specific quantities
    from app.schemas.boq import BOQItemUpdate as _ItemUpd
    push_data = {
        k: v for k, v in body.model_dump(exclude_unset=True).items()
        if k != "planned_quantity"
    }

    if not push_data:
        return ApiSuccess(
            data={"updated": 1, "lots_affected": 0},
            message="Site item updated. Nothing to push to lots (no non-quantity fields changed).",
        )

    lot_peer_q = (
        db.query(BOQItem)
        .filter(
            BOQItem.lot_id.in_(lot_ids),
            BOQItem.raw_description == desc,
            BOQItem.is_active == True,
        )
    )
    if unit is not None:
        lot_peer_q = lot_peer_q.filter(BOQItem.unit == unit)
    if item_type is not None:
        lot_peer_q = lot_peer_q.filter(BOQItem.item_type == item_type)

    lot_peers = lot_peer_q.all()
    affected_lot_ids = {str(p.lot_id) for p in lot_peers}

    for peer in lot_peers:
        boq_service.update_item(db, peer.id, _ItemUpd(**push_data))

    db.commit()

    return ApiSuccess(
        data={
            "updated":       len(lot_peers) + 1,
            "lots_affected": len(affected_lot_ids),
        },
        message=f"Site item updated and pushed to {len(lot_peers)} lot item(s) across {len(affected_lot_ids)} lot(s).",
    )


@boq_item_router.delete(
    "/{item_id}",
    response_model=ApiSuccess[None],
    dependencies=[OFFICE_AND_ABOVE],
)
def delete_boq_item(item_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    get_and_check_project_resource(db, current_user, BOQItem, item_id, "BOQ item not found.")
    boq_service.delete_item(db, item_id)
    return ApiSuccess(data=None, message="BOQ item deleted.")


# ── Section delete ────────────────────────────────────────────────────────────

@boq_sections_router.patch(
    "/{section_id}",
    response_model=ApiSuccess[BOQSectionRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_section(header_id: uuid.UUID, section_id: uuid.UUID, body: BOQSectionUpdate, db: DbSession):
    section = boq_service.update_section(db, section_id, body)
    return ApiSuccess(data=BOQSectionRead.model_validate(section), message="Section updated.")


@boq_sections_router.delete(
    "/{section_id}",
    response_model=ApiSuccess[SectionDeleteResult],
    dependencies=[OFFICE_AND_ABOVE],
)
def delete_section(
    header_id: uuid.UUID,
    section_id: uuid.UUID,
    db: DbSession,
    scope: Literal["lot", "site"] = Query("lot", description="'lot' deletes only this section; 'site' deletes matching sections across all lots in the same site"),
):
    result = boq_service.delete_section_scoped(db, section_id, scope=scope)
    return ApiSuccess(data=SectionDeleteResult(**result), message=result["message"])


# ── Full BOQ (nested) ─────────────────────────────────────────────────────────

@project_boq_router.get(
    "/{header_id}/full",
    response_model=ApiSuccess[dict],
    dependencies=[ALL_ROLES],
)
def get_full_boq(project_id: uuid.UUID, header_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """Return full nested BOQ with section totals and grand total."""
    check_project_access(db, current_user, project_id)
    full = boq_service.get_full_boq(db, header_id)
    return ApiSuccess(data={
        "header": BOQHeaderRead.model_validate(full["header"]).model_dump(),
        "sections": [
            {
                "section": BOQSectionRead.model_validate(s["section"]).model_dump(),
                "items": [BOQItemRead.model_validate(i).model_dump() for i in s["items"]],
                "section_total": s["section_total"],
            }
            for s in full["sections"]
        ],
        "grand_total": full["grand_total"],
    })


# ── Mark as template ──────────────────────────────────────────────────────────

class _MarkTemplateBody(BaseModel):
    template_name: str


@project_boq_router.post(
    "/{header_id}/mark-template",
    response_model=ApiSuccess[BOQHeaderRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def mark_as_template(project_id: uuid.UUID, header_id: uuid.UUID, db: DbSession, current_user: CurrentUser, body: _MarkTemplateBody):
    check_project_access(db, current_user, project_id)
    header = boq_service.mark_as_template(db, header_id, body.template_name)
    return ApiSuccess(data=BOQHeaderRead.model_validate(header), message="BOQ marked as template.")


# ── Seed standard template ────────────────────────────────────────────────────

@project_boq_router.post(
    "/seed-standard-template",
    response_model=ApiSuccess[BOQHeaderRead],
    status_code=201,
    dependencies=[OFFICE_AND_ABOVE],
)
def seed_standard_template(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """Create the Standard Residential Unit BOQ template for this project."""
    check_project_access(db, current_user, project_id)
    header = boq_service.seed_standard_residential_template(db, project_id, current_user.id)
    return ApiSuccess(data=BOQHeaderRead.model_validate(header), message="Standard template created.")


# ── Copy BOQ ──────────────────────────────────────────────────────────────────

class _CopyBoqBody(BaseModel):
    new_version_name:  str
    target_project_id: uuid.UUID
    target_site_id:    uuid.UUID | None = None


@boq_item_router.post("/headers/{header_id}/copy", status_code=201, dependencies=[OFFICE_AND_ABOVE])
def copy_boq(header_id: uuid.UUID, body: _CopyBoqBody, db: DbSession, current_user: CurrentUser):
    """Copy a BOQ header (all sections + items) to a new header, optionally on a different site."""
    header = boq_service.copy_boq(
        db, header_id, body.target_project_id,
        body.new_version_name, body.target_site_id, current_user.id,
    )
    return ApiSuccess(data=BOQHeaderRead.model_validate(header), message="BOQ copied.")


# ── Generate lot BOQs ─────────────────────────────────────────────────────────

class _GenerateLotBoqsBody(BaseModel):
    lot_ids: list[uuid.UUID]


@boq_item_router.post("/headers/{header_id}/generate-lot-boqs", dependencies=[OFFICE_AND_ABOVE])
def generate_lot_boqs(header_id: uuid.UUID, body: _GenerateLotBoqsBody, db: DbSession):
    """Copy all site-level BOQ items to lot-specific copies for each lot in lot_ids."""
    count = boq_service.generate_lot_boqs(db, header_id, body.lot_ids)
    return ApiSuccess(data={"created": count}, message=f"{count} BOQ item(s) created for lots.")


# ── Lot BOQ summary ───────────────────────────────────────────────────────────

@boq_item_router.get("/lot/{lot_id}/summary", dependencies=[ALL_ROLES])
def lot_boq_summary(lot_id: uuid.UUID, db: DbSession):
    """Return allocated / used / remaining per material item for a lot."""
    rows = boq_service.get_lot_boq_summary(db, lot_id)
    return ApiSuccess(data=rows)


# ── BOQ adjustments ───────────────────────────────────────────────────────────

class _AdjustmentBody(BaseModel):
    adjustment_type:   str             # CREDIT | NON_SUPPLY | RETURN
    reason:            str
    project_id:        uuid.UUID | None = None
    site_id:           uuid.UUID | None = None
    lot_id:            uuid.UUID | None = None
    boq_item_id:       uuid.UUID | None = None
    item_id:           uuid.UUID | None = None
    purchase_order_id: uuid.UUID | None = None
    invoice_id:        uuid.UUID | None = None
    delivery_id:       uuid.UUID | None = None
    supplier_id:       uuid.UUID | None = None
    quantity:          float | None = None
    amount:            float | None = None
    notes:             str   | None = None


@boq_item_router.post("/adjustments", status_code=201, dependencies=[OFFICE_AND_ABOVE])
def create_adjustment(body: _AdjustmentBody, db: DbSession, current_user: CurrentUser):
    """Record a BOQ credit, non-supply, or return."""
    adj = boq_service.create_adjustment(
        db,
        adjustment_type=body.adjustment_type,
        reason=body.reason,
        created_by_id=current_user.id,
        project_id=body.project_id,
        site_id=body.site_id,
        lot_id=body.lot_id,
        boq_item_id=body.boq_item_id,
        item_id=body.item_id,
        purchase_order_id=body.purchase_order_id,
        invoice_id=body.invoice_id,
        delivery_id=body.delivery_id,
        supplier_id=body.supplier_id,
        quantity=body.quantity,
        amount=body.amount,
        notes=body.notes,
    )
    return ApiSuccess(
        data={"id": str(adj.id), "type": adj.adjustment_type},
        message="Adjustment recorded.",
    )


@boq_item_router.get("/adjustments", dependencies=[OFFICE_AND_ABOVE])
def list_adjustments(
    db: DbSession,
    project_id:      uuid.UUID | None = None,
    site_id:         uuid.UUID | None = None,
    lot_id:          uuid.UUID | None = None,
    adjustment_type: str       | None = None,
    limit:           int             = 100,
):
    """List BOQ adjustments with optional filters."""
    rows = boq_service.list_adjustments(
        db, project_id=project_id, site_id=site_id,
        lot_id=lot_id, adjustment_type=adjustment_type, limit=limit,
    )
    return ApiSuccess(data=[
        {
            "id":              str(r.id),
            "adjustment_type": r.adjustment_type,
            "quantity":        float(r.quantity) if r.quantity else None,
            "amount":          float(r.amount) if r.amount else None,
            "reason":          r.reason,
            "notes":           r.notes,
            "created_at":      r.created_at.isoformat(),
        }
        for r in rows
    ])


# ── Site / Project hierarchy endpoints ────────────────────────────────────────

@boq_item_router.get("/projects/{project_id}/master-summary", dependencies=[ALL_ROLES])
def project_master_summary(project_id: uuid.UUID, db: DbSession):
    """Roll-up of all site BOQs for a project — used for the Master Summary view."""
    data = boq_service.get_project_master_summary(db, project_id)
    return ApiSuccess(data=data)


@boq_item_router.get("/sites/{site_id}/boq-summary", dependencies=[ALL_ROLES])
def site_boq_summary(site_id: uuid.UUID, db: DbSession):
    """Site-level BOQ: sections + items where lot_id IS NULL."""
    data = boq_service.get_site_boq_summary(db, site_id)
    if not data:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Site not found.")
    return ApiSuccess(data=data)


@boq_item_router.get("/sites/{site_id}/lot-boqs", dependencies=[ALL_ROLES])
def site_lot_boqs(site_id: uuid.UUID, db: DbSession):
    """Per-lot BOQ totals for all lots attached to a site."""
    data = boq_service.get_site_lot_boqs(db, site_id)
    return ApiSuccess(data=data)


@boq_item_router.post("/sites/{site_id}/generate-lot-boqs", dependencies=[OFFICE_AND_ABOVE])
def generate_site_lot_boqs(site_id: uuid.UUID, db: DbSession):
    """
    Find the site's BOQ header and generate lot-specific BOQ items
    for every lot attached to this site.

    Search order for site-level BOQ items (lot_id IS NULL):
    1. Items where site_id == site_id  (site-specific BOQ)
    2. Items where project_id == site.project_id AND site_id IS NULL (project-level template)
    This ensures sites 2-4 work even when the BOQ was built at project level.
    """
    from fastapi import HTTPException
    from app.models.site import Site
    from app.models.lot import Lot
    from app.models.boq import BOQItem as _BI, BOQSection as _BS

    site = db.get(Site, site_id)
    if not site:
        raise HTTPException(404, "Site not found.")

    # ── 1. Try site-specific items first ─────────────────────────────────────
    section_ids = [
        row[0] for row in (
            db.query(_BI.boq_section_id)
            .filter(_BI.site_id == site_id, _BI.lot_id.is_(None), _BI.is_active == True)
            .distinct()
            .all()
        )
    ]

    # ── 2. Fall back to project-level (site_id IS NULL) ───────────────────────
    if not section_ids:
        section_ids = [
            row[0] for row in (
                db.query(_BI.boq_section_id)
                .filter(
                    _BI.project_id == site.project_id,
                    _BI.site_id.is_(None),
                    _BI.lot_id.is_(None),
                    _BI.is_active == True,
                )
                .distinct()
                .all()
            )
        ]

    if not section_ids:
        # ── Fallback: check if lots already have BOQ items from template clone ──
        # clone_template_to_lots creates lot-level items directly; if the user
        # applies the template and then immediately clicks Generate Lot BOQs,
        # the site-level BOQ may not exist yet (older clones) but the lots
        # already have full BOQ item sets — nothing needs to be done.
        from app.models.lot import Lot as _Lot
        site_lot_ids = [
            row[0] for row in db.query(_Lot.id)
            .filter(_Lot.site_id == site_id, _Lot.project_id == site.project_id)
            .all()
        ]
        lots_already_have_boq = bool(
            db.query(_BI.id)
            .filter(_BI.lot_id.in_(site_lot_ids), _BI.is_active == True)
            .first()
        ) if site_lot_ids else False

        if lots_already_have_boq:
            return ApiSuccess(
                data={"created": 0, "lots_with_existing_boq": len(site_lot_ids)},
                message=(
                    "Lots already have BOQ items applied from the template clone. "
                    "No site-level BOQ was needed — lot BOQs are up to date."
                ),
            )

        raise HTTPException(
            400,
            "No site-level BOQ found for this site or its project. "
            "Apply a BOQ template first using the BOQ Templates page, "
            "or create a site BOQ manually before clicking Generate Lot BOQs.",
        )

    header_row = db.query(_BS.boq_header_id).filter(_BS.id.in_(section_ids)).first()
    if not header_row:
        raise HTTPException(400, "Could not resolve a BOQ header for this site.")

    site_lots = [
        row[0] for row in (
            db.query(Lot.id)
            .filter(Lot.site_id == site_id, Lot.project_id == site.project_id)
            .all()
        )
    ]

    # ── Fallback: use unassigned lots (site_id IS NULL) ───────────────────────
    # This is a safety net for projects created before site assignment was enforced.
    # It is intentionally restricted to NULL-site lots only — it does NOT pull lots
    # assigned to other sites, so Site 2/3/4 pools cannot contaminate each other.
    used_fallback = False
    unassigned_lot_ids: list[uuid.UUID] = []

    if site_lots:
        lot_ids = site_lots
    else:
        unassigned_lot_ids = [
            row[0] for row in (
                db.query(Lot.id)
                .filter(Lot.project_id == site.project_id, Lot.site_id.is_(None))
                .all()
            )
        ]
        if unassigned_lot_ids:
            lot_ids       = unassigned_lot_ids
            used_fallback = True
            _boq_log.warning("boq site=%s no lots with matching site_id — fallback to %d unassigned lots",
                              site_id, len(unassigned_lot_ids))
        else:
            lot_ids = []

    if not lot_ids:
        raise HTTPException(
            400,
            "No lots found for this site. Create lots using the Lots Generator and select "
            "this site, or assign existing lots to this site before generating.",
        )

    count = boq_service.generate_lot_boqs(db, header_row[0], lot_ids)

    warning = (
        f"Warning: {len(unassigned_lot_ids)} lot(s) had no site assignment. "
        "They were used as a fallback and BOQ items were generated for them. "
        "Assign these lots to the correct site to prevent them being re-used by other sites."
    ) if used_fallback else None

    return ApiSuccess(
        data={
            "created":         count,
            "lot_count":       len(lot_ids),
            "used_fallback":   used_fallback,
            "unassigned_lots": len(unassigned_lot_ids) if used_fallback else 0,
            "warning":         warning,
        },
        message=(
            warning if warning
            else f"{count} BOQ item(s) generated across {len(lot_ids)} lot(s)."
        ),
    )


@boq_item_router.post("/lots/{lot_id}/reset-to-site-boq", dependencies=[OFFICE_AND_ABOVE])
def reset_lot_to_site_boq(lot_id: uuid.UUID, db: DbSession):
    """Delete lot-specific BOQ items and regenerate from the site BOQ."""
    count = boq_service.reset_lot_to_site_boq(db, lot_id)
    return ApiSuccess(
        data={"created": count},
        message=f"Lot BOQ reset. {count} item(s) restored from site BOQ.",
    )
