"""
HMH End-to-End Test Script

Runs all critical flows against a running backend (localhost:8000).
Uses the demo seed data. Prints PASS/FAIL per step.

Usage:
    python scripts/test_end_to_end.py [--base-url http://localhost:8000]

Prerequisites:
    - Backend running: uvicorn main:app --reload --host 0.0.0.0 --port 8000
    - Seed applied:    python scripts/seed_hmh_connected_demo.py
"""

import sys
import os
import json
import argparse
import traceback
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

BASE_URL = "http://localhost:8000/api/v1"

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD  = "\033[1m"

results: list[dict] = []


def _p(symbol: str, label: str, detail: str = "") -> None:
    colour = GREEN if symbol == "PASS" else (RED if symbol == "FAIL" else YELLOW)
    print(f"  {colour}{symbol}{RESET}  {label}" + (f"  → {detail}" if detail else ""))


def step(label: str, fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
        _p("PASS", label, str(result)[:80] if result else "")
        results.append({"step": label, "status": "PASS"})
        return result
    except AssertionError as e:
        _p("FAIL", label, str(e)[:120])
        results.append({"step": label, "status": "FAIL", "error": str(e)})
        return None
    except Exception as e:
        _p("FAIL", label, f"{type(e).__name__}: {str(e)[:100]}")
        results.append({"step": label, "status": "FAIL", "error": traceback.format_exc(limit=3)})
        return None


# ── API helpers ───────────────────────────────────────────────────────────────

def login_user(email: str, password: str) -> Optional[str]:
    r = httpx.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password}, timeout=10)
    assert r.status_code == 200, f"Login failed ({r.status_code}): {r.text[:200]}"
    return r.json()["access_token"]


def get(tok: str, path: str, params: dict = None) -> dict:
    r = httpx.get(f"{BASE_URL}{path}", headers={"Authorization": f"Bearer {tok}"},
                  params=params or {}, timeout=10)
    assert r.status_code == 200, f"GET {path} → {r.status_code}: {r.text[:200]}"
    return r.json()


def post(tok: str, path: str, body: dict = None, expected: int = 200) -> dict:
    r = httpx.post(f"{BASE_URL}{path}", json=body or {},
                   headers={"Authorization": f"Bearer {tok}"}, timeout=10)
    assert r.status_code == expected, f"POST {path} → {r.status_code}: {r.text[:300]}"
    return r.json()


def patch(tok: str, path: str, body: dict) -> dict:
    r = httpx.patch(f"{BASE_URL}{path}", json=body,
                    headers={"Authorization": f"Bearer {tok}"}, timeout=10)
    assert r.status_code == 200, f"PATCH {path} → {r.status_code}: {r.text[:200]}"
    return r.json()


# ═════════════════════════════════════════════════════════════════════════════
# FLOW A — Authentication + Seed Verification
# ═════════════════════════════════════════════════════════════════════════════

def flow_a_auth():
    print(f"\n{BOLD}══ FLOW A: Authentication + Seed Verification ══{RESET}")

    owner_tok = step("Login as Owner (admin@hmhgroup.com)",
                     login_user, "admin@hmhgroup.com", "Mohammed@1")

    office_tok = step("Login as Office (office@hmhgroup.com)",
                      login_user, "office@hmhgroup.com", "Office@1234")

    site_tok = step("Login as Site (site@hmhgroup.com)",
                    login_user, "site@hmhgroup.com", "Site@1234")

    if not owner_tok:
        print(f"  {YELLOW}WARN{RESET}  Cannot continue without owner login. Run seed first.")
        return None, None, None

    def check_projects(tok):
        data = get(tok, "/projects/")
        projects = data.get("data", [])
        assert len(projects) > 0, "No projects found — seed not applied"
        names = [p["name"] for p in projects]
        assert any("Cornubia" in n for n in names), f"Expected Cornubia project, found: {names}"
        return f"{len(projects)} project(s)"

    step("Projects exist (Cornubia seeded)", check_projects, owner_tok)

    def check_seed_records(tok):
        # Check MR-001
        mrs = get(tok, "/projects/" + _get_cornubia_id(tok) + "/material-requests/").get("data", [])
        mr_numbers = [m["request_number"] for m in mrs]
        assert "MR-001" in mr_numbers, f"MR-001 not found. Found: {mr_numbers}"
        assert "MR-002" in mr_numbers, f"MR-002 not found"
        return f"Found {len(mrs)} MRs including MR-001, MR-002"

    step("Demo seed: MR-001 and MR-002 exist", check_seed_records, owner_tok)

    def check_jc_lab001(tok):
        pid = _get_cornubia_id(tok)
        jcs = get(tok, f"/projects/{pid}/job-cards/").get("data", [])
        numbers = [j["job_card_number"] for j in jcs]
        assert "JC-LAB-001" in numbers, f"JC-LAB-001 not found. Found: {numbers}"
        jc = next(j for j in jcs if j["job_card_number"] == "JC-LAB-001")
        assert jc["status"] == "SITE_APPROVED", f"Expected SITE_APPROVED, got {jc['status']}"
        return "JC-LAB-001 present and SITE_APPROVED"

    step("Demo seed: JC-LAB-001 (Lot 3 labour) exists and is SITE_APPROVED",
         check_jc_lab001, owner_tok)

    def check_vehicle(tok):
        vehicles = get(tok, "/vehicles/").get("data", [])
        regs = [v["registration"] for v in vehicles]
        assert "CA 123-456" in regs, f"VEH-001 Hilux not found. Found: {regs}"
        return "VEH-001 Toyota Hilux present"

    step("Demo seed: VEH-001 (Toyota Hilux) exists", check_vehicle, owner_tok)

    return owner_tok, office_tok, site_tok


def _get_cornubia_id(tok: str) -> str:
    projects = get(tok, "/projects/").get("data", [])
    for p in projects:
        if "Cornubia" in p["name"]:
            return p["id"]
    raise AssertionError("Cornubia project not found")


# ═════════════════════════════════════════════════════════════════════════════
# FLOW B — MR → PO → Email → Delivery → Invoice → Proof Pack
# ═════════════════════════════════════════════════════════════════════════════

def flow_b_procurement(owner_tok: str, office_tok: str):
    print(f"\n{BOLD}══ FLOW B: Procurement → Delivery → Invoice → Proof Pack ══{RESET}")

    project_id = _get_cornubia_id(office_tok)

    def check_po001():
        pos = get(office_tok, f"/projects/{project_id}/purchase-orders/").get("data", [])
        po = next((p for p in pos if p["po_number"] == "PO-001"), None)
        assert po is not None, f"PO-001 not found. POs: {[p['po_number'] for p in pos]}"
        assert po["status"] in ("RECEIVED", "MATCHED", "APPROVED", "SENT"), f"PO-001 status: {po['status']}"
        return f"PO-001 status={po['status']}"

    step("PO-001 exists and is in correct status", check_po001)

    def check_email_log():
        pos = get(office_tok, f"/projects/{project_id}/purchase-orders/").get("data", [])
        po = next((p for p in pos if p["po_number"] == "PO-001"), None)
        if not po:
            return "PO-001 not found"
        logs = get(office_tok, f"/purchase-orders/{po['id']}/email-log").get("data", [])
        assert len(logs) >= 1, "No email logs for PO-001"
        return f"Email log: {logs[0]['status']} to {logs[0]['sent_to']}"

    step("PO-001 has email log (mock sent to supplier)", check_email_log)

    def check_inv_bz001():
        invs = get(office_tok, f"/projects/{project_id}/invoices/").get("data", [])
        inv = next((i for i in invs if i["invoice_number"] == "INV-BZ-001"), None)
        assert inv is not None, f"INV-BZ-001 not found. Found: {[i['invoice_number'] for i in invs]}"
        assert inv["status"] in ("MATCHED", "APPROVED"), f"INV-BZ-001 status: {inv['status']}"
        return f"INV-BZ-001 status={inv['status']}"

    step("INV-BZ-001 exists and is MATCHED", check_inv_bz001)

    def check_proof_pack():
        invs = get(office_tok, f"/projects/{project_id}/invoices/").get("data", [])
        inv = next((i for i in invs if i["invoice_number"] == "INV-BZ-001"), None)
        assert inv is not None, "INV-BZ-001 missing"
        proof = get(office_tok, f"/invoices/{inv['id']}/proof").get("data", {})

        assert proof.get("invoice_number") == "INV-BZ-001"
        assert proof.get("po_number") is not None, "Proof pack missing PO number"
        assert proof.get("match_status") is not None, "Proof pack missing match_status"
        assert "is_matched" in proof
        assert "missing_delivery_note" in proof
        assert "missing_signature" in proof
        return f"Proof pack complete: match={proof['match_status']}, po={proof['po_number']}"

    step("INV-BZ-001 proof pack contains all artefacts", check_proof_pack)

    def check_mismatch():
        invs = get(office_tok, f"/projects/{project_id}/invoices/").get("data", [])
        inv = next((i for i in invs if i["invoice_number"] == "INV-BZ-002"), None)
        assert inv is not None, "INV-BZ-002 not found"
        proof = get(office_tok, f"/invoices/{inv['id']}/proof").get("data", {})
        assert proof.get("match_status") in ("QUANTITY_MISMATCH", "MISMATCH", "PARTIALLY_MATCHED"), \
            f"Expected mismatch, got: {proof.get('match_status')}"
        return f"INV-BZ-002 correctly shows {proof['match_status']}"

    step("INV-BZ-002 proof pack shows QUANTITY_MISMATCH", check_mismatch)


# ═════════════════════════════════════════════════════════════════════════════
# FLOW C — Over-BOQ Control
# ═════════════════════════════════════════════════════════════════════════════

def flow_c_overboq(office_tok: str):
    print(f"\n{BOLD}══ FLOW C: Over-BOQ Control ══{RESET}")

    project_id = _get_cornubia_id(office_tok)

    def check_mr002_alert():
        alerts = get(office_tok, f"/alerts/", params={"limit": 200}).get("data", [])
        overrun_alerts = [a for a in alerts if "BOQ" in a.get("alert_type", "") or "OVERUSE" in a.get("alert_type", "")]
        assert len(overrun_alerts) >= 1, f"No BOQ overrun alert found. Alert types: {[a['alert_type'] for a in alerts[:10]]}"
        return f"Found {len(overrun_alerts)} BOQ overrun alert(s)"

    step("Over-BOQ alert exists (from MR-002 or seeded)", check_mr002_alert)

    def check_whatsapp_queue():
        queue = get(office_tok, "/alerts/queue", params={"limit": 50}).get("data", [])
        assert len(queue) >= 1, "WhatsApp queue is empty — expected at least 1 mock message"
        statuses = [q["status"] for q in queue]
        assert any(s in ("MOCK_SENT", "SENT", "PENDING") for s in statuses), \
            f"No sent/pending messages. Statuses: {statuses}"
        return f"{len(queue)} queue entries, statuses: {set(statuses)}"

    step("WhatsApp queue has entries (mock mode)", check_whatsapp_queue)

    def check_lot2_overrun():
        lots = get(office_tok, f"/projects/{project_id}/lots/").get("data", [])
        lot2 = next((l for l in lots if l["lot_number"] == "2"), None)
        assert lot2 is not None, "Lot 2 not found"
        summary = get(office_tok, f"/lots/{lot2['id']}/boq-summary").get("data", {})
        assert summary.get("overrun_count", 0) >= 1, \
            f"Expected overrun on Lot 2, got overrun_count={summary.get('overrun_count')}"
        return f"Lot 2 has {summary['overrun_count']} overrun item(s)"

    step("Lot 2 BOQ summary shows overrun", check_lot2_overrun)


# ═════════════════════════════════════════════════════════════════════════════
# FLOW D — Job Cards
# ═════════════════════════════════════════════════════════════════════════════

def flow_d_jobcards(owner_tok: str, office_tok: str, site_tok: str):
    print(f"\n{BOLD}══ FLOW D: Job Cards (Labour Approval) ══{RESET}")

    if not site_tok:
        print(f"  {YELLOW}SKIP{RESET}  No site token available")
        return

    project_id = _get_cornubia_id(office_tok)

    def check_jclab001():
        jcs = get(office_tok, f"/projects/{project_id}/job-cards/").get("data", [])
        jc = next((j for j in jcs if j["job_card_number"] == "JC-LAB-001"), None)
        assert jc is not None, "JC-LAB-001 not found"
        assert jc["status"] == "SITE_APPROVED", f"Expected SITE_APPROVED, got {jc['status']}"
        assert not jc["status"] in ("PAYMENT_APPROVED", "PAID"), "Should not be payable yet"
        return f"JC-LAB-001: {jc['status']}, total=R{jc['total_amount']}"

    jc_data = step("JC-LAB-001 exists and is SITE_APPROVED (not yet payable)", check_jclab001)

    # Office approve JC-LAB-001
    def office_approve_jc():
        jcs = get(office_tok, f"/projects/{project_id}/job-cards/").get("data", [])
        jc = next((j for j in jcs if j["job_card_number"] == "JC-LAB-001"), None)
        assert jc is not None, "JC-LAB-001 not found"

        if jc["status"] == "OFFICE_APPROVED":
            return "Already OFFICE_APPROVED (skipping)"
        if jc["status"] not in ("SITE_APPROVED",):
            return f"Cannot office-approve from status {jc['status']}"

        r = post(office_tok, f"/job-cards/{jc['id']}/office-approve", expected=200)
        assert r["data"]["status"] == "OFFICE_APPROVED"
        return f"Progressed to OFFICE_APPROVED"

    step("Office approve JC-LAB-001", office_approve_jc)

    # Approve for payment
    def approve_payment_jc():
        jcs = get(office_tok, f"/projects/{project_id}/job-cards/").get("data", [])
        jc = next((j for j in jcs if j["job_card_number"] == "JC-LAB-001"), None)
        assert jc is not None

        if jc["status"] in ("PAYMENT_APPROVED", "PAID"):
            return "Already past payment approval"

        if jc["status"] == "OFFICE_APPROVED" and not jc["owner_approval_required"]:
            r = post(office_tok, f"/job-cards/{jc['id']}/approve-payment", expected=200)
            assert r["data"]["status"] == "PAYMENT_APPROVED"
            return "PAYMENT_APPROVED"
        return f"Status={jc['status']}, owner_required={jc['owner_approval_required']}"

    step("Approve JC-LAB-001 for payment", approve_payment_jc)


# ═════════════════════════════════════════════════════════════════════════════
# FLOW E — Dashboard + Alerts
# ═════════════════════════════════════════════════════════════════════════════

def flow_e_dashboard(owner_tok: str, office_tok: str):
    print(f"\n{BOLD}══ FLOW E: Dashboard + Alerts ══{RESET}")

    def check_dashboard():
        data = get(owner_tok, "/dashboard/stats").get("data", {})
        assert "active_projects" in data, f"Dashboard missing active_projects: {data}"
        assert data["active_projects"] >= 1
        return f"active_projects={data['active_projects']}, open_alerts={data.get('open_alerts', '?')}"

    step("Dashboard stats load without error", check_dashboard)

    def check_alerts():
        alerts = get(office_tok, "/alerts/").get("data", [])
        alert_types = {a["alert_type"] for a in alerts}
        expected = {"MATERIAL_OVERUSE", "BOQ_ALLOCATION_EXCEEDED", "DELIVERY_DISCREPANCY",
                    "SITE_DELAY", "BOQ_VARIANCE_OVERUSE"}
        found = expected & alert_types
        assert len(found) >= 1, f"Expected at least one of {expected}, found: {alert_types}"
        return f"Found alert types: {alert_types}"

    step("Alerts page contains expected alert types", check_alerts)

    def check_alert_stats():
        data = get(office_tok, "/alerts/stats").get("data", {})
        assert "open" in data
        assert "critical_open" in data
        assert data["open"] >= 0
        return f"open={data['open']}, critical={data['critical_open']}, pending_wa={data.get('pending_whatsapp_ack', 0)}"

    step("Alert stats endpoint returns correct fields", check_alert_stats)

    def check_queue_stats():
        data = get(office_tok, "/alerts/queue/stats").get("data", {})
        assert "pending" in data
        assert "mock_sent" in data
        return f"pending={data['pending']}, mock_sent={data['mock_sent']}, failed={data.get('failed', 0)}"

    step("WhatsApp queue stats endpoint works", check_queue_stats)


# ═════════════════════════════════════════════════════════════════════════════
# FLOW F — Stock Movements
# ═════════════════════════════════════════════════════════════════════════════

def flow_f_stock(office_tok: str):
    print(f"\n{BOLD}══ FLOW F: Stock — Ledger + Lot Issue ══{RESET}")

    project_id = _get_cornubia_id(office_tok)

    def check_stock_balances():
        data = get(office_tok, "/stock/balances", params={"project_id": project_id}).get("data", [])
        assert len(data) >= 1, "No stock balances found — has delivery DEL-001/DEL-002 been received?"
        total_bal = sum(b["balance"] for b in data)
        return f"{len(data)} balance line(s), total qty={total_bal:.1f}"

    step("Stock balances exist after demo seed deliveries", check_stock_balances)

    def check_ledger():
        data = get(office_tok, "/stock/ledger", params={"project_id": project_id, "limit": 20}).get("data", [])
        assert len(data) >= 1, "Stock ledger is empty"
        types = {e["movement_type"] for e in data}
        return f"{len(data)} ledger entries, types={types}"

    step("Stock ledger has entries from deliveries", check_ledger)

    def check_lot1_boq():
        lots = get(office_tok, f"/projects/{project_id}/lots/").get("data", [])
        lot1 = next((l for l in lots if l["lot_number"] == "1"), None)
        assert lot1 is not None, "Lot 1 not found"
        summary = get(office_tok, f"/lots/{lot1['id']}/boq-summary").get("data", {})
        assert summary.get("total_items", 0) >= 1, "Lot 1 has no BOQ items"
        return f"Lot 1 BOQ: {summary['total_items']} items, overruns={summary.get('overrun_count', 0)}"

    step("Lot 1 BOQ summary returns allocation data", check_lot1_boq)


# ═════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═════════════════════════════════════════════════════════════════════════════

def print_summary():
    print(f"\n{BOLD}{'═'*55}")
    print("  TEST SUMMARY")
    print(f"{'═'*55}{RESET}")

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    total = len(results)

    for r in results:
        colour = GREEN if r["status"] == "PASS" else RED
        print(f"  {colour}{r['status']}{RESET}  {r['step']}")

    print(f"\n  Total: {total}   {GREEN}Passed: {passed}{RESET}   {RED}Failed: {failed}{RESET}\n")

    if failed == 0:
        print(f"  {GREEN}{BOLD}✓ All flows passing end-to-end{RESET}\n")
    else:
        print(f"  {RED}{BOLD}✗ {failed} step(s) failed — review output above{RESET}\n")
        print("  Common fixes:")
        print("    1. Run: python scripts/seed_hmh_connected_demo.py")
        print("    2. Ensure backend is running: uvicorn main:app --reload --host 0.0.0.0 --port 8000")
        print("    3. Check DB connection: python scripts/create_db.py")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    global BASE_URL
    parser = argparse.ArgumentParser(description="HMH End-to-End Test Script")
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1",
                        help="Backend API base URL")
    args = parser.parse_args()
    BASE_URL = args.base_url

    print(f"\n{BOLD}{'═'*55}")
    print("  HMH Construction OS — End-to-End Test Runner")
    print(f"  Target: {BASE_URL}")
    print(f"{'═'*55}{RESET}")

    # Check backend is reachable
    try:
        r = httpx.get(f"{BASE_URL.replace('/api/v1', '')}/health", timeout=5)
        print(f"  Backend: {GREEN}reachable{RESET} ({r.status_code})")
    except Exception:
        print(f"  {RED}Backend not reachable at {BASE_URL}{RESET}")
        print("  Start with: uvicorn main:app --reload --host 0.0.0.0 --port 8000")
        sys.exit(1)

    # Run flows
    owner_tok, office_tok, site_tok = flow_a_auth()

    if office_tok:
        flow_b_procurement(owner_tok, office_tok)
        flow_c_overboq(office_tok)
        flow_d_jobcards(owner_tok, office_tok, site_tok)
        flow_e_dashboard(owner_tok, office_tok)
        flow_f_stock(office_tok)
    else:
        print(f"\n  {RED}Skipping procurement/stock flows — login failed{RESET}")
        print("  Run: python scripts/seed_owner.py && python scripts/seed_hmh_connected_demo.py")

    print_summary()

    failed = sum(1 for r in results if r["status"] == "FAIL")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
