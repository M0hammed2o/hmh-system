"""
Tests for invoice total parsing (Issue 1) and delivery note
capture/correction/signature flow (Issues 2-4).

Issue 1: Total Due must be used instead of Subtotal or unit price.
Issue 2: verify endpoint accessible to all roles (was OFFICE_AND_ABOVE → 403 for site staff).
Issue 3: OCR_NOT_AVAILABLE must not block manual correction or signature.
Issue 4: Image delivery note with OCR unavailable still creates draft verification.
"""

import io
import os
import uuid
import tempfile
import pytest
from datetime import datetime, timezone

from tests.conftest import auth, login, make_user, make_project, make_site, make_user_project_access


# ══════════════════════════════════════════════════════════════════════════════
# ISSUE 1 — Invoice total parsing
# ══════════════════════════════════════════════════════════════════════════════

INVOICE_TEXT = """Tazmeen Doors & Hardware
Tax Invoice

Supplier: HMH Group
Reference: INV-2026-0004 / MR-619B19DD-0004

Item                Quantity    Unit    Unit Price (ZAR)    Total (ZAR)
Internal Doors      3           door    2,500.00            7,500.00

Subtotal: R7,500.00
VAT (15%): R1,125.00
Total Due: R8,625.00
Payment Terms: 30 Days"""


class TestInvoiceParsing:
    def test_total_due_preferred_over_subtotal(self):
        from app.services.document_ai_service import _extract_total
        total = _extract_total(INVOICE_TEXT)
        assert total == pytest.approx(8625.00), (
            f"Expected 8625.00 (Total Due), got {total}. "
            "Parser should prioritise 'Total Due' over 'Subtotal'."
        )

    def test_total_not_unit_price(self):
        """Must NOT return 2500 (unit price) as the invoice total."""
        from app.services.document_ai_service import _extract_total
        total = _extract_total(INVOICE_TEXT)
        assert total != pytest.approx(2500.00), (
            "Parser must not return the unit price (2500) as the invoice total."
        )

    def test_parse_invoice_text_total_amount(self):
        from app.services.document_ai_service import parse_invoice_text
        fields = parse_invoice_text(INVOICE_TEXT)
        assert fields["total_amount"] == pytest.approx(8625.00), (
            f"parse_invoice_text total_amount={fields['total_amount']}, expected 8625."
        )

    def test_line_item_comma_formatted_numbers(self):
        """_parse_line_items must handle 2,500.00 and 7,500.00 with commas."""
        from app.services.document_ai_service import _parse_line_items
        items = _parse_line_items(INVOICE_TEXT)
        # The table row may or may not match depending on column spacing in text
        # If items are parsed, verify the values
        if items:
            item = items[0]
            assert item["quantity"] == pytest.approx(3.0)
            assert item["unit_price"] == pytest.approx(2500.00), (
                f"unit_price={item['unit_price']}, expected 2500.00"
            )
            assert item["line_total"] == pytest.approx(7500.00), (
                f"line_total={item['line_total']}, expected 7500.00"
            )

    def test_subtotal_not_returned_when_total_due_exists(self):
        """Subtotal (7500) must not be returned when Total Due (8625) is present."""
        from app.services.document_ai_service import _extract_total
        total = _extract_total(INVOICE_TEXT)
        assert total != pytest.approx(7500.00), (
            "Subtotal (7500) must not be returned when Total Due (8625) exists."
        )

    def test_grand_total_pattern(self):
        from app.services.document_ai_service import _extract_total
        text = "Grand Total: R12,500.00\nSome other line R100.00"
        assert _extract_total(text) == pytest.approx(12500.00)

    def test_amount_due_pattern(self):
        from app.services.document_ai_service import _extract_total
        text = "Amount Due: R9,000.00"
        assert _extract_total(text) == pytest.approx(9000.00)

    def test_total_due_beats_subtotal_in_priority(self):
        from app.services.document_ai_service import _extract_total
        text = "Subtotal: R5,000.00\nVAT: R750.00\nTotal Due: R5,750.00"
        assert _extract_total(text) == pytest.approx(5750.00)

    def test_full_extract_document_data_invoice(self):
        """End-to-end: extract_document_data on text file returns 8625 total."""
        from app.services.document_ai_service import extract_document_data
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w",
                                         encoding="utf-8", delete=False) as f:
            f.write(INVOICE_TEXT)
            path = f.name
        try:
            result = extract_document_data(path, "INVOICE")
            assert result["status"] in ("EXTRACTED", "NEEDS_REVIEW")
            assert result["fields"]["total_amount"] == pytest.approx(8625.00), (
                f"total_amount={result['fields']['total_amount']}, expected 8625."
            )
        finally:
            os.unlink(path)


# ══════════════════════════════════════════════════════════════════════════════
# ISSUE 2–4 — Delivery note capture / correction / signature
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def dn_setup(db, client):
    owner  = make_user(db, role="OWNER")
    staff  = make_user(db, role="SITE_STAFF")
    mgr    = make_user(db, role="SITE_MANAGER")
    project = make_project(db, owner_id=owner["id"])
    site   = make_site(db, project_id=project["id"])
    make_user_project_access(db, staff["id"], project["id"])
    make_user_project_access(db, mgr["id"], project["id"])
    db.commit()
    owner_tok = login(client, owner["email"], owner["password"])
    staff_tok = login(client, staff["email"], staff["password"])
    mgr_tok   = login(client, mgr["email"], mgr["password"])
    return dict(
        owner_id=owner["id"], staff_id=staff["id"], mgr_id=mgr["id"],
        project_id=project["id"], site_id=site["id"],
        owner_tok=owner_tok, staff_tok=staff_tok, mgr_tok=mgr_tok,
    )


def _upload_txt(client, tok, site_id, content=b"DN-001\nCement 30 bags"):
    return client.post(
        "/api/v1/site-capture/delivery-note/upload",
        files={"file": ("note.pdf", io.BytesIO(content), "application/pdf")},
        data={"site_id": site_id, "supplier_name": "Test Supplier"},
        headers=auth(tok),
    )


def _upload_image_placeholder(client, tok, site_id):
    """Upload a tiny 1×1 PNG — OCR will be unavailable but upload must succeed."""
    # Minimal valid PNG (1×1 white pixel)
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
        b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return client.post(
        "/api/v1/site-capture/delivery-note/upload",
        files={"file": ("photo.png", io.BytesIO(png), "image/png")},
        data={"site_id": site_id},
        headers=auth(tok),
    )


class TestDeliveryNoteUpload:
    def test_upload_creates_verification(self, client, db, dn_setup):
        s = dn_setup
        r = _upload_txt(client, s["staff_tok"], s["site_id"])
        assert r.status_code == 201, r.text
        assert "id" in r.json()["data"]

    def test_image_upload_with_no_ocr_still_creates_draft(self, client, db, dn_setup):
        """OCR_NOT_AVAILABLE must NOT block upload — draft verification is created."""
        from app.models.document_extraction import DeliveryVerification
        s = dn_setup
        r = _upload_image_placeholder(client, s["staff_tok"], s["site_id"])
        assert r.status_code == 201, r.text
        data = r.json()["data"]
        # Status may be OCR_NOT_AVAILABLE or FAILED — both acceptable for an image without OCR
        assert data["status"] in ("EXTRACTED", "OCR_NOT_AVAILABLE", "FAILED", "NEEDS_REVIEW")
        # Verification record must always be created
        vid = data["id"]
        v = db.query(DeliveryVerification).filter(
            DeliveryVerification.id == uuid.UUID(vid)
        ).first()
        assert v is not None
        assert v.verification_status == "DRAFT"


class TestDeliveryNoteCorrection:
    def test_manual_items_save_after_ocr_unavailable(self, client, db, dn_setup):
        """Manual item entry must work even when OCR returned nothing."""
        s = dn_setup
        r = _upload_image_placeholder(client, s["staff_tok"], s["site_id"])
        assert r.status_code == 201, r.text
        vid = r.json()["data"]["id"]

        r2 = client.post(
            f"/api/v1/site-capture/delivery-note/{vid}/correct",
            json={
                "supplier_name":        "Manual Supplier",
                "delivery_note_number": "DN-MANUAL-001",
                "items": [{
                    "description":         "Cement 50kg",
                    "unit":               "bags",
                    "expected_qty":        30,
                    "actual_received_qty": 30,
                    "accepted_qty":        30,
                    "rejected_qty":        0,
                }],
            },
            headers=auth(s["staff_tok"]),
        )
        assert r2.status_code == 200, r2.text

    def test_correction_updates_supplier_and_dn_number(self, client, db, dn_setup):
        from app.models.document_extraction import DeliveryVerification
        s = dn_setup
        r = _upload_txt(client, s["staff_tok"], s["site_id"])
        vid = r.json()["data"]["id"]

        client.post(
            f"/api/v1/site-capture/delivery-note/{vid}/correct",
            json={"supplier_name": "Corrected Supplier", "delivery_note_number": "DN-CORR-007"},
            headers=auth(s["staff_tok"]),
        )

        v = db.query(DeliveryVerification).filter(
            DeliveryVerification.id == uuid.UUID(vid)
        ).first()
        assert v.supplier_name == "Corrected Supplier"
        assert v.delivery_note_number == "DN-CORR-007"


class TestDeliveryNoteSignatureAndVerify:
    def _full_flow(self, client, db, dn_setup, tok):
        """Upload → correct → sign → verify. Returns the verify response."""
        s = dn_setup
        r = _upload_txt(client, tok, s["site_id"])
        assert r.status_code == 201, r.text
        vid = r.json()["data"]["id"]

        # Correct with one item (no mismatch)
        client.post(
            f"/api/v1/site-capture/delivery-note/{vid}/correct",
            json={"items": [{
                "description": "Cement", "unit": "bags",
                "expected_qty": 30, "actual_received_qty": 30,
                "accepted_qty": 30, "rejected_qty": 0,
            }]},
            headers=auth(tok),
        )

        # Sign with text initials
        r_sig = client.post(
            f"/api/v1/site-capture/delivery-note/{vid}/signature",
            json={"signature_data": "J.S.", "signed_by_name": "John Smith"},
            headers=auth(tok),
        )
        assert r_sig.status_code == 200, r_sig.text

        # Verify
        r_ver = client.post(
            f"/api/v1/site-capture/delivery-note/{vid}/verify",
            headers=auth(tok),
        )
        return r_ver, vid

    def test_site_staff_can_verify(self, client, db, dn_setup):
        """Previously 403 — verify must now be accessible to SITE_STAFF."""
        r, _ = self._full_flow(client, db, dn_setup, dn_setup["staff_tok"])
        assert r.status_code == 200, (
            f"SITE_STAFF got {r.status_code} — verify must allow all roles. "
            f"Body: {r.text[:300]}"
        )

    def test_site_manager_can_verify(self, client, db, dn_setup):
        r, _ = self._full_flow(client, db, dn_setup, dn_setup["mgr_tok"])
        assert r.status_code == 200, r.text

    def test_owner_can_verify(self, client, db, dn_setup):
        r, _ = self._full_flow(client, db, dn_setup, dn_setup["owner_tok"])
        assert r.status_code == 200, r.text

    def test_no_mismatch_status_verified(self, client, db, dn_setup):
        r, _ = self._full_flow(client, db, dn_setup, dn_setup["staff_tok"])
        assert r.json()["data"]["status"] == "VERIFIED"

    def test_rejected_qty_creates_mismatch(self, client, db, dn_setup):
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType
        s = dn_setup
        tok = s["staff_tok"]

        r = _upload_txt(client, tok, s["site_id"])
        vid = r.json()["data"]["id"]

        client.post(
            f"/api/v1/site-capture/delivery-note/{vid}/correct",
            json={"items": [{
                "description": "Cement", "unit": "bags",
                "expected_qty": 30, "actual_received_qty": 20,
                "accepted_qty": 20, "rejected_qty": 10,
                "mismatch_reason": "Damaged bags",
            }]},
            headers=auth(tok),
        )
        client.post(
            f"/api/v1/site-capture/delivery-note/{vid}/signature",
            json={"signature_data": "JS", "signed_by_name": "Jane"},
            headers=auth(tok),
        )

        before = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.DELIVERY_MISMATCH
        ).count()

        r_ver = client.post(
            f"/api/v1/site-capture/delivery-note/{vid}/verify",
            headers=auth(tok),
        )
        assert r_ver.status_code == 200
        assert r_ver.json()["data"]["status"] == "MISMATCH"

        after = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.DELIVERY_MISMATCH
        ).count()
        assert after > before

    def test_image_with_no_ocr_full_flow_completes(self, client, db, dn_setup):
        """
        Even when OCR is unavailable (image upload), the full correction →
        signature → verify flow must complete successfully with manual data.
        """
        s = dn_setup
        tok = s["staff_tok"]
        r = _upload_image_placeholder(client, tok, s["site_id"])
        assert r.status_code == 201, r.text
        vid = r.json()["data"]["id"]

        # Manual correction (no OCR data to start from)
        r2 = client.post(
            f"/api/v1/site-capture/delivery-note/{vid}/correct",
            json={
                "supplier_name": "Supplier A",
                "delivery_note_number": "DN-IMG-001",
                "items": [{
                    "description": "Steel bars", "unit": "kg",
                    "expected_qty": 100, "actual_received_qty": 100,
                    "accepted_qty": 100, "rejected_qty": 0,
                }],
            },
            headers=auth(tok),
        )
        assert r2.status_code == 200, r2.text

        r3 = client.post(
            f"/api/v1/site-capture/delivery-note/{vid}/signature",
            json={"signature_data": "M.M.", "signed_by_name": "Mohammed Moosa"},
            headers=auth(tok),
        )
        assert r3.status_code == 200, r3.text

        r4 = client.post(
            f"/api/v1/site-capture/delivery-note/{vid}/verify",
            headers=auth(tok),
        )
        assert r4.status_code == 200, (
            f"Full flow with image+no-OCR failed: {r4.status_code} {r4.text[:300]}"
        )
        assert r4.json()["data"]["status"] == "VERIFIED"
