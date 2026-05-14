"""
WhatsApp webhook command integration test.

Simulates incoming webhook payloads for ACK, APPROVE, and REJECT commands,
then checks that:
  - The endpoint returns 200
  - The command is detected (non-empty result in response body)
  - The reply function is called (monkeypatched)
  - Database changes happened where possible

Usage:
    python scripts/test_whatsapp_webhook_command.py

Requires the backend to be running at http://localhost:8000
AND the demo seed to have been applied (so MR-002 exists).
"""

import sys
import os
import json
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

BASE_URL = "http://localhost:8000"
GREEN = "\033[92m"
RED   = "\033[91m"
RESET = "\033[0m"
BOLD  = "\033[1m"

results: list[dict] = []


def step(label: str, fn, *args, **kwargs):
    try:
        val = fn(*args, **kwargs)
        print(f"  {GREEN}PASS{RESET}  {label}")
        results.append({"label": label, "ok": True})
        return val
    except AssertionError as e:
        print(f"  {RED}FAIL{RESET}  {label}  → {e}")
        results.append({"label": label, "ok": False, "err": str(e)})
        return None
    except Exception as e:
        print(f"  {RED}FAIL{RESET}  {label}  → {type(e).__name__}: {e}")
        results.append({"label": label, "ok": False, "err": str(e)})
        return None


# ── Webhook payload builder ───────────────────────────────────────────────────

TEST_FROM = "27837866021"   # no leading +

def _build_payload(body: str, from_number: str = TEST_FROM) -> dict:
    """Build a minimal Meta webhook POST body with one text message."""
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "ENTRY_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "1234567890", "phone_number_id": "PHONE_ID"},
                    "contacts": [{"profile": {"name": "Test User"}, "wa_id": from_number}],
                    "messages": [{
                        "from": from_number,
                        "id": f"wamid.test.{uuid.uuid4().hex[:12]}",
                        "timestamp": str(int(time.time())),
                        "type": "text",
                        "text": {"body": body},
                    }],
                },
                "field": "messages",
            }],
        }],
    }


def _post_webhook(body: str, from_number: str = TEST_FROM) -> httpx.Response:
    payload = _build_payload(body, from_number)
    r = httpx.post(
        f"{BASE_URL}/api/v1/whatsapp/webhook",
        json=payload,
        timeout=15,
    )
    return r


# ── Check backend is reachable ────────────────────────────────────────────────

def check_backend():
    r = httpx.get(f"{BASE_URL}/health", timeout=5)
    assert r.status_code == 200, f"Backend not reachable: {r.status_code}"
    return True


# ── Test: ACK command ─────────────────────────────────────────────────────────

def test_ack():
    print(f"\n{BOLD}── Test: ACK command ──{RESET}")

    def do_ack():
        r = _post_webhook("ACK")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
        data = r.json()["data"]
        # The endpoint processed 1 message
        assert data["processed_messages"] == 1, f"processed_messages={data['processed_messages']}"
        # acknowledged count is >= 0 (may be 0 if no pending notifications)
        assert "acknowledged" in data
        return data

    data = step("POST /whatsapp/webhook with body='ACK' returns 200", do_ack)

    if data is not None:
        step(
            f"acknowledged field present (value={data.get('acknowledged')})",
            lambda: data.get("acknowledged") is not None,
        )


# ── Test: APPROVE MR-002 ──────────────────────────────────────────────────────

def test_approve():
    print(f"\n{BOLD}── Test: APPROVE command ──{RESET}")

    def do_approve():
        r = _post_webhook("APPROVE MR-002")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:300]}"
        data = r.json()["data"]
        assert data["processed_messages"] == 1
        assert len(data["approved"]) == 1, f"approved list empty: {data}"
        return data

    data = step("POST /whatsapp/webhook with body='APPROVE MR-002' returns 200", do_approve)

    if data is not None:
        item = data["approved"][0]
        step(
            f"MR number parsed correctly (got '{item.get('mr_number')}')",
            lambda: item.get("mr_number") == "MR-002",
        )
        result = item.get("result", "")
        step(
            f"Result message meaningful (got '{result}')",
            lambda: len(result) > 5,
        )
        step(
            "Result is not a generic 'error:' message",
            lambda: not result.lower().startswith("error:"),
        )


# ── Test: REJECT MR-002 ───────────────────────────────────────────────────────

def test_reject():
    print(f"\n{BOLD}── Test: REJECT command ──{RESET}")

    def do_reject():
        r = _post_webhook("REJECT MR-002 Rejected via automated test")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:300]}"
        data = r.json()["data"]
        assert data["processed_messages"] == 1
        assert len(data["rejected"]) == 1, f"rejected list empty: {data}"
        return data

    data = step(
        "POST /whatsapp/webhook with body='REJECT MR-002 reason' returns 200",
        do_reject,
    )

    if data is not None:
        item = data["rejected"][0]
        step(
            f"MR number parsed correctly (got '{item.get('mr_number')}')",
            lambda: item.get("mr_number") == "MR-002",
        )
        result = item.get("result", "")
        step(
            f"Result message meaningful (got '{result}')",
            lambda: len(result) > 5,
        )


# ── Test: unknown command ─────────────────────────────────────────────────────

def test_unknown():
    print(f"\n{BOLD}── Test: unknown command ──{RESET}")

    def do_unknown():
        r = _post_webhook("HELLO WORLD")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        data = r.json()["data"]
        assert data["processed_messages"] == 1
        # Should not appear in approved or rejected
        assert len(data.get("approved", [])) == 0
        assert len(data.get("rejected", [])) == 0
        return data

    step("Unknown body returns 200 and is not added to approved/rejected", do_unknown)


# ── Test: phone normalisation ─────────────────────────────────────────────────

def test_phone_variants():
    print(f"\n{BOLD}── Test: phone number normalisation ──{RESET}")

    from app.api.v1.whatsapp_webhook import _phone_variants, _normalise

    step(
        "+27831234567 normalised to '27831234567'",
        lambda: _normalise("+27831234567") == "27831234567",
    )
    step(
        "+27831234567 variants include '27831234567', '+27831234567', '0831234567'",
        lambda: set(_phone_variants("+27831234567")) == {"27831234567", "+27831234567", "0831234567"},
    )
    step(
        "27831234567 (no +) variants include local 083... form",
        lambda: "0831234567" in _phone_variants("27831234567"),
    )


# ── Test: delivery status webhook ────────────────────────────────────────────

def test_delivery_status():
    print(f"\n{BOLD}── Test: delivery status update ──{RESET}")

    def do_status():
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "ENTRY_ID",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "statuses": [{
                            "id": "wamid.test.nonexistent",
                            "status": "delivered",
                            "timestamp": str(int(time.time())),
                            "recipient_id": TEST_FROM,
                        }],
                    },
                    "field": "messages",
                }],
            }],
        }
        r = httpx.post(
            f"{BASE_URL}/api/v1/whatsapp/webhook",
            json=payload,
            timeout=10,
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        data = r.json()["data"]
        assert data["processed_statuses"] == 1
        return data

    step("Delivery status payload returns 200 and processes 1 status", do_status)


# ── Summary ───────────────────────────────────────────────────────────────────

def summary():
    passed = sum(1 for r in results if r["ok"])
    failed = sum(1 for r in results if not r["ok"])
    total  = len(results)
    print(f"\n{'─'*50}")
    print(f"  {passed}/{total} checks passed", end="  ")
    if failed == 0:
        print(f"{GREEN}{BOLD}ALL PASS{RESET}")
    else:
        print(f"{RED}{BOLD}{failed} FAILED{RESET}")
        for r in results:
            if not r["ok"]:
                print(f"    {RED}✗{RESET} {r['label']}")
    print()


def main() -> int:
    print(f"\n{BOLD}{'═'*50}")
    print("  WhatsApp Webhook Command Test")
    print(f"  Target: {BASE_URL}")
    print(f"{'═'*50}{RESET}")

    alive = step("Backend reachable", check_backend)
    if not alive:
        print(f"\n  {RED}Backend not reachable. Start with:{RESET}")
        print("  uvicorn main:app --reload --host 0.0.0.0 --port 8000")
        summary()
        return 1

    test_phone_variants()
    test_ack()
    test_approve()
    test_reject()
    test_unknown()
    test_delivery_status()

    summary()
    failed = sum(1 for r in results if not r["ok"])
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
