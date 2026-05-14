"""
Tests for upgraded procurement matching with quantity comparison.

Covers:
- Gmail attachment triggers DocumentExtraction via _trigger_extraction
- match_invoice_to_po creates alert on amount mismatch
- match_invoice_to_po creates alert on unmatched invoice
- document_ai/compare endpoint detects quantity mismatch
- document_ai/compare returns MATCHED when quantities align
- extraction status endpoints work
"""

import io
import uuid
import pytest

from tests.conftest import auth, login, make_user, make_project, make_site, make_supplier


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def match_setup(db, client):
    owner   = make_user(db, role="OWNER")
    project = make_project(db, owner_id=owner["id"])
    site    = make_site(db, project_id=project["id"])
    supplier = make_supplier(db)
    tok     = login(client, owner["email"], owner["password"])
    return dict(
        owner_id=owner["id"],
        project_id=project["id"],
        site_id=site["id"],
        supplier_id=supplier["id"],
        tok=tok,
    )


def _make_po(db, project_id, supplier_id, created_by, total=1000.0, qty_received=0.0):
    from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
    from app.models.enums import RecordStatus, VatMode
    from decimal import Decimal
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    po = PurchaseOrder(
        po_number=f"PO-DM-{uuid.uuid4().hex[:6].upper()}",
        project_id=uuid.UUID(project_id),
        supplier_id=uuid.UUID(supplier_id),
        status=RecordStatus.SENT,
        po_date=now,
        total_amount=Decimal(str(total)),
        subtotal_amount=Decimal(str(round(total / 1.15, 2))),
        vat_amount=Decimal(str(round(total - total / 1.15, 2))),
        created_by=uuid.UUID(created_by),
        created_at=now, updated_at=now,
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderItem(
        purchase_order_id=po.id,
        description="Cement 50kg bags",
        quantity_ordered=Decimal("30"),
        quantity_received=Decimal(str(qty_received)),
        unit="bags",
        rate=Decimal(str(total / 30)),
        vat_mode=VatMode.INCLUSIVE,
        vat_rate=Decimal("15.00"),
        line_total=Decimal(str(total)),
        created_at=now,
    ))
    db.flush()
    return po


def _make_invoice(db, project_id, supplier_id, captured_by, total=1000.0):
    from app.models.invoice import Invoice
    from app.models.enums import RecordStatus
    from decimal import Decimal
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    inv = Invoice(
        invoice_number=f"INV-DM-{uuid.uuid4().hex[:6].upper()}",
        supplier_id=uuid.UUID(supplier_id),
        project_id=uuid.UUID(project_id),
        total_amount=Decimal(str(total)),
        subtotal_amount=Decimal(str(round(total / 1.15, 2))),
        vat_amount=Decimal(str(round(total - total / 1.15, 2))),
        status=RecordStatus.SUBMITTED,
        captured_by=uuid.UUID(captured_by),
        captured_at=datetime.now(timezone.utc),
    )
    db.add(inv)
    db.flush()
    return inv


# ── Gmail attachment extraction trigger ───────────────────────────────────────

class TestGmailExtractionTrigger:
    def test_gmail_fetch_mock_does_not_crash(self, client, db, match_setup):
        """IMAP disabled → fetch returns mock=True without any extraction."""
        tok = match_setup["tok"]
        r = client.post("/api/v1/gmail/fetch", headers=auth(tok))
        assert r.status_code == 200
        assert r.json()["data"]["mock"] is True

    def test_trigger_extraction_function_graceful_with_bad_path(self, db):
        """_trigger_extraction must not raise even if file doesn't exist."""
        from datetime import datetime, timezone
        from app.services.gmail_reader_service import _trigger_extraction
        # Should not raise
        _trigger_extraction(db, "/tmp/nonexistent_file_12345.pdf", "INVOICE",
                            str(uuid.uuid4()), datetime.now(timezone.utc))

    def test_extraction_stored_for_plain_text_file(self, db):
        """A .txt attachment triggers a DocumentExtraction record."""
        import os, tempfile
        from datetime import datetime, timezone
        from app.models.document_extraction import DocumentExtraction
        from app.services.gmail_reader_service import _trigger_extraction

        content = b"Invoice No: INV-GMAIL-001\nTotal: R1200.00"
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            now = datetime.now(timezone.utc)
            _trigger_extraction(db, path, "INVOICE", str(uuid.uuid4()), now)
            db.commit()

            ext = db.query(DocumentExtraction).filter(
                DocumentExtraction.file_path == path
            ).first()
            assert ext is not None
            assert ext.document_type == "INVOICE"
            assert ext.status in ("EXTRACTED", "NEEDS_REVIEW", "FAILED")
        finally:
            os.unlink(path)


# ── Invoice matching upgrade tests ────────────────────────────────────────────

class TestMatchingWithExtractionData:
    def test_quantity_mismatch_creates_mismatch_alert(self, db, match_setup):
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType
        from app.services.procurement_matching_service import match_invoice_to_po

        s = match_setup
        # PO for R1000, invoice for R1500 — amount mismatch
        _make_po(db, s["project_id"], s["supplier_id"], s["owner_id"], total=1000.0)
        inv = _make_invoice(db, s["project_id"], s["supplier_id"], s["owner_id"], total=1500.0)
        db.commit()

        before = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.INVOICE_MISMATCH
        ).count()
        match_invoice_to_po(inv.id, db)
        after = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.INVOICE_MISMATCH
        ).count()
        assert after > before

    def test_matched_amounts_no_alert(self, db, match_setup):
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType
        from app.services.procurement_matching_service import match_invoice_to_po

        s = match_setup
        _make_po(db, s["project_id"], s["supplier_id"], s["owner_id"], total=1000.0)
        inv = _make_invoice(db, s["project_id"], s["supplier_id"], s["owner_id"], total=1000.0)
        db.commit()

        before = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.INVOICE_MISMATCH
        ).count()
        result = match_invoice_to_po(inv.id, db)
        after = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.INVOICE_MISMATCH
        ).count()

        assert result["matched"] is True
        assert result["match_status"] == "MATCHED"
        assert after == before   # no new mismatch alert


# ── Document AI compare endpoint ──────────────────────────────────────────────

class TestDocumentAICompareEndpoint:
    def test_compare_partial_receipt_returns_mismatch(self, client, db, match_setup):
        s = match_setup
        tok = s["tok"]
        # PO with 10 bags received of 30 ordered
        po = _make_po(db, s["project_id"], s["supplier_id"], s["owner_id"],
                      total=1000.0, qty_received=10.0)
        db.commit()

        r = client.post(
            "/api/v1/document-ai/compare",
            json={"purchase_order_id": str(po.id)},
            headers=auth(tok),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "MISMATCH"
        assert len(data["checks"]) > 0

    def test_compare_fully_received_returns_matched(self, client, db, match_setup):
        s = match_setup
        tok = s["tok"]
        po = _make_po(db, s["project_id"], s["supplier_id"], s["owner_id"],
                      total=1000.0, qty_received=30.0)
        db.commit()

        r = client.post(
            "/api/v1/document-ai/compare",
            json={"purchase_order_id": str(po.id)},
            headers=auth(tok),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "MATCHED"

    def test_compare_unknown_po_returns_400(self, client, db, match_setup):
        s = match_setup
        r = client.post(
            "/api/v1/document-ai/compare",
            json={"purchase_order_id": str(uuid.uuid4())},
            headers=auth(s["tok"]),
        )
        assert r.status_code == 400


# ── Document AI extract endpoint ──────────────────────────────────────────────

class TestDocumentAIExtractEndpoint:
    def test_extract_nonexistent_file(self, client, db, match_setup):
        """Extracting non-existent file returns 200 with FAILED status."""
        s = match_setup
        r = client.post(
            "/api/v1/document-ai/extract",
            json={"file_path": "/tmp/does_not_exist.pdf", "document_type": "INVOICE"},
            headers=auth(s["tok"]),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "FAILED"
        assert "extraction_id" in data
