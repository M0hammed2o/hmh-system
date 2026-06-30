"""
Site Dashboard API — real-time BOQ allocation vs delivery vs usage tracking per lot.

GET  /site-dashboard/{site_id}/lots/{lot_id}/material-summary
GET  /site-dashboard/{site_id}/lots/{lot_id}/activity
"""

import os
import re as _re
import uuid

from fastapi import APIRouter, File, Form, UploadFile
from sqlalchemy import func

from app.core.logging_config import get_logger
from app.core.upload_validation import PHOTO_MIMES, validate_upload
from app.dependencies import ALL_ROLES, CurrentUser, OFFICE_AND_ABOVE, DbSession, check_project_access

_log = get_logger(__name__)
from app.models.boq import BOQItem
from app.models.enums import ItemType, MovementType
from app.models.stock import StockLedger
from app.schemas.common import ApiSuccess

router = APIRouter(prefix="/site-dashboard", tags=["site-dashboard"])
project_lot_router = APIRouter(prefix="/projects/{project_id}/lots", tags=["site-dashboard"])


# ── Material summary ──────────────────────────────────────────────────────────

@router.get("/{site_id}/lots/{lot_id}/material-summary", dependencies=[ALL_ROLES])
def lot_material_summary(site_id: uuid.UUID, lot_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    Per-item BOQ summary: allocated vs delivered vs used vs remaining.

    Data source priority:
      1. BOQItem rows where lot_id = <lot_id>   (lot-specific BOQ)
      2. BOQItem rows where site_id = <site_id> and lot_id IS NULL  (site template)

    Unlike allocation_service.get_all_lot_allocations(), this endpoint
    does NOT filter by item_id IS NOT NULL — so template items without
    a catalog link (item_id = NULL) are included correctly.

    Stock matching:
      - If item_id is set  → match StockLedger by item_id + lot_id
      - If item_id is NULL → match StockLedger by boq_item_id + lot_id
    """
    from app.models.lot import Lot
    from app.models.site import Site as _Site
    _site = db.get(_Site, site_id)
    if _site:
        check_project_access(db, current_user, _site.project_id)

    # ── 1. Fetch BOQ items (MATERIAL type only — Labour/Plant never in warehouse) ─
    boq_items = (
        db.query(BOQItem)
        .filter(
            BOQItem.lot_id    == lot_id,
            BOQItem.is_active == True,
            BOQItem.item_type == ItemType.MATERIAL,
        )
        .all()
    )

    # ── 2. Fall back to site-level template if lot has no BOQ items ───────────
    fallback = False
    if not boq_items:
        lot = db.get(Lot, lot_id)
        if lot and lot.site_id:
            boq_items = (
                db.query(BOQItem)
                .filter(
                    BOQItem.site_id   == lot.site_id,
                    BOQItem.lot_id.is_(None),
                    BOQItem.is_active == True,
                    BOQItem.item_type == ItemType.MATERIAL,
                )
                .all()
            )
            fallback = bool(boq_items)

    # ── 3. De-duplicate by (normalized_description, unit) ───────────────────
    # Duplicates arise when a template is applied to lots AND generate_lot_boqs
    # is also called, inserting two copies of each item for the same lot, OR
    # when the same material is allocated across multiple BOQ sections/milestones.
    # Whitespace is normalised so "Ceiling / Doors" == "Ceiling/Doors".
    # Unit is lowercased so "Rolls" == "rolls".
    # Sort: catalog-linked items (item_id set) win over non-catalog ones so the
    # item_id stock path is never lost.  Among equals, higher planned_qty wins.
    # Discarded aliases are tracked (boq_item_id → canonical BOQItem object) so
    # their stock is folded into the canonical using the right lookup dict.
    # Alias planned quantities are summed into canonical so the row shows the
    # TOTAL allocation across all sections (e.g. 26+13=39, not just 26).
    seen_keys: dict = {}              # normalized_key → canonical BOQItem
    boq_id_to_canonical: dict = {}   # discarded_boq_item_id → canonical BOQItem
    canonical_extra_qty: dict = {}   # canonical BOQItem.id → extra qty from aliases
    unique_boq_items = []
    for bi in sorted(
        boq_items,
        key=lambda x: (1 if x.item_id else 0, float(x.planned_quantity or 0)),
        reverse=True,
    ):
        key = (
            _re.sub(r"\s+", " ", (bi.raw_description or "").lower().strip()),
            (bi.unit or "").lower(),  # normalise unit case: "Rolls" == "rolls"
        )
        if key not in seen_keys:
            seen_keys[key] = bi
            unique_boq_items.append(bi)
        else:
            canonical = seen_keys[key]
            if bi.id:
                boq_id_to_canonical[bi.id] = canonical
            # Accumulate alias planned qty so canonical shows total allocation
            canonical_extra_qty[canonical.id] = (
                canonical_extra_qty.get(canonical.id, 0.0) + float(bi.planned_quantity or 0)
            )
    boq_items = unique_boq_items

    # ── 4. Batch-load all StockLedger aggregates in 4 queries (replaces N+1) ────
    from app.models.boq import BOQSection
    from app.models.item import Item
    from app.models.supplier import Supplier as _Sup

    item_ids          = [bi.item_id for bi in boq_items if bi.item_id]
    boq_item_ids      = [bi.id      for bi in boq_items if not bi.item_id]
    # Include alias IDs so stock recorded against discarded duplicates is captured
    all_boq_query_ids = list(set(boq_item_ids + list(boq_id_to_canonical.keys())))

    # Batch-load sections for section_name grouping
    section_ids = list(set(bi.boq_section_id for bi in boq_items))
    sections_map: dict = {}
    if section_ids:
        secs = db.query(BOQSection).filter(BOQSection.id.in_(section_ids)).all()
        sections_map = {s.id: s for s in secs}

    # delivered qty keyed by item_id — counts DELIVERY_RECEIVED at lot level
    # (direct delivery to lot) AND TRANSFER_IN at lot level (warehouse dispatch to lot).
    # This ensures both workflows are captured: old direct-to-lot and new warehouse flow.
    delivered_by_item: dict = {}
    if item_ids:
        rows = (
            db.query(StockLedger.item_id, func.coalesce(func.sum(StockLedger.quantity_in), 0))
            .filter(
                StockLedger.lot_id        == lot_id,
                StockLedger.item_id.in_(item_ids),
                StockLedger.movement_type.in_([
                    MovementType.DELIVERY_RECEIVED,
                    MovementType.TRANSFER_IN,
                ]),
            )
            .group_by(StockLedger.item_id)
            .all()
        )
        delivered_by_item = {r[0]: float(r[1]) for r in rows}

    # used qty keyed by item_id (catalog path)
    used_by_item: dict = {}
    if item_ids:
        rows = (
            db.query(StockLedger.item_id, func.coalesce(func.sum(StockLedger.quantity_out), 0))
            .filter(StockLedger.lot_id == lot_id, StockLedger.item_id.in_(item_ids))
            .group_by(StockLedger.item_id)
            .all()
        )
        used_by_item = {r[0]: float(r[1]) for r in rows}

    # delivered qty keyed by boq_item_id (template / non-catalog path)
    delivered_by_boq: dict = {}
    if all_boq_query_ids:
        rows = (
            db.query(StockLedger.boq_item_id, func.coalesce(func.sum(StockLedger.quantity_in), 0))
            .filter(
                StockLedger.lot_id        == lot_id,
                StockLedger.boq_item_id.in_(all_boq_query_ids),
                StockLedger.movement_type.in_([
                    MovementType.DELIVERY_RECEIVED,
                    MovementType.TRANSFER_IN,
                ]),
            )
            .group_by(StockLedger.boq_item_id)
            .all()
        )
        delivered_by_boq = {r[0]: float(r[1]) for r in rows}

    # used qty keyed by boq_item_id (template / non-catalog path)
    used_by_boq: dict = {}
    if all_boq_query_ids:
        rows = (
            db.query(StockLedger.boq_item_id, func.coalesce(func.sum(StockLedger.quantity_out), 0))
            .filter(StockLedger.lot_id == lot_id, StockLedger.boq_item_id.in_(all_boq_query_ids))
            .group_by(StockLedger.boq_item_id)
            .all()
        )
        used_by_boq = {r[0]: float(r[1]) for r in rows}

    # Fold alias stock into the canonical item via the correct lookup dict.
    # Canonical with item_id  → item_id path (delivered_by_item / used_by_item).
    # Canonical without item_id → boq_item_id path (delivered_by_boq / used_by_boq).
    for alias_id, canonical_bi in boq_id_to_canonical.items():
        alias_del  = delivered_by_boq.pop(alias_id, 0.0)
        alias_used = used_by_boq.pop(alias_id, 0.0)
        if canonical_bi.item_id:
            delivered_by_item[canonical_bi.item_id] = (
                delivered_by_item.get(canonical_bi.item_id, 0.0) + alias_del
            )
            used_by_item[canonical_bi.item_id] = (
                used_by_item.get(canonical_bi.item_id, 0.0) + alias_used
            )
        else:
            delivered_by_boq[canonical_bi.id] = (
                delivered_by_boq.get(canonical_bi.id, 0.0) + alias_del
            )
            used_by_boq[canonical_bi.id] = (
                used_by_boq.get(canonical_bi.id, 0.0) + alias_used
            )

    # Batch-load catalog items and suppliers (replaces db.get() inside the loop)
    supplier_ids = [bi.supplier_id for bi in boq_items if bi.supplier_id]
    items_map: dict = {}
    if item_ids:
        items_map = {i.id: i for i in db.query(Item).filter(Item.id.in_(item_ids)).all()}
    suppliers_map: dict = {}
    if supplier_ids:
        suppliers_map = {s.id: s for s in db.query(_Sup).filter(_Sup.id.in_(supplier_ids)).all()}

    # ── 5. Build summary rows (pure Python — zero additional DB queries) ────────
    result = []
    for bi in boq_items:
        # Sum canonical qty + any alias planned qtys (same material in other sections)
        allocated = float(bi.planned_quantity or 0) + canonical_extra_qty.get(bi.id, 0.0)

        if bi.item_id:
            delivered = delivered_by_item.get(bi.item_id, 0.0)
            used      = used_by_item.get(bi.item_id, 0.0)
        else:
            delivered = delivered_by_boq.get(bi.id, 0.0)
            used      = used_by_boq.get(bi.id, 0.0)

        remaining = max(0.0, allocated - used)
        over      = max(0.0, used - allocated)
        is_over   = allocated > 0 and used > allocated

        if is_over:
            status = "OVER_BOQ"
        elif allocated > 0 and remaining < allocated * 0.15:
            status = "LOW"
        elif used > 0 and delivered > 0 and used > delivered:
            status = "STOCK_ISSUE"
        else:
            status = "OK"

        description = bi.raw_description
        unit        = bi.unit
        cat_item    = items_map.get(bi.item_id) if bi.item_id else None
        if cat_item:
            description = cat_item.name
            unit        = cat_item.default_unit or bi.unit

        supplier_id   = str(bi.supplier_id) if bi.supplier_id else None
        supplier_name = None
        sup = suppliers_map.get(bi.supplier_id) if bi.supplier_id else None
        if sup:
            supplier_name = sup.name

        section    = sections_map.get(bi.boq_section_id)
        result.append({
            "boq_item_id":        str(bi.id),
            "item_id":            str(bi.item_id) if bi.item_id else None,
            "description":        description,
            "unit":               unit,
            "boq_allocated_qty":  round(allocated, 3),
            "delivered_qty":      round(delivered, 3),
            "used_qty":           round(used, 3),
            "remaining_qty":      round(remaining, 3),
            "over_qty":           round(over, 3),
            "status":             status,
            "from_site_template": fallback,
            "supplier_id":        supplier_id,
            "supplier_name":      supplier_name,
            # BOQ section / milestone grouping
            "section_name":       section.section_name if section else None,
            "section_order":      section.sequence_order if section else 0,
            # BOQ price columns
            "planned_rate":       float(bi.planned_rate) if bi.planned_rate is not None else None,
            "planned_total":      float(bi.planned_total) if bi.planned_total is not None else None,
            "item_type":          bi.item_type.value if bi.item_type else "MATERIAL",
        })

    return ApiSuccess(data=result)


# ── Activity feed ─────────────────────────────────────────────────────────────

@router.get("/{site_id}/lots/{lot_id}/activity", dependencies=[ALL_ROLES])
def lot_activity(site_id: uuid.UUID, lot_id: uuid.UUID, db: DbSession, current_user: CurrentUser, limit: int = 20):
    """
    Recent activity for a site/lot — deliveries, usage, alerts, stage updates.
    Returns a unified list sorted newest-first.
    """
    from app.models.delivery import Delivery
    from app.models.alert import SystemAlert
    from app.models.item import Item
    from app.models.stage import ProjectStageStatus
    from app.models.site import Site as _Site2
    _site2 = db.get(_Site2, site_id)
    if _site2:
        check_project_access(db, current_user, _site2.project_id)

    activities = []

    # Deliveries
    for d in (
        db.query(Delivery)
        .filter(Delivery.site_id == site_id)
        .order_by(Delivery.delivery_date.desc())
        .limit(8)
        .all()
    ):
        activities.append({
            "id":          str(d.id),
            "type":        "delivery",
            "record_id":   str(d.id),
            "record_type": "delivery",
            "title":       f"Delivery: {d.delivery_number or str(d.id)[:8]}",
            "date":        d.delivery_date.isoformat() if d.delivery_date else None,
            "status":      d.delivery_status.value if d.delivery_status else None,
            "photo_url":   d.delivery_note_image_url or None,
        })

    # Usage ledger entries for this lot
    for row in (
        db.query(StockLedger)
        .filter(
            StockLedger.site_id        == site_id,
            StockLedger.lot_id         == lot_id,
            StockLedger.movement_type  == MovementType.USAGE,
        )
        .order_by(StockLedger.movement_date.desc())
        .limit(8)
        .all()
    ):
        item = db.get(Item, row.item_id)
        item_name = item.name if item else "Unknown material"
        qty  = row.quantity_out
        unit = row.unit or ""

        # Evidence photo stored in notes as "comments | evidence:/uploads/..."
        photo_url = None
        if row.notes:
            for part in row.notes.split(" | "):
                part = part.strip()
                if part.startswith("evidence:"):
                    photo_url = part[len("evidence:"):].strip()
                    break

        activities.append({
            "id":          str(row.id),
            "type":        "usage",
            "record_id":   str(row.id),
            "record_type": "usage",
            "title":       f"Used: {item_name}",
            "subtitle":    f"{qty:.3g} {unit}".strip(),
            "date":        row.movement_date.isoformat() if row.movement_date else None,
            "status":      None,
            "photo_url":   photo_url,
        })

    # Alerts for this site
    for a in (
        db.query(SystemAlert)
        .filter(SystemAlert.site_id == site_id)
        .order_by(SystemAlert.created_at.desc())
        .limit(8)
        .all()
    ):
        activities.append({
            "type":     "alert",
            "title":    a.title,
            "date":     a.created_at.isoformat(),
            "status":   a.severity.value if a.severity else None,
            "severity": a.severity.value if a.severity else None,
        })

    # Stage updates for this lot
    from sqlalchemy.orm import joinedload as _jl
    from app.models.stage import StageMaster as _SM
    for s in (
        db.query(ProjectStageStatus)
        .options(_jl(ProjectStageStatus.stage))
        .filter(ProjectStageStatus.lot_id == lot_id)
        .order_by(ProjectStageStatus.updated_at.desc())
        .limit(4)
        .all()
    ):
        stage_name = s.stage.name if s.stage else "Unknown"

        # Evidence photo is embedded in notes as: "evidence:/uploads/... | rest of notes"
        photo_url = None
        if s.notes and s.notes.startswith("evidence:"):
            photo_url = s.notes.split(" | ", 1)[0].replace("evidence:", "").strip()

        activities.append({
            "id":          str(s.id),
            "type":        "stage",
            "record_id":   str(s.id),
            "record_type": "stage",
            "title":       f"Stage: {stage_name} → {s.status.value if s.status else '?'}",
            "date":        s.updated_at.isoformat() if s.updated_at else None,
            "status":      s.status.value if s.status else None,
            "photo_url":   photo_url,
        })

    activities.sort(key=lambda x: x.get("date") or "", reverse=True)
    return ApiSuccess(data=activities[:limit])


# ── Replace evidence photo ────────────────────────────────────────────────────

@router.post(
    "/replace-photo",
    response_model=ApiSuccess[dict],
    dependencies=[OFFICE_AND_ABOVE],
)
async def replace_evidence_photo(
    db: DbSession,
    record_type: str = Form(...),   # "delivery" | "stage" | "usage"
    record_id: str   = Form(...),   # UUID of the record to update
    photo: UploadFile = File(...),
):
    """
    Replace (or add) an evidence photo for an existing delivery, stage update,
    or material usage record.

    Saves the file under UPLOAD_DIR using the same directory structure as the
    original upload endpoints, then updates the correct DB field:
      delivery → Delivery.delivery_note_image_url
      stage    → ProjectStageStatus.notes  (evidence: token)
      usage    → StockLedger.notes + linked UsageLog.comments
    """
    import uuid as _uuid
    from app.core.config import settings as _s
    from fastapi import HTTPException

    # ── Save file ─────────────────────────────────────────────────────────────
    subdir_map = {
        "delivery": ("delivery_notes",),
        "stage":    ("site_evidence", "stages"),
        "usage":    ("site_evidence", "usage"),
    }
    if record_type not in subdir_map:
        raise HTTPException(422, f"Unsupported record_type: {record_type!r}")

    validate_upload(photo, PHOTO_MIMES)
    ext     = os.path.splitext(photo.filename or "photo")[1] or ".jpg"
    fname   = f"{_uuid.uuid4().hex}{ext}"
    save_dir = os.path.join(_s.UPLOAD_DIR, *subdir_map[record_type])
    os.makedirs(save_dir, exist_ok=True)
    content  = await photo.read()
    with open(os.path.join(save_dir, fname), "wb") as fh:
        fh.write(content)

    url_path = "/" + "/".join(["uploads", *subdir_map[record_type], fname])
    _log.info("replace_photo type=%s id=%s path=%s size=%d", record_type, record_id, url_path, len(content))

    # ── Update DB record ──────────────────────────────────────────────────────
    rid = _uuid.UUID(record_id)

    if record_type == "delivery":
        from app.models.delivery import Delivery
        obj = db.get(Delivery, rid)
        if not obj:
            raise HTTPException(404, "Delivery not found.")
        obj.delivery_note_image_url = url_path

    elif record_type == "stage":
        from app.models.stage import ProjectStageStatus
        obj = db.get(ProjectStageStatus, rid)
        if not obj:
            raise HTTPException(404, "Stage status record not found.")
        old_notes = obj.notes or ""
        # Replace existing evidence: token, or prepend a new one
        if "evidence:" in old_notes:
            parts = old_notes.split(" | ")
            parts = [p for p in parts if not p.strip().startswith("evidence:")]
            parts.insert(0, f"evidence:{url_path}")
            obj.notes = " | ".join(parts)
        else:
            obj.notes = f"evidence:{url_path}" + (f" | {old_notes}" if old_notes else "")

    elif record_type == "usage":
        from app.models.stock import StockLedger, UsageLog
        ledger = db.get(StockLedger, rid)
        if not ledger:
            raise HTTPException(404, "Usage record not found.")

        def _replace_notes(notes: str | None) -> str:
            if not notes:
                return f"evidence:{url_path}"
            parts = [p for p in notes.split(" | ") if not p.strip().startswith("evidence:")]
            parts.append(f"evidence:{url_path}")
            return " | ".join(parts)

        ledger.notes = _replace_notes(ledger.notes)

        # Also update the linked UsageLog if available
        if ledger.reference_type == "usage" and ledger.reference_id:
            usage_log = db.get(UsageLog, ledger.reference_id)
            if usage_log:
                usage_log.comments = _replace_notes(usage_log.comments)

    db.commit()
    return ApiSuccess(data={"photo_url": url_path}, message="Photo replaced.")


# ── Project-level lot material summary (Phase 3J finalization) ───────────────
# Works for both site-based lots and freestanding lots (site_id=None).
# Uses the Phase 3B warehouse model: deliveries go to project warehouse,
# then items are TRANSFERRED to lots.

@project_lot_router.get(
    "/{lot_id}/material-summary",
    dependencies=[ALL_ROLES],
)
def project_lot_material_summary(project_id: uuid.UUID, lot_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    Per-item material summary for a lot, compatible with Phase 3B warehouse model.

    Phase 3B routes deliveries to the Project Warehouse (site_id=NULL, lot_id=NULL).
    Stock reaches lots only via TRANSFER_IN movements.

    Column mapping:
      boq_allocated_qty  = BOQ planned quantity
      delivered_qty      = stock dispatched from Project Warehouse to this lot (TRANSFER_IN)
      used_qty           = recorded usage at lot level (quantity_out in stock_ledger)
      remaining_qty      = delivered_qty - used_qty
      over_qty           = max(0, used - allocated)
      shortfall_qty      = max(0, boq - delivered)

    Falls back to project-level master BOQ for freestanding lots (site_id=None).
    """
    from app.models.lot import Lot
    from app.models.item import Item

    check_project_access(db, current_user, project_id)

    lot = db.get(Lot, lot_id)
    if not lot or lot.project_id != project_id:
        from fastapi import HTTPException
        raise HTTPException(404, "Lot not found in this project.")

    # ── 1. Fetch BOQ items for this lot (MATERIAL only) ──────────────────────
    boq_items = (
        db.query(BOQItem)
        .filter(
            BOQItem.lot_id    == lot_id,
            BOQItem.is_active == True,
            BOQItem.item_type == ItemType.MATERIAL,
        )
        .all()
    )

    # ── 2. Fall back: freestanding lot → use project-level master (site_id=NULL, lot_id=NULL)
    #                 site lot          → use site master (site_id=X, lot_id=NULL)
    fallback = False
    if not boq_items:
        if lot.site_id:
            # Site lot — use site template
            boq_items = (
                db.query(BOQItem)
                .filter(
                    BOQItem.project_id == project_id,
                    BOQItem.site_id    == lot.site_id,
                    BOQItem.lot_id.is_(None),
                    BOQItem.is_active  == True,
                    BOQItem.item_type  == ItemType.MATERIAL,
                )
                .all()
            )
        else:
            # Freestanding lot — use project-level master
            boq_items = (
                db.query(BOQItem)
                .filter(
                    BOQItem.project_id  == project_id,
                    BOQItem.site_id.is_(None),
                    BOQItem.lot_id.is_(None),
                    BOQItem.is_active   == True,
                    BOQItem.item_type   == ItemType.MATERIAL,
                )
                .all()
            )
        fallback = bool(boq_items)

    # ── 3. De-duplicate by description+unit ──────────────────────────────────
    # Normalise unit case so "Rolls" == "rolls". Catalog-linked items win over
    # non-catalog; higher planned_qty wins among equals.
    # Alias planned quantities are summed so the canonical row shows the TOTAL
    # allocation across all sections (e.g. 26+13=39, not just 26).
    seen_keys_p: dict = {}
    boq_id_to_canonical_p: dict = {}   # alias boq_item_id → canonical BOQItem
    canonical_extra_qty_p: dict = {}   # canonical BOQItem.id → extra qty from aliases
    unique_items = []
    for bi in sorted(
        boq_items,
        key=lambda x: (1 if x.item_id else 0, float(x.planned_quantity or 0)),
        reverse=True,
    ):
        key = (
            _re.sub(r"\s+", " ", (bi.raw_description or "").lower().strip()),
            (bi.unit or "").lower(),
        )
        if key not in seen_keys_p:
            seen_keys_p[key] = bi
            unique_items.append(bi)
        else:
            canonical = seen_keys_p[key]
            if bi.id:
                boq_id_to_canonical_p[bi.id] = canonical
            canonical_extra_qty_p[canonical.id] = (
                canonical_extra_qty_p.get(canonical.id, 0.0) + float(bi.planned_quantity or 0)
            )
    boq_items = unique_items

    # ── 4. Build summary rows ─────────────────────────────────────────────────
    result = []
    for bi in boq_items:
        # Sum canonical qty + any alias planned qtys (same material in other sections)
        allocated = float(bi.planned_quantity or 0) + canonical_extra_qty_p.get(bi.id, 0.0)

        # Collect all boq_item_ids that map to this canonical (for non-catalog stock lookup)
        alias_boq_ids = [alias_id for alias_id, c in boq_id_to_canonical_p.items() if c.id == bi.id]

        if bi.item_id:
            # Phase 3B: "delivered to lot" = TRANSFER_IN at lot level
            delivered = float(
                db.query(func.coalesce(func.sum(StockLedger.quantity_in), 0))
                .filter(
                    StockLedger.project_id    == project_id,
                    StockLedger.lot_id        == lot_id,
                    StockLedger.item_id       == bi.item_id,
                    StockLedger.movement_type == MovementType.TRANSFER_IN,
                )
                .scalar() or 0
            )
            used = float(
                db.query(func.coalesce(func.sum(StockLedger.quantity_out), 0))
                .filter(
                    StockLedger.project_id == project_id,
                    StockLedger.lot_id     == lot_id,
                    StockLedger.item_id    == bi.item_id,
                )
                .scalar() or 0
            )
        else:
            # No catalog link — match by boq_item_id (canonical + all aliases)
            all_boq_ids = [bi.id] + alias_boq_ids
            delivered = float(
                db.query(func.coalesce(func.sum(StockLedger.quantity_in), 0))
                .filter(
                    StockLedger.project_id    == project_id,
                    StockLedger.lot_id        == lot_id,
                    StockLedger.boq_item_id.in_(all_boq_ids),
                    StockLedger.movement_type == MovementType.TRANSFER_IN,
                )
                .scalar() or 0
            )
            used = float(
                db.query(func.coalesce(func.sum(StockLedger.quantity_out), 0))
                .filter(
                    StockLedger.project_id  == project_id,
                    StockLedger.lot_id      == lot_id,
                    StockLedger.boq_item_id.in_(all_boq_ids),
                )
                .scalar() or 0
            )

        remaining    = max(0.0, delivered - used)
        over         = max(0.0, used - allocated)
        shortfall    = max(0.0, allocated - delivered)
        is_short     = shortfall > 0 and allocated > 0
        is_over      = allocated > 0 and used > allocated

        if is_over:
            status = "OVER_BOQ"
        elif is_short and delivered == 0:
            status = "STOCK_ISSUE"
        elif is_short:
            status = "LOW"
        else:
            status = "OK"

        description = bi.raw_description
        unit        = bi.unit
        if bi.item_id:
            cat_item = db.get(Item, bi.item_id)
            if cat_item:
                description = cat_item.name
                unit        = cat_item.default_unit or bi.unit

        supplier_id = str(bi.supplier_id) if bi.supplier_id else None
        supplier_name = None
        if bi.supplier_id:
            from app.models.supplier import Supplier as _Sup
            sup = db.get(_Sup, bi.supplier_id)
            if sup:
                supplier_name = sup.name

        result.append({
            "boq_item_id":       str(bi.id),
            "item_id":           str(bi.item_id) if bi.item_id else None,
            "description":       description,
            "unit":              unit,
            "boq_allocated_qty": round(allocated, 3),
            "delivered_qty":     round(delivered, 3),   # dispatched to this lot
            "used_qty":          round(used, 3),
            "remaining_qty":     round(remaining, 3),
            "over_qty":          round(over, 3),
            "shortfall_qty":     round(shortfall, 3),
            "status":            status,
            "from_site_template": fallback,
            "supplier_id":       supplier_id,
            "supplier_name":     supplier_name,
        })

    return ApiSuccess(data=result)
