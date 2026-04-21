"""Delivery service."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.delivery import Delivery, DeliveryItem
from app.models.enums import MovementType, RecordStatus
from app.models.project import Project
from app.models.site import Site
from app.models.stock import StockLedger
from app.schemas.delivery import DeliveryCreate, DeliveryUpdate


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


def list_deliveries(db: Session, project_id: uuid.UUID) -> list[Delivery]:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")
    return (
        db.query(Delivery)
        .filter(Delivery.project_id == project_id)
        .order_by(Delivery.delivery_date.desc())
        .all()
    )


def get_delivery(db: Session, delivery_id: uuid.UUID) -> Delivery:
    return _get_delivery_or_404(db, delivery_id)


def create_delivery(
    db: Session,
    project_id: uuid.UUID,
    data: DeliveryCreate,
    received_by_id: uuid.UUID,
) -> Delivery:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")

    site = db.get(Site, data.site_id)
    if not site or site.project_id != project_id:
        raise NotFoundError(f"Site {data.site_id} not found in this project.")

    # Check delivery_number uniqueness per project if provided
    if data.delivery_number:
        exists = (
            db.query(Delivery)
            .filter(
                Delivery.project_id == project_id,
                Delivery.delivery_number == data.delivery_number,
            )
            .first()
        )
        if exists:
            raise ConflictError(
                f"Delivery number '{data.delivery_number}' already exists in this project."
            )

    now = datetime.now(timezone.utc)
    delivery = Delivery(
        delivery_number=data.delivery_number,
        purchase_order_id=data.purchase_order_id,
        supplier_id=data.supplier_id,
        project_id=project_id,
        site_id=data.site_id,
        received_by_user_id=received_by_id,
        delivery_date=data.delivery_date or now,
        supplier_delivery_note_number=data.supplier_delivery_note_number,
        delivery_status=RecordStatus.RECEIVED,
        comments=data.comments,
    )
    db.add(delivery)
    db.flush()  # get delivery.id

    for item_data in data.items:
        di = DeliveryItem(
            delivery_id=delivery.id,
            purchase_order_item_id=item_data.purchase_order_item_id,
            item_id=item_data.item_id,
            boq_item_id=item_data.boq_item_id,
            description=item_data.description,
            quantity_expected=item_data.quantity_expected,
            quantity_received=item_data.quantity_received,
            unit=item_data.unit,
            discrepancy_reason=item_data.discrepancy_reason,
            created_at=now,
        )
        db.add(di)
        db.flush()

        # Post stock ledger entry for each received item
        if item_data.item_id:
            ledger = StockLedger(
                project_id=project_id,
                site_id=data.site_id,
                item_id=item_data.item_id,
                boq_item_id=item_data.boq_item_id,
                movement_type=MovementType.DELIVERY_RECEIVED,
                reference_type="delivery",
                reference_id=delivery.id,
                quantity_in=item_data.quantity_received,
                quantity_out=0,
                unit=item_data.unit,
                movement_date=delivery.delivery_date,
                entered_by=received_by_id,
                created_at=now,
            )
            db.add(ledger)

    db.commit()

    # Refresh stock_balances materialized view
    try:
        db.execute(
            "REFRESH MATERIALIZED VIEW CONCURRENTLY stock_balances"  # type: ignore[arg-type]
        )
        db.commit()
    except Exception:
        pass  # view refresh is best-effort; don't fail the delivery

    db.refresh(delivery)
    return delivery


def update_delivery(
    db: Session, delivery_id: uuid.UUID, data: DeliveryUpdate
) -> Delivery:
    delivery = _get_delivery_or_404(db, delivery_id)
    fields = data.model_fields_set

    if "delivery_status" in fields and data.delivery_status is not None:
        delivery.delivery_status = data.delivery_status
    if "comments" in fields:
        delivery.comments = data.comments
    if "supplier_delivery_note_number" in fields:
        delivery.supplier_delivery_note_number = data.supplier_delivery_note_number

    db.commit()
    db.refresh(delivery)
    return delivery
