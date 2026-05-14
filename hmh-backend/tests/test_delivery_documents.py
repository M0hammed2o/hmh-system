"""
Tests for Issue 1: delivery document fields in DeliveryRead.
Tests for Issue 2: manual reconciliation matching.
Tests for Issue 3: usage + stage evidence uploads.
"""

import io
import os
import uuid
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from tests.conftest import (
    auth, login,
    make_user, make_project, make_site, make_supplier, make_item, make_stock,
)


# ── Issue 1: DeliveryRead exposes delivery_note_image_url + signature fields ──

def test_delivery_read_includes_document_fields(db, client):
    """DeliveryRead schema must return delivery_note_image_url, signature_image_url, ocr_raw_data."""
    user = make_user(db, role="OFFICE_USER")
    token = login(client, user["email"], user["password"])

    proj     = make_project(db, user["id"])
    site     = make_site(db, proj["id"])
    supplier = make_supplier(db)

    # Create delivery via simple JSON endpoint
    payload = {
        "supplier_id":  supplier["id"],
        "site_id":      site["id"],
        "items": [{"description": "Test material", "quantity_received": 5.0}],
        "receiver_name": "Site Staff",
    }
    r = client.post(
        f"/api/v1/projects/{proj['id']}/deliveries/",
        json=payload,
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]

    # Schema fields must be present (even if null)
    assert "delivery_note_image_url" in data
    assert "signature_image_url"     in data
    assert "ocr_raw_data"            in data
    assert "receiver_name"           in data
    assert data["receiver_name"]     == "Site Staff"


def test_receive_with_document_creates_attachment_record(db, client, tmp_path):
    """
    POST /deliveries/receive-with-document with a file must:
    - save the delivery note to disk
    - store delivery_note_image_url in the delivery
    - create an Attachment record so GET /attachments?entity_type=DELIVERY returns it
    """
    user     = make_user(db, role="SITE_MANAGER")
    token    = login(client, user["email"], user["password"])
    proj     = make_project(db, user["id"])
    site     = make_site(db, proj["id"])
    supplier = make_supplier(db)

    # Create a tiny dummy file
    dummy_pdf = io.BytesIO(b"%PDF-1.0 fake pdf content")
    dummy_pdf.name = "delivery_note.pdf"

    import json
    data_form = {
        "project_id":  (None, proj["id"]),
        "site_id":     (None, site["id"]),
        "supplier_id": (None, supplier["id"]),
        "items_json":  (None, json.dumps([
            {"description": "Cement", "quantity_received": 10, "quantity_expected": 10, "unit": "bags"}
        ])),
        "receiver_name": (None, "John Test"),
        "delivery_note_file": ("delivery_note.pdf", dummy_pdf, "application/pdf"),
    }

    r = client.post(
        "/api/v1/deliveries/receive-with-document",
        files=data_form,
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    resp = r.json()["data"]
    assert resp["has_file"] is True

    delivery_id = resp["delivery_id"]

    # Fetch delivery detail — must include delivery_note_image_url
    r2 = client.get(f"/api/v1/deliveries/{delivery_id}", headers=auth(token))
    assert r2.status_code == 200
    detail = r2.json()["data"]
    assert detail["delivery_note_image_url"] is not None
    assert detail["delivery_note_image_url"].startswith("/uploads/delivery_notes/")

    # Attachment record must exist
    r3 = client.get(
        "/api/v1/attachments/",
        params={"entity_type": "DELIVERY", "entity_id": delivery_id},
        headers=auth(token),
    )
    assert r3.status_code == 200
    atts = r3.json()["data"]
    assert len(atts) >= 1
    assert any(a["attachment_type"] == "DELIVERY_NOTE" for a in atts)


def test_signature_stored_as_file_not_base64(db, client):
    """Signatures must be saved as PNG files; signature_image_url must be a path, not Base64."""
    user     = make_user(db, role="SITE_STAFF")
    token    = login(client, user["email"], user["password"])
    proj     = make_project(db, user["id"])
    site     = make_site(db, proj["id"])
    supplier = make_supplier(db)

    # Minimal 1x1 PNG as Base64
    import base64
    import struct, zlib
    def _tiny_png():
        def chunk(name, data):
            c = struct.pack(">I", len(data)) + name + data
            crc = struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)
            return c + crc
        raw = zlib.compress(b"\x00\xff\xff\xff")
        idat = chunk(b"IDAT", raw)
        ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        iend = chunk(b"IEND", b"")
        return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend

    sig_b64 = "data:image/png;base64," + base64.b64encode(_tiny_png()).decode()

    import json
    data_form = {
        "project_id":         (None, proj["id"]),
        "site_id":            (None, site["id"]),
        "supplier_id":        (None, supplier["id"]),
        "items_json":         (None, json.dumps([
            {"description": "Steel", "quantity_received": 2, "unit": "kg"}
        ])),
        "receiver_name":      (None, "Receiver X"),
        "receiver_signature": (None, sig_b64),
    }

    r = client.post(
        "/api/v1/deliveries/receive-with-document",
        files=data_form,
        headers=auth(token),
    )
    assert r.status_code == 201, r.text

    delivery_id = r.json()["data"]["delivery_id"]
    r2 = client.get(f"/api/v1/deliveries/{delivery_id}", headers=auth(token))
    sig_url = r2.json()["data"]["signature_image_url"]

    assert sig_url is not None
    # Must be a file path, not a Base64 string
    assert len(sig_url) <= 500, "signature_image_url must not contain raw Base64"
    assert sig_url.startswith("/uploads/delivery_signatures/")
    assert sig_url.endswith(".png")


# ── Issue 2: Manual reconciliation matching ──────────────────────────────────

def test_manual_match_invoice(db, client):
    """PATCH /invoices/{id}/match must create an InvoiceMatchingResult."""
    user     = make_user(db, role="OFFICE_ADMIN")
    token    = login(client, user["email"], user["password"])
    proj     = make_project(db, user["id"])
    supplier = make_supplier(db)

    # Create invoice
    r = client.post(
        f"/api/v1/projects/{proj['id']}/invoices/",
        json={
            "invoice_number": f"INV-{uuid.uuid4().hex[:6].upper()}",
            "supplier_id":    supplier["id"],
            "total_amount":   1500.00,
        },
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    invoice_id = r.json()["data"]["id"]

    # Manual match
    r2 = client.patch(
        f"/api/v1/invoices/{invoice_id}/match",
        json={"match_status": "MATCHED", "notes": "Manual match test"},
        headers=auth(token),
    )
    assert r2.status_code == 200, r2.text
    m = r2.json()["data"]
    assert m["match_status"] == "MATCHED"
    assert m["checked_by"] is not None
    assert m["notes"] == "Manual match test"

    # Proof pack must reflect the match
    r3 = client.get(f"/api/v1/invoices/{invoice_id}/proof", headers=auth(token))
    assert r3.status_code == 200
    proof = r3.json()["data"]
    assert proof["match_status"] == "MATCHED"
    assert proof["is_matched"] is True
    assert proof["checked_at"] is not None


def test_manual_match_partially_matched(db, client):
    """Partial match status should be stored and returned correctly."""
    user     = make_user(db, role="OFFICE_ADMIN")
    token    = login(client, user["email"], user["password"])
    proj     = make_project(db, user["id"])
    supplier = make_supplier(db)

    r = client.post(
        f"/api/v1/projects/{proj['id']}/invoices/",
        json={"invoice_number": f"INV-{uuid.uuid4().hex[:6]}", "supplier_id": supplier["id"], "total_amount": 500},
        headers=auth(token),
    )
    invoice_id = r.json()["data"]["id"]

    r2 = client.patch(
        f"/api/v1/invoices/{invoice_id}/match",
        json={"match_status": "PARTIALLY_MATCHED", "notes": "Missing delivery note"},
        headers=auth(token),
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["match_status"] == "PARTIALLY_MATCHED"


# ── Issue 3: Usage evidence ──────────────────────────────────────────────────

def test_record_usage_with_evidence_saves_file(db, client):
    """POST /stock/usage-with-evidence must save the evidence file and return UsageLog."""
    user     = make_user(db, role="SITE_MANAGER")
    token    = login(client, user["email"], user["password"])
    proj     = make_project(db, user["id"])
    site     = make_site(db, proj["id"])
    item     = make_item(db, name="Test Sand")
    make_stock(db, proj["id"], site["id"], item["id"], qty=50)

    dummy_img = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

    data_form = {
        "project_id":   (None, proj["id"]),
        "site_id":      (None, site["id"]),
        "item_id":      (None, item["id"]),
        "quantity_used":(None, "5.0"),
        "evidence_file": ("evidence.png", dummy_img, "image/png"),
    }
    r = client.post(
        "/api/v1/stock/usage-with-evidence",
        files=data_form,
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    usage = r.json()["data"]
    assert usage["quantity_used"] == 5.0
    # Evidence URL is encoded into comments
    assert "evidence:/uploads/site_evidence/usage/" in (usage.get("comments") or r.json().get("message", ""))


# ── Issue 3: Stage evidence ──────────────────────────────────────────────────

def test_update_stage_with_evidence_saves_file(db, client):
    """POST /projects/{id}/stage-statuses/with-evidence must save photo and update stage."""
    from app.services.stage_service import seed_default_stages
    seed_default_stages(db)
    db.flush()

    user  = make_user(db, role="SITE_MANAGER")
    token = login(client, user["email"], user["password"])
    proj  = make_project(db, user["id"])

    # Get a stage master id
    r = client.get("/api/v1/stages/", headers=auth(token))
    assert r.status_code == 200
    stages = r.json()["data"]
    assert len(stages) > 0
    stage_id = stages[0]["id"]

    dummy_img = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
    data_form = {
        "stage_id":    (None, stage_id),
        "status":      (None, "IN_PROGRESS"),
        "notes":       (None, "Foundation started"),
        "evidence_file": ("progress.png", dummy_img, "image/png"),
    }
    r2 = client.post(
        f"/api/v1/projects/{proj['id']}/stage-statuses/with-evidence",
        files=data_form,
        headers=auth(token),
    )
    assert r2.status_code == 201, r2.text
    pss = r2.json()["data"]
    assert pss["status"] == "IN_PROGRESS"
    # Evidence URL is embedded in notes
    assert "evidence:/uploads/site_evidence/stages/" in (pss.get("notes") or "")
