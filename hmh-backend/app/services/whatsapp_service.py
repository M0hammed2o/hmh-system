"""
WhatsApp Cloud API sender — HMH Construction OS.

Behaviour:
  WHATSAPP_ENABLED=false  →  MOCK_SENT (stored in queue, no HTTP call)
  WHATSAPP_ENABLED=true   →  Real Meta Cloud API call

The access token is NEVER logged or printed anywhere in this module.
"""

import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _messages_url() -> str:
    return (
        f"https://graph.facebook.com"
        f"/{settings.WHATSAPP_API_VERSION}"
        f"/{settings.WHATSAPP_PHONE_NUMBER_ID}"
        f"/messages"
    )


def _auth_headers() -> dict:
    """Return auth headers. Token is never placed in log calls."""
    return {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def _is_configured() -> bool:
    return bool(settings.WHATSAPP_ACCESS_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID)


def _normalise_phone(phone: str) -> str:
    """Strip leading + so Meta accepts the number."""
    return phone.lstrip("+").strip()


def _handle_response(resp: httpx.Response) -> tuple[str, Optional[str]]:
    """Parse a Meta API response into (status, message_id_or_error)."""
    try:
        data = resp.json()
    except Exception:
        data = {}

    if resp.status_code == 200:
        msg_id = data.get("messages", [{}])[0].get("id")
        return ("SENT", msg_id)

    # Extract error text without including any token
    err = data.get("error", {})
    error_text = err.get("message") or err.get("error_data", {}).get("details") or resp.text[:200]

    if resp.status_code == 401:
        logger.error("TOKEN EXPIRED / INVALID — WhatsApp API returned 401. Rotate WHATSAPP_ACCESS_TOKEN.")
        print("TOKEN EXPIRED / INVALID — WhatsApp API returned 401. Rotate WHATSAPP_ACCESS_TOKEN.", flush=True)

    logger.error("WhatsApp API error %s: %s", resp.status_code, error_text)
    return ("FAILED", error_text)


# ── Public API ────────────────────────────────────────────────────────────────

def send_text_message(
    to_phone: str,
    body: str,
) -> tuple[str, Optional[str]]:
    """
    Send a plain-text WhatsApp message.

    IMPORTANT: Plain-text messages only work when:
    - The recipient has messaged the business first (within 24 hours), OR
    - You are replying within an active 24-hour conversation window.
    Outside that window you must use an approved template instead.

    Returns:
      ("SENT",      message_id)  — real send succeeded
      ("MOCK_SENT", None)        — WHATSAPP_ENABLED=false
      ("FAILED",    error_text)  — real send failed
    """
    to = _normalise_phone(to_phone)

    if not settings.WHATSAPP_ENABLED:
        logger.info("[MOCK] WhatsApp text → %s (body omitted from log)", to)
        return ("MOCK_SENT", None)

    if not _is_configured():
        logger.warning("WhatsApp enabled but PHONE_NUMBER_ID or ACCESS_TOKEN not set — MOCK_SENT.")
        return ("MOCK_SENT", None)

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    try:
        resp = httpx.post(_messages_url(), json=payload, headers=_auth_headers(), timeout=15)
        return _handle_response(resp)
    except Exception as exc:
        logger.exception("WhatsApp send_text_message network error")
        return ("FAILED", str(exc))


# Keep the old name as an alias so existing callers don't break
send_text = send_text_message


def send_template_message(
    to_phone: str,
    template_name: str,
    language_code: str = "en_US",
    components: Optional[list] = None,
) -> tuple[str, Optional[str]]:
    """
    Send an approved Meta template message.

    Template messages work outside the 24-hour conversation window.
    The template must be pre-approved in Meta Business Manager.

    NOTE: Do NOT use 'hello_world' for production — it only works with
    Meta's public test numbers. Create and submit your own templates.

    Returns same (status, message_id_or_error) tuple as send_text_message.
    """
    to = _normalise_phone(to_phone)

    if not settings.WHATSAPP_ENABLED:
        logger.info("[MOCK] WhatsApp template '%s' → %s", template_name, to)
        return ("MOCK_SENT", None)

    if not _is_configured():
        logger.warning("WhatsApp enabled but credentials not set — MOCK_SENT.")
        return ("MOCK_SENT", None)

    payload: dict = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
        },
    }
    if components:
        payload["template"]["components"] = components

    try:
        resp = httpx.post(_messages_url(), json=payload, headers=_auth_headers(), timeout=15)
        return _handle_response(resp)
    except Exception as exc:
        logger.exception("WhatsApp send_template_message network error")
        return ("FAILED", str(exc))


# ── Webhook helpers ───────────────────────────────────────────────────────────

def verify_webhook(mode: str, token: str, challenge: str) -> Optional[str]:
    """
    Verify the Meta webhook handshake.
    Returns the challenge string on success, None on failure.
    """
    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        return challenge
    logger.warning("WhatsApp webhook verification failed: mode=%s", mode)
    return None


def parse_incoming(payload: dict) -> list[dict]:
    """
    Extract incoming user messages from a Meta webhook POST body.
    Returns list of dicts: {from_number, body, message_id, timestamp}.
    """
    results = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                if msg.get("type") != "text":
                    continue
                results.append({
                    "from_number": f"+{msg.get('from', '')}",
                    "body": msg.get("text", {}).get("body", "").strip(),
                    "message_id": msg.get("id"),
                    "timestamp": msg.get("timestamp"),
                })
    return results


def parse_statuses(payload: dict) -> list[dict]:
    """
    Extract delivery/read status updates from a Meta webhook POST body.
    Returns list of dicts: {message_id, status, recipient_id, timestamp}.
    """
    results = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for status in value.get("statuses", []):
                results.append({
                    "message_id": status.get("id"),
                    "status": status.get("status"),       # sent/delivered/read/failed
                    "recipient_id": status.get("recipient_id"),
                    "timestamp": status.get("timestamp"),
                    "errors": status.get("errors", []),
                })
    return results
