"""Dashboard stats service."""

import uuid
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.alert import SystemAlert
from app.models.delivery import Delivery
from app.models.enums import AlertStatus, PaymentStatus, ProjectStatus, RecordStatus
from app.models.fuel import FuelLog
from app.models.invoice import Invoice
from app.models.lot import Lot
from app.models.payment import Payment
from app.models.project import Project
from app.models.purchase_order import PurchaseOrder
from app.models.site import Site


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
