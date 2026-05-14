"""
WhatsApp webhook routes.

GET  /whatsapp/webhook  — Meta verification handshake
POST /whatsapp/webhook  — Incoming messages + delivery statuses
"""

import logging
import re

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import PlainTextResponse

from app.dependencies import DbSession
from app.schemas.common import ApiSuccess
from app.services import notification_service, whatsapp_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

print("### REAL WHATSAPP WEBHOOK FILE LOADED ###", flush=True)

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

@router.get("/debug")
def debug_router():
    print("### GET /whatsapp/debug HIT ###", flush=True)
    return {
        "loaded": True,
        "file": __file__,
        "message": "whatsapp webhook router active",
    }


# ── Verification ──────────────────────────────────────────────────────────────

@router.get("/webhook")
def verify_webhook(
    hub_mode:      str = Query(alias="hub.mode",         default=""),
    hub_token:     str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge",    default=""),
):
    print("### GET WHATSAPP WEBHOOK HIT ###", flush=True)
    result = whatsapp_service.verify_webhook(hub_mode, hub_token, hub_challenge)
    if result:
        print(f"[WA-WEBHOOK] Verified OK, challenge returned", flush=True)
        return PlainTextResponse(result)
    print(f"[WA-WEBHOOK] Verification FAILED — bad token", flush=True)
    return Response(status_code=403)


# ── Incoming messages + statuses ──────────────────────────────────────────────

@router.post("/webhook")
async def receive_webhook(request: Request, db: DbSession):
    print("### POST WHATSAPP WEBHOOK HIT ###", flush=True)
    try:
        payload = await request.json()
    except Exception:
        return Response(status_code=200)

    messages = whatsapp_service.parse_incoming(payload)
    statuses = whatsapp_service.parse_statuses(payload)

    print(f"[WA-WEBHOOK] Received: {len(messages)} message(s), {len(statuses)} status update(s)", flush=True)

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

        print(f"[WA-WEBHOOK] from={_normalise(from_number)} body={body_raw!r} intent={intent} mr={mr_match and mr_match.group(0)}", flush=True)

        # ── RESET TEST ALERTS — exact phrase, checked before intent ───────────
        if normalized == "RESET TEST ALERTS":
            print("[WA-WEBHOOK] Command=RESET_TEST_ALERTS", flush=True)
            reset_count = _reset_test_alerts(db, from_number)
            _reply(
                from_number,
                f"Test alerts reset. You can ACK again. ({reset_count} record(s) reset)"
            )
            continue

        # ── LIST ──────────────────────────────────────────────────────────────
        if "list" in tokens:
            print(f"[WA-WEBHOOK] Command=LIST", flush=True)
            _reply(from_number, _list_pending_alerts(db, from_number))
            continue

        # ── MR-specific commands (ID found in message) ────────────────────────
        if mr_match:
            mr_number = mr_match.group(0).upper()
            if intent == "APPROVE":
                print(f"[WA-WEBHOOK] Command=APPROVE mr={mr_number}", flush=True)
                result, reply = _approve_mr(db, mr_number, from_number)
                approved.append({"mr_number": mr_number, "result": result})
                _reply(from_number, reply)
                print(f"[WA-WEBHOOK] APPROVE done: result={result}", flush=True)
            elif intent == "REJECT":
                reason = _extract_reason(body_raw, tokens) or "Rejected via WhatsApp"
                print(f"[WA-WEBHOOK] Command=REJECT mr={mr_number} reason={reason!r}", flush=True)
                result, reply = _reject_mr(db, mr_number, from_number, reason)
                rejected.append({"mr_number": mr_number, "result": result})
                _reply(from_number, reply)
                print(f"[WA-WEBHOOK] REJECT done: result={result}", flush=True)
            else:
                print(f"[WA-WEBHOOK] Command=UNKNOWN_MR body={body_raw!r}", flush=True)
                _reply(from_number, _unknown_reply())
            continue

        # ── Safety check: nothing pending → skip processing ───────────────────
        if intent in ("ACK", "APPROVE", "REJECT"):
            if _latest_pending_queue_entry(db, from_number) is None:
                print(f"[WA-WEBHOOK] No pending alerts for {_normalise(from_number)}", flush=True)
                _reply(from_number, "No alerts to process.")
                continue

        # ── General intent — applies to latest pending alert ──────────────────
        if intent == "ACK":
            print(f"[WA-WEBHOOK] Command=ACK", flush=True)
            count = _ack_with_variants(db, from_number)
            total_acked += count
            _reply(from_number, f"Alerts acknowledged. ({count} updated)")
            print(f"[WA-WEBHOOK] ACK done: {count} updated", flush=True)

        elif intent == "APPROVE":
            print(f"[WA-WEBHOOK] Command=APPROVE_ALERT", flush=True)
            result, reply = _approve_latest_alert(db, from_number)
            _reply(from_number, reply)
            print(f"[WA-WEBHOOK] APPROVE_ALERT done: result={result}", flush=True)

        elif intent == "REJECT":
            reason = _extract_reason(body_raw, tokens)
            print(f"[WA-WEBHOOK] Command=REJECT_ALERT reason={reason!r}", flush=True)
            result, reply = _reject_latest_alert(db, from_number, reason)
            _reply(from_number, reply)
            print(f"[WA-WEBHOOK] REJECT_ALERT done: result={result}", flush=True)

        else:
            print(f"[WA-WEBHOOK] Command=UNKNOWN body={body_raw!r}", flush=True)
            _reply(from_number, _unknown_reply())

    print(f"[WA-WEBHOOK] Done: acked={total_acked} approved={len(approved)} rejected={len(rejected)}", flush=True)

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
    from app.core.config import settings
    print(f"[WA-REPLY] Sending to={_normalise(to)} enabled={settings.WHATSAPP_ENABLED}", flush=True)
    try:
        status, msg_id = whatsapp_service.send_text_message(to, text)
        print(f"[WA-REPLY] status={status} id={msg_id} text={text[:60]!r}", flush=True)
        logger.info("WhatsApp reply to %s: status=%s id=%s", _normalise(to), status, msg_id)
    except Exception as exc:
        print(f"[WA-REPLY] EXCEPTION: {exc}", flush=True)
        logger.exception("WhatsApp reply failed to %s", _normalise(to))


# ── ACK with phone variants ───────────────────────────────────────────────────

def _ack_with_variants(db, from_phone: str) -> int:
    total = 0
    seen: set = set()
    for variant in _phone_variants(from_phone):
        if variant in seen:
            continue
        seen.add(variant)
        n = notification_service.acknowledge_by_phone(db, variant)
        print(f"[WA-ACK] variant={variant!r} matched={n}", flush=True)
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
            print(f"[WA-RESET] queue id={entry.id} phone={variant!r} -> SENT", flush=True)
            if entry.alert_id and entry.alert_id not in seen_alert_ids:
                seen_alert_ids.add(entry.alert_id)

    # Reset parent alerts so they show as OPEN / Pending ACK again
    for alert_id in seen_alert_ids:
        alert = db.query(SystemAlert).filter(SystemAlert.id == alert_id).first()
        if alert and alert.status == AlertStatus.ACKNOWLEDGED:
            alert.status = AlertStatus.OPEN
            alert.acknowledged_at = None
            alert.acknowledged_by = None
            print(f"[WA-RESET] alert id={alert_id} -> OPEN", flush=True)

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
    print(f"[WA-APPROVE-ALERT] queue id={entry.id} -> ACKNOWLEDGED", flush=True)

    label = "Latest alert"
    if entry.alert_id:
        alert = db.query(SystemAlert).filter(SystemAlert.id == entry.alert_id).first()
        if alert:
            label = _short_title(alert)
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = now
            print(f"[WA-APPROVE-ALERT] alert id={alert.id} -> ACKNOWLEDGED", flush=True)

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
    print(f"[WA-REJECT-ALERT] queue id={entry.id} reason={reason!r} -> ACKNOWLEDGED", flush=True)

    label = "Latest alert"
    if entry.alert_id:
        alert = db.query(SystemAlert).filter(SystemAlert.id == entry.alert_id).first()
        if alert:
            label = _short_title(alert)
            alert.status = AlertStatus.RESOLVED
            alert.acknowledged_at = now
            alert.resolved_at = now
            print(f"[WA-REJECT-ALERT] alert id={alert.id} -> RESOLVED", flush=True)

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

        print(f"[WA-APPROVE] Found {mr_number} status={mr.status.value}", flush=True)

        if mr.status not in (RecordStatus.SUBMITTED, RecordStatus.PENDING_APPROVAL):
            return (
                "wrong_status",
                f"{mr_number} cannot be approved because it is currently {mr.status.value}.",
            )

        actor = _find_user_by_phone(db, from_phone)
        actor_id = (actor.id if actor else None) or mr.requested_by
        print(f"[WA-APPROVE] actor_id={actor_id}", flush=True)

        mr_service.approve_request(db, mr.id, actor_id)
        return ("approved", f"{mr_number} has been approved successfully.")

    except Exception as exc:
        print(f"[WA-APPROVE] EXCEPTION: {exc}", flush=True)
        logger.exception("approve_mr failed for %s", mr_number)
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

        print(f"[WA-REJECT] Found {mr_number} status={mr.status.value}", flush=True)
        actor = _find_user_by_phone(db, from_phone)
        actor_id = (actor.id if actor else None) or mr.requested_by

        mr_service.reject_request(db, mr.id, actor_id, reason)
        return ("rejected", f"{mr_number} has been rejected. Reason: {reason}")

    except Exception as exc:
        print(f"[WA-REJECT] EXCEPTION: {exc}", flush=True)
        logger.exception("reject_mr failed for %s", mr_number)
        return ("error", f"Error processing {mr_number}: {exc}")


def _find_user_by_phone(db, from_phone: str):
    from app.models.user import User
    for variant in _phone_variants(from_phone):
        user = db.query(User).filter(User.phone == variant).first()
        if user:
            print(f"[WA-USER] Found user for variant={variant!r}", flush=True)
            return user
    print(f"[WA-USER] No user found for phone={_normalise(from_phone)}", flush=True)
    return None


# ── Delivery status ───────────────────────────────────────────────────────────

def _handle_delivery_status(db, status: dict) -> None:
    msg_id    = status.get("message_id")
    wa_status = status.get("status")
    if not msg_id or not wa_status:
        return
    print(f"[WA-STATUS] id={msg_id} status={wa_status}", flush=True)
    try:
        from app.models.notification_queue import NotificationQueue
        from app.models.enums import NotificationStatus
        record = db.query(NotificationQueue).filter(
            NotificationQueue.provider_message_id == msg_id
        ).first()
        if not record:
            return
        if wa_status == "read":
            from datetime import datetime, timezone
            record.status = NotificationStatus.ACKNOWLEDGED
            record.acknowledged_at = datetime.now(timezone.utc)
            db.commit()
            print(f"[WA-STATUS] Marked ACKNOWLEDGED", flush=True)
        elif wa_status == "failed":
            errs = status.get("errors", [])
            record.status = NotificationStatus.FAILED
            record.error_message = errs[0].get("title", "Delivery failed") if errs else "Delivery failed"
            db.commit()
            print(f"[WA-STATUS] Marked FAILED", flush=True)
    except Exception:
        logger.exception("delivery_status update error msg_id=%s", msg_id)
