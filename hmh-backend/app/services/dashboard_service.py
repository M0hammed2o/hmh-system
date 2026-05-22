"""Dashboard stats service."""

import uuid
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.alert import SystemAlert
from app.models.delivery import Delivery
from app.models.enums import AlertStatus, LotStatus, PaymentStatus, ProjectStatus, RecordStatus, StageStatus
from app.models.fuel import FuelLog
from app.models.invoice import Invoice
from app.models.lot import Lot
from app.models.material_request import MaterialRequest
from app.models.payment import Payment
from app.models.project import Project
from app.models.purchase_order import PurchaseOrder
from app.models.site import Site
from app.models.stage import ProjectStageStatus


def get_stats(db: Session, project_id: Optional[uuid.UUID] = None) -> dict:
    """Return aggregated stats for the dashboard.

    If project_id is provided, stats are scoped to that project.
    Otherwise, system-wide totals are returned.
    """
    # Projects
    project_q = db.query(func.count(Project.id))
    active_project_count = project_q.filter(Project.status == ProjectStatus.ACTIVE).scalar() or 0
    total_project_count = project_q.scalar() or 0

    # Sites
    site_q = db.query(func.count(Site.id)).filter(Site.is_active == True)  # noqa: E712
    if project_id:
        site_q = site_q.filter(Site.project_id == project_id)
    site_count = site_q.scalar() or 0

    # Lots
    lot_q = db.query(func.count(Lot.id))
    if project_id:
        lot_q = lot_q.filter(Lot.project_id == project_id)
    lot_count = lot_q.scalar() or 0

    # Purchase Orders
    po_q = db.query(func.count(PurchaseOrder.id))
    if project_id:
        po_q = po_q.filter(PurchaseOrder.project_id == project_id)
    open_po_count = po_q.filter(
        PurchaseOrder.status.in_([RecordStatus.DRAFT, RecordStatus.APPROVED, RecordStatus.SENT])
    ).scalar() or 0

    # Invoices — pending
    inv_q = db.query(func.count(Invoice.id))
    if project_id:
        inv_q = inv_q.filter(Invoice.project_id == project_id)
    pending_invoice_count = inv_q.filter(
        Invoice.status.in_([RecordStatus.DRAFT, RecordStatus.SUBMITTED])
    ).scalar() or 0

    # Payments — pending approval
    pay_q = db.query(func.count(Payment.id))
    if project_id:
        pay_q = pay_q.filter(Payment.project_id == project_id)
    pending_payment_count = pay_q.filter(Payment.status == PaymentStatus.PENDING).scalar() or 0

    # Total paid amount
    paid_q = db.query(func.coalesce(func.sum(Payment.amount_paid), 0))
    if project_id:
        paid_q = paid_q.filter(Payment.project_id == project_id)
    total_paid = float(paid_q.filter(Payment.status == PaymentStatus.PAID).scalar() or 0)

    # Open alerts
    alert_q = db.query(func.count(SystemAlert.id))
    if project_id:
        alert_q = alert_q.filter(SystemAlert.project_id == project_id)
    open_alert_count = alert_q.filter(SystemAlert.status == AlertStatus.OPEN).scalar() or 0

    # Fuel — total cost across all logs (NULL total_cost rows excluded via coalesce)
    fuel_q = db.query(func.coalesce(func.sum(FuelLog.total_cost), 0))
    if project_id:
        fuel_q = fuel_q.filter(FuelLog.project_id == project_id)
    fuel_total_cost = float(fuel_q.scalar() or 0)

    # Fuel — total litres
    fuel_litres_q = db.query(func.coalesce(func.sum(FuelLog.litres), 0))
    if project_id:
        fuel_litres_q = fuel_litres_q.filter(FuelLog.project_id == project_id)
    fuel_total_litres = float(fuel_litres_q.scalar() or 0)

    return {
        "active_projects": active_project_count,
        "total_projects": total_project_count,
        "active_sites": site_count,
        "total_lots": lot_count,
        "open_purchase_orders": open_po_count,
        "pending_invoices": pending_invoice_count,
        "pending_payments": pending_payment_count,
        "total_paid_amount": total_paid,
        "open_alerts": open_alert_count,
        "fuel_total_cost": fuel_total_cost,
        "fuel_total_litres": fuel_total_litres,
    }


def get_project_operations(db: Session) -> list[dict]:
    """
    Per-project operational overview for the office dashboard.

    Returns one record per active project with:
      - lots (total, completed, in_progress)
      - milestones (completed, total)
      - active_material_requests
      - open_alerts
      - total_paid
    All in 6 bulk queries to avoid N+1.
    """
    projects = (
        db.query(Project)
        .filter(Project.status == ProjectStatus.ACTIVE)
        .order_by(Project.name)
        .all()
    )
    if not projects:
        return []

    project_ids = [p.id for p in projects]

    # Bulk Q1: lot counts per project by status
    lot_rows = (
        db.query(Lot.project_id, Lot.status, func.count(Lot.id).label("cnt"))
        .filter(Lot.project_id.in_(project_ids))
        .group_by(Lot.project_id, Lot.status)
        .all()
    )
    lots_by_proj: dict = {}
    for row in lot_rows:
        pid = str(row.project_id)
        lots_by_proj.setdefault(pid, {})
        lots_by_proj[pid][row.status.value if hasattr(row.status, "value") else row.status] = row.cnt

    # Bulk Q2: milestone counts per project by status
    ms_rows = (
        db.query(
            ProjectStageStatus.project_id,
            ProjectStageStatus.status,
            func.count(ProjectStageStatus.id).label("cnt"),
        )
        .filter(ProjectStageStatus.project_id.in_(project_ids))
        .group_by(ProjectStageStatus.project_id, ProjectStageStatus.status)
        .all()
    )
    ms_by_proj: dict = {}
    for row in ms_rows:
        pid = str(row.project_id)
        ms_by_proj.setdefault(pid, {})
        ms_by_proj[pid][row.status.value if hasattr(row.status, "value") else row.status] = row.cnt

    # Bulk Q3: active material requests per project
    mr_rows = (
        db.query(MaterialRequest.project_id, func.count(MaterialRequest.id).label("cnt"))
        .filter(
            MaterialRequest.project_id.in_(project_ids),
            MaterialRequest.status.in_([
                RecordStatus.DRAFT, RecordStatus.SUBMITTED, RecordStatus.PENDING_APPROVAL
            ]),
        )
        .group_by(MaterialRequest.project_id)
        .all()
    )
    mr_by_proj = {str(r.project_id): r.cnt for r in mr_rows}

    # Bulk Q4: open alerts per project
    alert_rows = (
        db.query(SystemAlert.project_id, func.count(SystemAlert.id).label("cnt"))
        .filter(
            SystemAlert.project_id.in_(project_ids),
            SystemAlert.status == AlertStatus.OPEN,
        )
        .group_by(SystemAlert.project_id)
        .all()
    )
    alerts_by_proj = {str(r.project_id): r.cnt for r in alert_rows}

    # Bulk Q5: total paid per project
    paid_rows = (
        db.query(Payment.project_id, func.coalesce(func.sum(Payment.amount_paid), 0).label("total"))
        .filter(Payment.project_id.in_(project_ids), Payment.status == PaymentStatus.PAID)
        .group_by(Payment.project_id)
        .all()
    )
    paid_by_proj = {str(r.project_id): float(r.total) for r in paid_rows}

    # Bulk Q6: site count per project
    site_rows = (
        db.query(Site.project_id, func.count(Site.id).label("cnt"))
        .filter(Site.project_id.in_(project_ids), Site.is_active == True)  # noqa
        .group_by(Site.project_id)
        .all()
    )
    sites_by_proj = {str(r.project_id): r.cnt for r in site_rows}

    result = []
    for p in projects:
        pid = str(p.id)
        lots    = lots_by_proj.get(pid, {})
        ms      = ms_by_proj.get(pid, {})

        total_lots      = sum(lots.values())
        lots_completed  = lots.get("COMPLETED", 0)
        lots_progress   = lots.get("IN_PROGRESS", 0)

        done_statuses   = {"COMPLETED", "CERTIFIED"}
        ms_done         = sum(v for k, v in ms.items() if k in done_statuses)
        ms_total        = sum(ms.values())
        progress_pct    = round((ms_done / ms_total * 100) if ms_total > 0 else 0.0, 1)

        result.append({
            "project_id":               pid,
            "project_name":             p.name,
            "project_code":             p.code or "",
            "site_count":               sites_by_proj.get(pid, 0),
            "total_lots":               total_lots,
            "lots_completed":           lots_completed,
            "lots_in_progress":         lots_progress,
            "milestones_completed":     ms_done,
            "total_milestones":         ms_total,
            "progress_pct":             progress_pct,
            "active_material_requests": mr_by_proj.get(pid, 0),
            "open_alerts":              alerts_by_proj.get(pid, 0),
            "total_paid":               paid_by_proj.get(pid, 0.0),
        })
    return result


def get_ops_summary(db: Session, project_id: Optional[uuid.UUID] = None) -> dict:
    """
    Operational command-center summary: what needs attention right now?

    Returns 4 sections in 6 bulk queries — NO N+1 queries.
    All counts only, all periods bounded (current month, last 7 days).

    Sections:
      financial  — invoices outstanding/overdue/partial/overpaid, payments this month
      milestones — blocked, in-progress, delayed, completed this week
      warehouse  — projects with warehouse stock, recent transfer count
      fuel       — total cost this month, flagged (high consumption) entries
    """
    from datetime import date, timedelta
    from sqlalchemy import and_

    # Period bounds
    today = date.today()
    first_of_month = today.replace(day=1)
    seven_days_ago = today - timedelta(days=7)

    # ── Financial ───────────────────────────────────────────────────────────
    inv_q = db.query(Invoice)
    pay_q = db.query(Payment)
    if project_id:
        inv_q = inv_q.filter(Invoice.project_id == project_id)
        pay_q = pay_q.filter(Payment.project_id == project_id)

    unpaid_statuses = [
        RecordStatus.MATCHED, RecordStatus.RECEIVED, RecordStatus.APPROVED,
        RecordStatus.PARTIALLY_PAID,
    ]

    # Outstanding + overdue (one pass, two accumulators)
    unpaid_invoices = inv_q.filter(Invoice.status.in_(unpaid_statuses)).all()
    outstanding_count = len(unpaid_invoices)
    outstanding_total = sum(float(i.total_amount or 0) for i in unpaid_invoices)
    overdue_count     = sum(1 for i in unpaid_invoices if i.due_date and i.due_date < today)
    overdue_total     = sum(float(i.total_amount or 0) for i in unpaid_invoices
                            if i.due_date and i.due_date < today)

    # Partial + overpaid counts
    partial_count  = inv_q.filter(Invoice.status == RecordStatus.PARTIALLY_PAID).count()
    overpaid_count = inv_q.filter(Invoice.status == RecordStatus.OVERPAID).count()

    # Payments this month (PAID status only)
    pay_this_month = float(
        db.query(func.coalesce(func.sum(Payment.amount_paid), 0))
        .filter(*([Payment.project_id == project_id] if project_id else []))
        .filter(Payment.status == PaymentStatus.PAID)
        .filter(Payment.payment_date >= first_of_month)
        .scalar() or 0
    )

    # ── Milestones ───────────────────────────────────────────────────────────
    ms_q = db.query(ProjectStageStatus)
    if project_id:
        ms_q = ms_q.filter(ProjectStageStatus.project_id == project_id)

    blocked_count    = ms_q.filter(ProjectStageStatus.status == StageStatus.BLOCKED).count()
    in_prog_count    = ms_q.filter(ProjectStageStatus.status == StageStatus.IN_PROGRESS).count()

    # Delayed: IN_PROGRESS + started > 30 days ago + progress_pct < 50
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import TIMESTAMP
    thirty_days_ago = today - timedelta(days=30)
    delayed_count = ms_q.filter(
        ProjectStageStatus.status     == StageStatus.IN_PROGRESS,
        ProjectStageStatus.started_at <= str(thirty_days_ago),
        ProjectStageStatus.progress_pct < 50,
    ).count()

    # Completed this week
    completed_week = ms_q.filter(
        ProjectStageStatus.status.in_([StageStatus.COMPLETED, StageStatus.CERTIFIED]),
        ProjectStageStatus.completed_at >= str(seven_days_ago),
    ).count()

    # ── Warehouse ────────────────────────────────────────────────────────────
    from app.models.stock import StockLedger
    from app.models.enums import MovementType as _MT

    # Projects that have any stock in project warehouse (site_id=NULL, lot_id=NULL)
    wh_q = db.query(func.count(func.distinct(StockLedger.project_id))).filter(
        StockLedger.site_id.is_(None),
        StockLedger.lot_id.is_(None),
    )
    if project_id:
        wh_q = wh_q.filter(StockLedger.project_id == project_id)
    projects_with_stock = int(wh_q.scalar() or 0)

    # Recent transfers (last 7 days)
    transfer_q = db.query(func.count(StockLedger.id)).filter(
        StockLedger.movement_type == _MT.TRANSFER_IN,
        StockLedger.movement_date >= str(seven_days_ago),
    )
    if project_id:
        transfer_q = transfer_q.filter(StockLedger.project_id == project_id)
    recent_transfers = int(transfer_q.scalar() or 0)

    # ── Fuel ─────────────────────────────────────────────────────────────────
    fuel_q = db.query(FuelLog)
    if project_id:
        fuel_q = fuel_q.filter(FuelLog.project_id == project_id)

    fuel_cost_month = float(
        db.query(func.coalesce(func.sum(FuelLog.total_cost), 0))
        .filter(*([FuelLog.project_id == project_id] if project_id else []))
        .filter(FuelLog.fuel_date >= str(first_of_month))
        .scalar() or 0
    )
    # Flagged: notes contain "⚠" (set by fuel service when l_per_100km > threshold)
    flagged_fuel = fuel_q.filter(FuelLog.notes.like("%⚠%")).count()

    return {
        "financial": {
            "outstanding_invoice_count": outstanding_count,
            "outstanding_total":         round(outstanding_total, 2),
            "overdue_count":             overdue_count,
            "overdue_total":             round(overdue_total, 2),
            "partially_paid_count":      partial_count,
            "overpaid_count":            overpaid_count,
            "payments_this_month":       round(pay_this_month, 2),
        },
        "milestones": {
            "blocked_count":         blocked_count,
            "in_progress_count":     in_prog_count,
            "delayed_count":         delayed_count,
            "completed_this_week":   completed_week,
        },
        "warehouse": {
            "projects_with_stock":   projects_with_stock,
            "recent_transfer_count": recent_transfers,
        },
        "fuel": {
            "total_cost_this_month":  round(fuel_cost_month, 2),
            "flagged_entries_count":  flagged_fuel,
        },
    }
