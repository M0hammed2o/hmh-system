"""
Delivery service — partial/full receive + stock routing.

When a delivery is confirmed:
- Adds stock into the destination (warehouse / site store / lot).
- For lot destination: runs BOQ allocation check.
- Updates PO item quantity_received.
- Creates audit trail.
"""

import base64
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.delivery import Delivery, DeliveryItem
from app.models.enums import (
    AlertSeverity, AlertStatus, AlertType,
    AuditAction, DeliveryDestination, MovementType, RecordStatus,
)
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.stock import StockLedger
from app.services import allocation_service, audit_service


def _save_base64_to_file(b64_data: str, subfolder: str) -> Optional[str]:
    """Decode a Base64 data URL and write as PNG. Returns URL path or None on failure."""
    if not b64_data:
        return None
    try:
        raw = b64_data.split(",", 1)[1] if "," in b64_data else b64_data
        folder = os.path.join(settings.UPLOAD_DIR, subfolder)
        os.makedirs(folder, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.png"
        with open(os.path.join(folder, filename), "wb") as f:
            f.write(base64.b64decode(raw))
        return f"/uploads/{subfolder}/{filename}"
    except Exception:
        return None


def _get_delivery_or_404(db: Session, delivery_id: uuid.UUID) -> Delivery:
    d = (
        db.query(Delivery)
        .options(joinedload(Delivery.items))
        .filter(Delivery.id == delivery_id)
        .first()
    )
    if not d:
        raise NotFoundError(f"Delivery {delivery_id} not found.")
    return d


# ── CRUD ──────────────────────────────────────────────────────────────────────

def list_deliveries(
    db: Session,
    project_id: uuid.UUID,
    site_id: Optional[uuid.UUID] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Delivery]:
    q = (
        db.query(Delivery)
        .options(joinedload(Delivery.items))
        .filter(Delivery.project_id == project_id)
    )
    if site_id:
        q = q.filter(Delivery.site_id == site_id)
    return q.order_by(Delivery.delivery_date.desc()).limit(limit).offset(offset).all()


def get_delivery(db: Session, delivery_id: uuid.UUID) -> Delivery:
    return _get_delivery_or_404(db, delivery_id)


def update_delivery(db: Session, delivery_id: uuid.UUID, data) -> Delivery:
    d = _get_delivery_or_404(db, delivery_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(d, field, value)
    db.commit()
    return _get_delivery_or_404(db, delivery_id)


def create_delivery(
    db: Session,
    project_id: uuid.UUID,
    data,
    current_user_id: uuid.UUID,
) -> Delivery:
    """
    Record a delivery note.

    - Creates Delivery + DeliveryItem rows.
    - Updates PurchaseOrderItem.quantity_received cumulatively.
    - Flags PARTIALLY_RECEIVED and raises a DELIVERY_DISCREPANCY alert
      when any item has quantity_received < quantity_expected.
    """
    now = datetime.now(timezone.utc)

    # Save receiver signature as PNG file — never store raw Base64 in VARCHAR(500)
    receiver_sig_url: Optional[str] = None
    sig_data = getattr(data, "signature_data", None)
    if sig_data:
        if sig_data.startswith("data:") or len(sig_data) > 500:
            receiver_sig_url = _save_base64_to_file(sig_data, "delivery_signatures")
        else:
            receiver_sig_url = sig_data  # already a file path

    # Save driver signature as PNG file
    driver_sig_url: Optional[str] = None
    driver_sig_data = getattr(data, "driver_signature_data", None)
    if driver_sig_data:
        if driver_sig_data.startswith("data:") or len(driver_sig_data) > 500:
            driver_sig_url = _save_base64_to_file(driver_sig_data, "delivery_signatures")
        else:
            driver_sig_url = driver_sig_data

    # Lightweight metadata only — no raw Base64 in the JSON column
    sig_meta: Optional[dict] = None
    if getattr(data, "driver_name", None) or driver_sig_url:
        sig_meta = {
            "driver_name":           getattr(data, "driver_name", None),
            "driver_signature_path": driver_sig_url,
            "receiver_name":         getattr(data, "receiver_name", None),
            "signed_at":             now.isoformat(),
        }

    delivery = Delivery(
        delivery_number=(
            data.delivery_number or f"DN-{uuid.uuid4().hex[:8].upper()}"
        ),
        purchase_order_id=data.purchase_order_id,
        supplier_id=data.supplier_id,
        project_id=project_id,
        site_id=data.site_id,
        received_by_user_id=current_user_id,
        delivery_date=data.delivery_date or now,
        supplier_delivery_note_number=data.supplier_delivery_note_number,
        delivery_status=RecordStatus.RECEIVED,
        comments=data.comments,
        receiver_name=getattr(data, "receiver_name", None),
        driver_name=getattr(data, "driver_name", None),
        signature_image_url=receiver_sig_url,
        ocr_raw_data=sig_meta,
    )
    db.add(delivery)
    db.flush()

    # Pre-load PO items for quantity tracking
    po_items: dict[uuid.UUID, PurchaseOrderItem] = {}
    if data.purchase_order_id:
        po = db.get(PurchaseOrder, data.purchase_order_id)
        if po:
            for poi in po.order_items:
                po_items[poi.id] = poi

    is_partial = False

    for item_data in data.items:
        received = float(item_data.quantity_received)
        expected = float(item_data.quantity_expected) if item_data.quantity_expected else None

        if expected is not None and received < expected:
            is_partial = True

        d_item = DeliveryItem(
            delivery_id=delivery.id,
            purchase_order_item_id=item_data.purchase_order_item_id,
            item_id=item_data.item_id,
            boq_item_id=getattr(item_data, "boq_item_id", None),
            description=item_data.description,
            quantity_expected=expected,
            quantity_received=received,
            unit=item_data.unit,
            discrepancy_reason=item_data.discrepancy_reason,
            created_at=now,
        )
        db.add(d_item)

        # Update PO item received quantity
        if item_data.purchase_order_item_id and item_data.purchase_order_item_id in po_items:
            poi = po_items[item_data.purchase_order_item_id]
            poi.quantity_received = float(poi.quantity_received or 0) + received
        elif po_items:
            # For BOQ-picked items without a purchase_order_item_id, try to match
            # by description so multi-item POs track received quantities correctly.
            if len(po_items) == 1:
                poi = next(iter(po_items.values()))
                poi.quantity_received = float(poi.quantity_received or 0) + received
            elif item_data.description:
                desc_norm = (item_data.description or "").strip().lower()
                matched = next(
                    (p for p in po_items.values()
                     if (p.description or "").strip().lower() == desc_norm),
                    None,
                )
                if matched:
                    matched.quantity_received = float(matched.quantity_received or 0) + received

        # Write stock ledger entry so stock balances reflect the delivery
        if item_data.item_id:
            db.add(StockLedger(
                project_id     = project_id,
                site_id        = None,
                lot_id         = None,
                item_id        = item_data.item_id,
                boq_item_id    = getattr(item_data, "boq_item_id", None),
                movement_type  = MovementType.DELIVERY_RECEIVED,
                reference_type = "delivery",
                reference_id   = delivery.id,
                quantity_in    = received,
                quantity_out   = 0,
                unit           = item_data.unit,
                movement_date  = now,
                entered_by     = current_user_id,
                created_at     = now,
            ))

    delivery.delivery_status = (
        RecordStatus.PARTIALLY_RECEIVED if is_partial else RecordStatus.RECEIVED
    )

    # Update PO status
    if data.purchase_order_id and po_items:
        all_done = all(
            float(poi.quantity_received or 0) >= float(poi.quantity_ordered)
            for poi in po_items.values()
        )
        po = db.get(PurchaseOrder, data.purchase_order_id)
        if po:
            po.status = RecordStatus.RECEIVED if all_done else RecordStatus.PARTIALLY_RECEIVED

    # Alert on partial delivery
    if is_partial:
        from app.models.alert import SystemAlert
        db.add(SystemAlert(
            project_id=project_id,
            site_id=data.site_id,
            reference_type="delivery",
            reference_id=delivery.id,
            alert_type=AlertType.DELIVERY_DISCREPANCY,
            severity=AlertSeverity.MEDIUM,
            title=f"Partial delivery: {delivery.delivery_number}",
            message=(
                f"Delivery {delivery.delivery_number} received fewer items than expected. "
                "Outstanding balance remains against the purchase order."
            ),
            status=AlertStatus.OPEN,
            notification_channel="in_app",
            created_at=now,
        ))

    # Auto-link delivery to an existing ProcurementReconciliation for this PO.
    # This ensures the reconciliation page shows the correct delivery and qty_received
    # instead of "No delivery linked / 0 received".
    if data.purchase_order_id:
        try:
            from app.models.procurement_reconciliation import ProcurementReconciliation
            from app.services import procurement_reconciliation_service as _recon_svc
            recon = (
                db.query(ProcurementReconciliation)
                .filter(
                    ProcurementReconciliation.purchase_order_id == data.purchase_order_id,
                    ProcurementReconciliation.delivery_id.is_(None),
                )
                .order_by(ProcurementReconciliation.created_at.desc())
                .first()
            )
            if recon:
                recon.delivery_id = delivery.id
                po_obj = db.get(PurchaseOrder, data.purchase_order_id)
                from app.models.invoice import Invoice
                from app.models.quotation import Quotation
                invoice_obj  = db.get(Invoice,   recon.invoice_id)  if recon.invoice_id  else None
                quotation_obj = db.get(Quotation, recon.quotation_id) if recon.quotation_id else None
                recon.variance_data = _recon_svc.compute_variances(po_obj, invoice_obj, quotation_obj, delivery)
                from app.models.enums import ReconciliationStatus
                if recon.variance_data["has_variance"]:
                    recon.status = ReconciliationStatus.VARIANCE_DETECTED
                else:
                    recon.status = ReconciliationStatus.MATCHED
        except Exception:
            pass  # reconciliation auto-link is non-critical; never block delivery creation

    db.commit()

    # Refresh stock balances view so StockPage shows up-to-date data
    import os as _os
    _in_test = bool(_os.getenv("PYTEST_CURRENT_TEST")) or _os.getenv("APP_ENV", "").lower() == "test"
    if not _in_test:
        try:
            db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY stock_balances"))
            db.commit()
        except Exception:
            db.rollback()

    return _get_delivery_or_404(db, delivery.id)


def receive_stock(
    db: Session,
    delivery_id: uuid.UUID,
    destination: DeliveryDestination,
    actor_id: uuid.UUID,
    lot_id: Optional[uuid.UUID] = None,
    overrun_reason: Optional[str] = None,
    items_received: Optional[list[dict]] = None,
) -> Delivery:
    """
    Confirm a delivery and route stock to the correct location.

    items_received: list of {delivery_item_id, quantity_received}
    If None, all items received at full expected quantity.
    """
    delivery = _get_delivery_or_404(db, delivery_id)
    now = datetime.now(timezone.utc)

    # Idempotency guard — prevent double stock write if receive_stock() is called twice.
    # Check for existing ledger entries with reference_id=delivery_id (written only by this fn).
    # If any exist, the delivery was already processed; return the current state safely.
    if delivery.delivery_status in (RecordStatus.RECEIVED, RecordStatus.PARTIALLY_RECEIVED):
        existing_ledger = db.query(StockLedger).filter(
            StockLedger.reference_type == "delivery",
            StockLedger.reference_id  == delivery_id,
        ).first()
        if existing_ledger:
            return delivery  # already processed — idempotent

    qty_map: dict[uuid.UUID, float] = {}
    if items_received:
        for ir in items_received:
            qty_map[uuid.UUID(str(ir["delivery_item_id"]))] = float(ir["quantity_received"])

    is_partial = False

    for d_item in delivery.items:
        recv_qty = qty_map.get(d_item.id, float(d_item.quantity_expected or d_item.quantity_received))
        if recv_qty <= 0:
            continue

        expected = float(d_item.quantity_expected or recv_qty)
        if recv_qty < expected:
            is_partial = True

        if destination == DeliveryDestination.LOT and lot_id and d_item.item_id:
            warning = allocation_service.check_before_issue(db, lot_id, d_item.item_id, recv_qty)
            if warning and not overrun_reason:
                raise ValidationError(
                    "Lot allocation exceeded. Provide overrun_reason to proceed.",
                    detail={
                        "overrun": True,
                        "lot_number": warning.lot_number,
                        "item_name": warning.item_name,
                        "item_unit": warning.item_unit,
                        "allocated_quantity": warning.allocated_quantity,
                        "already_used": warning.already_used,
                        "new_issue_quantity": recv_qty,
                        "new_total": warning.new_total,
                        "over_amount": warning.over_amount,
                    },
                )
            if warning and overrun_reason:
                allocation_service.create_overrun_alert(
                    db, warning, delivery.project_id, delivery.site_id,
                    overrun_reason, actor_id=actor_id,
                )

        # Route stock to the correct warehouse (Phase 3B).
        # SITE_STORE and MAIN_WAREHOUSE both land in the Project Warehouse
        # (site_id=NULL, lot_id=NULL) — Project Warehouse belongs to the
        # project, not to a specific site/block.
        # The Delivery record still holds the physical site for traceability.
        #
        #   SITE_STORE     → Project Warehouse (site_id=NULL, lot_id=NULL)
        #   MAIN_WAREHOUSE → Project Warehouse (site_id=NULL, lot_id=NULL)
        #   LOT            → Lot stock         (site_id=NULL, lot_id=Y)
        effective_site_id = None  # all warehouse entries are project-scoped
        effective_lot_id  = lot_id if destination == DeliveryDestination.LOT else None

        if d_item.item_id:
            db.add(StockLedger(
                project_id=delivery.project_id,
                site_id=effective_site_id,
                lot_id=effective_lot_id,
                item_id=d_item.item_id,
                boq_item_id=d_item.boq_item_id,
                movement_type=MovementType.DELIVERY_RECEIVED,
                reference_type="delivery",
                reference_id=delivery.id,
                quantity_in=recv_qty,
                quantity_out=0,
                movement_date=now,
                entered_by=actor_id,
                notes=f"Received: {delivery.delivery_number or str(delivery.id)[:8]}",
                created_at=now,
            ))
        d_item.quantity_received = recv_qty

        # Update PO item quantity_received
        if d_item.purchase_order_item_id:
            poi = db.get(PurchaseOrderItem, d_item.purchase_order_item_id)
            if poi:
                current = float(poi.quantity_received or 0)
                poi.quantity_received = current + recv_qty

    delivery.delivery_status = RecordStatus.PARTIALLY_RECEIVED if is_partial else RecordStatus.RECEIVED

    if delivery.purchase_order_id:
        po = db.get(PurchaseOrder, delivery.purchase_order_id)
        if po:
            po.status = RecordStatus.PARTIALLY_RECEIVED if is_partial else RecordStatus.RECEIVED

    if is_partial:
        from app.models.alert import SystemAlert
        db.add(SystemAlert(
            project_id=delivery.project_id,
            site_id=delivery.site_id,
            reference_type="delivery",
            reference_id=delivery.id,
            alert_type=AlertType.DELIVERY_DISCREPANCY,
            severity=AlertSeverity.MEDIUM,
            title=f"Partial delivery: {delivery.delivery_number or str(delivery.id)[:8]}",
            message="Items received at less than ordered quantity. Outstanding balance remains.",
            status=AlertStatus.OPEN,
            notification_channel="in_app",
            created_at=now,
        ))

    audit_service.write_event(
        db, AuditAction.UPDATE, "delivery", actor_id, delivery_id,
        after_value={
            "destination": destination.value,
            "is_partial": is_partial,
            "lot_id": str(lot_id) if lot_id else None,
        },
    )

    delivery_id_saved = delivery.id
    # Capture context before commit while ORM objects are still loaded
    _notify_project_id  = delivery.project_id
    _notify_dn          = delivery.delivery_number or str(delivery.id)[:8]
    _notify_delivery_id = delivery.id
    _notify_item_count  = len(delivery.items)
    db.commit()

    # WhatsApp notification: full delivery received (not partial — partial already has its own alert)
    if not is_partial:
        try:
            from app.services.notification_service import enqueue_direct
            from app.models.enums import AlertType, AlertSeverity
            enqueue_direct(
                db,
                alert_type=AlertType.DELIVERY_RECEIVED_ALERT,
                severity=AlertSeverity.LOW,
                title=f"Delivery Received: {_notify_dn}",
                message=(
                    f"Delivery {_notify_dn} has been received and confirmed. "
                    f"{_notify_item_count} item{'s' if _notify_item_count != 1 else ''}."
                ),
                project_id=_notify_project_id,
                entity_type="delivery",
                entity_id=_notify_delivery_id,
            )
            db.commit()
        except Exception:
            pass

    import os as _os
    _in_test = bool(_os.getenv("PYTEST_CURRENT_TEST")) or _os.getenv("APP_ENV", "").lower() == "test"
    if not _in_test:
        try:
            db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY stock_balances"))
            db.commit()
        except Exception:
            db.rollback()  # reset PostgreSQL aborted-transaction state; view may not exist everywhere

    reloaded = db.get(Delivery, delivery_id_saved)
    return reloaded if reloaded is not None else delivery


def get_po_outstanding(db: Session, po_id: uuid.UUID) -> dict:
    po = (
        db.query(PurchaseOrder)
        .options(joinedload(PurchaseOrder.order_items))
        .filter(PurchaseOrder.id == po_id)
        .first()
    )
    if not po:
        raise NotFoundError(f"PO {po_id} not found.")

    items_out = []
    for item in po.order_items:
        qty_ordered = float(item.quantity_ordered)
        qty_received = float(item.quantity_received or 0)
        outstanding = max(0.0, qty_ordered - qty_received)
        items_out.append({
            "po_item_id": str(item.id),
            "description": item.description,
            "unit": item.unit,
            "quantity_ordered": qty_ordered,
            "quantity_received": qty_received,
            "quantity_outstanding": outstanding,
            "is_fully_received": outstanding == 0,
        })

    return {
        "po_id": str(po_id),
        "po_number": po.po_number,
        "status": po.status.value,
        "items": items_out,
        "total_outstanding_lines": sum(1 for i in items_out if i["quantity_outstanding"] > 0),
        "is_fully_received": all(i["is_fully_received"] for i in items_out),
    }
