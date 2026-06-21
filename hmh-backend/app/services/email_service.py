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
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
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
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> Optional[str]:
    """
    Send via SMTP. Returns None on success, error string on failure.

    Connection strategy (auto-selected):
      port 465 or SMTP_USE_SSL=true  → smtplib.SMTP_SSL  (SSL on connect)
      port 587 (default)             → smtplib.SMTP + STARTTLS

    Timeout is 30 seconds for both connect and send.
    Prints diagnostics to stdout so they appear in the backend CMD window.

    attachments: list of (filename, file_bytes, mime_type) tuples e.g.
        [("invoice.pdf", b"...", "application/pdf")]
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
        if attachments:
            # Mixed container: body + file attachments
            outer = MIMEMultipart("mixed")
            alt   = MIMEMultipart("alternative")
            alt.attach(MIMEText(body_html, "html"))
            outer.attach(alt)
            for filename, file_bytes, mime_type in attachments:
                main_type, sub_type = (mime_type.split("/", 1) if "/" in mime_type else ("application", "octet-stream"))
                part = MIMEBase(main_type, sub_type)
                part.set_payload(file_bytes)
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", "attachment", filename=filename)
                outer.attach(part)
            msg = outer
        else:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body_html, "html"))

        msg["Subject"] = subject
        msg["From"]    = f"{settings.SMTP_FROM_NAME} <{sender}>"
        msg["To"]      = to_email
        if cc:
            msg["Cc"] = ", ".join(cc)

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

        logger.info("email_sent to=%s attachments=%d", to_email, len(attachments or []))
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

    error = _send_smtp(
        to_email, subject, body,
        cc=effective_cc or None, bcc=effective_bcc or None,
        attachments=attachments or None,
    )
    if error:
        return {"status": "FAILED", "error": error, "provider_message_id": None}
    return {"status": "SENT", "error": None, "provider_message_id": None}


# ── Company details lookup ────────────────────────────────────────────────────

_COMPANY_DETAILS: dict[str, dict] = {
    "HMH_GROUP": {
        "name":    "HMH Group",
        "address": "",
        "vat":     "",
        "tel":     "",
        "color":   "#1e3a5f",
    },
    "MINERAT": {
        "name":    "Minerat Construction & Civils",
        "address": "361 Mont Blank, 51 OR Tambo Pamde, Durban, 4001",
        "vat":     "4380258618",
        "tel":     "(031) 301 3038",
        "color":   "#1e3a5f",
    },
}


def _company(key: Optional[str]) -> dict:
    return _COMPANY_DETAILS.get(key or "HMH_GROUP", _COMPANY_DETAILS["HMH_GROUP"])


# ── PDF generators ───────────────────────────────────────────────────────────

def _generate_po_pdf(po) -> bytes:
    """Return raw PDF bytes for a purchase order."""
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor, white, black
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    co    = _company(getattr(po, "issuing_company", None))
    brand = HexColor(co["color"])
    light = HexColor("#f0f4f8")

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    W = doc.width

    def _p(text, size=9, bold=False, align=TA_LEFT, color=black):
        font = "Helvetica-Bold" if bold else "Helvetica"
        return Paragraph(str(text), ParagraphStyle(
            "_", fontName=font, fontSize=size,
            textColor=color, alignment=align, spaceAfter=0,
        ))

    story = []

    # Header
    hdr = Table([
        [_p(co["name"], 16, bold=True, color=white),
         _p(f"Purchase Order<br/>{po.po_number}", 10, align=TA_RIGHT, color=white)],
        [_p(po.po_date.strftime("%d %B %Y"), 9, color=HexColor("#aabbd4")),
         _p(f"VAT: {co['vat']}" if co.get("vat") else "", 9, align=TA_RIGHT, color=HexColor("#aabbd4"))],
    ], colWidths=[W * 0.6, W * 0.4])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), brand),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (0,  -1), 16),
        ("RIGHTPADDING",  (1, 0), (1,  -1), 16),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 0.5 * cm))

    # Items table
    col_w = [190, 35, 40, 65, 35, 35, 81]
    rows = [[_p(h, 8, bold=True) for h in
             ["Description", "QTY", "Unit", "Unit Price", "Disc%", "VAT%", "Nett Price"]]]
    for item in po.order_items:
        rate = float(item.rate or 0)
        qty  = float(item.quantity_ordered)
        line = float(item.line_total or 0)
        rows.append([
            _p(item.description, 8),
            _p(f"{qty:g}",      8, align=TA_CENTER),
            _p(item.unit or "", 8, align=TA_CENTER),
            _p(f"R{rate:,.2f}", 8, align=TA_RIGHT),
            _p("0%",            8, align=TA_CENTER),
            _p("15%",           8, align=TA_CENTER),
            _p(f"R{line:,.2f}", 8, align=TA_RIGHT),
        ])

    subtotal = float(po.subtotal_amount or 0)
    vat_amt  = float(po.vat_amount or 0)
    total    = float(po.total_amount or 0)
    n        = len(po.order_items)
    for label, val in [("Subtotal:", subtotal), ("VAT (15%):", vat_amt)]:
        rows.append(["", "", "", "", "", _p(label, 8, align=TA_RIGHT), _p(f"R{val:,.2f}", 8, align=TA_RIGHT)])
    rows.append(["", "", "", "", "",
                 _p("Total:", 9, bold=True, align=TA_RIGHT),
                 _p(f"R{total:,.2f}", 9, bold=True, align=TA_RIGHT)])

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0),  (-1, 0),    brand),
        ("TEXTCOLOR",     (0, 0),  (-1, 0),    white),
        ("TOPPADDING",    (0, 0),  (-1, 0),    7),
        ("BOTTOMPADDING", (0, 0),  (-1, 0),    7),
        ("TOPPADDING",    (0, 1),  (-1, n),    5),
        ("BOTTOMPADDING", (0, 1),  (-1, n),    5),
        ("LEFTPADDING",   (0, 0),  (0,  -1),   6),
        ("RIGHTPADDING",  (-1, 0), (-1, -1),   6),
        ("ROWBACKGROUNDS",(0, 1),  (-1, n),    [white, light]),
        ("GRID",          (0, 0),  (-1, n),    0.3, HexColor("#dddddd")),
        ("BACKGROUND",    (0, n+1),(-1, n+2),  HexColor("#fafafa")),
        ("BACKGROUND",    (0, n+3),(-1, n+3),  light),
        ("LINEABOVE",     (0, n+1),(-1, n+1),  1, HexColor("#cccccc")),
        ("SPAN",          (0, n+1),(4,  n+1)),
        ("SPAN",          (0, n+2),(4,  n+2)),
        ("SPAN",          (0, n+3),(4,  n+3)),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.5 * cm))

    # Metadata
    delivery_date = (po.expected_delivery_date.strftime("%d %B %Y")
                     if po.expected_delivery_date else "To be confirmed")
    meta_rows = [[_p("Required delivery date:", 9, bold=True), _p(delivery_date, 9)]]
    if po.notes:
        meta_rows.append([_p("Notes:", 9, bold=True), _p(po.notes, 9)])
    meta = Table(meta_rows, colWidths=[160, W - 160])
    meta.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta)
    story.append(Spacer(1, 0.4 * cm))
    story.append(_p(
        f"Please confirm receipt of this order and advise your estimated delivery date. "
        f"Quote reference {po.po_number} on all correspondence.",
        8, color=HexColor("#666666"),
    ))

    doc.build(story)
    return buf.getvalue()


def _generate_mr_pdf(db: Session, mr, supplier_override=None, items_override=None) -> bytes:
    """Return raw PDF bytes for a material-request approval."""
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor, white, black
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    from app.models.site import Site
    from app.models.lot import Lot
    from app.models.user import User
    from app.models.supplier import Supplier

    co    = _company(getattr(mr, "issuing_company", None))
    brand = HexColor("#e85d04")
    light = HexColor("#f5f5f5")

    site      = db.get(Site, mr.site_id)     if mr.site_id      else None
    lot       = db.get(Lot,  mr.lot_id)      if mr.lot_id       else None
    requester = db.get(User, mr.requested_by) if mr.requested_by else None
    approver  = db.get(User, mr.approved_by)  if mr.approved_by  else None
    supplier  = supplier_override or (
        db.get(Supplier, mr.preferred_supplier_id) if mr.preferred_supplier_id else None
    )

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    W = doc.width

    def _p(text, size=9, bold=False, align=TA_LEFT, color=black):
        font = "Helvetica-Bold" if bold else "Helvetica"
        return Paragraph(str(text), ParagraphStyle(
            "_", fontName=font, fontSize=size,
            textColor=color, alignment=align, spaceAfter=0,
        ))

    story = []

    # Header
    hdr = Table([
        [_p(co["name"], 16, bold=True, color=white),
         _p(f"Material Request<br/>{mr.request_number}", 10, align=TA_RIGHT, color=white)],
        [_p("Approved", 9, color=HexColor("#ffd7b5")),
         _p(mr.approved_at.strftime("%d %B %Y") if getattr(mr, "approved_at", None) else "",
            9, align=TA_RIGHT, color=HexColor("#ffd7b5"))],
    ], colWidths=[W * 0.6, W * 0.4])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), brand),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (0,  -1), 16),
        ("RIGHTPADDING",  (1, 0), (1,  -1), 16),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 0.5 * cm))

    # Items table
    col_w = [310, 90, 81]
    rows = [[_p("Material", 8, bold=True),
             _p("Quantity", 8, bold=True, align=TA_RIGHT),
             _p("Unit",     8, bold=True)]]
    for item in (items_override if items_override is not None else getattr(mr, "items", [])):
        qty  = float(getattr(item, "requested_quantity", 0) or 0)
        unit = getattr(item, "unit", "") or ""
        desc = getattr(item, "description", "Material")
        rows.append([_p(desc, 8), _p(f"{qty:g}", 8, align=TA_RIGHT), _p(unit, 8)])

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  brand),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  white),
        ("TOPPADDING",    (0, 0), (-1, 0),  7),
        ("BOTTOMPADDING", (0, 0), (-1, 0),  7),
        ("TOPPADDING",    (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (0,  -1), 8),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [white, light]),
        ("GRID",          (0, 0), (-1, -1), 0.3, HexColor("#dddddd")),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.5 * cm))

    # Metadata
    needed_by = (mr.needed_by_date.strftime("%d %B %Y")
                 if getattr(mr, "needed_by_date", None) else "As soon as possible")
    meta_rows = [[_p("Site:", 9, bold=True), _p(site.name if site else "—", 9)]]
    if lot:
        meta_rows.append([_p("Lot:", 9, bold=True), _p(lot.lot_number, 9)])
    meta_rows.append([_p("Required by:", 9, bold=True), _p(needed_by, 9)])
    if requester:
        meta_rows.append([_p("Requested by:", 9, bold=True), _p(requester.full_name, 9)])
    if approver:
        meta_rows.append([_p("Approved by:", 9, bold=True), _p(approver.full_name, 9)])
    if supplier:
        meta_rows.append([_p("Supplier:", 9, bold=True), _p(supplier.name, 9)])
    if mr.notes:
        meta_rows.append([_p("Notes:", 9, bold=True), _p(mr.notes, 9)])

    meta = Table(meta_rows, colWidths=[130, W - 130])
    meta.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta)
    story.append(Spacer(1, 0.4 * cm))
    story.append(_p(
        f"Please reply with your quote or confirm availability. "
        f"Quote reference {mr.request_number} on all correspondence.",
        8, color=HexColor("#666666"),
    ))

    doc.build(story)
    return buf.getvalue()


# ── PO email builder ──────────────────────────────────────────────────────────

def build_po_email_body(po: PurchaseOrder) -> tuple[str, str]:
    """Return (subject, html_body) for a purchase-order email."""
    from app.models.supplier import Supplier as _Supplier

    co = _company(getattr(po, "issuing_company", None))
    co_name = co["name"]
    subject = f"Purchase Order {po.po_number} — {co_name}"

    # Build items table rows
    items_html = ""
    for item in po.order_items:
        rate  = float(item.rate or 0)
        qty   = float(item.quantity_ordered)
        line  = float(item.line_total or 0)
        unit  = item.unit or ""
        items_html += (
            f"<tr>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;font-size:13px'>{item.description}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;text-align:center;font-size:13px'>{qty:g}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;text-align:center;font-size:13px'>{unit}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;text-align:right;font-size:13px'>R{rate:,.2f}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;text-align:center;font-size:13px'>0%</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;text-align:center;font-size:13px'>15%</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;text-align:right;font-size:13px'>R{line:,.2f}</td>"
            f"</tr>"
        )

    subtotal = float(po.subtotal_amount or 0)
    vat_amt  = float(po.vat_amount or 0)
    total    = float(po.total_amount or 0)

    delivery_date = (
        po.expected_delivery_date.strftime("%d %B %Y")
        if po.expected_delivery_date else "To be confirmed"
    )

    co_meta = ""
    if co["address"] or co["vat"] or co["tel"]:
        parts = [p for p in [co["address"], f"VAT: {co['vat']}" if co["vat"] else "", f"Tel: {co['tel']}" if co["tel"] else ""] if p]
        co_meta = f"<p style='color:#aabbd4;font-size:12px;margin:2px 0 0'>{' | '.join(parts)}</p>"

    body = f"""
<html><body style="font-family:Arial,sans-serif;color:#333;max-width:750px;margin:0 auto">
<div style="background:{co['color']};padding:20px 30px">
  <h2 style="color:white;margin:0">{co_name} — Purchase Order</h2>
  <p style="color:#aabbd4;margin:4px 0 0;font-size:14px">{po.po_number} &nbsp;|&nbsp; {po.po_date.strftime('%d %B %Y')}</p>
  {co_meta}
</div>
<div style="padding:24px 30px">
  <p>Dear Supplier,</p>
  <p>Please find our purchase order <strong>{po.po_number}</strong> dated {po.po_date.strftime('%d %B %Y')}.</p>

  <table style="width:100%;border-collapse:collapse;margin:20px 0;font-size:13px">
    <thead>
      <tr style="background:#f0f4f8">
        <th style="text-align:left;padding:9px 10px;border-bottom:2px solid {co['color']}">Description</th>
        <th style="text-align:center;padding:9px 10px;border-bottom:2px solid {co['color']}">QTY</th>
        <th style="text-align:center;padding:9px 10px;border-bottom:2px solid {co['color']}">Unit</th>
        <th style="text-align:right;padding:9px 10px;border-bottom:2px solid {co['color']}">Unit Price</th>
        <th style="text-align:center;padding:9px 10px;border-bottom:2px solid {co['color']}">Disc%</th>
        <th style="text-align:center;padding:9px 10px;border-bottom:2px solid {co['color']}">VAT%</th>
        <th style="text-align:right;padding:9px 10px;border-bottom:2px solid {co['color']}">Nett Price</th>
      </tr>
    </thead>
    <tbody>{items_html}</tbody>
    <tfoot>
      <tr style="background:#fafafa">
        <td colspan="6" style="padding:7px 10px;text-align:right;font-size:13px">Subtotal (excl. VAT):</td>
        <td style="padding:7px 10px;text-align:right;font-size:13px">R{subtotal:,.2f}</td>
      </tr>
      <tr style="background:#fafafa">
        <td colspan="6" style="padding:7px 10px;text-align:right;font-size:13px">VAT (15%):</td>
        <td style="padding:7px 10px;text-align:right;font-size:13px">R{vat_amt:,.2f}</td>
      </tr>
      <tr style="background:#f0f4f8;font-weight:bold">
        <td colspan="6" style="padding:9px 10px;text-align:right">Total (incl. VAT):</td>
        <td style="padding:9px 10px;text-align:right">R{total:,.2f}</td>
      </tr>
    </tfoot>
  </table>

  <table style="width:100%;font-size:13px;margin-bottom:16px">
    <tr>
      <td style="color:#666;width:180px;padding:3px 0">Required delivery date:</td>
      <td style="font-weight:500">{delivery_date}</td>
    </tr>
    {f'<tr><td style="color:#666;padding:3px 0">Notes:</td><td>{po.notes}</td></tr>' if po.notes else ''}
  </table>

  <p style="color:#555;font-size:13px;margin-top:20px;border-top:1px solid #eee;padding-top:16px">
    Please confirm receipt of this order and advise your estimated delivery date.<br><br>
    <strong>IMPORTANT — Document submission:</strong><br>
    Send your invoice, delivery note, and any supporting documents directly to:<br>
    <a href="mailto:{settings.smtp_sender_address}" style="color:#e85d04">
      {settings.smtp_sender_address}
    </a><br>
    Quote reference <strong>{po.po_number}</strong> in the subject line of all correspondence
    so your documents can be automatically matched to this order.
  </p>
  <p style="color:#aaa;font-size:11px;margin-top:16px">{co_name} Procurement &mdash; NextGen Intelligence</p>
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
        try:
            pdf_bytes = _generate_po_pdf(po)
            attachments: list | None = [(f"PO-{po.po_number}.pdf", pdf_bytes, "application/pdf")]
        except Exception as pdf_exc:
            logger.warning("PO PDF generation failed for %s: %s", po.po_number, pdf_exc)
            attachments = None

        cc  = settings.procurement_cc_list
        bcc = settings.procurement_bcc_list
        error_msg = _send_smtp(to_email, subject, body_html,
                               cc=cc or None, bcc=bcc or None,
                               attachments=attachments)
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
    """Create a SystemAlert so the PO email failure appears in WhatsApp alerts (deduplicated)."""
    try:
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertSeverity, AlertStatus
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        # Deduplicate: skip if an OPEN alert for the same PO already exists
        existing = db.query(SystemAlert).filter(
            SystemAlert.project_id == po.project_id,
            SystemAlert.alert_type == AlertType.DELIVERY_WITHOUT_PO,
            SystemAlert.status     == AlertStatus.OPEN,
            SystemAlert.title.like(f"%{po.po_number}%"),
        ).first()
        if existing:
            return

        # Resolve supplier name for clearer alert message
        supplier_name = ""
        if po.supplier_id:
            from app.models.supplier import Supplier
            sup = db.get(Supplier, po.supplier_id)
            supplier_name = f" ({sup.name})" if sup else ""

        db.add(SystemAlert(
            alert_type=AlertType.DELIVERY_WITHOUT_PO,
            severity=AlertSeverity.HIGH,
            title=f"PO email failed — {po.po_number}",
            message=(
                f"Failed to email purchase order {po.po_number}{supplier_name} to supplier. "
                f"Error: {error[:200]}. Please resend manually."
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

def build_mr_email_body(db: Session, mr, supplier_override=None, items_override=None) -> tuple[str, str]:
    """Return (subject, html_body) for a material-request approval email.

    supplier_override: Supplier ORM object to address email to (overrides mr.preferred_supplier_id lookup).
    items_override: list of MR item objects to include (overrides mr.items — used for per-supplier splits).
    """
    from app.models.site import Site
    from app.models.lot import Lot
    from app.models.user import User
    from app.models.supplier import Supplier

    request_number = mr.request_number
    co = _company(getattr(mr, "issuing_company", None))
    co_name = co["name"]
    subject = f"Material Request {request_number} — {co_name}"

    site     = db.get(Site, mr.site_id) if mr.site_id else None
    lot      = db.get(Lot,  mr.lot_id)  if mr.lot_id  else None
    requester = db.get(User, mr.requested_by) if mr.requested_by else None
    approver  = db.get(User, mr.approved_by)  if mr.approved_by  else None
    supplier  = supplier_override or (db.get(Supplier, mr.preferred_supplier_id) if mr.preferred_supplier_id else None)

    site_name      = site.name       if site      else "—"
    lot_number     = lot.lot_number  if lot       else None
    requester_name = (requester.full_name if requester else "—") + \
                     (f" &lt;{requester.email}&gt;" if requester else "")
    approver_name  = (approver.full_name  if approver  else "—") + \
                     (f" &lt;{approver.email}&gt;"  if approver  else "")
    contact_name   = (supplier.contact_person or supplier.name) if supplier else "Supplier"
    needed_by      = mr.needed_by_date.strftime("%d %B %Y") if mr.needed_by_date else "As soon as possible"

    # Items — use override list (per-supplier slice) if provided, otherwise all items
    items_html = ""
    for item in (items_override if items_override is not None else getattr(mr, "items", [])):
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
  <h2 style="color:white;margin:0;font-size:20px">{co_name} — Material Request</h2>
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
  <p style="color:#999;font-size:12px">{co_name} Procurement &mdash; NextGen Intelligence</p>
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
    Send approval emails to all suppliers referenced by MR items.

    Each unique preferred_supplier_id on the MR items gets its own email containing
    only the items assigned to that supplier.  Items with no per-item supplier fall
    back to mr.preferred_supplier_id.  One MREmailLog row is written per email sent.

    Returns the last log created (or the existing one when skipping a duplicate).
    Never raises — failures are recorded in the log and trigger an alert.
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

    # ── Group items by supplier ───────────────────────────────────────────────
    # Each item carries preferred_supplier_id; fall back to the MR-level supplier.
    fallback_sid = mr.preferred_supplier_id
    supplier_items: dict = {}   # supplier_id (uuid) → list of items

    for item in getattr(mr, "items", []):
        sid = getattr(item, "preferred_supplier_id", None) or fallback_sid
        if sid:
            supplier_items.setdefault(sid, []).append(item)

    # If no grouping possible, record a failure
    if not supplier_items:
        log = MREmailLog(
            material_request_id=mr.id,
            sent_to_email="(no supplier)",
            email_subject=f"MR {mr.request_number} — no supplier assigned",
            status="FAILED",
            error_message="No preferred supplier set on the material request or its items.",
            sent_by=sent_by_id,
            created_at=now,
        )
        db.add(log)
        db.commit()
        return log

    # ── Send one email per supplier group ─────────────────────────────────────
    last_log: Optional["MREmailLog"] = None
    total = len(supplier_items)

    for idx, (supplier_id, items) in enumerate(supplier_items.items(), 1):
        supplier = db.get(Supplier, supplier_id)
        if not supplier:
            logger.warning("MR %s: supplier %s not found — skipping.", mr.request_number, supplier_id)
            continue

        to_email = supplier.email or ""
        subject, body_html = build_mr_email_body(db, mr, supplier_override=supplier, items_override=items)

        # Append supplier indicator when there are multiple recipients
        if total > 1:
            subject = f"{subject} [{idx}/{total}]"

        logger.info(
            "email mr_send mr=%s supplier=%s to=%s items=%d",
            mr.request_number, supplier.name, to_email or "(no email)", len(items),
        )

        error_msg: Optional[str] = None
        if not to_email:
            status_str = "FAILED"
            error_msg  = f"Supplier '{supplier.name}' has no email address — add email to supplier record."
            logger.warning("email mr_send_failed mr=%s supplier=%s reason=no_email", mr.request_number, supplier.name)
        elif not _smtp_is_real():
            reason = "pytest" if _in_pytest() else ("EMAIL_MOCK_MODE" if settings.EMAIL_MOCK_MODE else "SMTP_ENABLED=false")
            logger.info("email mr_mock_sent mr=%s to=%s reason=%s", mr.request_number, to_email, reason)
            status_str = "MOCK_SENT"
        else:
            try:
                pdf_bytes = _generate_mr_pdf(db, mr, supplier_override=supplier, items_override=items)
                mr_attachments: list | None = [(f"MR-{mr.request_number}.pdf", pdf_bytes, "application/pdf")]
            except Exception as pdf_exc:
                logger.warning("MR PDF generation failed for %s: %s", mr.request_number, pdf_exc)
                mr_attachments = None

            err = _send_smtp(
                to_email, subject, body_html,
                cc=settings.procurement_cc_list or None,
                bcc=settings.procurement_bcc_list or None,
                attachments=mr_attachments,
            )
            if err:
                status_str = "FAILED"
                error_msg  = err
                logger.error("MR email failed for %s → %s: %s", mr.request_number, supplier.name, err)
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
        last_log = log

        if status_str == "FAILED":
            db.flush()   # get log.id before alert
            _create_mr_email_failure_alert(db, mr, error_msg or "Unknown error")

    if last_log is None:
        # All suppliers were missing — return a failure stub
        last_log = MREmailLog(
            material_request_id=mr.id,
            sent_to_email="(all suppliers missing)",
            status="FAILED",
            error_message="All referenced suppliers could not be found in the database.",
            sent_by=sent_by_id,
            created_at=now,
        )
        db.add(last_log)

    db.commit()
    return last_log


def _create_mr_email_failure_alert(db: Session, mr, error: str) -> None:
    """Create a SystemAlert when an MR approval email fails (deduplicated)."""
    try:
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType, AlertSeverity, AlertStatus
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        # Deduplicate: skip if an OPEN alert for the same MR already exists
        existing = db.query(SystemAlert).filter(
            SystemAlert.project_id == mr.project_id,
            SystemAlert.alert_type == AlertType.REQUEST_PENDING_TOO_LONG,
            SystemAlert.status     == AlertStatus.OPEN,
            SystemAlert.title.like(f"%{mr.request_number}%"),
        ).first()
        if existing:
            return

        # Resolve supplier name for clearer alert message
        supplier_name = ""
        if mr.preferred_supplier_id:
            from app.models.supplier import Supplier
            sup = db.get(Supplier, mr.preferred_supplier_id)
            supplier_name = f" (supplier: {sup.name})" if sup else ""

        db.add(SystemAlert(
            alert_type=AlertType.REQUEST_PENDING_TOO_LONG,
            severity=AlertSeverity.HIGH,
            title=f"MR email failed — {mr.request_number}",
            message=(
                f"Failed to email supplier for approved material request "
                f"{mr.request_number}{supplier_name}. "
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


# ── Quote rejection email ─────────────────────────────────────────────────────

def send_quote_rejection_email(
    db: Session,
    mr,
    quote,
    reason: str,
    sent_by_id: Optional[uuid.UUID] = None,
) -> dict:
    """
    Email the supplier that their quotation was rejected, with the reason and
    an invitation to resubmit.  Always creates an MREmailLog entry.
    Never raises — failures are logged but do not block the rejection flow.

    Returns {"status": "SENT"|"MOCK_SENT"|"FAILED", "sent_to": email}.
    """
    from app.models.supplier import Supplier
    from app.models.mr_email_log import MREmailLog

    now = datetime.now(timezone.utc)

    supplier = db.get(Supplier, quote.supplier_id) if quote.supplier_id else None
    to_email = (supplier.email or "") if supplier else ""
    contact  = (supplier.contact_person or supplier.name) if supplier else "Supplier"
    mr_number = mr.request_number

    subject = f"Quotation Not Accepted — {mr_number} | HMH Group"

    # Format quoted items for the email body
    items_html = ""
    if quote.description:
        items_html = (
            f"<tr>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee'>{quote.description}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;text-align:right'>"
            f"{quote.quoted_quantity:g} {quote.unit or ''}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;text-align:right'>"
            f"R {float(quote.unit_price):,.2f}</td>"
            f"</tr>"
        )

    body_html = f"""
<html><body style="font-family:Arial,sans-serif;color:#1a1a1a;max-width:680px;margin:0 auto;background:#f7f7f7">
<div style="background:#e85d04;padding:22px 32px">
  <h2 style="color:white;margin:0;font-size:20px">HMH Group — Quotation Not Accepted</h2>
  <p style="color:#ffd7b5;margin:4px 0 0;font-size:14px">Material Request: {mr_number}</p>
</div>
<div style="background:white;padding:28px 32px">
  <p>Dear {contact},</p>
  <p>Thank you for submitting your quotation for material request <strong>{mr_number}</strong>.</p>
  <p>Unfortunately, we are unable to accept this quotation at this time.</p>

  <div style="background:#fff3f3;border-left:4px solid #e74c3c;padding:16px 20px;margin:20px 0;border-radius:4px">
    <p style="margin:0 0 6px;font-weight:600;color:#c0392b">Reason for rejection:</p>
    <p style="margin:0;color:#555">{reason}</p>
  </div>

  {'<p><strong>Items in your quotation:</strong></p><table style="width:100%;border-collapse:collapse"><thead><tr style="background:#f5f5f5"><th style="padding:8px 12px;text-align:left">Description</th><th style="padding:8px 12px;text-align:right">Qty</th><th style="padding:8px 12px;text-align:right">Unit Price</th></tr></thead><tbody>' + items_html + '</tbody></table>' if items_html else ''}

  <p style="margin-top:24px">We invite you to submit a revised quotation that addresses the above feedback.
  Please reply to this email with your updated pricing.</p>

  <p>If you have any questions, please do not hesitate to contact us.</p>
  <p style="color:#888;font-size:13px;margin-top:32px">Kind regards,<br><strong>HMH Procurement Team</strong></p>
</div>
</body></html>"""

    error_msg: Optional[str] = None
    if not to_email:
        status_str = "FAILED"
        error_msg  = f"Supplier has no email address — cannot send rejection."
        logger.warning("quote_rejection_email no email mr=%s supplier=%s", mr_number, quote.supplier_id)
    elif not _smtp_is_real():
        status_str = "MOCK_SENT"
        logger.info("quote_rejection_mock mr=%s to=%s", mr_number, to_email)
    else:
        err = _send_smtp(to_email, subject, body_html)
        status_str = "SENT" if err is None else "FAILED"
        error_msg  = err
        if err:
            logger.error("quote_rejection_email failed mr=%s: %s", mr_number, err)

    log = MREmailLog(
        material_request_id=mr.id,
        supplier_id=quote.supplier_id,
        sent_to_email=to_email or "(no email)",
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

    return {"status": status_str, "sent_to": to_email}
