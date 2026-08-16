"""Project Cost Summary — aggregates all cost sources for a project into one view."""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.dependencies import ALL_ROLES, DbSession
from app.schemas.common import ApiSuccess

router = APIRouter(prefix="/projects", tags=["cost-summary"])


def _build_summary(db: Session, project_id: uuid.UUID) -> dict:
    from app.models.project import Project
    from app.models.boq import BOQItem
    from app.models.payment import Payment
    from app.models.job_card import JobCard
    from app.models.work_done import SubcontractorWorkDone
    from app.models.fuel import FuelLog
    from app.models.fuel_management import FuelIssue
    from app.models.vehicle import VehicleCost
    from app.models.material_request import MaterialRequest, MaterialRequestItem
    from app.models.enums import JobCardStatus, WorkDoneStatus

    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # ── BOQ Budget ──────────────────────────────────────────────────────────────
    boq_budget = db.query(
        func.coalesce(func.sum(BOQItem.planned_total), 0)
    ).filter(BOQItem.project_id == project_id).scalar() or 0

    # ── Procurement Spend (actual payments made) ────────────────────────────────
    procurement_spend = db.query(
        func.coalesce(func.sum(Payment.amount_paid), 0)
    ).filter(Payment.project_id == project_id).scalar() or 0

    # ── Labour (job cards — approved or paid) ──────────────────────────────────
    labour_cost = db.query(
        func.coalesce(func.sum(JobCard.total_amount), 0)
    ).filter(
        JobCard.project_id == project_id,
        JobCard.status.in_([
            JobCardStatus.OWNER_APPROVED,
            JobCardStatus.PAYMENT_APPROVED,
            JobCardStatus.PAID,
        ]),
    ).scalar() or 0

    # ── Subcontractor / Contractor work ────────────────────────────────────────
    subcontractor_cost = db.query(
        func.coalesce(func.sum(SubcontractorWorkDone.amount), 0)
    ).filter(
        SubcontractorWorkDone.project_id == project_id,
        SubcontractorWorkDone.status.in_([
            WorkDoneStatus.SITE_APPROVED,
            WorkDoneStatus.OFFICE_APPROVED,
            WorkDoneStatus.PAID,
        ]),
    ).scalar() or 0

    # ── Fuel costs ─────────────────────────────────────────────────────────────
    # Combined at this reporting layer only (never in stock calculations):
    # FuelLog covers historical fills, FuelIssue covers everything recorded
    # after a project cuts over to Fuel Management. A project never double
    # counts — FuelLog writes freeze the moment Fuel Management goes live.
    fuel_cost = float(db.query(
        func.coalesce(func.sum(FuelLog.total_cost), 0)
    ).filter(FuelLog.project_id == project_id).scalar() or 0)
    fuel_cost += float(db.query(
        func.coalesce(func.sum(FuelIssue.total_cost), 0)
    ).filter(FuelIssue.project_id == project_id, FuelIssue.is_reversed.is_(False)).scalar() or 0)

    fuel_litres = float(db.query(
        func.coalesce(func.sum(FuelLog.litres), 0)
    ).filter(FuelLog.project_id == project_id).scalar() or 0)
    fuel_litres += float(db.query(
        func.coalesce(func.sum(FuelIssue.litres), 0)
    ).filter(FuelIssue.project_id == project_id, FuelIssue.is_reversed.is_(False)).scalar() or 0)

    # ── Vehicle repair costs ────────────────────────────────────────────────────
    vehicle_repair_cost = db.query(
        func.coalesce(func.sum(VehicleCost.amount), 0)
    ).filter(VehicleCost.project_id == project_id).scalar() or 0

    # ── Extra / Breakage costs (MR items with extra_reason_type set) ───────────
    extra_rows = (
        db.query(
            MaterialRequestItem.extra_reason_type,
            MaterialRequestItem.description,
            MaterialRequestItem.requested_quantity,
            MaterialRequestItem.unit,
            MaterialRequestItem.extra_reason_notes,
        )
        .join(MaterialRequest, MaterialRequest.id == MaterialRequestItem.material_request_id)
        .filter(
            MaterialRequest.project_id == project_id,
            MaterialRequestItem.extra_reason_type.isnot(None),
        )
        .all()
    )

    extra_by_type: dict[str, list[dict]] = {}
    for row in extra_rows:
        key = row.extra_reason_type or "OTHER"
        if key not in extra_by_type:
            extra_by_type[key] = []
        extra_by_type[key].append({
            "description": row.description,
            "quantity": float(row.requested_quantity),
            "unit": row.unit,
            "notes": row.extra_reason_notes,
        })

    extra_summary = [
        {"type": k, "items": v, "count": len(v)}
        for k, v in extra_by_type.items()
    ]

    # ── Totals ──────────────────────────────────────────────────────────────────
    total_actual = (
        float(procurement_spend)
        + float(labour_cost)
        + float(subcontractor_cost)
        + float(fuel_cost)
        + float(vehicle_repair_cost)
    )

    variance = float(boq_budget) - total_actual  # positive = under budget

    return {
        "project_id":          str(project_id),
        "project_name":        project.name,
        "project_code":        project.code,
        "project_status":      project.status.value,
        # Budget
        "boq_budget":          float(boq_budget),
        # Actuals
        "procurement_spend":   float(procurement_spend),
        "labour_cost":         float(labour_cost),
        "subcontractor_cost":  float(subcontractor_cost),
        "fuel_cost":           float(fuel_cost),
        "fuel_litres":         float(fuel_litres),
        "vehicle_repair_cost": float(vehicle_repair_cost),
        # Derived
        "total_actual":        total_actual,
        "variance":            variance,             # positive = under budget
        "variance_pct":        round(variance / float(boq_budget) * 100, 1) if boq_budget else None,
        # Extra / breakage detail
        "extra_costs":         extra_summary,
        "extra_items_total":   len(extra_rows),
    }


@router.get(
    "/{project_id}/cost-summary",
    response_model=ApiSuccess[dict],
    dependencies=[ALL_ROLES],
)
def get_project_cost_summary(project_id: uuid.UUID, db: DbSession):
    """
    Returns a full cost breakdown for a project:
    BOQ budget, procurement spend, labour, subcontractors, fuel, vehicle repairs, and extra/breakage items.
    """
    summary = _build_summary(db, project_id)
    return ApiSuccess(data=summary)
