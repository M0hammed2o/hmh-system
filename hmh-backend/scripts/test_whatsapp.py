"""
WhatsApp Cloud API smoke test.

Usage:
    python scripts/test_whatsapp.py

Reads all config from .env — never prints the access token.
Sends a plain-text message to WHATSAPP_TEST_TO.

IMPORTANT NOTES:
  - Plain text messages only work within an active 24-hour conversation window
    (the recipient must have sent the business a message first).
  - Outside the 24-hour window you must use an approved template message.
  - Do NOT use 'hello_world' for production — it only works with Meta's
    public test numbers, not real business numbers.
  - Set WHATSAPP_ENABLED=true and provide a valid ACCESS_TOKEN before running.
"""

import sys
import os

# Make sure we can import from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.services.whatsapp_service import send_text_message

GREEN = "\033[92m"
RED   = "\033[91m"
RESET = "\033[0m"
BOLD  = "\033[1m"


def check(label: str, condition: bool, detail: str = "") -> bool:
    mark = f"{GREEN}PASS{RESET}" if condition else f"{RED}FAIL{RESET}"
    print(f"  {mark}  {label}" + (f"  ({detail})" if detail else ""))
    return condition


def main() -> int:
    print(f"\n{BOLD}WhatsApp Cloud API — Smoke Test{RESET}")
    print("─" * 45)

    passed = 0
    failed = 0

    def record(ok: bool) -> None:
        nonlocal passed, failed
        if ok:
            passed += 1
        else:
            failed += 1

    # 1. Config checks
    record(check("WHATSAPP_ENABLED is true",
                 settings.WHATSAPP_ENABLED,
                 "set WHATSAPP_ENABLED=true in .env"))

    record(check("WHATSAPP_PHONE_NUMBER_ID set",
                 bool(settings.WHATSAPP_PHONE_NUMBER_ID),
                 settings.WHATSAPP_PHONE_NUMBER_ID or "missing"))

    record(check("WHATSAPP_ACCESS_TOKEN set",
                 bool(settings.WHATSAPP_ACCESS_TOKEN),
                 "(token present)" if settings.WHATSAPP_ACCESS_TOKEN else "missing"))

    record(check("WHATSAPP_TEST_TO set",
                 bool(settings.WHATSAPP_TEST_TO),
                 settings.WHATSAPP_TEST_TO or "missing — set WHATSAPP_TEST_TO in .env"))

    record(check("WHATSAPP_VERIFY_TOKEN set",
                 bool(settings.WHATSAPP_VERIFY_TOKEN)))

    print(f"\n  API version : {settings.WHATSAPP_API_VERSION}")
    print(f"  Phone ID    : {settings.WHATSAPP_PHONE_NUMBER_ID}")
    print(f"  Business ID : {settings.WHATSAPP_BUSINESS_ACCOUNT_ID}")
    print(f"  Test number : {settings.WHATSAPP_TEST_TO}")

    if failed > 0:
        print(f"\n  {RED}Config errors — fix .env before sending.{RESET}\n")
        return 1

    # 2. Send test message
    to = settings.WHATSAPP_TEST_TO
    body = (
        "HMH Construction OS — WhatsApp test message.\n"
        "If you received this, the Cloud API integration is working."
    )

    print(f"\n  Sending plain-text message to +{to} ...")
    status, msg_id = send_text_message(to, body)

    ok = status in ("SENT", "MOCK_SENT")
    record(check(
        f"send_text_message returned {status}",
        ok,
        msg_id or "no message ID",
    ))

    if status == "SENT":
        print(f"\n  {GREEN}Message sent successfully.{RESET}")
        print(f"  Provider message ID: {msg_id}")
    elif status == "MOCK_SENT":
        print(f"\n  {GREEN}Mock send recorded (WHATSAPP_ENABLED=false).{RESET}")
    else:
        print(f"\n  {RED}Send failed: {msg_id}{RESET}")
        print("  Common causes:")
        print("  - Access token expired or invalid")
        print("  - Recipient not in 24-hour conversation window (use a template)")
        print("  - Phone number not registered on WhatsApp")
        print("  - Business account not verified")

    # Summary
    print("\n" + "─" * 45)
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
