"""System alert routes — CRUD, acknowledge/resolve, WhatsApp recipients, notification queue."""

import uuid
from typing import Optional

from fastapi import APIRouter, Query

from app.dependencies import ALL_ROLES, CurrentUser, DbSession, OFFICE_AND_ABOVE
from app.models.enums import AlertStatus, NotificationStatus
from app.schemas.alert import AlertRead, AlertUpdate
from app.schemas.common import ApiSuccess
from app.schemas.notification import (
    AlertRecipientCreate,
    AlertRecipientRead,
    AlertRecipientUpdate,
    NotificationQueueRead,
    QueueStats,
)
from app.core.config import settings
from app.core.logging_config import get_logger
from app.services import alert_service, notification_service, recipient_service

logger = get_logger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


# ── Alert list + update ───────────────────────────────────────────────────────

@router.get("/", response_model=ApiSuccess[list[AlertRead]], dependencies=[ALL_ROLES])
def list_alerts(
    db: DbSession,
    project_id: Optional[uuid.UUID] = Query(None),
    status: Optional[AlertStatus] = Query(None),
    alert_type: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
):
    from app.models.project import Project
    from app.models.site import Site

    alerts = alert_service.list_alerts(db, project_id, status, limit, alert_type)

    # Batch-enrich with project/site names (avoids N+1 queries)
    pids = {a.project_id for a in alerts if a.project_id}
    sids = {a.site_id for a in alerts if a.site_id}
    pmap = {p.id: p.name for p in db.query(Project).filter(Project.id.in_(pids)).all()} if pids else {}
    smap = {s.id: s.name for s in db.query(Site).filter(Site.id.in_(sids)).all()} if sids else {}

    result = []
    for a in alerts:
        read = AlertRead.model_validate(a)
        read.project_name = pmap.get(a.project_id)
        read.site_name = smap.get(a.site_id)
        result.append(read)

    return ApiSuccess(data=result)


@router.get("/{alert_id}/context", response_model=ApiSuccess[dict], dependencies=[ALL_ROLES])
def get_alert_context(alert_id: uuid.UUID, db: DbSession):
    """Returns the alert plus enriched context fetched from the referenced record."""
    from fastapi import HTTPException
    from app.models.alert import SystemAlert
    from app.models.project import Project
    from app.models.site import Site

    alert = db.get(SystemAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")

    base = AlertRead.model_validate(alert).model_dump()

    # Enrich with project/site names
    if alert.project_id:
        p = db.get(Project, alert.project_id)
        base["project_name"] = p.name if p else None
    if alert.site_id:
        s = db.get(Site, alert.site_id)
        base["site_name"] = s.name if s else None

    # Fetch referenced record details
    context: dict = {}
    try:
        if alert.reference_type == "material_request" and alert.reference_id:
            from app.models.material_request import MaterialRequest, MaterialRequestItem
            mr = db.get(MaterialRequest, alert.reference_id)
            if mr:
                items = (
                    db.query(MaterialRequestItem)
                    .filter(MaterialRequestItem.material_request_id == mr.id)
                    .all()
                )
                context = {
                    "request_number": mr.request_number,
                    "status": mr.status.value if mr.status else None,
                    "items": [
                        {
                            "name": item.description or str(item.id)[:8],
                            "quantity": float(item.requested_quantity or 0),
                            "unit": item.unit or "",
                        }
                        for item in items
                    ],
                }

        elif alert.reference_type == "invoice" and alert.reference_id:
            from app.models.invoice import Invoice
            from app.models.supplier import Supplier
            inv = db.get(Invoice, alert.reference_id)
            if inv:
                sup = db.get(Supplier, inv.supplier_id) if inv.supplier_id else None
                context = {
                    "invoice_number": inv.invoice_number,
                    "amount": float(inv.total_amount or 0),
                    "due_date": inv.due_date.isoformat() if inv.due_date else None,
                    "status": inv.status.value if inv.status else None,
                    "supplier_name": sup.name if sup else None,
                }

        elif alert.reference_type == "delivery" and alert.reference_id:
            from app.models.delivery import Delivery
            d = db.get(Delivery, alert.reference_id)
            if d:
                context = {
                    "delivery_number": d.delivery_number or str(d.id)[:8],
                    "status": d.delivery_status.value if d.delivery_status else None,
                    "delivery_date": d.delivery_date.isoformat() if d.delivery_date else None,
                    "has_signature": d.signature_image_url is not None,
                    "has_po": d.purchase_order_id is not None,
                }
    except Exception:
        pass  # context is best-effort — never crash the alert endpoint

    base["context"] = context
    return ApiSuccess(data=base)


@router.patch("/{alert_id}", response_model=ApiSuccess[AlertRead], dependencies=[ALL_ROLES])
def update_alert(alert_id: uuid.UUID, body: AlertUpdate, db: DbSession, current_user: CurrentUser):
    alert = alert_service.update_alert(db, alert_id, body, current_user.id)
    return ApiSuccess(data=AlertRead.model_validate(alert), message="Alert updated.")


@router.post("/{alert_id}/acknowledge", response_model=ApiSuccess[AlertRead], dependencies=[ALL_ROLES])
def acknowledge_alert(alert_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    from app.schemas.alert import AlertUpdate as AU
    alert = alert_service.update_alert(db, alert_id, AU(status=AlertStatus.ACKNOWLEDGED), current_user.id)
    return ApiSuccess(data=AlertRead.model_validate(alert), message="Alert acknowledged.")


@router.post("/{alert_id}/resolve", response_model=ApiSuccess[AlertRead], dependencies=[ALL_ROLES])
def resolve_alert(alert_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    from app.schemas.alert import AlertUpdate as AU
    alert = alert_service.update_alert(db, alert_id, AU(status=AlertStatus.RESOLVED), current_user.id)
    return ApiSuccess(data=AlertRead.model_validate(alert), message="Alert resolved.")


@router.post("/resolve-all", response_model=ApiSuccess[dict], dependencies=[ALL_ROLES])
def resolve_all_alerts(
    db: DbSession,
    current_user: CurrentUser,
    project_id: Optional[uuid.UUID] = Query(None),
):
    """Resolve every OPEN alert in one go — they move to history (RESOLVED)."""
    from app.models.alert import SystemAlert
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    q = db.query(SystemAlert).filter(SystemAlert.status == AlertStatus.OPEN)
    if project_id:
        q = q.filter(SystemAlert.project_id == project_id)
    alerts = q.all()
    for a in alerts:
        a.status = AlertStatus.RESOLVED
        a.resolved_at = now
        a.resolved_by = current_user.id
    db.commit()
    return ApiSuccess(data={"resolved": len(alerts)}, message=f"{len(alerts)} alert(s) moved to history.")


# ── Alert stats ───────────────────────────────────────────────────────────────

@router.get("/stats", response_model=ApiSuccess[dict], dependencies=[ALL_ROLES])
def get_alert_stats(db: DbSession, project_id: Optional[uuid.UUID] = Query(None)):
    stats = alert_service.get_stats(db, project_id)
    return ApiSuccess(data=stats)


# ── Daily summary ─────────────────────────────────────────────────────────────

@router.post("/daily-summary", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def generate_daily_summary(db: DbSession):
    """Build daily summary text and optionally send to all daily-summary recipients."""
    text = notification_service.build_daily_summary_text(db)

    # Enqueue for all daily-summary recipients
    from app.models.enums import AlertSeverity, AlertType
    from app.models.alert import SystemAlert
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    summary_alert = SystemAlert(
        alert_type=AlertType.DAILY_SUMMARY,
        severity=AlertSeverity.LOW,
        title="Daily Business Summary",
        message=text,
        status=AlertStatus.OPEN,
        notification_channel="in_app",
        created_at=now,
    )
    db.add(summary_alert)
    db.flush()

    queued = notification_service.enqueue_for_alert(db, summary_alert)
    counts = notification_service.process_queue(db)

    return ApiSuccess(
        data={
            "summary_text": text,
            "queued": len(queued),
            "send_counts": counts,
        },
        message="Daily summary generated.",
    )


# ── Proactive alert scan ──────────────────────────────────────────────────────

@router.post("/scan", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def scan_and_create_alerts(db: DbSession, project_id: Optional[uuid.UUID] = Query(None), current_user: CurrentUser = None):
    """
    Proactive scan: creates alerts for conditions that aren't triggered by events.
    Covers: low/negative stock, overdue payments, long-pending MRs, deliveries without PO,
    missing delivery notes, missing signatures.
    Safe to call repeatedly — deduplicates by checking for existing OPEN alerts of the same type.
    """
    role = current_user.role.value if current_user else "unknown"
    logger.info("alert_scan user=%s role=%s project_id=%s", getattr(current_user, 'id', None), role, project_id)
    from datetime import datetime, timezone, timedelta
    from app.models.alert import SystemAlert
    from app.models.enums import (
        AlertType, AlertSeverity, AlertStatus, RecordStatus, MovementType
    )
    from app.models.stock import StockLedger
    from app.models.item import Item
    from app.models.project import Project
    from app.models.site import Site
    from app.models.delivery import Delivery
    from app.models.invoice import Invoice
    from app.models.material_request import MaterialRequest
    from app.core.config import settings

    now = datetime.now(timezone.utc)
    created = 0

    def _already_open(project_id_val, site_id_val, alert_type: AlertType) -> bool:
        """Return True if an OPEN alert of this type already exists."""
        q = db.query(SystemAlert).filter(
            SystemAlert.alert_type == alert_type,
            SystemAlert.status == AlertStatus.OPEN,
        )
        if project_id_val:
            q = q.filter(SystemAlert.project_id == project_id_val)
        if site_id_val:
            q = q.filter(SystemAlert.site_id == site_id_val)
        return q.first() is not None

    def _add(alert: SystemAlert) -> None:
        nonlocal created
        db.add(alert)
        created += 1

    # ── Determine scope ───────────────────────────────────────────────────────
    projects = db.query(Project).filter(
        Project.id == project_id if project_id else True
    ).all()

    for project in projects:
        pid = project.id

        # 1. Low / Negative stock ──────────────────────────────────────────────
        from sqlalchemy import func, text as _t
        try:
            low_threshold = float(getattr(settings, "LOW_STOCK_THRESHOLD", 5))
        except Exception:
            low_threshold = 5.0

        try:
            neg_rows = db.execute(_t("""
                SELECT item_id, site_id, SUM(quantity_in) - SUM(quantity_out) AS balance
                FROM stock_ledger
                WHERE project_id = :pid
                GROUP BY item_id, site_id
                HAVING SUM(quantity_in) - SUM(quantity_out) < :threshold
            """), {"pid": pid, "threshold": low_threshold}).mappings().all()

            for row in neg_rows:
                atype = AlertType.NEGATIVE_STOCK if row["balance"] < 0 else AlertType.LOW_STOCK
                if not _already_open(pid, row["site_id"], atype):
                    item = db.get(Item, row["item_id"])
                    stock_alert = SystemAlert(
                        project_id=pid, site_id=row["site_id"],
                        alert_type=atype,
                        severity=AlertSeverity.HIGH if row["balance"] < 0 else AlertSeverity.MEDIUM,
                        title=f"{'Negative' if row['balance'] < 0 else 'Low'} stock: {item.name if item else row['item_id']}",
                        message=f"Balance is {row['balance']:.2f} {'(below zero — over-issued)' if row['balance'] < 0 else f'(below threshold {low_threshold})'}.",
                        status=AlertStatus.OPEN,
                        notification_channel="whatsapp",  # Phase 3Q.2: enqueue for WhatsApp
                        created_at=now,
                    )
                    _add(stock_alert)
                    # Phase 3Q.2: enqueue WhatsApp notification (best-effort, after flush)
                    try:
                        db.flush()
                        from app.services import notification_service
                        notification_service.enqueue_for_alert(db, stock_alert)
                    except Exception:
                        pass
        except Exception:
            pass

        # 2. Overdue invoices ──────────────────────────────────────────────────
        from datetime import date
        overdue_invs = (
            db.query(Invoice)
            .filter(
                Invoice.project_id == pid,
                Invoice.due_date < now.date(),
                Invoice.status.notin_([RecordStatus.PAID, RecordStatus.CANCELLED]),
            )
            .all()
        )
        for inv in overdue_invs:
            if not _already_open(pid, None, AlertType.OVERDUE_PAYMENT):
                overdue_alert = SystemAlert(
                    project_id=pid,
                    reference_type="invoice",
                    reference_id=inv.id,
                    alert_type=AlertType.OVERDUE_PAYMENT,
                    severity=AlertSeverity.HIGH,
                    title=f"Overdue invoice: {inv.invoice_number}",
                    message=f"Invoice {inv.invoice_number} was due {inv.due_date}.",
                    status=AlertStatus.OPEN,
                    notification_channel="whatsapp",  # Phase 3Q.3: upgraded from in_app
                    created_at=now,
                )
                _add(overdue_alert)
                # Phase 3Q.3: enqueue WhatsApp notification (best-effort)
                try:
                    db.flush()
                    from app.services import notification_service
                    notification_service.enqueue_for_alert(db, overdue_alert)
                except Exception:
                    pass
                break  # one alert per project

        # 2b. Payment due soon ─────────────────────────────────────────────────
        try:
            due_days = int(getattr(settings, "PAYMENT_DUE_DAYS", 3))
        except Exception:
            due_days = 3
        due_cutoff = now.date() + timedelta(days=due_days)
        upcoming_invs = (
            db.query(Invoice)
            .filter(
                Invoice.project_id == pid,
                Invoice.due_date > now.date(),
                Invoice.due_date <= due_cutoff,
                Invoice.status.notin_([RecordStatus.PAID, RecordStatus.CANCELLED]),
            )
            .all()
        )
        for inv in upcoming_invs:
            if not _already_open(pid, None, AlertType.PAYMENT_DUE):
                days_left = (inv.due_date - now.date()).days
                due_alert = SystemAlert(
                    project_id=pid,
                    reference_type="invoice",
                    reference_id=inv.id,
                    alert_type=AlertType.PAYMENT_DUE,
                    severity=AlertSeverity.MEDIUM,
                    title=f"Payment Due Soon: {inv.invoice_number}",
                    message=(
                        f"Invoice {inv.invoice_number} "
                        f"(R{float(inv.total_amount):,.2f}) "
                        f"is due in {days_left} day(s) on {inv.due_date}."
                    ),
                    status=AlertStatus.OPEN,
                    notification_channel="whatsapp",
                    created_at=now,
                )
                _add(due_alert)
                try:
                    db.flush()
                    from app.services import notification_service
                    notification_service.enqueue_for_alert(db, due_alert)
                except Exception:
                    pass
                break  # one alert per project per scan

        # 3. Material Requests pending too long ────────────────────────────────
        try:
            pending_days = int(getattr(settings, "PENDING_MR_DAYS", 5))
        except Exception:
            pending_days = 5
        cutoff = now - timedelta(days=pending_days)
        stale_mrs = (
            db.query(MaterialRequest)
            .filter(
                MaterialRequest.project_id == pid,
                MaterialRequest.status.in_([RecordStatus.SUBMITTED, RecordStatus.PENDING_APPROVAL]),
                MaterialRequest.created_at < cutoff,
            )
            .all()
        )
        for mr in stale_mrs:
            if not _already_open(pid, mr.site_id, AlertType.REQUEST_PENDING_TOO_LONG):
                _add(SystemAlert(
                    project_id=pid, site_id=mr.site_id,
                    reference_type="material_request", reference_id=mr.id,
                    alert_type=AlertType.REQUEST_PENDING_TOO_LONG,
                    severity=AlertSeverity.MEDIUM,
                    title=f"MR pending too long: {mr.request_number}",
                    message=f"Material request {mr.request_number} has been pending for over {pending_days} days.",
                    status=AlertStatus.OPEN,
                    notification_channel="in_app",
                    created_at=now,
                ))

        # 4. Deliveries without PO ────────────────────────────────────────────
        no_po_dels = (
            db.query(Delivery)
            .filter(
                Delivery.project_id == pid,
                Delivery.purchase_order_id.is_(None),
                Delivery.created_at > now - timedelta(days=30),
            )
            .all()
        )
        for d in no_po_dels:
            if not _already_open(pid, d.site_id, AlertType.DELIVERY_WITHOUT_PO):
                _add(SystemAlert(
                    project_id=pid, site_id=d.site_id,
                    reference_type="delivery", reference_id=d.id,
                    alert_type=AlertType.DELIVERY_WITHOUT_PO,
                    severity=AlertSeverity.MEDIUM,
                    title=f"Delivery without PO: {d.delivery_number or str(d.id)[:8]}",
                    message="This delivery was received without a linked Purchase Order (PO).",
                    status=AlertStatus.OPEN,
                    notification_channel="in_app",
                    created_at=now,
                ))
                break  # one alert per project for this type

        # 5. Missing signatures ────────────────────────────────────────────────
        unsigned_dels = (
            db.query(Delivery)
            .filter(
                Delivery.project_id == pid,
                Delivery.signature_image_url.is_(None),
                Delivery.created_at > now - timedelta(days=30),
            )
            .limit(5)
            .all()
        )
        for d in unsigned_dels:
            if not _already_open(pid, d.site_id, AlertType.DELIVERY_SIGNATURE_MISSING):
                _add(SystemAlert(
                    project_id=pid, site_id=d.site_id,
                    reference_type="delivery", reference_id=d.id,
                    alert_type=AlertType.DELIVERY_SIGNATURE_MISSING,
                    severity=AlertSeverity.LOW,
                    title=f"Missing signature: {d.delivery_number or str(d.id)[:8]}",
                    message="Delivery was recorded without a receiver signature.",
                    status=AlertStatus.OPEN,
                    notification_channel="in_app",
                    created_at=now,
                ))
                break

    db.commit()
    return ApiSuccess(
        data={"alerts_created": created, "projects_scanned": len(projects)},
        message=f"{created} alert(s) created.",
    )


# ── WhatsApp Recipients ───────────────────────────────────────────────────────

@router.get("/recipients", response_model=ApiSuccess[list[AlertRecipientRead]], dependencies=[ALL_ROLES])
def list_recipients(db: DbSession):
    recipients = recipient_service.list_recipients(db)
    return ApiSuccess(data=[AlertRecipientRead.model_validate(r) for r in recipients])


@router.post("/recipients", response_model=ApiSuccess[AlertRecipientRead], status_code=201, dependencies=[OFFICE_AND_ABOVE])
def create_recipient(body: AlertRecipientCreate, db: DbSession, current_user: CurrentUser):
    recipient = recipient_service.create_recipient(db, body, created_by=current_user.id)
    return ApiSuccess(data=AlertRecipientRead.model_validate(recipient), message="Recipient added.")


@router.patch("/recipients/{recipient_id}", response_model=ApiSuccess[AlertRecipientRead], dependencies=[OFFICE_AND_ABOVE])
def update_recipient(recipient_id: uuid.UUID, body: AlertRecipientUpdate, db: DbSession):
    recipient = recipient_service.update_recipient(db, recipient_id, body)
    return ApiSuccess(data=AlertRecipientRead.model_validate(recipient), message="Recipient updated.")


@router.patch("/recipients/{recipient_id}/activate", response_model=ApiSuccess[AlertRecipientRead], dependencies=[OFFICE_AND_ABOVE])
def activate_recipient(recipient_id: uuid.UUID, db: DbSession):
    from app.schemas.notification import AlertRecipientUpdate as ARU
    recipient = recipient_service.update_recipient(db, recipient_id, ARU(is_active=True))
    return ApiSuccess(data=AlertRecipientRead.model_validate(recipient), message="Recipient activated.")


@router.patch("/recipients/{recipient_id}/deactivate", response_model=ApiSuccess[AlertRecipientRead], dependencies=[OFFICE_AND_ABOVE])
def deactivate_recipient_toggle(recipient_id: uuid.UUID, db: DbSession):
    from app.schemas.notification import AlertRecipientUpdate as ARU
    recipient = recipient_service.update_recipient(db, recipient_id, ARU(is_active=False))
    return ApiSuccess(data=AlertRecipientRead.model_validate(recipient), message="Recipient deactivated.")


@router.delete("/recipients/{recipient_id}", response_model=ApiSuccess[None], dependencies=[OFFICE_AND_ABOVE])
def delete_recipient(recipient_id: uuid.UUID, db: DbSession):
    """Permanently remove a recipient and all their notification history."""
    recipient_service.delete_recipient(db, recipient_id)
    return ApiSuccess(data=None, message="Recipient deleted.")


@router.post("/recipients/{recipient_id}/test", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def send_test_message(recipient_id: uuid.UUID, db: DbSession):
    """
    Send a test WhatsApp message to this recipient using the configured alert template.
    Blocked for inactive recipients.
    """
    from app.services import whatsapp_service
    from app.core.exceptions import ValidationError

    recipient = recipient_service.get_recipient(db, recipient_id)

    if not recipient.is_active:
        raise ValidationError("Recipient is inactive. Activate before testing.")

    template_name = settings.WHATSAPP_ALERT_TEMPLATE_NAME
    if not template_name:
        return ApiSuccess(
            data={"status": "NOT_CONFIGURED", "provider_message_id": None, "method": None,
                  "error": "WhatsApp template not configured. Set WHATSAPP_ALERT_TEMPLATE_NAME."},
            message="Template not configured.",
        )

    # Auto-resolve var_count and language from Meta API (cached).
    var_count, lang = whatsapp_service.resolve_template_params(template_name)
    test_params = [
        "Test Alert",
        "This is a test notification from HMH System. No action required.",
        "HMH Group",
    ]
    components: list | None = None
    if var_count > 0:
        parameters = [
            {"type": "text", "text": test_params[i] if i < len(test_params) else f"param{i+1}"}
            for i in range(var_count)
        ]
        components = [{"type": "body", "parameters": parameters}]

    logger.info(
        "wa_test_send template=%s lang=%s phone=%s var_count=%d",
        template_name, lang, recipient.phone_number, var_count,
    )
    status, msg_id = whatsapp_service.send_template_message(
        recipient.phone_number, template_name, lang, components=components
    )
    logger.info("wa_test_result status=%s msg_id=%s recipient=%s", status, msg_id, recipient.name)

    # Record in the notification queue so test results are visible in the queue UI
    # with a clear TEST marker — this does NOT send another message.
    from app.models.notification_queue import NotificationQueue
    from app.models.enums import NotificationChannel, NotificationStatus
    from datetime import datetime, timezone as _tz
    _now = datetime.now(_tz.utc)
    _queue_status = NotificationStatus.SENT if status == "SENT" else NotificationStatus.FAILED
    _entry = NotificationQueue(
        channel=NotificationChannel.WHATSAPP,
        phone_number=recipient.phone_number,
        message_body=(
            "[TEST] Test Alert\n"
            "This is a test notification from HMH System. No action required."
        ),
        status=_queue_status,
        attempt_count=1,
        last_attempt_at=_now,
        provider_message_id=msg_id or None,
        error_message=msg_id if status == "FAILED" else None,
        is_test=True,
        recipient_id=recipient.id,
        created_at=_now,
    )
    db.add(_entry)
    db.commit()

    return ApiSuccess(
        data={
            "status": status,
            "provider_message_id": msg_id,
            "method": "template",
            "template_used": template_name,
            "language_used": lang,
            "body_vars_sent": var_count,
            "queue_entry_id": str(_entry.id),
        },
        message=f"Test queued to WhatsApp API: {status}",
    )


@router.get("/whatsapp/template-info", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def get_whatsapp_template_info():
    """
    Fetch live template definition from Meta Graph API.
    Shows template name, language, status, body text, and exact variable count.
    Use this to verify WHATSAPP_ALERT_TEMPLATE_BODY_VAR_COUNT and language are correct.
    """
    from app.services import whatsapp_service
    template_name = settings.WHATSAPP_ALERT_TEMPLATE_NAME
    if not template_name:
        return ApiSuccess(data={
            "configured": False,
            "error": "WHATSAPP_ALERT_TEMPLATE_NAME not set",
        })

    info = whatsapp_service.fetch_template_info(template_name)
    if not info:
        return ApiSuccess(data={
            "configured": True,
            "template_name": template_name,
            "meta_api_reachable": False,
            "error": (
                "Could not fetch template from Meta API. "
                "Check WHATSAPP_BUSINESS_ACCOUNT_ID and WHATSAPP_ACCESS_TOKEN."
            ),
            "config_var_count": getattr(settings, "WHATSAPP_ALERT_TEMPLATE_BODY_VAR_COUNT", 2),
            "config_language": settings.WHATSAPP_ALERT_TEMPLATE_LANGUAGE or "en_US",
        })

    var_count = whatsapp_service.count_body_vars(info)
    body_text = next(
        (c.get("text", "") for c in info.get("components", [])
         if c.get("type", "").upper() == "BODY"),
        None,
    )
    cfg_var_count = getattr(settings, "WHATSAPP_ALERT_TEMPLATE_BODY_VAR_COUNT", 2)
    cfg_language  = settings.WHATSAPP_ALERT_TEMPLATE_LANGUAGE or "en_US"
    return ApiSuccess(data={
        "configured": True,
        "meta_api_reachable": True,
        "template_name": info.get("name"),
        "language": info.get("language"),
        "status": info.get("status"),
        "body_text": body_text,
        "body_var_count": var_count,
        "components": info.get("components", []),
        "config_var_count": cfg_var_count,
        "config_language": cfg_language,
        "mismatch_var_count": var_count != cfg_var_count,
        "mismatch_language": (info.get("language") or "") != cfg_language,
    })


# ── Notification Queue ────────────────────────────────────────────────────────

@router.get("/queue", response_model=ApiSuccess[list[NotificationQueueRead]], dependencies=[ALL_ROLES])
def get_notification_queue(
    db: DbSession,
    status: Optional[NotificationStatus] = Query(None),
    limit: int = Query(50, le=200),
):
    entries = notification_service.get_queue(db, status, limit)
    return ApiSuccess(data=[NotificationQueueRead.model_validate(e) for e in entries])


@router.get("/queue/stats", response_model=ApiSuccess[QueueStats], dependencies=[ALL_ROLES])
def get_queue_stats(db: DbSession):
    from sqlalchemy import func
    from app.models.notification_queue import NotificationQueue
    rows = (
        db.query(NotificationQueue.status, func.count(NotificationQueue.id))
        .group_by(NotificationQueue.status)
        .all()
    )
    counts = {r[0].value: r[1] for r in rows}
    return ApiSuccess(data=QueueStats(
        pending=counts.get("PENDING", 0),
        sent=counts.get("SENT", 0),
        mock_sent=counts.get("MOCK_SENT", 0),
        failed=counts.get("FAILED", 0),
        acknowledged=counts.get("ACKNOWLEDGED", 0),
        cancelled=counts.get("CANCELLED", 0),
    ))


@router.post("/queue/process", response_model=ApiSuccess[dict], dependencies=[OFFICE_AND_ABOVE])
def process_notification_queue(db: DbSession):
    """Manually trigger queue processing (send pending messages)."""
    counts = notification_service.process_queue(db)
    return ApiSuccess(data=counts, message="Queue processed.")
