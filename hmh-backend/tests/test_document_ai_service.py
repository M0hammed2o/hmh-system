"""
Tests for document_ai_service.py

Pure-function tests (no file I/O for parsers) and graceful-failure tests.
Covers:
- Invoice/DN/quote parser field extraction from known text
- OCR unavailable does not crash
- extract_document_data with non-existent file returns FAILED
- extract_document_data with plain-text file returns EXTRACTED
- compare_po_invoice_delivery detects quantity mismatch and creates alert
"""

import os
import uuid
import tempfile
import pytest

from app.services.document_ai_service import (
    parse_invoice_text,
    parse_delivery_note_text,
    parse_quote_text,
    extract_document_data,
    extract_text_from_image,
)
from tests.conftest import make_user, make_project, make_supplier


# ── Parser tests (pure text — no file I/O) ───────────────────────────────────

class TestParseInvoiceText:
    SAMPLE = """
    TAX INVOICE
    Invoice No: INV-2024-055
    Date: 12/03/2024
    Purchase Order: PO-DEMO-001

    Cement 50kg bags    30   bag   180.00   5400.00
    Bricks              500  ea     2.50    1250.00

    Total: R6650.00

    supplier@buildmart.co.za
    """

    def test_extracts_invoice_number(self):
        fields = parse_invoice_text(self.SAMPLE)
        assert fields["invoice_number"] is not None
        assert "INV" in fields["invoice_number"].upper() or "2024" in fields["invoice_number"]

    def test_extracts_po_number(self):
        fields = parse_invoice_text(self.SAMPLE)
        assert fields["po_number"] is not None
        assert "DEMO" in fields["po_number"].upper() or "001" in fields["po_number"]

    def test_extracts_total_amount(self):
        fields = parse_invoice_text(self.SAMPLE)
        assert fields["total_amount"] is not None
        assert float(fields["total_amount"]) > 0

    def test_extracts_email(self):
        fields = parse_invoice_text(self.SAMPLE)
        assert fields["supplier_email"] == "supplier@buildmart.co.za"

    def test_extracts_date(self):
        fields = parse_invoice_text(self.SAMPLE)
        assert fields["date"] is not None

    def test_missing_fields_return_none(self):
        fields = parse_invoice_text("No useful content here.")
        assert fields["invoice_number"] is None
        assert fields["total_amount"] is None


class TestParseDeliveryNoteText:
    SAMPLE = """
    DELIVERY NOTE
    DN-0042
    Delivery No: DN-0042
    Date: 15/03/2024
    Purchase Order: PO-DEMO-001

    Cement 50kg bags    30 bags
    """

    def test_extracts_dn_number(self):
        fields = parse_delivery_note_text(self.SAMPLE)
        assert fields["delivery_note_number"] is not None
        assert "0042" in fields["delivery_note_number"]

    def test_extracts_po_number(self):
        fields = parse_delivery_note_text(self.SAMPLE)
        assert fields["po_number"] is not None

    def test_no_total_for_dn(self):
        fields = parse_delivery_note_text(self.SAMPLE)
        assert fields["total_amount"] is None


class TestParseQuoteText:
    SAMPLE = """
    QUOTATION
    Quote No: QT-2024-003
    Date: 10 March 2024
    Email: info@supplier.co.za

    Grand Total: R9500.00
    """

    def test_extracts_total(self):
        fields = parse_quote_text(self.SAMPLE)
        assert fields["total_amount"] is not None
        assert float(fields["total_amount"]) > 0

    def test_extracts_email(self):
        fields = parse_quote_text(self.SAMPLE)
        assert fields["supplier_email"] is not None


# ── Graceful failure tests ────────────────────────────────────────────────────

class TestExtractDocumentData:
    def test_nonexistent_file_returns_failed(self):
        result = extract_document_data("/tmp/does_not_exist_12345.pdf")
        assert result["status"] == "FAILED"
        assert len(result["warnings"]) > 0

    def test_returns_required_keys(self):
        result = extract_document_data("/tmp/does_not_exist.pdf")
        for key in ["status", "document_type", "raw_text", "fields", "items", "warnings"]:
            assert key in result

    def test_fields_has_required_subkeys(self):
        result = extract_document_data("/tmp/does_not_exist.pdf")
        for key in ["po_number", "invoice_number", "delivery_note_number",
                    "supplier_name", "supplier_email", "date", "total_amount"]:
            assert key in result["fields"]

    def test_plain_text_file_extracts_invoice(self):
        """Plain .txt file is readable — no PDF/OCR library needed."""
        content = "Tax Invoice\nINV-TEST-001\nPO-TEST-001\nTotal: R1000.00\ntest@example.com"
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            result = extract_document_data(path, "INVOICE")
            assert result["status"] in ("EXTRACTED", "NEEDS_REVIEW")
            assert result["raw_text"].strip() != ""
        finally:
            os.unlink(path)

    def test_plain_text_extracts_po_number(self):
        content = "INVOICE\nINV-001\nPurchase Order: PO-MATCH-001\nTotal: R5000.00"
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            result = extract_document_data(path, "INVOICE")
            assert result["fields"]["po_number"] is not None
        finally:
            os.unlink(path)

    def test_plain_text_delivery_note(self):
        content = "DELIVERY NOTE\nDN-TEST-007\nDelivery No: DN-TEST-007\nPO-TEST-002"
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            result = extract_document_data(path, "DELIVERY_NOTE")
            assert result["fields"]["delivery_note_number"] is not None
        finally:
            os.unlink(path)


class TestExtractTextFromImage:
    def test_unavailable_returns_empty_string_not_crash(self):
        """pytesseract not installed → returns empty string, does not raise."""
        result = extract_text_from_image("/tmp/fake_image_12345.png")
        assert isinstance(result, str)


# ── Comparison tests ──────────────────────────────────────────────────────────

@pytest.fixture
def compare_setup(db, client):
    from tests.conftest import make_user, make_project, make_supplier
    owner    = make_user(db, role="OWNER")
    project  = make_project(db, owner_id=owner["id"])
    supplier = make_supplier(db)
    return dict(owner_id=owner["id"], project_id=project["id"], supplier_id=supplier["id"])


def _make_po_for_compare(db, project_id, supplier_id, created_by, total=1000.0):
    from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
    from app.models.enums import RecordStatus, VatMode
    from decimal import Decimal
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    po = PurchaseOrder(
        po_number=f"PO-CMP-{uuid.uuid4().hex[:6].upper()}",
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
        quantity_received=Decimal("20"),   # partial — 10 outstanding
        unit="bags",
        rate=Decimal(str(total / 30)),
        vat_mode=VatMode.INCLUSIVE,
        vat_rate=Decimal("15.00"),
        line_total=Decimal(str(total)),
        created_at=now,
    ))
    db.flush()
    return po


class TestComparePOInvoiceDelivery:
    def test_partial_receipt_creates_mismatch(self, db, compare_setup):
        from app.services.document_ai_service import compare_po_invoice_delivery
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType

        s = compare_setup
        po = _make_po_for_compare(db, s["project_id"], s["supplier_id"], s["owner_id"])
        db.commit()

        before = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.DELIVERY_MISMATCH
        ).count()

        result = compare_po_invoice_delivery(
            po_id=str(po.id),
            invoice_id=None,
            delivery_note_id=None,
            db=db,
        )

        # 10 bags outstanding → MISMATCH
        assert result["status"] == "MISMATCH"
        assert len(result["checks"]) > 0

        after = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.DELIVERY_MISMATCH
        ).count()
        assert after > before

    def test_unknown_po_id_returns_failed(self, db):
        from app.services.document_ai_service import compare_po_invoice_delivery
        result = compare_po_invoice_delivery(
            po_id=str(uuid.uuid4()),
            invoice_id=None,
            delivery_note_id=None,
            db=db,
        )
        assert result["status"] == "FAILED"
