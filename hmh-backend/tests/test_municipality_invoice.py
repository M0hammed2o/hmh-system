"""
Tests for Municipality Invoice module.

Covers:
  - Create invoice (with and without items)
  - List invoices filtered by project
  - Get single invoice
  - Update invoice fields and items
  - Delete draft invoice
  - Cannot delete FINALISED invoice
  - Totals auto-computed from items
  - Excel export returns bytes
  - Subcontractor payment summary (monthly) cross-check
  - Requires auth
"""

import uuid
from datetime import date

import pytest

from tests.conftest import auth, login, make_project, make_user, make_user_project_access


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def ctx(db, client):
    owner   = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    token   = login(client, owner["email"], owner["password"])
    return {
        "owner":   owner,
        "project": project,
        "token":   token,
        "headers": auth(token),
        "project_id": project["id"],
    }


def _create(client, ctx, **overrides):
    payload = {
        "cert_number":          "26",
        "invoice_date":         "2026-01-26",
        "client_name":          "Ethekweni Municipality",
        "client_vat_no":        "4880193505",
        "client_address":       "PO BOX 828,Durban\n4001",
        "company_email":        "dwt786@gmail.com",
        "project_description":  "Kwalinda Rural Housing Project",
        "contract_reference":   "Contract 1H-42037",
        "previously_paid":      0,
        "vat_rate":             15,
        "bank_name":            "FIRST NATIONAL BANK",
        "account_number":       "62381077893",
        "branch_name":          "FLORIDA ROAD",
        "branch_code":          "220526",
        "notes":                "In this invoice we claiming for 15 completions.",
        "items": [
            {"line_number": "7",  "description": "Wall-plate , door & window ceiling", "quantity": 2,  "sort_order": 6},
            {"line_number": "8",  "description": "Roof & Ceiling",                     "quantity": 8,  "sort_order": 7},
            {"line_number": "9",  "description": "Electrical",                         "quantity": 15, "unit_price": 5000, "sort_order": 8},
            {"line_number": "10", "description": "Concrete Aprons",                    "quantity": 15, "unit_price": 2000, "sort_order": 9},
            {"line_number": "11", "description": "Finishing-plaster, paint , windows & doors", "quantity": 15, "unit_price": 3000, "sort_order": 10},
        ],
    }
    payload.update(overrides)
    return client.post(
        f"/api/v1/projects/{ctx['project_id']}/municipality-invoices/",
        json=payload,
        headers=ctx["headers"],
    )


# ── Create ────────────────────────────────────────────────────────────────────

class TestCreate:
    def test_returns_201(self, db, client, ctx):
        r = _create(client, ctx)
        assert r.status_code == 201, r.text
        data = r.json()["data"]
        assert data["cert_number"] == "26"
        assert data["client_name"] == "Ethekweni Municipality"
        assert data["status"] == "DRAFT"
        assert data["invoice_number"].startswith("IN")

    def test_totals_computed_from_items(self, db, client, ctx):
        r = _create(client, ctx)
        assert r.status_code == 201
        data = r.json()["data"]
        # Items with totals: 15*5000 + 15*2000 + 15*3000 = 75000+30000+45000 = 150000
        assert data["subtotal"] == 150000.0
        assert data["vat_amount"] == pytest.approx(22500.0, abs=1)
        assert data["total_due"]  == pytest.approx(172500.0, abs=1)

    def test_invoice_number_auto_generated(self, db, client, ctx):
        r = _create(client, ctx)
        assert r.status_code == 201
        assert r.json()["data"]["invoice_number"].startswith("IN")

    def test_custom_invoice_number(self, db, client, ctx):
        r = _create(client, ctx, invoice_number="IN00472")
        assert r.status_code == 201
        assert r.json()["data"]["invoice_number"] == "IN00472"

    def test_duplicate_invoice_number_rejected(self, db, client, ctx):
        _create(client, ctx, invoice_number="INX001")
        r2 = _create(client, ctx, invoice_number="INX001")
        assert r2.status_code in (400, 422)

    def test_requires_auth(self, db, client, ctx):
        r = client.post(
            f"/api/v1/projects/{ctx['project_id']}/municipality-invoices/",
            json={"cert_number": "1", "invoice_date": "2026-01-01"},
        )
        assert r.status_code == 401

    def test_items_stored_in_order(self, db, client, ctx):
        r = _create(client, ctx)
        data = r.json()["data"]
        numbers = [i["line_number"] for i in data["items"]]
        assert numbers[:3] == ["7", "8", "9"]


# ── List ──────────────────────────────────────────────────────────────────────

class TestList:
    def test_list_returns_created(self, db, client, ctx):
        _create(client, ctx)
        _create(client, ctx)
        r = client.get(
            f"/api/v1/projects/{ctx['project_id']}/municipality-invoices/",
            headers=ctx["headers"],
        )
        assert r.status_code == 200
        assert len(r.json()["data"]) >= 2

    def test_filter_by_status(self, db, client, ctx):
        _create(client, ctx)
        r = client.get(
            f"/api/v1/projects/{ctx['project_id']}/municipality-invoices/?status=DRAFT",
            headers=ctx["headers"],
        )
        assert r.status_code == 200
        for inv in r.json()["data"]:
            assert inv["status"] == "DRAFT"


# ── Get ───────────────────────────────────────────────────────────────────────

class TestGet:
    def test_get_by_id(self, db, client, ctx):
        r = _create(client, ctx)
        inv_id = r.json()["data"]["id"]
        r2 = client.get(f"/api/v1/municipality-invoices/{inv_id}", headers=ctx["headers"])
        assert r2.status_code == 200
        assert r2.json()["data"]["id"] == inv_id

    def test_get_includes_items(self, db, client, ctx):
        r = _create(client, ctx)
        inv_id = r.json()["data"]["id"]
        r2 = client.get(f"/api/v1/municipality-invoices/{inv_id}", headers=ctx["headers"])
        assert len(r2.json()["data"]["items"]) == 5

    def test_404_on_missing(self, db, client, ctx):
        r = client.get(f"/api/v1/municipality-invoices/{uuid.uuid4()}", headers=ctx["headers"])
        assert r.status_code == 404


# ── Update ────────────────────────────────────────────────────────────────────

class TestUpdate:
    def test_update_notes(self, db, client, ctx):
        r = _create(client, ctx)
        inv_id = r.json()["data"]["id"]
        r2 = client.patch(
            f"/api/v1/municipality-invoices/{inv_id}",
            json={"notes": "Updated note"},
            headers=ctx["headers"],
        )
        assert r2.status_code == 200
        assert r2.json()["data"]["notes"] == "Updated note"

    def test_update_replaces_items(self, db, client, ctx):
        r = _create(client, ctx)
        inv_id = r.json()["data"]["id"]
        r2 = client.patch(
            f"/api/v1/municipality-invoices/{inv_id}",
            json={"items": [{"line_number": "1", "description": "P&G", "quantity": 5, "unit_price": 1000, "sort_order": 0}]},
            headers=ctx["headers"],
        )
        assert r2.status_code == 200
        data = r2.json()["data"]
        assert len(data["items"]) == 1
        assert data["subtotal"] == 5000.0

    def test_finalised_cannot_be_edited(self, db, client, ctx):
        r = _create(client, ctx)
        inv_id = r.json()["data"]["id"]
        # Finalise it
        client.patch(
            f"/api/v1/municipality-invoices/{inv_id}",
            json={"status": "FINALISED"},
            headers=ctx["headers"],
        )
        # Try to edit
        r2 = client.patch(
            f"/api/v1/municipality-invoices/{inv_id}",
            json={"notes": "Should fail"},
            headers=ctx["headers"],
        )
        assert r2.status_code in (400, 422)

    def test_update_previously_paid_adjusts_totals(self, db, client, ctx):
        r = _create(client, ctx)
        inv_id = r.json()["data"]["id"]
        r2 = client.patch(
            f"/api/v1/municipality-invoices/{inv_id}",
            json={"previously_paid": 50000},
            headers=ctx["headers"],
        )
        assert r2.status_code == 200
        data = r2.json()["data"]
        # net = 150000 - 50000 = 100000; vat = 15000; due = 115000
        assert data["total_due"] == pytest.approx(115000.0, abs=1)


# ── Delete ────────────────────────────────────────────────────────────────────

class TestDelete:
    def test_delete_draft(self, db, client, ctx):
        r = _create(client, ctx)
        inv_id = r.json()["data"]["id"]
        r2 = client.delete(f"/api/v1/municipality-invoices/{inv_id}", headers=ctx["headers"])
        assert r2.status_code == 200
        # Verify gone
        r3 = client.get(f"/api/v1/municipality-invoices/{inv_id}", headers=ctx["headers"])
        assert r3.status_code == 404

    def test_cannot_delete_finalised(self, db, client, ctx):
        r = _create(client, ctx)
        inv_id = r.json()["data"]["id"]
        client.patch(
            f"/api/v1/municipality-invoices/{inv_id}",
            json={"status": "FINALISED"},
            headers=ctx["headers"],
        )
        r2 = client.delete(f"/api/v1/municipality-invoices/{inv_id}", headers=ctx["headers"])
        assert r2.status_code in (400, 422)


# ── Excel export ──────────────────────────────────────────────────────────────

class TestExcelExport:
    def test_export_returns_bytes(self, db, client, ctx):
        r = _create(client, ctx)
        inv_id = r.json()["data"]["id"]
        r2 = client.get(
            f"/api/v1/municipality-invoices/{inv_id}/export/excel",
            headers=ctx["headers"],
        )
        assert r2.status_code == 200
        assert r2.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert len(r2.content) > 1000  # non-trivial file

    def test_export_filename_contains_invoice_number(self, db, client, ctx):
        r = _create(client, ctx, invoice_number="IN00472")
        inv_id = r.json()["data"]["id"]
        r2 = client.get(
            f"/api/v1/municipality-invoices/{inv_id}/export/excel",
            headers=ctx["headers"],
        )
        assert r2.status_code == 200
        disposition = r2.headers.get("content-disposition", "")
        assert "IN00472" in disposition

    def test_export_excel_is_valid_workbook(self, db, client, ctx):
        """Parse the returned bytes with openpyxl to confirm it's a valid workbook."""
        import io
        import openpyxl

        r = _create(client, ctx, invoice_number="IN99999")
        inv_id = r.json()["data"]["id"]
        r2 = client.get(
            f"/api/v1/municipality-invoices/{inv_id}/export/excel",
            headers=ctx["headers"],
        )
        wb = openpyxl.load_workbook(io.BytesIO(r2.content))
        ws = wb.active
        # TAX INVOICE must appear in the sheet
        cell_values = [ws.cell(row=r, column=8).value for r in range(1, 10)]
        assert any("TAX INVOICE" in str(v) for v in cell_values if v)

    def test_export_contains_client_name(self, db, client, ctx):
        import io
        import openpyxl

        r = _create(client, ctx)
        inv_id = r.json()["data"]["id"]
        r2 = client.get(
            f"/api/v1/municipality-invoices/{inv_id}/export/excel",
            headers=ctx["headers"],
        )
        wb = openpyxl.load_workbook(io.BytesIO(r2.content))
        ws = wb.active
        all_values = []
        for row in ws.iter_rows(values_only=True):
            all_values.extend([str(c) for c in row if c is not None])
        assert any("Ethekweni Municipality" in v for v in all_values)


# ── Subcontractor payment summary cross-check ─────────────────────────────────

class TestSubconSummary:
    """Verify the monthly summary endpoint still works alongside municipality invoices."""

    def test_monthly_summary_zero_for_new_project(self, db, client, ctx):
        r = client.get(
            f"/api/v1/projects/{ctx['project_id']}/work-done/monthly-summary?month=2026-01-01",
            headers=ctx["headers"],
        )
        assert r.status_code == 200
        assert r.json()["data"]["total_records"] == 0
        assert r.json()["data"]["total_amount"] == 0.0
