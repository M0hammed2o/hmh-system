"""Delivery routes."""

import base64
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.upload_validation import DOCUMENT_MIMES, validate_upload
from app.core.resource_access import get_and_check_project_resource, secure_project_lookup
from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE, check_project_access
from app.models.delivery import Delivery

logger = get_logger(__name__)
from app.models.enums import DeliveryDestination
from app.schemas.common import ApiSuccess
from app.schemas.delivery import DeliveryCreate, DeliveryRead, DeliveryUpdate
from app.services import delivery_service

project_delivery_router = APIRouter(
    prefix="/projects/{project_id}/deliveries",
    tags=["deliveries"],
)
delivery_router = APIRouter(prefix="/deliveries", tags=["deliveries"])


@project_delivery_router.get(
    "/",
    response_model=ApiSuccess[list[DeliveryRead]],
    dependencies=[ALL_ROLES],
)
def list_deliveries(
    project_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    check_project_access(db, current_user, project_id)
    deliveries = delivery_service.list_deliveries(db, project_id, limit=limit, offset=offset)
    return ApiSuccess(data=[DeliveryRead.model_validate(d) for d in deliveries])


@project_delivery_router.post(
    "/",
    response_model=ApiSuccess[DeliveryRead],
    status_code=201,
    dependencies=[ALL_ROLES],
)
def create_delivery(
    project_id: uuid.UUID,
    body: DeliveryCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    check_project_access(db, current_user, project_id)
    delivery = delivery_service.create_delivery(db, project_id, body, current_user.id)
    return ApiSuccess(
        data=DeliveryRead.model_validate(delivery),
        message="Delivery recorded.",
    )


@delivery_router.get(
    "/{delivery_id}",
    response_model=ApiSuccess[DeliveryRead],
    dependencies=[ALL_ROLES],
)
def get_delivery(delivery_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    delivery = secure_project_lookup(delivery_service.get_delivery(db, delivery_id), db, current_user)
    return ApiSuccess(data=DeliveryRead.model_validate(delivery))


@delivery_router.patch(
    "/{delivery_id}",
    response_model=ApiSuccess[DeliveryRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def update_delivery(delivery_id: uuid.UUID, body: DeliveryUpdate, db: DbSession, current_user: CurrentUser):
    get_and_check_project_resource(db, current_user, Delivery, delivery_id, "Delivery not found.")
    delivery = delivery_service.update_delivery(db, delivery_id, body)
    return ApiSuccess(data=DeliveryRead.model_validate(delivery), message="Delivery updated.")


class ReceiveStockBody(BaseModel):
    destination: DeliveryDestination
    lot_id: Optional[uuid.UUID] = None
    overrun_reason: Optional[str] = None
    items_received: Optional[list[dict]] = None  # [{delivery_item_id, quantity_received}]


@delivery_router.post(
    "/{delivery_id}/receive-stock",
    response_model=ApiSuccess[DeliveryRead],
    dependencies=[ALL_ROLES],
)
def receive_stock(delivery_id: uuid.UUID, body: ReceiveStockBody, db: DbSession, current_user: CurrentUser):
    get_and_check_project_resource(db, current_user, Delivery, delivery_id, "Delivery not found.")
    from app.services.delivery_service import receive_stock as _receive
    delivery = _receive(
        db, delivery_id,
        destination=body.destination,
        actor_id=current_user.id,
        lot_id=body.lot_id,
        overrun_reason=body.overrun_reason,
        items_received=body.items_received,
    )
    return ApiSuccess(data=DeliveryRead.model_validate(delivery), message="Stock received.")


# ── Unified receive-with-document ─────────────────────────────────────────────

@delivery_router.post(
    "/receive-with-document",
    status_code=201,
    dependencies=[ALL_ROLES],
)
async def receive_delivery_with_document(
    db:             DbSession,
    current_user:   CurrentUser,
    project_id:     str           = Form(...),
    site_id:        str           = Form(...),
    supplier_id:    str           = Form(...),
    delivery_note_number: str     = Form(""),
    purchase_order_id: Optional[str] = Form(None),
    lot_id:         Optional[str] = Form(None),
    destination:    str           = Form("SITE_STORE"),
    items_json:     str           = Form("[]"),
    driver_name:    Optional[str] = Form(None),
    driver_signature: Optional[str] = Form(None),
    receiver_name:  Optional[str] = Form(None),
    receiver_signature: Optional[str] = Form(None),
    comments:       Optional[str] = Form(None),
    delivery_note_file: Optional[UploadFile] = File(None),
):
    """
    Unified delivery-receive endpoint.

    Creates a real Delivery + DeliveryItem records.
    Accepts an optional file (photo / PDF of the delivery note).
    Saves driver and receiver signatures in the delivery record.
    Updates PO outstanding quantities and creates stock ledger entries.
    Creates a DELIVERY_DISCREPANCY alert for short deliveries.

    destination: SITE_STORE (default) | MAIN_WAREHOUSE | LOT
      SITE_STORE     → stock at (project, site_id=NULL, lot=NULL) — Project Warehouse
      MAIN_WAREHOUSE → stock at (project, site_id=NULL, lot=NULL) — Project Warehouse (same level)
      LOT            → stock at (project, site_id=NULL, lot=Y)   — requires lot_id

    Phase 3B note: SITE_STORE now writes to site_id=NULL (Project Warehouse).
    The per-site stock level (site_id=X) is a legacy alias kept for backward
    compatibility via /sites/{id}/warehouse/ endpoints.
    """
    import mimetypes
    from app.models.attachment import Attachment
    from app.models.delivery import Delivery, DeliveryItem
    from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
    from app.models.stock import StockLedger
    from app.models.enums import (
        AttachmentEntity, AttachmentType,
        RecordStatus, MovementType, AlertType, AlertSeverity, AlertStatus,
    )
    from app.models.alert import SystemAlert

    # ── Validate destination ──────────────────────────────────────────────────
    _valid_destinations = {"MAIN_WAREHOUSE", "SITE_STORE", "LOT"}
    if destination not in _valid_destinations:
        raise HTTPException(
            422,
            f"Invalid destination '{destination}'. "
            f"Must be one of: {', '.join(sorted(_valid_destinations))}.",
        )
    if destination == "LOT" and not lot_id:
        raise HTTPException(422, "lot_id is required when destination is LOT.")

    now = datetime.now(timezone.utc)

    # ── Parse items ───────────────────────────────────────────────────────────
    try:
        items_data: list[dict] = json.loads(items_json) if items_json.strip() else []
    except json.JSONDecodeError:
        items_data = []

    # ── Save delivery note file — always persist to disk even if OCR fails ────
    delivery_note_url: Optional[str] = None
    dn_fname:          Optional[str] = None
    dn_mime:           Optional[str] = None
    dn_size:           int           = 0
    if delivery_note_file and delivery_note_file.filename:
        validate_upload(delivery_note_file, DOCUMENT_MIMES)
        from app.core.storage import save_upload as _save
        ext       = os.path.splitext(delivery_note_file.filename)[1] or ".bin"
        dn_fname  = f"{uuid.uuid4().hex}{ext}"
        content   = await delivery_note_file.read()
        dn_size   = len(content)
        dn_mime   = mimetypes.guess_type(delivery_note_file.filename)[0] or "application/octet-stream"
        delivery_note_url = _save(content, f"delivery_notes/{dn_fname}")

    # ── Save receiver signature as PNG file (never store raw Base64) ─────────
    receiver_sig_url: Optional[str] = None
    if receiver_signature:
        if receiver_signature.startswith("data:") or len(receiver_signature) > 500:
            try:
                from app.core.storage import save_upload as _save
                b64 = receiver_signature.split(",", 1)[1] if "," in receiver_signature else receiver_signature
                sig_fname = f"{uuid.uuid4().hex}.png"
                receiver_sig_url = _save(base64.b64decode(b64), f"delivery_signatures/{sig_fname}")
            except Exception:
                receiver_sig_url = None
        else:
            receiver_sig_url = receiver_signature  # already a path

    # ── Save driver signature as PNG file ─────────────────────────────────────
    driver_sig_url: Optional[str] = None
    if driver_signature:
        if driver_signature.startswith("data:") or len(driver_signature) > 500:
            try:
                from app.core.storage import save_upload as _save
                b64 = driver_signature.split(",", 1)[1] if "," in driver_signature else driver_signature
                sig_fname = f"{uuid.uuid4().hex}.png"
                driver_sig_url = _save(base64.b64decode(b64), f"delivery_signatures/{sig_fname}")
            except Exception:
                driver_sig_url = None
        else:
            driver_sig_url = driver_signature  # already a path

    # ── Determine if partial ──────────────────────────────────────────────────
    is_partial = any(
        float(i.get("quantity_received", 0)) < float(i.get("quantity_expected", 0))
        for i in items_data
        if i.get("quantity_expected") is not None
    )

    # ── Lightweight metadata only — no raw Base64 in the JSON column ─────────
    sig_meta: Optional[dict] = None
    if driver_name or driver_sig_url:
        sig_meta = {
            "driver_name":           driver_name,
            "driver_signature_path": driver_sig_url,
            "receiver_name":         receiver_name,
            "signed_at":             now.isoformat(),
        }

    # ── Create Delivery ───────────────────────────────────────────────────────
    delivery = Delivery(
        delivery_number                = f"DN-{uuid.uuid4().hex[:8].upper()}",
        purchase_order_id              = uuid.UUID(purchase_order_id) if purchase_order_id else None,
        supplier_id                    = uuid.UUID(supplier_id),
        project_id                     = uuid.UUID(project_id),
        site_id                        = uuid.UUID(site_id),
        received_by_user_id            = current_user.id,
        delivery_date                  = now,
        supplier_delivery_note_number  = delivery_note_number or None,
        delivery_status                = RecordStatus.PARTIALLY_RECEIVED if is_partial else RecordStatus.RECEIVED,
        comments                       = comments,
        delivery_note_image_url        = delivery_note_url,
        receiver_name                  = receiver_name,
        signature_image_url            = receiver_sig_url,
        ocr_raw_data                   = sig_meta,
    )
    db.add(delivery)
    db.flush()
    logger.info("delivery created id=%s", delivery.id)

    # ── Create Attachment record for delivery note file (enables delivery detail view) ──
    if delivery_note_url and dn_fname:
        db.add(Attachment(
            entity_type=AttachmentEntity.DELIVERY,
            entity_id=delivery.id,
            file_name=dn_fname,
            stored_path=delivery_note_url,  # ORM column (migration 0004)
            file_url=delivery_note_url,     # legacy NOT NULL column (migration 0001)
            mime_type=dn_mime or "application/octet-stream",
            file_size_bytes=dn_size or None,
            attachment_type=AttachmentType.DELIVERY_NOTE,
            uploaded_by=current_user.id,
            uploaded_at=now,
            is_active=True,
        ))

    # ── Create DeliveryItems + update PO + add stock ledger entries ───────────
    has_discrepancy  = False
    unlinked_items: list[dict] = []   # items with no catalog item_id — stock NOT updated
    stock_updated_count = 0
    non_boq_items: list[str]  = []    # items received outside the BOQ (item_id present, boq_item_id absent)

    for item_data in items_data:
        qty_exp = item_data.get("quantity_expected")
        qty_rec = float(item_data.get("quantity_received", 0))
        reason  = item_data.get("reason") or item_data.get("discrepancy_reason")

        if qty_exp is not None and qty_rec < float(qty_exp):
            has_discrepancy = True

        item_id    = uuid.UUID(item_data["item_id"])    if item_data.get("item_id")    else None
        boq_item_id = uuid.UUID(item_data["boq_item_id"]) if item_data.get("boq_item_id") else None

        # If item_id not supplied, resolve it from the linked PO item (by explicit ID or description).
        # This preserves the catalog link when PO was created from an MR/BOQ item.
        if not item_id and purchase_order_id:
            po_item_id_raw = item_data.get("purchase_order_item_id")
            _po_item = None
            if po_item_id_raw:
                _po_item = db.query(PurchaseOrderItem).filter(
                    PurchaseOrderItem.id == uuid.UUID(po_item_id_raw)
                ).first()
            if not _po_item:
                # Fallback: match by description within the same PO
                _desc = (item_data.get("description") or "").lower().strip()
                _po_item = (
                    db.query(PurchaseOrderItem)
                    .filter(
                        PurchaseOrderItem.purchase_order_id == uuid.UUID(purchase_order_id),
                        PurchaseOrderItem.item_id.isnot(None),
                    )
                    .all()
                )
                _po_item = next(
                    (p for p in _po_item if p.description.lower().strip() == _desc), None
                ) if _po_item else None
            if _po_item:
                if not item_id and _po_item.item_id:
                    item_id = _po_item.item_id
                    logger.debug("delivery resolved item_id=%s for '%s'", item_id, item_data.get('description'))
                if not boq_item_id and _po_item.boq_item_id:
                    boq_item_id = _po_item.boq_item_id

        # Track non-BOQ items (item_id present but boq_item_id absent) for alerting
        if item_id and not boq_item_id:
            non_boq_items.append(item_data.get("description", "Unknown"))

        d_item = DeliveryItem(
            delivery_id           = delivery.id,
            item_id               = item_id,
            boq_item_id           = boq_item_id,
            description           = item_data.get("description", ""),
            quantity_expected     = float(qty_exp) if qty_exp is not None else None,
            quantity_received     = qty_rec,
            unit                  = item_data.get("unit"),
            discrepancy_reason    = reason,
            created_at            = now,
        )
        db.add(d_item)

        # Update PO item received qty
        if purchase_order_id and item_id:
            poi = (
                db.query(PurchaseOrderItem)
                .filter(
                    PurchaseOrderItem.purchase_order_id == uuid.UUID(purchase_order_id),
                    PurchaseOrderItem.item_id           == item_id,
                )
                .first()
            )
            if poi:
                poi.quantity_received = float(poi.quantity_received or 0) + qty_rec

        # ── Route stock to the correct warehouse based on destination ─────────
        # Phase 3B: SITE_STORE and MAIN_WAREHOUSE both land in the Project
        # Warehouse (site_id=NULL, lot_id=NULL).  The Delivery record still
        # stores the physical delivery site for traceability.
        #
        # SITE_STORE     → Project Warehouse (project, site=NULL, lot=NULL)
        # MAIN_WAREHOUSE → Project Warehouse (project, site=NULL, lot=NULL)
        # LOT            → Lot stock         (project, site=NULL, lot=Y)
        if destination in ("MAIN_WAREHOUSE", "SITE_STORE"):
            effective_site_id  = None
            effective_lot_id   = None
        elif lot_id:
            # LOT destination — or SITE_STORE with an explicit lot_id
            effective_site_id  = None
            effective_lot_id   = uuid.UUID(lot_id)
        else:
            # Fallback: project warehouse
            effective_site_id  = None
            effective_lot_id   = None

        # Stock ledger entry — only when item_id is linked to the catalog.
        # Items without item_id are tracked in unlinked_items so office staff can fix them.
        if item_id:
            db.add(StockLedger(
                project_id    = uuid.UUID(project_id),
                site_id       = effective_site_id,
                lot_id        = effective_lot_id,
                item_id       = item_id,
                boq_item_id   = boq_item_id,
                movement_type = MovementType.DELIVERY_RECEIVED,
                reference_type = "delivery",
                reference_id  = delivery.id,
                quantity_in   = qty_rec,
                quantity_out  = 0,
                unit          = item_data.get("unit"),
                movement_date = now,
                entered_by    = current_user.id,
                created_at    = now,
            ))
            stock_updated_count += 1
        else:
            # No catalog link — stock cannot be updated for this line
            unlinked_items.append({
                "description":       item_data.get("description", ""),
                "quantity_received": qty_rec,
                "unit":              item_data.get("unit"),
            })
            if item_data.get("description"):
                logger.warning("delivery unlinked_item '%s' no item_id — stock not updated", item_data.get('description'))

    # ── Update PO status ──────────────────────────────────────────────────────
    if purchase_order_id:
        po = db.get(PurchaseOrder, uuid.UUID(purchase_order_id))
        if po and po.order_items:
            all_done = all(
                float(i.quantity_received or 0) >= float(i.quantity_ordered)
                for i in po.order_items
            )
            po.status = RecordStatus.RECEIVED if all_done else RecordStatus.PARTIALLY_RECEIVED

    # ── Alert on short / partial delivery ─────────────────────────────────────
    if has_discrepancy:
        db.add(SystemAlert(
            alert_type           = AlertType.DELIVERY_DISCREPANCY,
            severity             = AlertSeverity.HIGH,
            title                = f"Short delivery — {delivery.delivery_number}",
            message              = "Received quantity is less than ordered. Outstanding balance remains.",
            status               = AlertStatus.OPEN,
            project_id           = uuid.UUID(project_id),
            site_id              = uuid.UUID(site_id),
            notification_channel = "whatsapp",
            created_at           = now,
            sent_at              = now,
        ))

    # ── Alert on non-BOQ items ────────────────────────────────────────────────
    # Non-BOQ items are valid deliveries but office should be aware.
    if non_boq_items:
        items_preview = ", ".join(non_boq_items[:3])
        if len(non_boq_items) > 3:
            items_preview += f" (+{len(non_boq_items) - 3} more)"
        db.add(SystemAlert(
            alert_type           = AlertType.DELIVERY_MISMATCH,
            severity             = AlertSeverity.LOW,
            title                = f"Non-BOQ item(s) received — {delivery.delivery_number}",
            message              = (
                f"Delivery {delivery.delivery_number} contains {len(non_boq_items)} item(s) "
                f"not on the BOQ: {items_preview}. Review and update the BOQ if required."
            ),
            status               = AlertStatus.OPEN,
            project_id           = uuid.UUID(project_id),
            site_id              = uuid.UUID(site_id),
            notification_channel = "in_app",
            created_at           = now,
        ))

    db.commit()

    # Refresh materialized view — skip in pytest (CONCURRENTLY cannot run inside a transaction)
    import os as _os
    _in_test = bool(_os.getenv("PYTEST_CURRENT_TEST")) or _os.getenv("APP_ENV", "").lower() == "test"
    if not _in_test:
        try:
            from sqlalchemy import text as _t
            db.execute(_t("REFRESH MATERIALIZED VIEW CONCURRENTLY stock_balances"))
            db.commit()
        except Exception:
            pass

    logger.info("delivery saved id=%s partial=%s items=%d stock_updated=%d unlinked=%d",
                delivery.id, is_partial, len(items_data), stock_updated_count, len(unlinked_items))
    msg = "Delivery recorded successfully."
    if unlinked_items:
        msg = (
            f"Delivery recorded. {len(unlinked_items)} item(s) have no catalog link — "
            "stock balances NOT updated for those lines. Use the Deliveries page to link them."
        )
    return ApiSuccess(
        data={
            "delivery_id":          str(delivery.id),
            "delivery_number":      delivery.delivery_number,
            "status":               delivery.delivery_status.value,
            "items_count":          len(items_data),
            "is_partial":           is_partial,
            "has_file":             delivery_note_url is not None,
            "unlinked_items":       unlinked_items,
            "unlinked_count":       len(unlinked_items),
            "stock_updated_count":  stock_updated_count,
        },
        message=msg,
    )


# ── Link delivery item to catalog item ───────────────────────────────────────

class _LinkItemBody(BaseModel):
    item_id: uuid.UUID


@delivery_router.patch(
    "/{delivery_id}/items/{delivery_item_id}/link",
    response_model=ApiSuccess[DeliveryRead],
    dependencies=[OFFICE_AND_ABOVE],
)
def link_delivery_item(
    delivery_id:      uuid.UUID,
    delivery_item_id: uuid.UUID,
    body:             _LinkItemBody,
    db:               DbSession,
    current_user:     CurrentUser,
):
    """
    Link a delivery item to a catalog item (set item_id) and write the missing
    StockLedger entry.  Called by office staff when a delivery was recorded with
    an unlinked item — fixes the stock balance retroactively.
    """
    from app.models.delivery import DeliveryItem
    from app.models.item import Item
    from app.models.stock import StockLedger
    from app.models.enums import MovementType
    from sqlalchemy.orm import joinedload

    delivery = get_and_check_project_resource(db, current_user, Delivery, delivery_id, "Delivery not found.")

    d_item = (
        db.query(DeliveryItem)
        .filter(DeliveryItem.id == delivery_item_id, DeliveryItem.delivery_id == delivery_id)
        .first()
    )
    if not d_item:
        raise HTTPException(404, "Delivery item not found.")

    catalog_item = db.get(Item, body.item_id)
    if not catalog_item:
        raise HTTPException(404, "Catalog item not found.")

    if d_item.item_id is not None and d_item.item_id != body.item_id:
        raise HTTPException(
            422,
            f"Item already linked to '{catalog_item.name}'. "
            "Cannot re-link a delivery item that already has a catalog entry.",
        )

    # Set the catalog link
    d_item.item_id = body.item_id

    now = datetime.now(timezone.utc)

    # Write the missing stock ledger entry at Project Warehouse level.
    # Phase 3B: all warehouse stock at site_id=NULL, lot_id=NULL.
    # The Delivery.site_id records the physical delivery location for traceability only.
    db.add(StockLedger(
        project_id    = delivery.project_id,
        site_id       = None,
        lot_id        = None,
        item_id       = body.item_id,
        boq_item_id   = d_item.boq_item_id,
        movement_type = MovementType.DELIVERY_RECEIVED,
        reference_type = "delivery",
        reference_id  = delivery.id,
        quantity_in   = float(d_item.quantity_received),
        quantity_out  = 0,
        unit          = d_item.unit,
        movement_date = delivery.delivery_date or now,
        entered_by    = current_user.id,
        notes         = f"Linked post-delivery: {delivery.delivery_number or str(delivery.id)[:8]}",
        created_at    = now,
    ))

    db.commit()
    logger.info("delivery item_linked delivery=%s item=%s qty=%s",
                delivery.delivery_number, catalog_item.name, d_item.quantity_received)

    # Refresh materialized view
    import os as _os
    if not (bool(_os.getenv("PYTEST_CURRENT_TEST")) or _os.getenv("APP_ENV", "").lower() == "test"):
        try:
            from sqlalchemy import text as _t
            db.execute(_t("REFRESH MATERIALIZED VIEW CONCURRENTLY stock_balances"))
            db.commit()
        except Exception:
            db.rollback()

    updated = (
        db.query(Delivery)
        .options(joinedload(Delivery.items))
        .filter(Delivery.id == delivery_id)
        .first()
    )
    return ApiSuccess(
        data=DeliveryRead.model_validate(updated),
        message=f"Item linked to '{catalog_item.name}'. Stock balance updated.",
    )


# ── Reconciliation ────────────────────────────────────────────────────────────

@delivery_router.get("/{delivery_id}/reconcile", dependencies=[OFFICE_AND_ABOVE])
def reconcile_delivery(delivery_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """
    Reconcile a delivery against its linked PO and any supplier invoices.
    Returns a structured match result with per-item checks.
    """
    from app.models.invoice import Invoice
    from app.models.purchase_order import PurchaseOrder
    from sqlalchemy.orm import joinedload

    delivery = (
        db.query(delivery_service.Delivery if hasattr(delivery_service, "Delivery") else __import__("app.models.delivery", fromlist=["Delivery"]).Delivery)
        .options(joinedload(__import__("app.models.delivery", fromlist=["Delivery"]).Delivery.items))
        .filter(__import__("app.models.delivery", fromlist=["Delivery"]).Delivery.id == delivery_id)
        .first()
    )
    if not delivery:
        raise HTTPException(404, "Delivery not found.")

    from app.models.delivery import DeliveryItem
    delivery = db.query(Delivery).options(joinedload(Delivery.items)).filter(Delivery.id == delivery_id).first()
    if not delivery:
        raise HTTPException(404, "Delivery not found.")
    check_project_access(db, current_user, delivery.project_id)

    po      = db.get(PurchaseOrder, delivery.purchase_order_id) if delivery.purchase_order_id else None
    invoices = (
        db.query(Invoice)
        .filter(Invoice.purchase_order_id == po.id)
        .all()
    ) if po else []
    invoice = invoices[0] if invoices else None

    checks: list[dict] = []

    # ── Quantity checks ───────────────────────────────────────────────────────
    for d_item in delivery.items:
        poi = None
        if po and d_item.item_id:
            from app.models.purchase_order import PurchaseOrderItem
            poi = (
                db.query(PurchaseOrderItem)
                .filter(
                    PurchaseOrderItem.purchase_order_id == po.id,
                    PurchaseOrderItem.item_id           == d_item.item_id,
                )
                .first()
            )
        ordered  = float(poi.quantity_ordered if poi else (d_item.quantity_expected or 0))
        received = float(d_item.quantity_received or 0)
        inv_qty  = None

        status_item = "MATCHED"
        if ordered > 0 and abs(received - ordered) / ordered > 0.01:
            status_item = "QUANTITY_MISMATCH"

        checks.append({
            "type":          "QUANTITY",
            "item":          d_item.description,
            "ordered_qty":   ordered,
            "received_qty":  received,
            "invoiced_qty":  inv_qty,
            "status":        status_item,
        })

    # ── Invoice checks ────────────────────────────────────────────────────────
    if po and not invoices:
        checks.append({"type": "MISSING_INVOICE", "status": "MISSING_INVOICE"})
    elif invoice and po:
        inv_total = float(invoice.total_amount or 0)
        po_total  = float(po.total_amount or 0)
        if po_total > 0 and abs(inv_total - po_total) / po_total > 0.02:
            checks.append({
                "type":     "PRICE_MISMATCH",
                "inv_total": inv_total,
                "po_total":  po_total,
                "status":   "PRICE_MISMATCH",
            })

    # ── Delivery note check ───────────────────────────────────────────────────
    if not delivery.supplier_delivery_note_number:
        checks.append({"type": "MISSING_DELIVERY_NOTE", "status": "MISSING_DELIVERY_NOTE"})

    # ── Supplier match check ──────────────────────────────────────────────────
    if po and po.supplier_id != delivery.supplier_id:
        checks.append({"type": "SUPPLIER_MISMATCH", "status": "SUPPLIER_MISMATCH"})

    mismatch_types = {c["status"] for c in checks if c.get("status") != "MATCHED"}
    if not mismatch_types:
        overall = "MATCHED"
    elif "QUANTITY_MISMATCH" in mismatch_types:
        overall = "QUANTITY_MISMATCH"
    elif "PRICE_MISMATCH" in mismatch_types:
        overall = "PRICE_MISMATCH"
    elif "SUPPLIER_MISMATCH" in mismatch_types:
        overall = "SUPPLIER_MISMATCH"
    elif "MISSING_INVOICE" in mismatch_types:
        overall = "MISSING_INVOICE"
    else:
        overall = "MISSING_DELIVERY_NOTE"

    from app.models.supplier import Supplier
    supplier = db.get(Supplier, delivery.supplier_id)

    return ApiSuccess(data={
        "delivery_id":          str(delivery_id),
        "delivery_number":      delivery.delivery_number,
        "po_number":            po.po_number if po else None,
        "supplier":             supplier.name if supplier else None,
        "invoice_number":       invoice.invoice_number if invoice else None,
        "delivery_note_number": delivery.supplier_delivery_note_number,
        "ordered_total":        float(po.total_amount) if po else None,
        "invoice_total":        float(invoice.total_amount) if invoice else None,
        "overall_status":       overall,
        "checks":               checks,
    })
