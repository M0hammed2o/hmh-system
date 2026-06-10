"""
Phase 4 — Procurement Reconciliation tests.

Covers:
  - Create reconciliation record from PO + Invoice
  - Variance detection (PO vs Invoice amount mismatch)
  - Clean match (amounts equal)
  - Approve and Reject workflows
  - Recompute endpoint
  - Dashboard stats counts
  - List with status filter
  - Auto-resolve quotation from PO
"""

import uuid
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import (
    auth, login, make_project, make_site, make_supplier, make_user,
    make_user_project_access,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(tz=timezone.utc)


def _make_po(db: Session, project_id: str, supplier_id: str, created_by: str,
             subtotal=100_000.0, vat=15_000.0, total=115_000.0) -> dict:
    from app.models.enums import RecordStatus
    from app.models.purchase_order import PurchaseOrder
    po = PurchaseOrder(
        po_number=f"PO-TEST-{uuid.uuid4().hex[:6]}",
        project_id=uuid.UUID(project_id),
        supplier_id=uuid.UUID(supplier_id),
        status=RecordStatus.SENT,
        po_date=_now(),
        subtotal_amount=subtotal,
        vat_amount=vat,
        total_amount=total,
        created_by=uuid.UUID(created_by),
        created_at=_now(),
    )
    db.add(po)
    db.flush()
    return {"id": str(po.id), "po_number": po.po_number}


def _make_invoice(db: Session, project_id: str, supplier_id: str, po_id: str,
                  captured_by: str = None,
                  subtotal=100_000.0, vat=15_000.0, total=115_000.0) -> dict:
    from app.models.enums import RecordStatus
    from app.models.invoice import Invoice
    inv = Invoice(
        invoice_number=f"INV-TEST-{uuid.uuid4().hex[:6]}",
        project_id=uuid.UUID(project_id),
        supplier_id=uuid.UUID(supplier_id),
        purchase_order_id=uuid.UUID(po_id),
        total_amount=total,
        subtotal_amount=subtotal,
        vat_amount=vat,
        status=RecordStatus.SUBMITTED,
        captured_by=uuid.UUID(captured_by) if captured_by else None,
        captured_at=_now(),
    )
    db.add(inv)
    db.flush()
    return {"id": str(inv.id), "invoice_number": inv.invoice_number}


def _make_quotation(db: Session, supplier_id: str,
                    net=100_000.0, vat=15_000.0, gross=115_000.0) -> dict:
    from app.models.enums import QuotationStatus
    from app.models.quotation import Quotation
    q = Quotation(
        quote_number=f"Q-TEST-{uuid.uuid4().hex[:6]}",
        supplier_id=uuid.UUID(supplier_id),
        status=QuotationStatus.APPROVED,
        net_amount=net,
        vat_amount=vat,
        gross_amount=gross,
        vat_rate_used=15.0,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(q)
    db.flush()
    return {"id": str(q.id), "quote_number": q.quote_number}


@pytest.fixture()
def setup(db: Session, client: TestClient):
    owner = make_user(db, role="OWNER")
    office = make_user(db, role="OFFICE_USER")
    project = make_project(db, owner["id"])
    site = make_site(db, project["id"])
    supplier = make_supplier(db)
    make_user_project_access(db, office["id"], project["id"])
    db.flush()
    return {
        "owner": owner,
        "office": office,
        "project": project,
        "site": site,
        "supplier": supplier,
    }


# ── Dashboard ─────────────────────────────────────────────────────────────────

def test_dashboard_empty(db: Session, client: TestClient, setup: dict):
    token = login(client, setup["owner"]["email"], "Test@1234")
    r = client.get("/api/v1/reconciliations/dashboard", headers=auth(token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "pending" in data
    assert "matched" in data
    assert "variance_detected" in data
    assert "awaiting_review" in data
    assert data["total"] >= 0


# ── Create — no invoice (PENDING) ─────────────────────────────────────────────

def test_create_reconciliation_pending(db: Session, client: TestClient, setup: dict):
    token = login(client, setup["owner"]["email"], "Test@1234")
    po = _make_po(db, setup["project"]["id"], setup["supplier"]["id"], setup["owner"]["id"])

    r = client.post(
        "/api/v1/reconciliations/",
        json={"purchase_order_id": po["id"]},
        headers=auth(token),
    )
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["status"] == "PENDING"
    assert data["purchase_order_id"] == po["id"]
    assert data["invoice_id"] is None
    assert data["variance_data"] is not None
    assert data["reconciliation_number"].startswith("REC-")


# ── Create — perfect match (MATCHED) ─────────────────────────────────────────

def test_create_reconciliation_matched(db: Session, client: TestClient, setup: dict):
    token = login(client, setup["owner"]["email"], "Test@1234")
    po = _make_po(db, setup["project"]["id"], setup["supplier"]["id"], setup["owner"]["id"],
                  subtotal=80_000, vat=12_000, total=92_000)
    inv = _make_invoice(db, setup["project"]["id"], setup["supplier"]["id"], po["id"], setup["owner"]["id"],
                        subtotal=80_000, vat=12_000, total=92_000)

    r = client.post(
        "/api/v1/reconciliations/",
        json={"purchase_order_id": po["id"], "invoice_id": inv["id"]},
        headers=auth(token),
    )
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["status"] == "MATCHED"
    assert data["variance_data"]["has_variance"] is False
    assert data["variance_data"]["total_variances"] == 0


# ── Create — variance detected ────────────────────────────────────────────────

def test_create_reconciliation_variance(db: Session, client: TestClient, setup: dict):
    token = login(client, setup["owner"]["email"], "Test@1234")
    po = _make_po(db, setup["project"]["id"], setup["supplier"]["id"], setup["owner"]["id"],
                  subtotal=100_000, vat=15_000, total=115_000)
    inv = _make_invoice(db, setup["project"]["id"], setup["supplier"]["id"], po["id"], setup["owner"]["id"],
                        subtotal=102_000, vat=15_300, total=117_300)

    r = client.post(
        "/api/v1/reconciliations/",
        json={"purchase_order_id": po["id"], "invoice_id": inv["id"]},
        headers=auth(token),
    )
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["status"] == "VARIANCE_DETECTED"
    vd = data["variance_data"]
    assert vd["has_variance"] is True
    assert vd["total_variances"] > 0
    # Verify comparisons structure
    po_vs_inv = next(c for c in vd["comparisons"] if c["label"] == "PO vs Invoice")
    gross_row = next(f for f in po_vs_inv["fields"] if f["name"] == "Gross Amount")
    assert gross_row["diff"] == pytest.approx(2300.0, abs=0.1)
    assert gross_row["has_variance"] is True


# ── Create — with quotation (Quotation vs PO comparison) ─────────────────────

def test_create_reconciliation_with_quotation(db: Session, client: TestClient, setup: dict):
    token = login(client, setup["owner"]["email"], "Test@1234")
    quotation = _make_quotation(db, setup["supplier"]["id"],
                                net=98_000, vat=14_700, gross=112_700)
    po = _make_po(db, setup["project"]["id"], setup["supplier"]["id"], setup["owner"]["id"],
                  subtotal=100_000, vat=15_000, total=115_000)
    inv = _make_invoice(db, setup["project"]["id"], setup["supplier"]["id"], po["id"], setup["owner"]["id"],
                        subtotal=100_000, vat=15_000, total=115_000)

    r = client.post(
        "/api/v1/reconciliations/",
        json={
            "purchase_order_id": po["id"],
            "invoice_id": inv["id"],
            "quotation_id": quotation["id"],
        },
        headers=auth(token),
    )
    assert r.status_code == 201
    data = r.json()["data"]
    vd = data["variance_data"]
    # Quotation gross (112,700) ≠ PO total (115,000) → variance
    assert vd["has_variance"] is True
    q_vs_po = next(c for c in vd["comparisons"] if c["label"] == "Quotation vs PO")
    gross_row = next(f for f in q_vs_po["fields"] if f["name"] == "Gross Amount")
    assert gross_row["a_label"] == "Quotation"
    assert gross_row["b_label"] == "PO"
    assert gross_row["diff"] == pytest.approx(2300.0, abs=0.1)


# ── Approve workflow ──────────────────────────────────────────────────────────

def test_approve_reconciliation(db: Session, client: TestClient, setup: dict):
    token = login(client, setup["owner"]["email"], "Test@1234")
    po = _make_po(db, setup["project"]["id"], setup["supplier"]["id"], setup["owner"]["id"])
    inv = _make_invoice(db, setup["project"]["id"], setup["supplier"]["id"], po["id"], captured_by=setup["owner"]["id"])

    create_r = client.post(
        "/api/v1/reconciliations/",
        json={"purchase_order_id": po["id"], "invoice_id": inv["id"]},
        headers=auth(token),
    )
    recon_id = create_r.json()["data"]["id"]

    # Approve with notes
    r = client.patch(
        f"/api/v1/reconciliations/{recon_id}",
        json={"status": "APPROVED", "notes": "Approved after manual review."},
        headers=auth(token),
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "APPROVED"
    assert data["notes"] == "Approved after manual review."
    assert data["reviewed_at"] is not None
    assert data["reviewed_by"] is not None


# ── Reject workflow ───────────────────────────────────────────────────────────

def test_reject_reconciliation(db: Session, client: TestClient, setup: dict):
    token = login(client, setup["owner"]["email"], "Test@1234")
    po = _make_po(db, setup["project"]["id"], setup["supplier"]["id"], setup["owner"]["id"],
                  subtotal=100_000, vat=15_000, total=115_000)
    inv = _make_invoice(db, setup["project"]["id"], setup["supplier"]["id"], po["id"], setup["owner"]["id"],
                        subtotal=102_000, vat=15_300, total=117_300)

    create_r = client.post(
        "/api/v1/reconciliations/",
        json={"purchase_order_id": po["id"], "invoice_id": inv["id"]},
        headers=auth(token),
    )
    recon_id = create_r.json()["data"]["id"]

    r = client.patch(
        f"/api/v1/reconciliations/{recon_id}",
        json={"status": "REJECTED", "notes": "Invoice amount does not match PO."},
        headers=auth(token),
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "REJECTED"
    assert data["reviewed_at"] is not None


# ── Recompute ─────────────────────────────────────────────────────────────────

def test_recompute_variances(db: Session, client: TestClient, setup: dict):
    token = login(client, setup["owner"]["email"], "Test@1234")
    po = _make_po(db, setup["project"]["id"], setup["supplier"]["id"], setup["owner"]["id"],
                  subtotal=100_000, vat=15_000, total=115_000)

    create_r = client.post(
        "/api/v1/reconciliations/",
        json={"purchase_order_id": po["id"]},
        headers=auth(token),
    )
    recon_id = create_r.json()["data"]["id"]
    assert create_r.json()["data"]["status"] == "PENDING"

    # Now add an invoice and recompute
    inv = _make_invoice(db, setup["project"]["id"], setup["supplier"]["id"], po["id"], setup["owner"]["id"],
                        subtotal=100_000, vat=15_000, total=115_000)
    client.patch(
        f"/api/v1/reconciliations/{recon_id}",
        json={"invoice_id": inv["id"]},
        headers=auth(token),
    )

    r = client.post(f"/api/v1/reconciliations/{recon_id}/recompute", headers=auth(token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "MATCHED"
    assert data["variance_data"]["has_variance"] is False


# ── Get detail ────────────────────────────────────────────────────────────────

def test_get_detail_includes_document_summaries(db: Session, client: TestClient, setup: dict):
    token = login(client, setup["owner"]["email"], "Test@1234")
    po = _make_po(db, setup["project"]["id"], setup["supplier"]["id"], setup["owner"]["id"])
    inv = _make_invoice(db, setup["project"]["id"], setup["supplier"]["id"], po["id"], captured_by=setup["owner"]["id"])

    create_r = client.post(
        "/api/v1/reconciliations/",
        json={"purchase_order_id": po["id"], "invoice_id": inv["id"]},
        headers=auth(token),
    )
    recon_id = create_r.json()["data"]["id"]

    r = client.get(f"/api/v1/reconciliations/{recon_id}", headers=auth(token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["po"] is not None
    assert data["po"]["po_number"] == po["po_number"]
    assert data["invoice"] is not None
    assert data["invoice"]["invoice_number"] == inv["invoice_number"]


# ── List with status filter ───────────────────────────────────────────────────

def test_list_filter_by_status(db: Session, client: TestClient, setup: dict):
    token = login(client, setup["owner"]["email"], "Test@1234")
    po1 = _make_po(db, setup["project"]["id"], setup["supplier"]["id"], setup["owner"]["id"])
    po2 = _make_po(db, setup["project"]["id"], setup["supplier"]["id"], setup["owner"]["id"])

    # One PENDING, one MATCHED
    client.post("/api/v1/reconciliations/",
                json={"purchase_order_id": po1["id"]}, headers=auth(token))
    inv = _make_invoice(db, setup["project"]["id"], setup["supplier"]["id"], po2["id"], captured_by=setup["owner"]["id"])
    client.post("/api/v1/reconciliations/",
                json={"purchase_order_id": po2["id"], "invoice_id": inv["id"]},
                headers=auth(token))

    r = client.get("/api/v1/reconciliations/?status=PENDING", headers=auth(token))
    assert r.status_code == 200
    pending_records = r.json()["data"]
    assert all(rec["status"] == "PENDING" for rec in pending_records)


# ── Delete ────────────────────────────────────────────────────────────────────

def test_delete_reconciliation(db: Session, client: TestClient, setup: dict):
    token = login(client, setup["owner"]["email"], "Test@1234")
    po = _make_po(db, setup["project"]["id"], setup["supplier"]["id"], setup["owner"]["id"])

    create_r = client.post(
        "/api/v1/reconciliations/",
        json={"purchase_order_id": po["id"]},
        headers=auth(token),
    )
    recon_id = create_r.json()["data"]["id"]

    del_r = client.delete(f"/api/v1/reconciliations/{recon_id}", headers=auth(token))
    assert del_r.status_code == 200

    get_r = client.get(f"/api/v1/reconciliations/{recon_id}", headers=auth(token))
    assert get_r.status_code == 404


# ── Dashboard counts update ───────────────────────────────────────────────────

def test_dashboard_counts_reflect_records(db: Session, client: TestClient, setup: dict):
    token = login(client, setup["owner"]["email"], "Test@1234")

    pre = client.get("/api/v1/reconciliations/dashboard", headers=auth(token)).json()["data"]

    # Create one PENDING
    po = _make_po(db, setup["project"]["id"], setup["supplier"]["id"], setup["owner"]["id"])
    client.post("/api/v1/reconciliations/",
                json={"purchase_order_id": po["id"]}, headers=auth(token))

    post = client.get("/api/v1/reconciliations/dashboard", headers=auth(token)).json()["data"]
    assert post["pending"] == pre["pending"] + 1
    assert post["total"] == pre["total"] + 1
