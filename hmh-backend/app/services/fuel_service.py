"""Fuel log service."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.fuel import FuelLog
from app.models.project import Project
from app.schemas.fuel import FuelLogCreate, FuelLogUpdate


def _get_or_404(db: Session, log_id: uuid.UUID) -> FuelLog:
    log = db.get(FuelLog, log_id)
    if not log:
        raise NotFoundError(f"Fuel log {log_id} not found.")
    return log


def list_fuel_logs(
    db: Session,
    project_id: uuid.UUID,
    site_id: Optional[uuid.UUID] = None,
    limit: int = 200,
) -> list[FuelLog]:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")

    q = db.query(FuelLog).filter(FuelLog.project_id == project_id)
    if site_id:
        q = q.filter(FuelLog.site_id == site_id)
    return q.order_by(FuelLog.fuel_date.desc()).limit(limit).all()


def get_fuel_log(db: Session, log_id: uuid.UUID) -> FuelLog:
    return _get_or_404(db, log_id)


def create_fuel_log(
    db: Session,
    project_id: uuid.UUID,
    data: FuelLogCreate,
    recorded_by_id: uuid.UUID,
) -> FuelLog:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found.")

    _fuel_date = data.fuel_date or datetime.now(timezone.utc)
    log = FuelLog(
        project_id=project_id,
        site_id=data.site_id,
        vehicle_id=getattr(data, "vehicle_id", None),  # added in 0002
        fuel_type=data.fuel_type,
        usage_type=data.usage_type,
        equipment_ref=data.equipment_ref,
        litres=data.litres,
        cost_per_litre=data.cost_per_litre,
        # total_cost is GENERATED ALWAYS AS STORED — not set here
        fuelled_by=data.fuelled_by,
        recorded_by=recorded_by_id,
        fuel_date=_fuel_date,
        log_date=_fuel_date.date() if hasattr(_fuel_date, "date") else _fuel_date,  # legacy NOT NULL col
        odometer_reading=getattr(data, "odometer_reading", None),
        notes=data.notes,
    )
    # ── Consumption calculation from previous odometer reading ──────────────
    # Find the most recent fuel log for the same vehicle (if vehicle linked)
    if _fuel_date and data.vehicle_id and _fuel_date and getattr(data, "odometer_reading", None):
        prev = (
            db.query(FuelLog)
            .filter(
                FuelLog.vehicle_id == data.vehicle_id,
                FuelLog.odometer_reading.isnot(None),
            )
            .order_by(FuelLog.fuel_date.desc())
            .first()
        )
        if prev and prev.odometer_reading is not None:
            dist = float(data.odometer_reading) - float(prev.odometer_reading)
            if dist > 0 and data.litres > 0:
                log.distance_km    = dist
                log.efficiency_kpl = round(dist / data.litres, 3)
                log.l_per_100km    = round(data.litres / dist * 100, 3)
                # Flag unusual consumption (> 50 L/100km is suspicious)
                if log.l_per_100km > 50:
                    existing_notes = log.notes or ""
                    log.notes = f"⚠ High consumption ({log.l_per_100km:.1f} L/100km) — verify. " + existing_notes

    db.add(log)
    db.flush()  # get log.id before updating total_cost

    # total_cost is declared Computed() in the ORM model but the production DB
    # column is a plain nullable column (not GENERATED ALWAYS).  Calculate and
    # set it via raw SQL so the value is visible immediately after INSERT.
    if log.cost_per_litre is not None:
        from sqlalchemy import text as _t
        from decimal import Decimal, ROUND_HALF_UP
        tc = (Decimal(str(log.litres)) * Decimal(str(log.cost_per_litre))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        db.execute(_t("UPDATE fuel_logs SET total_cost = :tc WHERE id = :id"),
                   {"tc": float(tc), "id": str(log.id)})

    db.commit()
    db.refresh(log)
    return log


def update_fuel_log(
    db: Session,
    log_id: uuid.UUID,
    data: FuelLogUpdate,
) -> FuelLog:
    log = _get_or_404(db, log_id)
    fields = data.model_fields_set

    if "fuel_type" in fields and data.fuel_type is not None:
        log.fuel_type = data.fuel_type
    if "usage_type" in fields and data.usage_type is not None:
        log.usage_type = data.usage_type
    if "equipment_ref" in fields:
        log.equipment_ref = data.equipment_ref
    if "litres" in fields and data.litres is not None:
        log.litres = data.litres
    if "cost_per_litre" in fields:
        log.cost_per_litre = data.cost_per_litre
    if "fuelled_by" in fields:
        log.fuelled_by = data.fuelled_by
    if "site_id" in fields:
        log.site_id = data.site_id
    if "fuel_date" in fields and data.fuel_date is not None:
        log.fuel_date = data.fuel_date
    if "notes" in fields:
        log.notes = data.notes

    db.commit()
    db.refresh(log)   # pick up new total_cost from DB
    return log
