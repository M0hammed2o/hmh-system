"""
WhatsApp Cloud API sender — HMH Construction OS.

Behaviour:
  WHATSAPP_ENABLED=false  →  MOCK_SENT (stored in queue, no HTTP call)
  WHATSAPP_ENABLED=true   →  Real Meta Cloud API call

The access token is NEVER logged or printed anywhere in this module.
"""

import logging
import re as _re
from datetime import datetime, timezone as _tz
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Process-level cache: template_name → {components, language, status, fetched_at}
_template_cache: dict = {}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _messages_url() -> str:
    return (
        f"https://graph.facebook.com"
        f"/{settings.WHATSAPP_API_VERSION}"
        f"/{settings.WHATSAPP_PHONE_NUMBER_ID}"
        f"/messages"
    )


def _templates_url() -> str:
    return (
        f"https://graph.facebook.com"
        f"/{settings.WHATSAPP_API_VERSION}"
        f"/{settings.WHATSAPP_BUSINESS_ACCOUNT_ID}"
        f"/message_templates"
    )


# ── Template introspection ────────────────────────────────────────────────────

def fetch_template_info(template_name: str) -> Optional[dict]:
    """
    Query Meta Graph API for the template definition (cached 1 h per process).
    Returns the first matching template dict or None on any failure.
    Includes: name, language, status, components (with body text + example).
    """
    cached = _template_cache.get(template_name)
    if cached:
        age = (datetime.now(_tz.utc) - cached["fetched_at"]).total_seconds()
        if age < 3600:
            return cached

    if not settings.WHATSAPP_BUSINESS_ACCOUNT_ID or not settings.WHATSAPP_ACCESS_TOKEN:
        logger.debug("Cannot fetch template info: BUSINESS_ACCOUNT_ID or ACCESS_TOKEN missing")
        return None

    try:
        resp = httpx.get(
            _templates_url(),
            params={"name": template_name, "fields": "name,language,status,components"},
            headers=_auth_headers(),
            timeout=10,
        )
        data = resp.json()
        templates = data.get("data", [])
        if not templates:
            logger.warning("WA-TEMPLATE-NOT-FOUND name=%s (check Meta Business Manager)", template_name)
            return None
        result = dict(templates[0])
        result["fetched_at"] = datetime.now(_tz.utc)
        _template_cache[template_name] = result
        logger.info(
            "WA-TEMPLATE-INFO name=%s language=%s status=%s",
            result.get("name"), result.get("language"), result.get("status"),
        )
        return result
    except Exception as exc:
        logger.warning("WA-TEMPLATE-FETCH-FAILED name=%s error=%s", template_name, exc)
        return None


def count_body_vars(template_info: dict) -> int:
    """Count {{N}} variables in the BODY component of a fetched template."""
    for comp in template_info.get("components", []):
        if comp.get("type", "").upper() == "BODY":
            text = comp.get("text", "")
            return len(_re.findall(r'\{\{\d+\}\}', text))
    return 0


def resolve_template_params(template_name: str) -> tuple[int, str]:
    """
    Return (body_var_count, language_code) for the named template.
    Fetches live from Meta API; falls back to configured env vars on failure.
    This is the single source of truth used by both the test endpoint and
    the live notification queue sender.
    """
    info = fetch_template_info(template_name)
    if info:
        var_count = count_body_vars(info)
        lang = info.get("language") or settings.WHATSAPP_ALERT_TEMPLATE_LANGUAGE or "en_US"
        logger.info(
            "WA-TEMPLATE-RESOLVED name=%s var_count=%d lang=%s (source=meta_api)",
            template_name, var_count, lang,
        )
        return var_count, lang

    # Fallback to manually configured values
    var_count = max(0, int(getattr(settings, "WHATSAPP_ALERT_TEMPLATE_BODY_VAR_COUNT", 2)))
    lang = settings.WHATSAPP_ALERT_TEMPLATE_LANGUAGE or "en_US"
    logger.info(
        "WA-TEMPLATE-RESOLVED name=%s var_count=%d lang=%s (source=config_fallback)",
        template_name, var_count, lang,
    )
    return var_count, lang


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
        logger.error("WA_TOKEN_EXPIRED WhatsApp API returned 401 — rotate WHATSAPP_ACCESS_TOKEN")

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
