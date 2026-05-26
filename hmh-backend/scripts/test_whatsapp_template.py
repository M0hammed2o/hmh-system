"""
WhatsApp approved-template smoke test.

Usage:
    python scripts/test_whatsapp_template.py

Reads config from .env — the access token is NEVER printed or logged.

Sends both the alert template (WHATSAPP_ALERT_TEMPLATE_NAME) and the daily
summary template (WHATSAPP_DAILY_SUMMARY_TEMPLATE_NAME) to
WHATSAPP_TEST_PHONE_NUMBER (falls back to WHATSAPP_TEST_TO if not set).

Template messages work outside the 24-hour conversation window and are
required for proactive business-initiated notifications.

Prerequisites:
  1. WHATSAPP_ENABLED=true
  2. Valid WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID
  3. Templates approved in Meta Business Manager
  4. WHATSAPP_TEST_PHONE_NUMBER (or WHATSAPP_TEST_TO) set to a real number
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.services.whatsapp_service import send_template_message

GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD  = "\033[1m"


def check(label: str, condition: bool, detail: str = "") -> bool:
    mark = f"{GREEN}PASS{RESET}" if condition else f"{RED}FAIL{RESET}"
    print(f"  {mark}  {label}" + (f"  ({detail})" if detail else ""))
    return condition


def main() -> int:
    print(f"\n{BOLD}WhatsApp Template Validation — HMH Construction OS{RESET}")
    print("─" * 55)

    passed = 0
    failed = 0

    def record(ok: bool) -> None:
        nonlocal passed, failed
        if ok:
            passed += 1
        else:
            failed += 1

    # ── Config checks ─────────────────────────────────────────────────────────
    print(f"\n{BOLD}1. Configuration{RESET}")

    record(check("WHATSAPP_ENABLED is true",
                 settings.WHATSAPP_ENABLED,
                 "set WHATSAPP_ENABLED=true in .env"))

    record(check("WHATSAPP_PHONE_NUMBER_ID set",
                 bool(settings.WHATSAPP_PHONE_NUMBER_ID),
                 settings.WHATSAPP_PHONE_NUMBER_ID or "missing"))

    record(check("WHATSAPP_ACCESS_TOKEN set",
                 bool(settings.WHATSAPP_ACCESS_TOKEN),
                 "(token present)" if settings.WHATSAPP_ACCESS_TOKEN else "missing"))

    test_phone = settings.WHATSAPP_TEST_PHONE_NUMBER or settings.WHATSAPP_TEST_TO
    record(check("Test phone number set",
                 bool(test_phone),
                 test_phone or "set WHATSAPP_TEST_PHONE_NUMBER in .env"))

    alert_tpl = settings.WHATSAPP_ALERT_TEMPLATE_NAME
    summary_tpl = settings.WHATSAPP_DAILY_SUMMARY_TEMPLATE_NAME
    lang = settings.WHATSAPP_ALERT_TEMPLATE_LANGUAGE or "en_US"

    record(check("WHATSAPP_ALERT_TEMPLATE_NAME set",
                 bool(alert_tpl),
                 alert_tpl or "missing — set WHATSAPP_ALERT_TEMPLATE_NAME in .env"))

    print(f"\n  API version     : {settings.WHATSAPP_API_VERSION}")
    print(f"  Phone ID        : {settings.WHATSAPP_PHONE_NUMBER_ID}")
    print(f"  Alert template  : {alert_tpl or '(not set)'}")
    print(f"  Summary template: {summary_tpl or '(not set)'}")
    print(f"  Language        : {lang}")
    print(f"  Test number     : {test_phone or '(not set)'}")

    if failed > 0:
        print(f"\n  {RED}Config errors — fix .env before testing templates.{RESET}\n")
        return 1

    # ── Template sends ─────────────────────────────────────────────────────────
    print(f"\n{BOLD}2. Template Sends{RESET}")

    # Alert template
    print(f"\n  Sending alert template '{alert_tpl}' → {test_phone} ...")
    status, msg_id = send_template_message(test_phone, alert_tpl, lang)
    ok = status in ("SENT", "MOCK_SENT")
    record(check(
        f"Alert template '{alert_tpl}' → {status}",
        ok,
        msg_id or "no message ID",
    ))
    if not ok:
        print(f"  {RED}Error: {msg_id}{RESET}")
        print("  Verify the template name exactly matches Meta Business Manager.")
        print("  Template names are lowercase, underscores only, no spaces.")

    # Daily summary template (optional)
    if summary_tpl:
        print(f"\n  Sending daily-summary template '{summary_tpl}' → {test_phone} ...")
        status2, msg_id2 = send_template_message(test_phone, summary_tpl, lang)
        ok2 = status2 in ("SENT", "MOCK_SENT")
        record(check(
            f"Daily summary template '{summary_tpl}' → {status2}",
            ok2,
            msg_id2 or "no message ID",
        ))
        if not ok2:
            print(f"  {RED}Error: {msg_id2}{RESET}")
    else:
        print(f"\n  {YELLOW}SKIP{RESET}  Daily summary template (WHATSAPP_DAILY_SUMMARY_TEMPLATE_NAME not set)")

    # ── Cost optimization summary ──────────────────────────────────────────────
    print(f"\n{BOLD}3. Cost Optimization Config{RESET}")
    opt = settings.WHATSAPP_COST_OPTIMIZATION_ENABLED
    print(f"  Cost optimization : {'enabled' if opt else 'disabled'}")
    if opt:
        print(f"  Summary interval  : {settings.WHATSAPP_SUMMARY_INTERVAL_MINUTES} min (MEDIUM/LOW delay)")
        print(f"  Hourly cap        : {settings.WHATSAPP_MAX_ALERTS_PER_HOUR_PER_RECIPIENT} per recipient")
        qh = settings.WHATSAPP_QUIET_HOURS_ENABLED
        print(f"  Quiet hours       : {'enabled ' + settings.WHATSAPP_QUIET_HOURS_START + '–' + settings.WHATSAPP_QUIET_HOURS_END + ' UTC' if qh else 'disabled'}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "─" * 55)
    total = passed + failed
    print(f"  {passed}/{total} checks passed", end="")
    if failed == 0:
        print(f"  {GREEN}{BOLD}ALL PASS{RESET}")
    else:
        print(f"  {RED}{BOLD}{failed} FAILED{RESET}")
    print()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
