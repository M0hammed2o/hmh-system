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
    parse_purchase_order_text,
    parse_fuel_slip_text,
    parse_payment_proof_text,
    extract_document_data,
    extract_text_from_image,
    _similar,
    fuzzy_match_supplier,
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


# ── Google Vision OCR tests (all mocked — no real API calls) ─────────────────

class TestGoogleVisionOCR:
    """
    Tests for extract_text_via_google_vision() and validate_ocr_setup().
    All Vision API calls are mocked; no real credentials or network needed.
    """

    def _mock_vision(self, text: str = "", error_msg: str = ""):
        """Return a minimal google.cloud.vision mock wired to return `text`."""
        from unittest.mock import MagicMock
        mock_v = MagicMock()
        mock_resp = MagicMock()
        mock_resp.error.message = error_msg
        mock_resp.full_text_annotation.text = text
        mock_v.ImageAnnotatorClient.return_value.document_text_detection.return_value = mock_resp
        mock_v.Image.return_value = MagicMock()
        return mock_v

    def _patch_vision(self, mock_v):
        """Return a patch.dict context that injects `mock_v` as google.cloud.vision."""
        import sys
        from unittest.mock import MagicMock, patch
        mock_gc = MagicMock()
        mock_gc.vision = mock_v
        return patch.dict(sys.modules, {
            "google": MagicMock(),
            "google.cloud": mock_gc,
            "google.cloud.vision": mock_v,
        })

    def test_vision_not_installed_returns_empty(self, tmp_path):
        """ImportError (package not installed) → returns empty string, never raises."""
        import sys
        from unittest.mock import patch
        from app.services.document_ai_service import extract_text_via_google_vision

        with patch.dict(sys.modules, {"google.cloud.vision": None}):
            result = extract_text_via_google_vision(str(tmp_path / "fake.png"))
        assert result == ""

    def test_vision_success_returns_text(self, tmp_path, monkeypatch):
        """Mocked Vision API returns text → function returns that text."""
        from app.services.document_ai_service import extract_text_via_google_vision

        test_file = tmp_path / "invoice.png"
        test_file.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header bytes

        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setattr(
            "app.services.document_ai_service._prepare_credentials", lambda: None
        )

        mock_v = self._mock_vision(text="Invoice INV-MOCK-001\nTotal Due: R12500.00")
        with self._patch_vision(mock_v):
            result = extract_text_via_google_vision(str(test_file))

        assert "INV-MOCK-001" in result
        assert "12500" in result

    def test_vision_api_error_returns_empty(self, tmp_path, monkeypatch):
        """Vision response.error.message set → returns empty string, no raise."""
        from app.services.document_ai_service import extract_text_via_google_vision

        test_file = tmp_path / "doc.png"
        test_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setattr(
            "app.services.document_ai_service._prepare_credentials", lambda: None
        )

        mock_v = self._mock_vision(text="", error_msg="PERMISSION_DENIED: quota exceeded")
        with self._patch_vision(mock_v):
            result = extract_text_via_google_vision(str(test_file))

        assert result == ""

    def test_vision_client_exception_returns_empty(self, tmp_path, monkeypatch):
        """Vision client constructor raises (bad credentials) → returns empty string."""
        import sys
        from unittest.mock import MagicMock, patch
        from app.services.document_ai_service import extract_text_via_google_vision

        test_file = tmp_path / "doc.png"
        test_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        monkeypatch.setattr(
            "app.services.document_ai_service._prepare_credentials", lambda: None
        )

        mock_v = MagicMock()
        mock_v.ImageAnnotatorClient.side_effect = Exception("DefaultCredentialsError: no credentials found")

        with self._patch_vision(mock_v):
            result = extract_text_via_google_vision(str(test_file))

        assert result == ""

    def test_vision_missing_file_returns_empty(self, monkeypatch):
        """File does not exist → open() raises → caught → returns empty string."""
        from app.services.document_ai_service import extract_text_via_google_vision
        monkeypatch.setattr(
            "app.services.document_ai_service._prepare_credentials", lambda: None
        )
        mock_v = self._mock_vision(text="some text")
        with self._patch_vision(mock_v):
            result = extract_text_via_google_vision("/nonexistent/path/invoice.png")
        assert result == ""

    def test_disabled_provider_returns_not_available(self, tmp_path, monkeypatch):
        """OCR_PROVIDER=disabled → extract_document_data returns OCR_NOT_AVAILABLE for images."""
        monkeypatch.setattr("app.services.document_ai_service._ocr_provider", lambda: "disabled")

        img_file = tmp_path / "scan.png"
        img_file.write_bytes(b"\x89PNG\r\n\x1a\n")

        from app.services.document_ai_service import extract_document_data
        result = extract_document_data(str(img_file), "INVOICE")
        assert result["status"] == "OCR_NOT_AVAILABLE"

    def test_validate_ocr_setup_disabled(self, monkeypatch):
        """validate_ocr_setup returns ready=True for disabled provider."""
        monkeypatch.setattr("app.services.document_ai_service._ocr_provider", lambda: "disabled")
        from app.services.document_ai_service import validate_ocr_setup
        status = validate_ocr_setup()
        assert status["ready"] is True
        assert status["provider"] == "disabled"

    def test_validate_ocr_setup_vision_missing_credentials(self, monkeypatch):
        """validate_ocr_setup returns ready=False when credentials not configured."""
        monkeypatch.setattr("app.services.document_ai_service._ocr_provider", lambda: "google_vision")
        from app.core.config import settings
        monkeypatch.setattr(settings, "GOOGLE_APPLICATION_CREDENTIALS", "")
        from app.services.document_ai_service import validate_ocr_setup
        status = validate_ocr_setup()
        assert status["ready"] is False
        assert "GOOGLE_APPLICATION_CREDENTIALS" in status["message"]

    def test_validate_ocr_setup_vision_file_not_found(self, monkeypatch):
        """validate_ocr_setup returns ready=False when credentials file doesn't exist."""
        monkeypatch.setattr("app.services.document_ai_service._ocr_provider", lambda: "google_vision")
        from app.core.config import settings
        monkeypatch.setattr(settings, "GOOGLE_APPLICATION_CREDENTIALS", "/nonexistent/creds.json")
        from app.services.document_ai_service import validate_ocr_setup
        status = validate_ocr_setup()
        assert status["ready"] is False
        assert "not found" in status["message"]

    def test_validate_ocr_setup_vision_ready(self, monkeypatch, tmp_path):
        """validate_ocr_setup returns ready=True when credentials file exists and library installed."""
        import sys
        from unittest.mock import MagicMock, patch

        cred_file = tmp_path / "creds.json"
        cred_file.write_text('{"type": "service_account"}')

        monkeypatch.setattr("app.services.document_ai_service._ocr_provider", lambda: "google_vision")
        from app.core.config import settings
        monkeypatch.setattr(settings, "GOOGLE_APPLICATION_CREDENTIALS", str(cred_file))

        mock_v = MagicMock()
        with patch.dict(sys.modules, {
            "google": MagicMock(),
            "google.cloud": MagicMock(vision=mock_v),
            "google.cloud.vision": mock_v,
        }):
            from app.services.document_ai_service import validate_ocr_setup
            status = validate_ocr_setup()

        assert status["ready"] is True
        assert status["provider"] == "google_vision"


# ── D.2 additional parser tests ───────────────────────────────────────────────

class TestInvoiceSubtotalAndVAT:
    """Invoice parser extracts subtotal, VAT, and due date."""

    SAMPLE = """
    TAX INVOICE
    Invoice No: INV-2024-100
    Date: 01/04/2024
    Due Date: 30/04/2024
    Purchase Order: PO-HMH-001

    Subtotal: R8,500.00
    VAT @ 15%: R1,275.00
    Total Due: R9,775.00
    """

    def test_extracts_subtotal(self):
        fields = parse_invoice_text(self.SAMPLE)
        assert fields["subtotal"] is not None
        assert abs(fields["subtotal"] - 8500.0) < 0.01

    def test_extracts_vat_amount(self):
        fields = parse_invoice_text(self.SAMPLE)
        assert fields["vat_amount"] is not None
        assert fields["vat_amount"] > 0

    def test_extracts_due_date(self):
        fields = parse_invoice_text(self.SAMPLE)
        assert fields["due_date"] is not None

    def test_total_due_preferred_over_subtotal(self):
        """Total Due should be returned as total_amount, not subtotal."""
        fields = parse_invoice_text(self.SAMPLE)
        assert fields["total_amount"] is not None
        assert fields["total_amount"] > fields["subtotal"]

    def test_sa_wording_inv_no(self):
        """'Inv No' is recognised as an invoice number label."""
        text = "Inv No: INV-SA-2024\nTotal: R5000.00"
        fields = parse_invoice_text(text)
        assert fields["invoice_number"] is not None
        assert "SA-2024" in fields["invoice_number"] or "INV" in fields["invoice_number"].upper()

    def test_sa_wording_po_number_label(self):
        """'PO Number:' (not just 'Purchase Order:') is recognised."""
        text = "PO Number: PO-HMH-999\nTotal: R1000.00"
        fields = parse_invoice_text(text)
        assert fields["po_number"] is not None
        assert "HMH-999" in fields["po_number"] or "999" in fields["po_number"]


class TestDeliveryNoteEnhanced:
    """Delivery note parser now extracts supplier name and received_by."""

    SAMPLE = """
    DELIVERY NOTE
    Supplier: BuildMart Supply Co
    D/N: DN-2024-099
    Delivery No: DN-2024-099
    Date: 10/04/2024
    Purchase Order: PO-HMH-001

    Cement 50kg bags    30  bags
    Steel rods          50  pcs

    Received By: John Smith
    """

    def test_extracts_supplier_name(self):
        fields = parse_delivery_note_text(self.SAMPLE)
        assert fields["supplier_name"] is not None
        assert len(fields["supplier_name"]) > 2

    def test_extracts_received_by(self):
        fields = parse_delivery_note_text(self.SAMPLE)
        assert fields["received_by"] is not None
        assert "John" in fields["received_by"] or "Smith" in fields["received_by"]

    def test_extracts_dn_number(self):
        fields = parse_delivery_note_text(self.SAMPLE)
        assert fields["delivery_note_number"] is not None
        assert "2024-099" in fields["delivery_note_number"]

    def test_extracts_po_number(self):
        fields = parse_delivery_note_text(self.SAMPLE)
        assert fields["po_number"] is not None

    def test_no_total_for_delivery_note(self):
        fields = parse_delivery_note_text(self.SAMPLE)
        assert fields["total_amount"] is None

    def test_delivery_items_parsed(self):
        """_parse_delivery_items picks up simple 2-col rows."""
        from app.services.document_ai_service import _parse_delivery_items
        items = _parse_delivery_items(self.SAMPLE)
        # At least one item row should be parsed
        assert len(items) >= 1
        qtys = [i["quantity"] for i in items]
        assert 30.0 in qtys or 50.0 in qtys


class TestParseFuelSlip:
    """Fuel slip parser extracts station, litres, vehicle reg, odometer."""

    SAMPLE = """
    BP NORTHGATE
    Station Name: BP Northgate
    Date: 12/03/2024
    Vehicle: HHH 001 GP
    Odometer: 145,230

    Unleaded 95    30.50 L    R24.40/L
    Total: R744.20
    """

    def test_extracts_total(self):
        fields = parse_fuel_slip_text(self.SAMPLE)
        assert fields["total_amount"] is not None
        assert fields["total_amount"] > 0

    def test_extracts_station_name(self):
        fields = parse_fuel_slip_text(self.SAMPLE)
        assert fields["station_name"] is not None
        assert len(fields["station_name"]) > 2

    def test_extracts_vehicle_registration(self):
        fields = parse_fuel_slip_text(self.SAMPLE)
        assert fields["vehicle_registration"] is not None

    def test_extracts_odometer(self):
        fields = parse_fuel_slip_text(self.SAMPLE)
        assert fields["odometer"] is not None
        assert fields["odometer"] > 0

    def test_extracts_date(self):
        fields = parse_fuel_slip_text(self.SAMPLE)
        assert fields["date"] is not None

    def test_litres_extracted(self):
        text = "Litres: 45.20\nTotal: R1100.00"
        fields = parse_fuel_slip_text(text)
        assert fields["litres"] is not None
        assert abs(fields["litres"] - 45.2) < 0.01

    def test_no_invoice_or_dn_number(self):
        fields = parse_fuel_slip_text(self.SAMPLE)
        assert fields["invoice_number"] is None
        assert fields["delivery_note_number"] is None


class TestParsePaymentProof:
    """Payment proof parser extracts paid amount, reference, beneficiary."""

    SAMPLE = """
    ELECTRONIC TRANSFER CONFIRMATION
    Date: 15/04/2024
    Account Name: BuildMart Supply Co
    Beneficiary: BuildMart Supply Co
    Reference No: INV-2024-055
    Amount Paid: R9,775.00
    """

    def test_extracts_paid_amount(self):
        fields = parse_payment_proof_text(self.SAMPLE)
        assert fields["paid_amount"] is not None
        assert fields["paid_amount"] > 0

    def test_extracts_reference_number(self):
        fields = parse_payment_proof_text(self.SAMPLE)
        assert fields["reference_number"] is not None
        assert "INV" in fields["reference_number"].upper() or "2024" in fields["reference_number"]

    def test_extracts_beneficiary(self):
        fields = parse_payment_proof_text(self.SAMPLE)
        assert fields["beneficiary"] is not None
        assert len(fields["beneficiary"]) > 3

    def test_extracts_date(self):
        fields = parse_payment_proof_text(self.SAMPLE)
        assert fields["payment_date"] is not None

    def test_total_amount_equals_paid_amount(self):
        fields = parse_payment_proof_text(self.SAMPLE)
        assert fields["total_amount"] is not None
        assert fields["total_amount"] == fields["paid_amount"]

    def test_missing_all_fields_returns_nones(self):
        fields = parse_payment_proof_text("Nothing useful here.")
        assert fields["paid_amount"] is None
        assert fields["reference_number"] is None
        assert fields["beneficiary"] is None


class TestParsePurchaseOrder:
    """Purchase order parser extracts PO number, supplier, date, total."""

    SAMPLE = """
    PURCHASE ORDER
    PO Number: PO-HMH-2024-001
    Date: 01/04/2024
    Supplier: BuildMart Supply Co
    supplier@buildmart.co.za

    Cement 50kg bags    30   bag    180.00   5400.00
    Bricks              500  ea       2.50   1250.00

    Subtotal: R5,785.00
    VAT @ 15%: R867.75
    Total: R6,652.75
    """

    def test_extracts_po_number(self):
        fields = parse_purchase_order_text(self.SAMPLE)
        assert fields["po_number"] is not None
        assert "HMH-2024-001" in fields["po_number"] or "HMH" in fields["po_number"]

    def test_extracts_supplier_name(self):
        fields = parse_purchase_order_text(self.SAMPLE)
        assert fields["supplier_name"] is not None

    def test_extracts_total(self):
        fields = parse_purchase_order_text(self.SAMPLE)
        assert fields["total_amount"] is not None
        assert fields["total_amount"] > 0

    def test_extracts_subtotal(self):
        fields = parse_purchase_order_text(self.SAMPLE)
        assert fields["subtotal"] is not None
        assert fields["subtotal"] < fields["total_amount"]

    def test_extracts_date(self):
        fields = parse_purchase_order_text(self.SAMPLE)
        assert fields["date"] is not None


class TestFuzzyMatchSimilar:
    """_similar() uses difflib for fuzzy matching."""

    def test_exact_match(self):
        assert _similar("Cement 50kg bags", "Cement 50kg bags") is True

    def test_case_insensitive(self):
        assert _similar("cement bags", "CEMENT BAGS") is True

    def test_minor_typo_matches(self):
        assert _similar("BuildMart Supply Co", "Buildmart Supply Co") is True

    def test_clearly_different_no_match(self):
        assert _similar("Steel rods", "Cement bags") is False

    def test_empty_strings_no_match(self):
        assert _similar("", "Cement") is False
        assert _similar("Cement", "") is False

    def test_partial_overlap_below_threshold(self):
        assert _similar("Steel", "Stainless Steel Wire Mesh") is False


class TestExtractDocumentDataNewTypes:
    """extract_document_data wires new document types correctly."""

    def _make_file(self, content: str, suffix: str = ".txt") -> str:
        import tempfile
        f = tempfile.NamedTemporaryFile(suffix=suffix, mode="w", delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_fuel_slip_type_extracts_fields(self):
        content = "Station Name: BP Test\nDate: 01/01/2024\nLitres: 50.0 L\nVehicle: ABC 123 GP\nTotal: R1200.00"
        path = self._make_file(content)
        try:
            result = extract_document_data(path, "FUEL_SLIP")
            assert result["status"] in ("EXTRACTED", "OCR_EXTRACTED", "NEEDS_REVIEW")
            assert result["fields"]["station_name"] is not None or result["fields"]["total_amount"] is not None
        finally:
            os.unlink(path)

    def test_payment_proof_type_extracts_reference(self):
        content = "Amount Paid: R5000.00\nReference No: REF-2024-001\nBeneficiary: Test Supplier"
        path = self._make_file(content)
        try:
            result = extract_document_data(path, "PAYMENT_PROOF")
            assert result["status"] in ("EXTRACTED", "OCR_EXTRACTED", "NEEDS_REVIEW")
        finally:
            os.unlink(path)

    def test_purchase_order_type_extracts_po_number(self):
        content = "PURCHASE ORDER\nPO Number: PO-TEST-2024\nDate: 01/01/2024\nTotal: R5000.00"
        path = self._make_file(content)
        try:
            result = extract_document_data(path, "PURCHASE_ORDER")
            assert result["status"] in ("EXTRACTED", "OCR_EXTRACTED")
            assert result["fields"]["po_number"] is not None
        finally:
            os.unlink(path)

    def test_all_fields_always_present_in_result(self):
        """extract_document_data always returns all known field keys, even when None."""
        result = extract_document_data("/nonexistent_file.pdf", "INVOICE")
        required = [
            "po_number", "invoice_number", "delivery_note_number",
            "supplier_name", "supplier_email", "date", "total_amount",
            "subtotal", "vat_amount", "due_date",
            "received_by", "station_name", "litres",
            "vehicle_registration", "odometer",
            "payment_date", "paid_amount", "reference_number", "beneficiary",
        ]
        for key in required:
            assert key in result["fields"], f"Missing field: {key}"

    def test_ocr_extracted_status_propagated(self, tmp_path, monkeypatch):
        """When OCR is used on an image, status is OCR_EXTRACTED (not EXTRACTED)."""
        from unittest.mock import MagicMock, patch
        import sys

        img_file = tmp_path / "invoice.png"
        img_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        monkeypatch.setattr(
            "app.services.document_ai_service._prepare_credentials", lambda: None
        )
        monkeypatch.setattr(
            "app.services.document_ai_service._ocr_provider", lambda: "google_vision"
        )

        mock_v = MagicMock()
        mock_resp = MagicMock()
        mock_resp.error.message = ""
        mock_resp.full_text_annotation.text = "Invoice No: INV-OCR-001\nTotal Due: R5000.00"
        mock_v.ImageAnnotatorClient.return_value.document_text_detection.return_value = mock_resp
        mock_v.Image.return_value = MagicMock()
        mock_gc = MagicMock()
        mock_gc.vision = mock_v

        with patch.dict(sys.modules, {
            "google": MagicMock(), "google.cloud": mock_gc, "google.cloud.vision": mock_v,
        }):
            result = extract_document_data(str(img_file), "INVOICE")

        assert result["status"] in ("OCR_EXTRACTED", "NEEDS_REVIEW")


class TestAmountMatchTolerance:
    """_amount_match handles relative (2%) and absolute (R50) tolerance."""

    def test_exact_match(self):
        from app.services.procurement_matching_service import _amount_match
        assert _amount_match(1000.0, 1000.0) is True

    def test_within_absolute_tolerance(self):
        from app.services.procurement_matching_service import _amount_match
        # R30 difference on a R500 invoice — within R50 absolute
        assert _amount_match(500.0, 470.0) is True

    def test_within_relative_tolerance(self):
        from app.services.procurement_matching_service import _amount_match
        # 1% of R10000 = R100, within 2% tolerance
        assert _amount_match(10000.0, 9920.0) is True

    def test_outside_tolerance(self):
        from app.services.procurement_matching_service import _amount_match
        # R200 difference on R1000 — exceeds both 2% (R20) and R50
        assert _amount_match(1000.0, 800.0) is False

    def test_both_zero(self):
        from app.services.procurement_matching_service import _amount_match
        assert _amount_match(0.0, 0.0) is True
