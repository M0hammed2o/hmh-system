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

    log = FuelLog(
        project_id=project_id,
        site_id=data.site_id,
        fuel_type=data.fuel_type,
        usage_type=data.usage_type,
        equipment_ref=data.equipment_ref,
        litres=data.litres,
        cost_per_litre=data.cost_per_litre,
        # total_cost is GENERATED ALWAYS AS STORED — not set here
        fuelled_by=data.fuelled_by,
        recorded_by=recorded_by_id,
        fuel_date=data.fuel_date or datetime.now(timezone.utc),
        notes=data.notes,
    )
    db.add(log)
    db.commit()
    db.refresh(log)   # loads the DB-generated total_cost
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
