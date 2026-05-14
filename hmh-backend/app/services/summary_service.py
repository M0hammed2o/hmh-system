"""
Daily business summary service.

Computes a single snapshot of the business state: spend today/week/month,
deliveries, alerts, lot statuses, vehicle costs. Used by the owner dashboard
and the daily WhatsApp summary.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.alert import SystemAlert
from app.models.enums import AlertStatus, AlertType, LotStatus, PaymentStatus, RecordStatus
from app.models.invoice import Invoice
from app.models.lot import Lot
from app.models.payment import Payment
from app.models.stock import StockLedger
from app.models.vehicle import VehicleCost


@dataclass
class DailySummary:
    # Date range
    date_today: date

    # Spend
    spend_today: float
    spend_week: float
    spend_month: float

    # Deliveries
    deliveries_today: int

    # Lots
    active_lots: int
    delayed_lots: int
    completed_lots: int

    # Alerts
    open_alerts: int
    material_overrun_alerts: int
    unmatched_invoices: int

    # Vehicle
    vehicle_spend_today: float
    vehicle_spend_month: float

    # Cash burn
    burn_rate_daily_avg: float  # average daily spend over last 30 days


def get_daily_summary(db: Session, project_id: Optional[uuid.UUID] = None) -> DailySummary:
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    thirty_days_ago = today_start - timedelta(days=30)

    def payment_spend(from_dt: datetime, to_dt: Optional[datetime] = None) -> float:
        q = (
            db.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(
                Payment.status == PaymentStatus.PAID,
                Payment.payment_date >= from_dt.date(),
            )
        )
        if to_dt:
            q = q.filter(Payment.payment_date < to_dt.date())
        if project_id:
            q = q.filter(Payment.project_id == project_id)
        return float(q.scalar() or 0)

    spend_today = payment_spend(today_start)
    spend_week = payment_spend(week_start)
    spend_month = payment_spend(month_start)

    # Deliveries today
    from app.models.delivery import Delivery
    del_q = db.query(func.count(Delivery.id)).filter(
        Delivery.delivery_date >= today_start
    )
    if project_id:
        del_q = del_q.filter(Delivery.project_id == project_id)
    deliveries_today = int(del_q.scalar() or 0)

    # Lot statuses
    lot_q = db.query(Lot)
    if project_id:
        lot_q = lot_q.filter(Lot.project_id == project_id)
    lots = lot_q.all()
    active_lots = sum(1 for l in lots if l.status == LotStatus.IN_PROGRESS)
    completed_lots = sum(1 for l in lots if l.status == LotStatus.COMPLETED)

    # Delayed = past expected_completion_date and not completed
    today = now.date()
    delayed_lots = sum(
        1 for l in lots
        if l.expected_completion_date
        and l.expected_completion_date < today
        and l.status not in (LotStatus.COMPLETED,)
    )

    # Alerts
    alert_q = db.query(SystemAlert).filter(SystemAlert.status == AlertStatus.OPEN)
    if project_id:
        alert_q = alert_q.filter(SystemAlert.project_id == project_id)
    alerts = alert_q.all()
    open_alerts = len(alerts)
    material_overrun_alerts = sum(1 for a in alerts if a.alert_type == AlertType.MATERIAL_OVERUSE)

    # Unmatched invoices
    inv_q = db.query(func.count(Invoice.id)).filter(
        Invoice.status.notin_([RecordStatus.MATCHED, RecordStatus.PAID, RecordStatus.CANCELLED])
    )
    if project_id:
        inv_q = inv_q.filter(Invoice.project_id == project_id)
    unmatched_invoices = int(inv_q.scalar() or 0)

    # Vehicle costs
    vc_today_q = db.query(func.coalesce(func.sum(VehicleCost.amount), 0)).filter(
        VehicleCost.cost_date >= today_start.date()
    )
    if project_id:
        vc_today_q = vc_today_q.filter(VehicleCost.project_id == project_id)
    vehicle_spend_today = float(vc_today_q.scalar() or 0)

    vc_month_q = db.query(func.coalesce(func.sum(VehicleCost.amount), 0)).filter(
        VehicleCost.cost_date >= month_start.date()
    )
    if project_id:
        vc_month_q = vc_month_q.filter(VehicleCost.project_id == project_id)
    vehicle_spend_month = float(vc_month_q.scalar() or 0)

    # 30-day burn rate
    spend_30d = payment_spend(thirty_days_ago)
    burn_rate_daily_avg = spend_30d / 30.0

    return DailySummary(
        date_today=today,
        spend_today=spend_today,
        spend_week=spend_week,
        spend_month=spend_month,
        deliveries_today=deliveries_today,
        active_lots=active_lots,
        delayed_lots=delayed_lots,
        completed_lots=completed_lots,
        open_alerts=open_alerts,
        material_overrun_alerts=material_overrun_alerts,
        unmatched_invoices=unmatched_invoices,
        vehicle_spend_today=vehicle_spend_today,
        vehicle_spend_month=vehicle_spend_month,
        burn_rate_daily_avg=burn_rate_daily_avg,
    )
