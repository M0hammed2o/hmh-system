"""
Tests for gmail_reader_service.py

Covers:
- classify_document: all four categories
- extract_po_number: various formats
- fetch_procurement_emails mock mode (IMAP disabled)
- GET /gmail/incoming endpoint
- GET /gmail/fetch triggers service
"""

import uuid
import pytest
from datetime import datetime, timezone

from app.services.gmail_reader_service import classify_document, extract_po_number
from tests.conftest import auth, login, make_user, make_project


# ── Pure-logic tests (no DB required) ────────────────────────────────────────

class TestClassifyDocument:
    def test_invoice_by_filename(self):
        assert classify_document("invoice_001.pdf") == "INVOICE"

    def test_invoice_by_subject(self):
        assert classify_document("document.pdf", "Tax Invoice from Supplier") == "INVOICE"

    def test_invoice_abbrev(self):
        assert classify_document("INV-2024-003.pdf") == "INVOICE"

    def test_delivery_note_by_filename(self):
        assert classify_document("delivery_note.pdf") == "DELIVERY_NOTE"

    def test_delivery_note_by_dn_prefix(self):
        assert classify_document("DN-005.pdf") == "DELIVERY_NOTE"

    def test_delivery_note_by_subject(self):
        assert classify_document("scan.pdf", "Delivery receipt attached") == "DELIVERY_NOTE"

    def test_quote_by_filename(self):
        assert classify_document("quotation_steel.pdf") == "QUOTE"

    def test_quote_by_subject(self):
        assert classify_document("doc.pdf", "Our pricing proposal for your review") == "QUOTE"

    def test_other_fallback(self):
        assert classify_document("photo.jpg", "Site update") == "OTHER"

    def test_case_insensitive(self):
        assert classify_document("INVOICE.PDF") == "INVOICE"
        assert classify_document("Delivery_Note.PDF") == "DELIVERY_NOTE"


class TestExtractPoNumber:
    def test_hyphen_format(self):
        assert extract_po_number("Please see PO-DEMO-001 attached") == "PO-DEMO-001"

    def test_space_format(self):
        result = extract_po_number("Re: PO 12345 invoice")
        assert result is not None
        assert "12345" in result

    def test_no_match_returns_none(self):
        assert extract_po_number("No reference here") is None

    def test_none_input_returns_none(self):
        assert extract_po_number(None) is None

    def test_case_insensitive(self):
        result = extract_po_number("po-abc-123")
        assert result is not None


# ── Mock mode tests ───────────────────────────────────────────────────────────

class TestFetchMockMode:
    def test_returns_empty_when_imap_disabled(self, db):
        """IMAP_ENABLED=false must return mock result without connecting."""
        from app.services.gmail_reader_service import fetch_procurement_emails
        # settings.IMAP_ENABLED is False in test env
        result = fetch_procurement_emails(db, limit=5)
        assert result["mock"] is True
        assert result["fetched"] == 0
        assert result["saved"] == 0


# ── API endpoint tests ────────────────────────────────────────────────────────

@pytest.fixture
def gmail_setup(db, client):
    owner = make_user(db, role="OWNER")
    tok   = login(client, owner["email"], owner["password"])
    return {"tok": tok, "owner_id": owner["id"]}


def _seed_incoming_email(db, from_email="supplier@example.com", subject="Invoice attached"):
    from app.models.incoming_email import IncomingEmail
    now = datetime.now(timezone.utc)
    e = IncomingEmail(
        id=uuid.uuid4(),
        from_email=from_email,
        subject=subject,
        body_snippet="Please find attached our invoice.",
        received_at=now,
        has_attachments=True,
        processed_status="UNPROCESSED",
        matched_po_number=None,
        created_at=now,
    )
    db.add(e)
    db.flush()
    return e


class TestGmailApiEndpoints:
    def test_fetch_returns_mock_result(self, client, db, gmail_setup):
        tok = gmail_setup["tok"]
        r = client.post("/api/v1/gmail/fetch", headers=auth(tok))
        assert r.status_code == 200
        data = r.json()["data"]
        assert "fetched" in data
        assert data.get("mock") is True

    def test_list_incoming_empty(self, client, db, gmail_setup):
        tok = gmail_setup["tok"]
        r = client.get("/api/v1/gmail/incoming", headers=auth(tok))
        assert r.status_code == 200
        data = r.json()["data"]
        assert "items" in data

    def test_list_incoming_returns_seeded_email(self, client, db, gmail_setup):
        tok = gmail_setup["tok"]
        _seed_incoming_email(db, from_email="test@supplier.co.za")
        db.commit()

        r = client.get("/api/v1/gmail/incoming", headers=auth(tok))
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert any(i["from_email"] == "test@supplier.co.za" for i in items)

    def test_get_incoming_by_id(self, client, db, gmail_setup):
        tok = gmail_setup["tok"]
        e = _seed_incoming_email(db)
        db.commit()

        r = client.get(f"/api/v1/gmail/incoming/{e.id}", headers=auth(tok))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["id"] == str(e.id)
        assert "attachments" in data

    def test_get_unknown_email_returns_404(self, client, db, gmail_setup):
        tok = gmail_setup["tok"]
        r = client.get(f"/api/v1/gmail/incoming/{uuid.uuid4()}", headers=auth(tok))
        assert r.status_code == 404

    def test_attachment_classification_stored(self, client, db, gmail_setup):
        """Seeded attachment with INVOICE type is returned correctly."""
        from app.models.incoming_email import IncomingEmailAttachment
        e   = _seed_incoming_email(db)
        now = datetime.now(timezone.utc)
        att = IncomingEmailAttachment(
            id=uuid.uuid4(),
            incoming_email_id=e.id,
            filename="invoice_001.pdf",
            file_path="uploads/gmail/invoices/abc_invoice_001.pdf",
            content_type="application/pdf",
            detected_type="INVOICE",
            created_at=now,
        )
        db.add(att)
        e.has_attachments = True
        db.commit()

        r = client.get(f"/api/v1/gmail/incoming/{e.id}", headers=auth(tok := gmail_setup["tok"]))
        assert r.status_code == 200
        atts = r.json()["data"]["attachments"]
        assert len(atts) == 1
        assert atts[0]["detected_type"] == "INVOICE"
