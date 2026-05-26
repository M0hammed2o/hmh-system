"""
Email service — SMTP sender + mock mode.

Config (all read from settings/env):
    SMTP_ENABLED             — true/false (default false = mock mode)
    SMTP_HOST                — e.g. smtp.gmail.com
    SMTP_PORT                — e.g. 587
    SMTP_USERNAME            — Gmail address used to authenticate and send
    SMTP_PASSWORD            — App password (16-char Gmail app password)
    SMTP_FROM_EMAIL          — Sender address (defaults to SMTP_USERNAME)
    SMTP_FROM_NAME           — Display name, e.g. "HMH Procurement"
    PROCUREMENT_EMAIL_CC     — Comma-separated CC addresses for all PO emails
    PROCUREMENT_EMAIL_BCC    — Comma-separated BCC addresses for all PO emails

In mock mode nothing is sent externally; the body is stored in PoEmailLog.
send_email() and send_po_email() never raise — they always return a result dict
or PoEmailLog so the procurement flow is never interrupted by email failure.
"""

import logging
import os
import smtplib
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import EmailStatus
from app.models.purchase_order import PoEmailLog, PurchaseOrder

from app.core.logging_config import get_logger

logger = get_logger(__name__)


def _in_pytest() -> bool:
    """True only inside a pytest run — never during normal server operation."""
    return bool(os.getenv("PYTEST_CURRENT_TEST")) or os.getenv("APP_ENV", "").lower() == "test"


def _smtp_is_real() -> bool:
    """
    True when we should attempt a real SMTP send.

    Real send requires ALL of:
      • Not a pytest run
      • SMTP_ENABLED=true in .env / settings
      • EMAIL_MOCK_MODE=false (or unset)
      • SMTP_USERNAME is configured (resolves SMTP_USER / GMAIL_USER aliases automatically)
    """
    if _in_pytest():
        return False
    if settings.EMAIL_MOCK_MODE:
        return False
    if not settings.SMTP_ENABLED:
        return False
    return True


def _smtp_diagnose() -> str:
    """Return a human-readable summary of current SMTP config (no password)."""
    return (
        f"SMTP_ENABLED={settings.SMTP_ENABLED}  "
        f"EMAIL_MOCK_MODE={settings.EMAIL_MOCK_MODE}  "
        f"SMTP_HOST={settings.SMTP_HOST}:{settings.SMTP_PORT}  "
        f"SMTP_USERNAME={'<set>' if settings.SMTP_USERNAME else '<EMPTY>'}  "
        f"SMTP_FROM={settings.smtp_sender_address or '<EMPTY>'}"
    )


# ── Internal SMTP send ────────────────────────────────────────────────────────

def _use_ssl() -> bool:
    """True when SSL-on-connect should be used (port 465 or SMTP_USE_SSL=true)."""
    return settings.SMTP_USE_SSL or settings.SMTP_PORT == 465


def _send_smtp(
    to_email: str,
    subject: str,
    body_html: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> Optional[str]:
    """
    Send via SMTP. Returns None on success, error string on failure.

    Connection strategy (auto-selected):
      port 465 or SMTP_USE_SSL=true  → smtplib.SMTP_SSL  (SSL on connect)
      port 587 (default)             → smtplib.SMTP + STARTTLS

    Timeout is 30 seconds for both connect and send.
    Prints diagnostics to stdout so they appear in the backend CMD window.
    """
    sender = settings.smtp_sender_address
    if not sender:
        err = "SMTP sender address is empty — check SMTP_USERNAME / SMTP_USER in .env"
        logger.error("email_send_error: %s", err)
        return err
    if not settings.SMTP_USERNAME:
        err = "SMTP_USERNAME is empty — check .env (use SMTP_USERNAME= or SMTP_USER=)"
        logger.error("email_send_error: %s", err)
        return err

    use_ssl = _use_ssl()
    mode    = "SSL" if use_ssl else "STARTTLS"
    logger.info("email_send host=%s port=%d mode=%s sender=%s to=%s subject=%.80s",
                settings.SMTP_HOST, settings.SMTP_PORT, mode, sender, to_email, subject)

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{settings.SMTP_FROM_NAME} <{sender}>"
        msg["To"]      = to_email
        if cc:
            msg["Cc"] = ", ".join(cc)
        msg.attach(MIMEText(body_html, "html"))

        all_recipients = [to_email] + (cc or []) + (bcc or [])

        if use_ssl:
            # Direct SSL connection (port 465)
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.sendmail(sender, all_recipients, msg.as_string())
        else:
            # STARTTLS connection (port 587, default for Gmail)
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.sendmail(sender, all_recipients, msg.as_string())

        logger.info("email_sent to=%s", to_email)
        return None
    except Exception as exc:
        logger.exception("email_send_failed to=%s error=%s", to_email, exc)
        return str(exc)


# ── Public generic sender ─────────────────────────────────────────────────────

def send_email(
    to_email: str,
    subject: str,
    body: str,
    attachments: list | None = None,
    cc: list | None = None,
    bcc: list | None = None,
) -> dict:
    """
    Generic email sender. Never raises.
    Returns: {"status": "SENT"|"MOCK_SENT"|"FAILED", "error": str|None, ...}
    """
    logger.debug("email send_email to=%s", to_email)

    if not _smtp_is_real():
        reason = "pytest" if _in_pytest() else ("EMAIL_MOCK_MODE=true" if settings.EMAIL_MOCK_MODE else "SMTP_ENABLED=false")
        logger.info("email mock_sent to=%s subject=%.80s reason=%s", to_email, subject, reason)
        return {"status": "MOCK_SENT", "error": None, "provider_message_id": None}

    if not settings.SMTP_USERNAME:
        err = "SMTP_USERNAME is empty — set SMTP_USERNAME (or SMTP_USER) in .env"
        logger.warning("email_config_error: %s", err)
        return {"status": "FAILED", "error": err, "provider_message_id": None}

    effective_cc  = cc  if cc  is not None else settings.procurement_cc_list
    effective_bcc = bcc if bcc is not None else settings.procurement_bcc_list

    error = _send_smtp(to_email, subject, body, cc=effective_cc or None, bcc=effective_bcc or None)
    if error:
        return {"status": "FAILED", "error": error, "provider_message_id": None}
    return {"status": "SENT", "error": None, "provider_message_id": None}


# ── PO email builder ──────────────────────────────────────────────────────────

def build_po_email_body(po: PurchaseOrder) -> tuple[str, str]:
    """Return (subject, html_body) for a purchase-order email."""
    subject = f"Purchase Order {po.po_number} — HMH Group"

    items_html = ""
    for item in po.order_items:
        line = float(item.line_total or 0)
        items_html += (
            f"<tr>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>{item.description}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;text-align:right'>"
            f"{item.quantity_ordered} {item.unit or ''}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;text-align:right'>"
            f"R{float(item.rate or 0):,.2f}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;text-align:right'>"
            f"R{line:,.2f}</td>"
            f"</tr>"
        )

    delivery_date = (
        po.expected_delivery_date.strftime("%d %B %Y")
        if po.expected_delivery_date else "To be confirmed"
    )

    body = f"""
<html><body style="font-family:Arial,sans-serif;color:#333;max-width:700px;margin:0 auto">
<div style="background:#1e3a5f;padding:20px 30px">
  <h2 style="color:white;margin:0">HMH Group — Purchase Order</h2>
  <p style="color:#aabbd4;margin:4px 0 0">{po.po_number}</p>
</div>
<div style="padding:24px 30px">
  <p>Dear Supplier,</p>
  <p>Please find our purchase order <strong>{po.po_number}</strong>
     dated {po.po_date.strftime('%d %B %Y')}.</p>

  <table style="width:100%;border-collapse:collapse;margin:20px 0">
    <thead>
      <tr style="background:#f5f5f5">
        <th style="text-align:left;padding:8px 10px">Description</th>
        <th style="text-align:right;padding:8px 10px">Qty</th>
        <th style="text-align:right;padding:8px 10px">Unit Price</th>
        <th style="text-align:right;padding:8px 10px">Total</th>
      </tr>
    </thead>
    <tbody>{items_html}</tbody>
    <tfoot>
      <tr style="background:#f9f9f9;font-weight:bold">
        <td colspan="3" style="padding:10px;text-align:right">Order Total (incl. VAT):</td>
        <td style="padding:10px;text-align:right">R{float(po.total_amount):,.2f}</td>
      </tr>
    </tfoot>
  </table>

  <p><strong>Required delivery date:</strong> {delivery_date}</p>
  {f'<p><strong>Notes:</strong> {po.notes}</p>' if po.notes else ''}

  <p style="color:#555;font-size:13px;margin-top:24px">
    Please confirm receipt and advise your delivery date.<br><br>
    <strong>IMPORTANT — Document submission:</strong><br>
    Send your invoice, delivery note, and any supporting documents directly to:<br>
    <a href="mailto:{settings.smtp_sender_address}" style="color:#e85d04">
      {settings.smtp_sender_address}
    </a><br>
    Quote reference <strong>{po.po_number}</strong> in the subject line of all correspondence
    so your documents can be automatically matched to this order.
  </p>
  <p style="color:#888;font-size:12px">HMH Group Procurement</p>
</div>
</body></html>
"""
    return subject, body


# ── PO email sender ───────────────────────────────────────────────────────────

def send_po_email(
    db: Session,
    po: PurchaseOrder,
    sent_by_id: Optional[uuid.UUID] = None,
    mr_id: Optional[uuid.UUID] = None,
) -> PoEmailLog:
    """
    Send (or mock-send) a PO email to the supplier.
    Always creates and commits a PoEmailLog record.
    Never raises — failures are recorded in the log.
    """
    from app.models.supplier import Supplier

    supplier = db.get(Supplier, po.supplier_id)
    if not supplier:
        raise ValueError(f"Supplier {po.supplier_id} not found.")

    to_email   = supplier.email or ""
    subject, body_html = build_po_email_body(po)
    now        = datetime.now(timezone.utc)
    error_msg: Optional[str] = None

    logger.info("email po_send po=%s to=%s", po.po_number, to_email or "(no email)")

    if not to_email:
        status    = EmailStatus.failed
        error_msg = f"Supplier '{supplier.name}' has no email address configured."
        logger.warning("email po_send_failed po=%s reason=no_supplier_email", po.po_number)
    elif not _smtp_is_real():
        reason = "pytest" if _in_pytest() else ("EMAIL_MOCK_MODE" if settings.EMAIL_MOCK_MODE else "SMTP_ENABLED=false")
        logger.info("email po_mock_sent po=%s to=%s reason=%s", po.po_number, to_email, reason)
        status = EmailStatus.sent
    else:
        cc  = settings.procurement_cc_list
        bcc = settings.procurement_bcc_list
        error_msg = _send_smtp(to_email, subject, body_html, cc=cc or None, bcc=bcc or None)
        status = EmailStatus.sent if error_msg is None else EmailStatus.failed
        if error_msg:
            logger.error("PO email failed for %s: %s", po.po_number, error_msg)

    log = PoEmailLog(
        id=uuid.uuid4(),
        purchase_order_id=po.id,
        sent_to_email=to_email,
        sent_by=sent_by_id,
        email_subject=subject,
        email_body=body_html,
        material_request_id=mr_id,
        status=status,
        error_message=error_msg,
        sent_at=now if status == EmailStatus.sent else None,
        created_at=now,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    # If email failed, raise a WhatsApp-visible alert
    if status == EmailStatus.failed:
        _create_po_email_failure_alert(db, po, error_msg or "Unknown error")

    return log


def _create_po_email_failure_alert(db: Session, po: PurchaseOrder, error: str) -> None:
    """Create a SystemAlert so the PO email failure appears in WhatsApp alerts."""
    try:
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertSeverity, AlertStatus
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        db.add(SystemAlert(
            alert_type=AlertType.DELIVERY_WITHOUT_PO,   # closest available type for email failures
            severity=AlertSeverity.HIGH,
            title=f"PO email failed — {po.po_number}",
            message=(
                f"Failed to send purchase order {po.po_number} to supplier by email. "
                f"Error: {error[:200]}"
            ),
            status=AlertStatus.OPEN,
            project_id=po.project_id,
            notification_channel="whatsapp",
            created_at=now,
            sent_at=now,
        ))
        db.commit()
    except Exception:
        logger.exception("Could not create PO email failure alert for %s", po.po_number)


# ── High-level: send by PO ID ──────────────────────────────────────────────────

def send_supplier_po_email(
    po_id: uuid.UUID,
    db: Session,
    sent_by_id: Optional[uuid.UUID] = None,
) -> PoEmailLog:
    """
    Look up a PO by ID and send the full procurement email to the supplier.
    Includes project/site/lot context and document submission instructions.
    """
    from sqlalchemy.orm import joinedload
    po = (
        db.query(PurchaseOrder)
        .options(joinedload(PurchaseOrder.order_items))
        .filter(PurchaseOrder.id == po_id)
        .first()
    )
    if not po:
        raise ValueError(f"Purchase order {po_id} not found.")

    return send_po_email(db, po, sent_by_id=sent_by_id)


# ── Material Request approval email ───────────────────────────────────────────

def build_mr_email_body(db: Session, mr) -> tuple[str, str]:
    """Return (subject, html_body) for a material-request approval email."""
    from app.models.site import Site
    from app.models.lot import Lot
    from app.models.user import User
    from app.models.supplier import Supplier

    request_number = mr.request_number
    subject = f"Material Request {request_number} — HMH Group"

    site     = db.get(Site, mr.site_id) if mr.site_id else None
    lot      = db.get(Lot,  mr.lot_id)  if mr.lot_id  else None
    requester = db.get(User, mr.requested_by) if mr.requested_by else None
    approver  = db.get(User, mr.approved_by)  if mr.approved_by  else None
    supplier  = db.get(Supplier, mr.preferred_supplier_id) if mr.preferred_supplier_id else None

    site_name      = site.name       if site      else "—"
    lot_number     = lot.lot_number  if lot       else None
    requester_name = (requester.full_name if requester else "—") + \
                     (f" &lt;{requester.email}&gt;" if requester else "")
    approver_name  = (approver.full_name  if approver  else "—") + \
                     (f" &lt;{approver.email}&gt;"  if approver  else "")
    contact_name   = (supplier.contact_person or supplier.name) if supplier else "Supplier"
    needed_by      = mr.needed_by_date.strftime("%d %B %Y") if mr.needed_by_date else "As soon as possible"

    # Items
    items_html = ""
    for item in getattr(mr, "items", []):
        qty  = float(getattr(item, "requested_quantity", 0) or 0)
        unit = getattr(item, "unit", "") or ""
        desc = getattr(item, "description", "Material")
        items_html += (
            f"<tr>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee'>{desc}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;text-align:right'>{qty:g}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;color:#555'>{unit}</td>"
            f"</tr>"
        )

    lot_row      = f"<tr><td style='padding:5px 0;color:#666;width:150px'>Lot</td><td style='font-weight:500'>{lot_number}</td></tr>" if lot_number else ""
    notes_row    = f"<tr><td style='padding:5px 0;color:#666'>Notes</td><td>{mr.notes}</td></tr>" if mr.notes else ""

    body = f"""
<html><body style="font-family:Arial,sans-serif;color:#1a1a1a;max-width:680px;margin:0 auto;background:#f7f7f7">
<div style="background:#e85d04;padding:22px 32px">
  <h2 style="color:white;margin:0;font-size:20px">HMH Group — Material Request</h2>
  <p style="color:#ffd7b5;margin:4px 0 0;font-size:14px">{request_number}</p>
</div>
<div style="background:white;padding:28px 32px">
  <p>Dear {contact_name},</p>
  <p>We have an approved material request. Please confirm stock availability and provide pricing for the following items:</p>

  <table style="width:100%;border-collapse:collapse;margin:20px 0">
    <thead>
      <tr style="background:#f5f5f5">
        <th style="text-align:left;padding:10px 12px;border-bottom:2px solid #e85d04">Material</th>
        <th style="text-align:right;padding:10px 12px;border-bottom:2px solid #e85d04">Quantity</th>
        <th style="text-align:left;padding:10px 12px;border-bottom:2px solid #e85d04">Unit</th>
      </tr>
    </thead>
    <tbody>{items_html}</tbody>
  </table>

  <table style="width:100%;border-collapse:collapse;margin:20px 0;font-size:14px">
    <tr><td style="padding:5px 0;color:#666;width:150px">Site</td><td style="font-weight:500">{site_name}</td></tr>
    {lot_row}
    <tr><td style="padding:5px 0;color:#666">Required by</td><td style="font-weight:500">{needed_by}</td></tr>
    <tr><td style="padding:5px 0;color:#666">Requested by</td><td style="font-weight:500">{requester_name}</td></tr>
    <tr><td style="padding:5px 0;color:#666">Approved by</td><td style="font-weight:500">{approver_name}</td></tr>
    {notes_row}
  </table>

  <p style="color:#555;font-size:13px;border-top:1px solid #eee;padding-top:16px;margin-top:20px">
    Please reply to this email with your quote or confirm availability.<br>
    Send invoices and delivery documents to:
    <a href="mailto:{settings.smtp_sender_address}" style="color:#e85d04">
      {settings.smtp_sender_address}
    </a><br>
    Quote reference <strong>{request_number}</strong> on all correspondence.
  </p>
  <p style="color:#999;font-size:12px">HMH Group Procurement &mdash; Construction Management System</p>
</div>
</body></html>
"""
    return subject, body


def send_mr_approval_email(
    db: Session,
    mr,
    sent_by_id: Optional[uuid.UUID] = None,
    force_resend: bool = False,
) -> "MREmailLog":
    """
    Send an approval email to the preferred supplier for a material request.

    - If SMTP_ENABLED=false, creates a MOCK_SENT record.
    - If already sent successfully and force_resend=False, returns the existing log.
    - On failure, creates a SystemAlert.
    - Never raises — caller should handle the returned log.
    """
    from app.models.mr_email_log import MREmailLog
    from app.models.supplier import Supplier

    now = datetime.now(timezone.utc)

    # ── Duplicate guard ───────────────────────────────────────────────────────
    if not force_resend:
        existing = (
            db.query(MREmailLog)
            .filter(
                MREmailLog.material_request_id == mr.id,
                MREmailLog.status.in_(["SENT", "MOCK_SENT"]),
            )
            .order_by(MREmailLog.created_at.desc())
            .first()
        )
        if existing:
            logger.info("MR %s email already sent (%s) — skipping duplicate.", mr.request_number, existing.status)
            return existing

    # ── Resolve supplier ──────────────────────────────────────────────────────
    if not mr.preferred_supplier_id:
        # No supplier — create a placeholder log and return
        log = MREmailLog(
            material_request_id=mr.id,
            sent_to_email="(no supplier)",
            email_subject=f"MR {mr.request_number} — no supplier assigned",
            status="FAILED",
            error_message="No preferred supplier set on the material request.",
            sent_by=sent_by_id,
            created_at=now,
        )
        db.add(log)
        db.commit()
        return log

    supplier = db.get(Supplier, mr.preferred_supplier_id)
    if not supplier:
        log = MREmailLog(
            material_request_id=mr.id,
            sent_to_email="(supplier not found)",
            status="FAILED",
            error_message=f"Supplier {mr.preferred_supplier_id} not found.",
            sent_by=sent_by_id,
            created_at=now,
        )
        db.add(log)
        db.commit()
        return log

    to_email = supplier.email or ""
    subject, body_html = build_mr_email_body(db, mr)

    # ── Send ──────────────────────────────────────────────────────────────────
    error_msg: Optional[str] = None
    status_str: str

    logger.info("email mr_send mr=%s to=%s", mr.request_number, to_email or "(no email)")

    if not to_email:
        status_str = "FAILED"
        error_msg  = f"Supplier '{supplier.name}' has no email address — add email to supplier record."
        logger.warning("email mr_send_failed mr=%s reason=no_supplier_email", mr.request_number)
    elif not _smtp_is_real():
        reason = "pytest" if _in_pytest() else ("EMAIL_MOCK_MODE" if settings.EMAIL_MOCK_MODE else "SMTP_ENABLED=false")
        logger.info("email mr_mock_sent mr=%s to=%s reason=%s", mr.request_number, to_email, reason)
        status_str = "MOCK_SENT"
    else:
        err = _send_smtp(
            to_email, subject, body_html,
            cc=settings.procurement_cc_list or None,
            bcc=settings.procurement_bcc_list or None,
        )
        if err:
            status_str = "FAILED"
            error_msg  = err
            logger.error("MR email failed for %s: %s", mr.request_number, err)
        else:
            status_str = "SENT"

    log = MREmailLog(
        material_request_id=mr.id,
        supplier_id=supplier.id,
        sent_to_email=to_email,
        email_subject=subject,
        email_body=body_html,
        status=status_str,
        error_message=error_msg,
        sent_by=sent_by_id,
        sent_at=now if status_str in ("SENT", "MOCK_SENT") else None,
        created_at=now,
    )
    db.add(log)
    db.commit()

    # ── Alert on failure ──────────────────────────────────────────────────────
    if status_str == "FAILED":
        _create_mr_email_failure_alert(db, mr, error_msg or "Unknown error")

    return log


def _create_mr_email_failure_alert(db: Session, mr, error: str) -> None:
    """Create a SystemAlert when an MR approval email fails."""
    try:
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertSeverity, AlertStatus
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        db.add(SystemAlert(
            alert_type=AlertType.REQUEST_PENDING_TOO_LONG,
            severity=AlertSeverity.HIGH,
            title=f"MR email failed — {mr.request_number}",
            message=(
                f"Failed to email supplier for approved material request {mr.request_number}. "
                f"Error: {error[:200]}. Please resend manually."
            ),
            status=AlertStatus.OPEN,
            project_id=mr.project_id,
            notification_channel="whatsapp",
            created_at=now,
            sent_at=now,
        ))
        db.commit()
    except Exception:
        logger.exception("Could not create MR email failure alert for %s", mr.request_number)
