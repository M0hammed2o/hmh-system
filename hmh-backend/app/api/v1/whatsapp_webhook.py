"""
WhatsApp webhook routes.

GET  /whatsapp/webhook  — Meta verification handshake
POST /whatsapp/webhook  — Incoming messages + delivery statuses
"""

import hashlib
import hmac
import logging
import re

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.dependencies import DbSession
from app.schemas.common import ApiSuccess
from app.services import notification_service, whatsapp_service

from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


# ── HMAC signature verification ───────────────────────────────────────────────

def _verify_hmac_signature(body: bytes, signature_header: str) -> bool:
    """
    Verify the X-Hub-Signature-256 header sent by Meta on every webhook POST.

    The HMAC is computed with the Meta App Secret as the key and the raw
    request body as the message (SHA-256).  Returns True when the signature
    is valid or when WHATSAPP_APP_SECRET is not configured (dev/test mode).
    """
    app_secret = settings.WHATSAPP_APP_SECRET
    if not app_secret:
        # No secret configured — skip verification (dev / disabled mode).
        return True

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected = "sha256=" + hmac.new(
        app_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)

# Intent keyword groups — checked in APPROVE > REJECT > ACK priority order
_APPROVE_KEYWORDS = {"approve", "approved", "yes", "confirm"}
_REJECT_KEYWORDS  = {"reject", "rejected", "no", "cancel", "decline"}
_ACK_KEYWORDS     = {"ack", "ok", "done", "received", "seen", "resolved", "acknowledge"}

# Words stripped when extracting a rejection reason
_FILLER_WORDS = {"this", "the", "a", "an", "it", "that", "please", "alert"}

# Extracts a MR reference from anywhere in the message (e.g. "approve MR-002")
_MR_ID_RE = re.compile(r"\bMR-[A-Z0-9-]+\b", re.IGNORECASE)


# ── Phone normalisation ───────────────────────────────────────────────────────

def _normalise(phone: str) -> str:
    return phone.strip().lstrip("+")


def _phone_variants(phone: str) -> list[str]:
    digits = _normalise(phone)
    variants = [digits, f"+{digits}"]
    if digits.startswith("27") and len(digits) == 11:
        variants.append("0" + digits[2:])
    return list(dict.fromkeys(variants))


# ── Intent parsing ───────────────────────────────────────────────────────────

def _tokenise(text: str) -> set[str]:
    """Lowercase words, punctuation stripped."""
    return set(re.sub(r"[^\w]", " ", text.lower()).split())


def _detect_intent(tokens: set[str]) -> str:
    """Return APPROVE, REJECT, ACK, or UNKNOWN based on keyword presence."""
    if tokens & _APPROVE_KEYWORDS:
        return "APPROVE"
    if tokens & _REJECT_KEYWORDS:
        return "REJECT"
    if tokens & _ACK_KEYWORDS:
        return "ACK"
    return "UNKNOWN"


def _extract_reason(body_raw: str, tokens: set[str]) -> str:
    """Strip intent and filler words; returns empty string if no real reason given."""
    stop = _REJECT_KEYWORDS | _APPROVE_KEYWORDS | _FILLER_WORDS
    words = [w for w in body_raw.split() if w.lower() not in stop]
    return " ".join(words).strip()


def _short_title(alert) -> str:
    """4-6 word description from alert title, stripped of the word 'Alert'."""
    title = re.sub(r"\bAlert\b", "", alert.title, flags=re.IGNORECASE).strip()
    return " ".join(title.split()[:6])


def _unknown_reply() -> str:
    return (
        "I didn't understand that.\n\n"
        "You can reply:\n"
        "OK → acknowledge\n"
        "APPROVE → approve\n"
        "REJECT → reject\n"
        "LIST → view alerts"
    )


# ── Debug ─────────────────────────────────────────────────────────────────────

@router.get("/debug", include_in_schema=False)
def debug_router():
    logger.debug("GET /whatsapp/debug hit")
    return {"loaded": True, "message": "whatsapp webhook router active"}


# ── Verification ──────────────────────────────────────────────────────────────

@router.get("/webhook")
def verify_webhook(
    hub_mode:      str = Query(alias="hub.mode",         default=""),
    hub_token:     str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge",    default=""),
):
    result = whatsapp_service.verify_webhook(hub_mode, hub_token, hub_challenge)
    if result:
        logger.info("wa_webhook verified ok challenge_returned")
        return PlainTextResponse(result)
    logger.warning("wa_webhook verification_failed bad_token")
    return Response(status_code=403)


# ── Incoming messages + statuses ──────────────────────────────────────────────

@router.post("/webhook")
async def receive_webhook(request: Request, db: DbSession):
    # Read raw bytes first so we can verify the HMAC before parsing JSON.
    body = await request.body()

    signature = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_hmac_signature(body, signature):
        # Log rejection without including the signature or secret values.
        logger.warning(
            "wa_webhook HMAC_REJECTED ip=%s signature_present=%s",
            request.client.host if request.client else "unknown",
            bool(signature),
        )
        return Response(status_code=403)

    try:
        import json
        payload = json.loads(body)
    except Exception:
        logger.warning("wa_webhook JSON parse error — returning 200 to Meta")
        return Response(status_code=200)

    messages = whatsapp_service.parse_incoming(payload)
    statuses = whatsapp_service.parse_statuses(payload)

    logger.info("wa_webhook received messages=%d statuses=%d", len(messages), len(statuses))

    for status in statuses:
        _handle_delivery_status(db, status)

    total_acked = 0
    approved: list = []
    rejected: list = []

    for msg in messages:
        from_number = msg["from_number"]
        body_raw    = msg["body"].strip()
        normalized  = " ".join(body_raw.upper().split())
        tokens      = _tokenise(body_raw)
        intent      = _detect_intent(tokens)
        mr_match    = _MR_ID_RE.search(body_raw)

        # Stamp last_inbound_at on the matching AlertRecipient so
        # notification_service knows the 24-hour window is open.
        _stamp_recipient_inbound(db, from_number)

        logger.info("wa_msg from=%s intent=%s mr=%s", _normalise(from_number), intent, mr_match and mr_match.group(0))

        # ── RESET TEST ALERTS — exact phrase, checked before intent ───────────
        if normalized == "RESET TEST ALERTS":
            # Only known AlertRecipients may reset alerts (prevents spoofing)
            from app.models.alert_recipient import AlertRecipient
            _authorized = db.query(AlertRecipient).filter(
                AlertRecipient.phone_number.in_(_phone_variants(from_number)),
                AlertRecipient.is_active == True,  # noqa: E712
            ).first()
            if not _authorized:
                logger.warning(
                    "wa_command RESET_TEST_ALERTS rejected unknown_phone=%s",
                    _normalise(from_number),
                )
                continue
            logger.info("wa_command cmd=RESET_TEST_ALERTS from=%s", _normalise(from_number))
            reset_count = _reset_test_alerts(db, from_number)
            _reply(
                from_number,
                f"Test alerts reset. You can ACK again. ({reset_count} record(s) reset)"
            )
            continue

        # ── LIST ──────────────────────────────────────────────────────────────
        if "list" in tokens:
            logger.info("wa_command cmd=LIST from=%s", _normalise(from_number))
            _reply(from_number, _list_pending_alerts(db, from_number))
            continue

        # ── MR-specific commands (ID found in message) ────────────────────────
        if mr_match:
            mr_number = mr_match.group(0).upper()
            if intent == "APPROVE":
                logger.info("wa_command cmd=APPROVE_MR mr=%s", mr_number)
                result, reply = _approve_mr(db, mr_number, from_number)
                approved.append({"mr_number": mr_number, "result": result})
                _reply(from_number, reply)
                logger.info("wa_approve_mr done mr=%s result=%s", mr_number, result)
            elif intent == "REJECT":
                reason = _extract_reason(body_raw, tokens) or "Rejected via WhatsApp"
                logger.info("wa_command cmd=REJECT_MR mr=%s", mr_number)
                result, reply = _reject_mr(db, mr_number, from_number, reason)
                rejected.append({"mr_number": mr_number, "result": result})
                _reply(from_number, reply)
                logger.info("wa_reject_mr done mr=%s result=%s", mr_number, result)
            else:
                logger.info("wa_command cmd=UNKNOWN_MR from=%s", _normalise(from_number))
                _reply(from_number, _unknown_reply())
            continue

        # ── Safety check: nothing pending → skip processing ───────────────────
        if intent in ("ACK", "APPROVE", "REJECT"):
            if _latest_pending_queue_entry(db, from_number) is None:
                logger.info("wa_no_pending_alerts from=%s", _normalise(from_number))
                _reply(from_number, "No alerts to process.")
                continue

        # ── General intent — applies to latest pending alert ──────────────────
        if intent == "ACK":
            logger.info("wa_command cmd=ACK from=%s", _normalise(from_number))
            count = _ack_with_variants(db, from_number)
            total_acked += count
            _reply(from_number, f"Alerts acknowledged. ({count} updated)")
            logger.info("wa_ack done count=%d from=%s", count, _normalise(from_number))

        elif intent == "APPROVE":
            logger.info("wa_command cmd=APPROVE_ALERT from=%s", _normalise(from_number))
            result, reply = _approve_latest_alert(db, from_number)
            _reply(from_number, reply)
            logger.info("wa_approve_alert done result=%s", result)

        elif intent == "REJECT":
            reason = _extract_reason(body_raw, tokens)
            logger.info("wa_command cmd=REJECT_ALERT from=%s", _normalise(from_number))
            result, reply = _reject_latest_alert(db, from_number, reason)
            _reply(from_number, reply)
            logger.info("wa_reject_alert done result=%s", result)

        else:
            logger.info("wa_command cmd=UNKNOWN from=%s", _normalise(from_number))
            _reply(from_number, _unknown_reply())

    # Commit any pending flushes (e.g. last_inbound_at stamps not yet committed)
    try:
        db.commit()
    except Exception:
        logger.exception("wa_webhook final commit failed")
        db.rollback()

    logger.info("wa_webhook done acked=%d approved=%d rejected=%d", total_acked, len(approved), len(rejected))

    return ApiSuccess(data={
        "processed_messages": len(messages),
        "processed_statuses": len(statuses),
        "acknowledged": total_acked,
        "approved": approved,
        "rejected": rejected,
    })


# ── Reply helper ──────────────────────────────────────────────────────────────

def _reply(to: str, text: str) -> None:
    """Send a WhatsApp reply. Never raises. Prints result to CMD."""
    try:
        status, msg_id = whatsapp_service.send_text_message(to, text)
        logger.info("wa_reply to=%s status=%s id=%s", _normalise(to), status, msg_id)
    except Exception as exc:
        logger.exception("wa_reply_failed to=%s error=%s", _normalise(to), exc)


# ── ACK with phone variants ───────────────────────────────────────────────────

def _ack_with_variants(db, from_phone: str) -> int:
    total = 0
    seen: set = set()
    for variant in _phone_variants(from_phone):
        if variant in seen:
            continue
        seen.add(variant)
        n = notification_service.acknowledge_by_phone(db, variant)
        logger.debug("wa_ack variant=%s matched=%d", variant, n)
        total += n
    return total


# ── Reset test alerts ────────────────────────────────────────────────────────

def _reset_test_alerts(db, from_phone: str) -> int:
    from datetime import datetime, timezone
    from app.models.notification_queue import NotificationQueue
    from app.models.alert import SystemAlert
    from app.models.enums import NotificationStatus, AlertStatus

    total = 0
    seen_alert_ids: set = set()

    for variant in _phone_variants(from_phone):
        entries = (
            db.query(NotificationQueue)
            .filter(NotificationQueue.phone_number == variant)
            .all()
        )
        for entry in entries:
            entry.acknowledged_at = None
            entry.status = NotificationStatus.SENT
            total += 1
            logger.debug("wa_reset queue_id=%s phone=%s -> SENT", entry.id, variant)
            if entry.alert_id and entry.alert_id not in seen_alert_ids:
                seen_alert_ids.add(entry.alert_id)

    # Reset parent alerts so they show as OPEN / Pending ACK again
    for alert_id in seen_alert_ids:
        alert = db.query(SystemAlert).filter(SystemAlert.id == alert_id).first()
        if alert and alert.status == AlertStatus.ACKNOWLEDGED:
            alert.status = AlertStatus.OPEN
            alert.acknowledged_at = None
            alert.acknowledged_by = None
            logger.debug("wa_reset alert_id=%s -> OPEN", alert_id)

    db.commit()
    return total


# ── List pending alerts ──────────────────────────────────────────────────────

def _list_pending_alerts(db, from_phone: str) -> str:
    from app.models.notification_queue import NotificationQueue
    from app.models.alert import SystemAlert
    from app.models.enums import NotificationStatus

    seen_ids: set = set()
    entries = []

    for variant in _phone_variants(from_phone):
        rows = (
            db.query(NotificationQueue)
            .filter(
                NotificationQueue.phone_number == variant,
                NotificationQueue.acknowledged_at.is_(None),
                NotificationQueue.status != NotificationStatus.ACKNOWLEDGED,
            )
            .order_by(NotificationQueue.created_at.desc())
            .all()
        )
        for row in rows:
            if row.id not in seen_ids:
                seen_ids.add(row.id)
                entries.append(row)

    entries.sort(key=lambda e: e.created_at, reverse=True)
    entries = entries[:3]

    if not entries:
        return "No pending alerts."

    lines = ["Pending alerts:\n"]
    for i, entry in enumerate(entries, 1):
        if entry.alert_id:
            alert = db.query(SystemAlert).filter(SystemAlert.id == entry.alert_id).first()
            if alert:
                lines.append(f"{i}. {alert.severity.value}: {_short_title(alert)}")
                continue
        lines.append(f"{i}. (no details)")

    lines.append("\nReply APPROVE or REJECT")
    return "\n".join(lines)


# ── Approve / Reject latest alert ────────────────────────────────────────────

def _latest_pending_queue_entry(db, from_phone: str):
    """Return the most-recent unacknowledged NotificationQueue row for any phone variant."""
    from app.models.notification_queue import NotificationQueue
    from app.models.enums import NotificationStatus

    for variant in _phone_variants(from_phone):
        entry = (
            db.query(NotificationQueue)
            .filter(
                NotificationQueue.phone_number == variant,
                NotificationQueue.acknowledged_at.is_(None),
                NotificationQueue.status != NotificationStatus.ACKNOWLEDGED,
            )
            .order_by(NotificationQueue.created_at.desc())
            .first()
        )
        if entry:
            return entry
    return None


def _approve_latest_alert(db, from_phone: str) -> tuple[str, str]:
    from datetime import datetime, timezone
    from app.models.alert import SystemAlert
    from app.models.enums import NotificationStatus, AlertStatus

    entry = _latest_pending_queue_entry(db, from_phone)
    if not entry:
        return ("not_found", "No pending alert found to approve.")

    now = datetime.now(timezone.utc)
    entry.acknowledged_at = now
    entry.status = NotificationStatus.ACKNOWLEDGED
    logger.info("wa_approve_alert queue_id=%s -> ACKNOWLEDGED", entry.id)

    label = "Latest alert"
    if entry.alert_id:
        alert = db.query(SystemAlert).filter(SystemAlert.id == entry.alert_id).first()
        if alert:
            label = _short_title(alert)
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = now
            logger.info("wa_approve_alert alert_id=%s -> ACKNOWLEDGED", alert.id)

    db.commit()
    return ("approved", f"{label} approved.")


def _reject_latest_alert(db, from_phone: str, reason: str) -> tuple[str, str]:
    from datetime import datetime, timezone
    from app.models.alert import SystemAlert
    from app.models.enums import NotificationStatus, AlertStatus

    entry = _latest_pending_queue_entry(db, from_phone)
    if not entry:
        return ("not_found", "No pending alert found to reject.")

    now = datetime.now(timezone.utc)
    entry.acknowledged_at = now
    entry.status = NotificationStatus.ACKNOWLEDGED
    logger.info("wa_reject_alert queue_id=%s -> ACKNOWLEDGED", entry.id)

    label = "Latest alert"
    if entry.alert_id:
        alert = db.query(SystemAlert).filter(SystemAlert.id == entry.alert_id).first()
        if alert:
            label = _short_title(alert)
            alert.status = AlertStatus.RESOLVED
            alert.acknowledged_at = now
            alert.resolved_at = now
            logger.info("wa_reject_alert alert_id=%s -> RESOLVED", alert.id)

    db.commit()
    reply = f"{label} rejected. Reason: {reason}" if reason else f"{label} rejected."
    return ("rejected", reply)


# ── Approve / Reject MR ───────────────────────────────────────────────────────

def _approve_mr(db, mr_number: str, from_phone: str) -> tuple[str, str]:
    try:
        from app.models.material_request import MaterialRequest
        from app.models.enums import RecordStatus
        from app.services import mr_service

        mr = db.query(MaterialRequest).filter(
            MaterialRequest.request_number == mr_number
        ).first()

        if not mr:
            return ("not_found", f"{mr_number} was not found.")

        logger.debug("wa_approve_mr found mr=%s status=%s", mr_number, mr.status.value)

        if mr.status not in (RecordStatus.SUBMITTED, RecordStatus.PENDING_APPROVAL):
            return (
                "wrong_status",
                f"{mr_number} cannot be approved because it is currently {mr.status.value}.",
            )

        actor = _find_user_by_phone(db, from_phone)
        actor_id = (actor.id if actor else None) or mr.requested_by
        logger.debug("wa_approve_mr actor_id=%s", actor_id)

        mr_service.approve_request(db, mr.id, actor_id)
        return ("approved", f"{mr_number} has been approved successfully.")

    except Exception as exc:
        logger.exception("wa_approve_mr failed mr=%s", mr_number)
        return ("error", f"Error processing {mr_number}: {exc}")


def _reject_mr(db, mr_number: str, from_phone: str, reason: str) -> tuple[str, str]:
    try:
        from app.models.material_request import MaterialRequest
        from app.services import mr_service

        mr = db.query(MaterialRequest).filter(
            MaterialRequest.request_number == mr_number
        ).first()

        if not mr:
            return ("not_found", f"{mr_number} was not found.")

        logger.debug("wa_reject_mr found mr=%s status=%s", mr_number, mr.status.value)
        actor = _find_user_by_phone(db, from_phone)
        actor_id = (actor.id if actor else None) or mr.requested_by

        mr_service.reject_request(db, mr.id, actor_id, reason)
        return ("rejected", f"{mr_number} has been rejected. Reason: {reason}")

    except Exception as exc:
        logger.exception("wa_reject_mr failed mr=%s", mr_number)
        return ("error", f"Error processing {mr_number}: {exc}")


def _stamp_recipient_inbound(db, from_phone: str) -> None:
    """
    Record the timestamp of an inbound WhatsApp message against the matching
    AlertRecipient row.  Called for every incoming message so notification_service
    can decide whether the 24-hour conversation window is still open.
    Uses flush (not commit) — caller is responsible for the transaction boundary.
    """
    from datetime import datetime, timezone
    from app.models.alert_recipient import AlertRecipient

    now = datetime.now(timezone.utc)
    for variant in _phone_variants(from_phone):
        recipient = db.query(AlertRecipient).filter(
            AlertRecipient.phone_number == variant
        ).first()
        if recipient:
            recipient.last_inbound_at = now
            db.flush()
            logger.debug("wa_inbound_stamped recipient=%s phone=%s", recipient.name, variant)
            return


def _find_user_by_phone(db, from_phone: str):
    from app.models.user import User
    for variant in _phone_variants(from_phone):
        user = db.query(User).filter(User.phone == variant).first()
        if user:
            logger.debug("wa_user found variant=%s", variant)
            return user
    logger.debug("wa_user not_found phone=%s", _normalise(from_phone))
    return None


# ── Delivery status ───────────────────────────────────────────────────────────

def _handle_delivery_status(db, status: dict) -> None:
    msg_id    = status.get("message_id")
    wa_status = status.get("status")
    recipient = status.get("recipient_id", "unknown")

    if not msg_id or not wa_status:
        return

    logger.debug("wa_status msg_id=%s status=%s recipient=%s", msg_id, wa_status, recipient)

    # Log full failure detail IMMEDIATELY — before any DB lookup so it always
    # fires even when no NotificationQueue row exists for the message_id.
    if wa_status == "failed":
        errs      = status.get("errors", [])
        err       = errs[0] if errs else {}
        err_code  = err.get("code", "n/a")
        err_title = err.get("title", "Delivery failed")
        err_msg   = err.get("message", "")
        logger.error(
            "WhatsApp delivery FAILED | msg_id=%s recipient=%s error_code=%s"
            " error_title=%r error_message=%r full_errors=%r",
            msg_id, recipient, err_code, err_title, err_msg, errs,
        )

    # DB update (best-effort — record may not exist for unknown message IDs)
    try:
        from app.models.notification_queue import NotificationQueue
        from app.models.enums import NotificationStatus
        record = db.query(NotificationQueue).filter(
            NotificationQueue.provider_message_id == msg_id
        ).first()
        if not record:
            logger.debug("wa_status no_queue_record msg_id=%s", msg_id)
            return
        # Idempotency guards — Meta retries webhooks on timeout; skip terminal-state rewrites
        if wa_status == "read" and record.status == NotificationStatus.ACKNOWLEDGED:
            logger.debug("wa_status already_acknowledged msg_id=%s", msg_id)
            return
        if wa_status == "failed" and record.status == NotificationStatus.FAILED:
            logger.debug("wa_status already_failed msg_id=%s", msg_id)
            return
        if wa_status in ("sent", "delivered"):
            logger.debug("wa_status %s msg_id=%s recipient=%s", wa_status, msg_id, recipient)
            # No DB update — Meta confirming delivery progress; record stays SENT
        elif wa_status == "read":
            from datetime import datetime, timezone
            record.status = NotificationStatus.ACKNOWLEDGED
            record.acknowledged_at = datetime.now(timezone.utc)
            db.commit()
            logger.info("wa_status acknowledged msg_id=%s", msg_id)
        elif wa_status == "failed":
            errs      = status.get("errors", [])
            err       = errs[0] if errs else {}
            err_code  = err.get("code", "n/a")
            err_title = err.get("title", "Delivery failed")
            err_msg   = err.get("message", "")
            record.status        = NotificationStatus.FAILED
            record.error_message = f"[{err_code}] {err_title}" + (f": {err_msg}" if err_msg else "")
            db.commit()
            logger.warning("wa_status marked_failed msg_id=%s code=%s", msg_id, err_code)
    except Exception:
        logger.exception("delivery_status DB update error msg_id=%s", msg_id)
