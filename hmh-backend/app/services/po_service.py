"""Purchase Order service.

VAT logic (V1): All supplier pricing is VAT-inclusive.
  vat_amount  = ROUND(subtotal * 15 / 115, 2)
  total_amount = subtotal_amount
The DB trigger fn_recalculate_po_totals() handles this automatically
after each INSERT/UPDATE/DELETE on purchase_order_items.
We therefore do NOT manually update totals here — the trigger owns that.
"""

import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import RecordStatus
from app.models.project import Project
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.schemas.purchase_order import (
    POItemCreate, POItemUpdate,
    PurchaseOrderCreate, PurchaseOrderUpdate,
)


def _generate_po_number(db: Session, project_id: uuid.UUID) -> str:
    count = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.project_id == project_id)
        .count()
    )
    return f"PO-{str(project_id)[:8].upper()}-{count + 1:04d}"


def _get_po_or_404(db: Session, po_id: uuid.UUID) -> PurchaseOrder:
    po = (
        db.query(PurchaseOrder)
        .options(joinedload(PurchaseOrder.order_items))
        .filter(PurchaseOrder.id == po_id)
        .first()
    )
    if not po:
        raise NotFoundError(f"Purchase order {po_id} not found.")
    return po


def list_pos(db: Session, project_id: uuid.UUID) -> list[PurchaseOrder]:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")
    return (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.project_id == project_id)
        .order_by(PurchaseOrder.created_at.desc())
        .all()
    )


def get_po(db: Session, po_id: uuid.UUID) -> PurchaseOrder:
    return _get_po_or_404(db, po_id)


def create_po(
    db: Session,
    project_id: uuid.UUID,
    data: PurchaseOrderCreate,
    created_by_id: uuid.UUID,
) -> PurchaseOrder:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")

    po = PurchaseOrder(
        po_number=_generate_po_number(db, project_id),
        project_id=project_id,
        site_id=data.site_id,
        supplier_id=data.supplier_id,
        material_request_id=data.material_request_id,
        status=RecordStatus.DRAFT,
        po_date=datetime.now(timezone.utc),
        expected_delivery_date=data.expected_delivery_date,
        created_by=created_by_id,
        notes=data.notes,
    )
    db.add(po)
    db.flush()  # get po.id

    for item_data in data.items:
        line_total = None
        if item_data.rate is not None:
            line_total = float(
                (Decimal(str(item_data.quantity_ordered)) * Decimal(str(item_data.rate)))
                .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            )
        poi = PurchaseOrderItem(
            purchase_order_id=po.id,
            item_id=item_data.item_id,
            boq_item_id=item_data.boq_item_id,
            lot_id=item_data.lot_id,
            stage_id=item_data.stage_id,
            description=item_data.description,
            quantity_ordered=item_data.quantity_ordered,
            unit=item_data.unit,
            rate=item_data.rate,
            vat_mode=item_data.vat_mode,
            vat_rate=item_data.vat_rate,
            line_total=line_total,
            created_at=datetime.now(timezone.utc),
        )
        db.add(poi)

    db.commit()
    db.refresh(po)
    return po


def update_po(db: Session, po_id: uuid.UUID, data: PurchaseOrderUpdate) -> PurchaseOrder:
    po = _get_po_or_404(db, po_id)
    fields = data.model_fields_set

    if "status" in fields and data.status is not None:
        po.status = data.status
    if "expected_delivery_date" in fields:
        po.expected_delivery_date = data.expected_delivery_date
    if "notes" in fields:
        po.notes = data.notes
    if "site_id" in fields:
        po.site_id = data.site_id

    db.commit()
    db.refresh(po)
    return po


def add_po_item(db: Session, po_id: uuid.UUID, data: POItemCreate) -> PurchaseOrderItem:
    po = db.get(PurchaseOrder, po_id)
    if not po:
        raise NotFoundError(f"Purchase order {po_id} not found.")

    line_total = None
    if data.rate is not None:
        line_total = float(
            (Decimal(str(data.quantity_ordered)) * Decimal(str(data.rate)))
            .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )

    poi = PurchaseOrderItem(
        purchase_order_id=po_id,
        item_id=data.item_id,
        boq_item_id=data.boq_item_id,
        lot_id=data.lot_id,
        stage_id=data.stage_id,
        description=data.description,
        quantity_ordered=data.quantity_ordered,
        unit=data.unit,
        rate=data.rate,
        vat_mode=data.vat_mode,
        vat_rate=data.vat_rate,
        line_total=line_total,
        created_at=datetime.now(timezone.utc),
    )
    db.add(poi)
    db.commit()
    db.refresh(poi)
    # DB trigger will have updated PO totals
    return poi
