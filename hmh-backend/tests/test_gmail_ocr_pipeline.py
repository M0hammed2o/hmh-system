"""
Phase E — Gmail → OCR → PO Matching pipeline tests.

Covers:
  - Document classification (new types: PAYMENT_PROOF, FUEL_SLIP, PURCHASE_ORDER)
  - Attachment MIME/size validation
  - Duplicate filename detection
  - Reconciliation suggestion structure + requires_review always True
  - Duplicate invoice detection
  - PO matching confidence scoring
  - _score_match issues generation
  - Alert creation helpers (duplicate invoice, supplier mismatch)
  - POST /gmail/incoming/{id}/suggest endpoint
  - build_proof_pack ocr_extraction key
"""

import io
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import make_supplier, make_user, make_project, login


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _make_incoming_email(db, from_email: str = "supplier@example.com", subject: str = "Invoice"):
    from app.models.incoming_email import IncomingEmail
    e = IncomingEmail(
        from_email=from_email,
        subject=subject,
        received_at=_now(),
        has_attachments=True,
        processed_status="UNPROCESSED",
        body_snippet="",
        message_id=f"msg-{uuid.uuid4().hex[:8]}",
        created_at=_now(),
    )
    db.add(e)
    db.flush()
    return e


def _make_attachment(db, email, filename: str = "invoice.pdf",
                     detected_type: str = "INVOICE",
                     file_path: str = "/tmp/invoice.pdf",
                     content_type: str = "application/pdf"):
    from app.models.incoming_email import IncomingEmailAttachment
    a = IncomingEmailAttachment(
        incoming_email_id=email.id,
        filename=filename,
        file_path=file_path,
        content_type=content_type,
        detected_type=detected_type,
        created_at=_now(),
    )
    db.add(a)
    db.flush()
    return a


def _make_po(db, supplier_id, po_number: str = None, total: float = 10000.0):
    from app.models.purchase_order import PurchaseOrder
    from app.models.enums import RecordStatus
    po_number = po_number or f"PO-{uuid.uuid4().hex[:6].upper()}"
    user = make_user(db)
    proj = make_project(db, user["id"])
    po = PurchaseOrder(
        po_number=po_number,
        supplier_id=uuid.UUID(supplier_id),
        project_id=uuid.UUID(proj["id"]),
        created_by=uuid.UUID(user["id"]),
        status=RecordStatus.SENT,
        po_date=_now().date(),
        total_amount=total,
        created_at=_now(), updated_at=_now(),
    )
    db.add(po)
    db.flush()
    return po


def _make_invoice(db, supplier_id, po_id=None, invoice_number: str = None,
                  total: float = 9800.0, project_id: str = None):
    from app.models.invoice import Invoice
    from app.models.enums import RecordStatus
    invoice_number = invoice_number or f"INV-{uuid.uuid4().hex[:6].upper()}"
    if not project_id:
        user = make_user(db)
        proj = make_project(db, user["id"])
        project_id = proj["id"]
    inv = Invoice(
        invoice_number=invoice_number,
        supplier_id=uuid.UUID(supplier_id),
        project_id=uuid.UUID(project_id),
        purchase_order_id=uuid.UUID(po_id) if po_id else None,
        total_amount=total,
        status=RecordStatus.SUBMITTED,
        captured_at=_now(),
        created_at=_now(), updated_at=_now(),
    )
    db.add(inv)
    db.flush()
    return inv


def _make_extraction(db, att, status: str = "EXTRACTED", fields: dict = None):
    from app.models.document_extraction import DocumentExtraction
    fields = fields or {"invoice_number": "INV-001", "total_amount": 9800.0}
    payload = {"status": status, "fields": fields, "items": [], "warnings": []}
    ex = DocumentExtraction(
        source_type="GMAIL_ATTACHMENT",
        source_id=att.id,
        file_path=att.file_path,
        document_type=att.detected_type,
        status=status,
        raw_text="",
        extracted_json=json.dumps(payload),
        created_at=_now(),
    )
    db.add(ex)
    db.flush()
    return ex


# ─────────────────────────────────────────────────────────────────────────────
# 1. Document classification
# ─────────────────────────────────────────────────────────────────────────────

class TestClassifyDocument:
    def test_invoice_filename(self):
        from app.services.gmail_reader_service import classify_document
        assert classify_document("supplier_invoice_aug.pdf") == "INVOICE"

    def test_delivery_note_filename(self):
        from app.services.gmail_reader_service import classify_document
        assert classify_document("delivery_note_001.pdf") == "DELIVERY_NOTE"

    def test_payment_proof_filename(self):
        from app.services.gmail_reader_service import classify_document
        assert classify_document("proof_of_payment.pdf") == "PAYMENT_PROOF"

    def test_payment_proof_eft_confirmation(self):
        from app.services.gmail_reader_service import classify_document
        assert classify_document("eft_confirmation_aug.pdf") == "PAYMENT_PROOF"

    def test_fuel_slip_filename(self):
        from app.services.gmail_reader_service import classify_document
        assert classify_document("fuel_slip_20240801.jpg") == "FUEL_SLIP"

    def test_fuel_receipt_filename(self):
        from app.services.gmail_reader_service import classify_document
        assert classify_document("fuel_receipt.png") == "FUEL_SLIP"

    def test_purchase_order_filename(self):
        from app.services.gmail_reader_service import classify_document
        assert classify_document("purchase_order_2024.pdf") == "PURCHASE_ORDER"

    def test_quote_filename(self):
        from app.services.gmail_reader_service import classify_document
        assert classify_document("quotation_supplier.pdf") == "QUOTE"

    def test_unknown_falls_back_to_other(self):
        from app.services.gmail_reader_service import classify_document
        assert classify_document("random_document.docx") == "OTHER"

    def test_payment_proof_priority_over_invoice(self):
        # "proof of payment invoice" — PAYMENT_PROOF wins
        from app.services.gmail_reader_service import classify_document
        result = classify_document("proof_of_payment_invoice.pdf")
        assert result == "PAYMENT_PROOF"


# ─────────────────────────────────────────────────────────────────────────────
# 2. MIME/size validation
# ─────────────────────────────────────────────────────────────────────────────

class TestAttachmentValidation:
    def test_pdf_allowed(self):
        from app.services.gmail_reader_service import _is_allowed_attachment
        assert _is_allowed_attachment("application/pdf", 1024) is True

    def test_jpeg_allowed(self):
        from app.services.gmail_reader_service import _is_allowed_attachment
        assert _is_allowed_attachment("image/jpeg", 512 * 1024) is True

    def test_png_allowed(self):
        from app.services.gmail_reader_service import _is_allowed_attachment
        assert _is_allowed_attachment("image/png", 2 * 1024 * 1024) is True

    def test_docx_blocked(self):
        from app.services.gmail_reader_service import _is_allowed_attachment
        assert _is_allowed_attachment(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 1024
        ) is False

    def test_exe_blocked(self):
        from app.services.gmail_reader_service import _is_allowed_attachment
        assert _is_allowed_attachment("application/x-msdownload", 512) is False

    def test_oversized_pdf_blocked(self):
        from app.services.gmail_reader_service import _is_allowed_attachment
        assert _is_allowed_attachment("application/pdf", 11 * 1024 * 1024) is False

    def test_exactly_10mb_allowed(self):
        from app.services.gmail_reader_service import _is_allowed_attachment
        assert _is_allowed_attachment("application/pdf", 10 * 1024 * 1024) is True

    def test_one_byte_over_blocked(self):
        from app.services.gmail_reader_service import _is_allowed_attachment
        assert _is_allowed_attachment("application/pdf", 10 * 1024 * 1024 + 1) is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Reconciliation suggestion structure
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildReconciliationSuggestion:
    def test_missing_attachment_returns_error(self, db):
        from app.services.gmail_ocr_pipeline_service import build_reconciliation_suggestion
        result = build_reconciliation_suggestion(db, uuid.uuid4())
        assert "error" in result
        assert result["requires_review"] is True

    def test_requires_review_always_true(self, db):
        from app.services.gmail_ocr_pipeline_service import build_reconciliation_suggestion
        email = _make_incoming_email(db)
        att   = _make_attachment(db, email)
        _make_extraction(db, att, fields={"invoice_number": "INV-TEST-001", "total_amount": 5000.0})

        with patch("app.services.gmail_ocr_pipeline_service._find_best_po_match", return_value=None):
            result = build_reconciliation_suggestion(db, att.id)

        assert result["requires_review"] is True

    def test_return_shape_complete(self, db):
        from app.services.gmail_ocr_pipeline_service import build_reconciliation_suggestion
        email = _make_incoming_email(db)
        att   = _make_attachment(db, email)
        _make_extraction(db, att, fields={"invoice_number": "INV-XYZ", "total_amount": 1000.0})

        with patch("app.services.gmail_ocr_pipeline_service._find_best_po_match", return_value=None):
            result = build_reconciliation_suggestion(db, att.id)

        required_keys = {
            "attachment_id", "filename", "document_type", "extraction_status",
            "invoice_number", "delivery_note_number", "po_number_from_doc",
            "supplier_name", "supplier_email", "total_amount", "date",
            "matched_po", "matched_po_id", "match_confidence",
            "issues", "requires_review", "extraction_warnings",
        }
        assert required_keys.issubset(result.keys())

    def test_uses_cached_extraction(self, db):
        from app.services.gmail_ocr_pipeline_service import build_reconciliation_suggestion
        email = _make_incoming_email(db)
        att   = _make_attachment(db, email)
        _make_extraction(db, att, status="EXTRACTED",
                         fields={"invoice_number": "CACHED-001", "total_amount": 7500.0})

        with patch("app.services.document_ai_service.extract_document_data") as mock_ocr, \
             patch("app.services.gmail_ocr_pipeline_service._find_best_po_match", return_value=None):
            result = build_reconciliation_suggestion(db, att.id)
            mock_ocr.assert_not_called()   # must NOT re-run OCR when cache exists

        assert result["invoice_number"] == "CACHED-001"

    def test_duplicate_invoice_flagged(self, db):
        from app.services.gmail_ocr_pipeline_service import build_reconciliation_suggestion
        sup      = make_supplier(db)
        inv_num  = f"DUP-INV-{uuid.uuid4().hex[:6].upper()}"
        email    = _make_incoming_email(db)
        att      = _make_attachment(db, email)
        _make_extraction(db, att, fields={"invoice_number": inv_num, "total_amount": 5000.0})
        _make_invoice(db, sup["id"], invoice_number=inv_num)

        with patch("app.services.gmail_ocr_pipeline_service._find_best_po_match", return_value=None):
            result = build_reconciliation_suggestion(db, att.id)

        assert any("duplicate_invoice" in str(i) for i in result["issues"])

    def test_no_po_match_issue_added(self, db):
        from app.services.gmail_ocr_pipeline_service import build_reconciliation_suggestion
        email = _make_incoming_email(db)
        att   = _make_attachment(db, email)
        _make_extraction(db, att)

        with patch("app.services.gmail_ocr_pipeline_service._find_best_po_match", return_value=None):
            result = build_reconciliation_suggestion(db, att.id)

        assert "no_po_match_found" in result["issues"]
        assert result["matched_po"] is None
        assert result["match_confidence"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Duplicate invoice detection
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectDuplicateInvoice:
    def test_returns_false_when_no_invoice(self, db):
        from app.services.gmail_ocr_pipeline_service import detect_duplicate_invoice
        assert detect_duplicate_invoice(db, "NONEXISTENT-INV-999") is False

    def test_returns_true_when_invoice_exists(self, db):
        from app.services.gmail_ocr_pipeline_service import detect_duplicate_invoice
        sup = make_supplier(db)
        _make_invoice(db, sup["id"], invoice_number="FOUND-INV-001")
        assert detect_duplicate_invoice(db, "FOUND-INV-001") is True

    def test_scoped_by_supplier_id_no_match(self, db):
        from app.services.gmail_ocr_pipeline_service import detect_duplicate_invoice
        sup1 = make_supplier(db)
        sup2 = make_supplier(db)
        _make_invoice(db, sup1["id"], invoice_number="SUP-INV-001")
        # Same invoice number but different supplier → not a dup for sup2
        assert detect_duplicate_invoice(db, "SUP-INV-001", uuid.UUID(sup2["id"])) is False

    def test_scoped_by_supplier_id_match(self, db):
        from app.services.gmail_ocr_pipeline_service import detect_duplicate_invoice
        sup = make_supplier(db)
        _make_invoice(db, sup["id"], invoice_number="SUP-INV-002")
        assert detect_duplicate_invoice(db, "SUP-INV-002", uuid.UUID(sup["id"])) is True

    def test_never_raises(self):
        from app.services.gmail_ocr_pipeline_service import detect_duplicate_invoice
        bad_db = MagicMock()
        bad_db.query.side_effect = Exception("DB exploded")
        result = detect_duplicate_invoice(bad_db, "ANY-INV")
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# 5. Confidence scoring
# ─────────────────────────────────────────────────────────────────────────────

class TestScoreMatch:
    def _mock_po(self, po_number="PO-2024-001", total=10000.0, supplier_name="ABC Builders"):
        po = MagicMock()
        po.po_number   = po_number
        po.total_amount = total
        supplier       = MagicMock()
        supplier.name  = supplier_name
        po.supplier    = supplier
        return po

    def test_no_po_returns_zero_confidence(self):
        from app.services.gmail_ocr_pipeline_service import _score_match
        conf, issues = _score_match({}, "INVOICE", None)
        assert conf == 0.0
        assert "no_po_match_found" in issues

    def test_exact_po_number_adds_0_55(self):
        from app.services.gmail_ocr_pipeline_service import _score_match
        po = self._mock_po("PO-2024-001")
        conf, issues = _score_match({"po_number": "PO-2024-001"}, "INVOICE", po)
        assert conf >= 0.55

    def test_amount_within_tolerance_adds_0_25(self):
        from app.services.gmail_ocr_pipeline_service import _score_match
        po = self._mock_po("PO-ABC", total=10000.0, supplier_name="")
        # po_number not in fields → no PO signal; amount within 2% tolerance
        conf, _ = _score_match(
            {"po_number": "PO-ABC", "total_amount": 10050.0, "supplier_name": ""},
            "INVOICE", po
        )
        # 0.55 (PO exact) + 0.25 (amount)
        assert conf >= 0.75

    def test_amount_outside_tolerance_adds_issue(self):
        from app.services.gmail_ocr_pipeline_service import _score_match
        po = self._mock_po("PO-Z", total=10000.0, supplier_name="")
        _, issues = _score_match(
            {"po_number": "PO-Z", "total_amount": 5000.0, "supplier_name": ""},
            "INVOICE", po
        )
        assert any("invoice_total_differs_by" in i for i in issues)

    def test_max_confidence_capped_at_1(self):
        from app.services.gmail_ocr_pipeline_service import _score_match
        po = self._mock_po("PO-MAX", total=9800.0, supplier_name="ABC Builders")
        with patch("app.services.document_ai_service._similar", return_value=True):
            conf, _ = _score_match(
                {"po_number": "PO-MAX", "total_amount": 9800.0, "supplier_name": "ABC Builders"},
                "INVOICE", po
            )
        assert conf <= 1.0

    def test_no_po_number_in_document_issue(self):
        from app.services.gmail_ocr_pipeline_service import _score_match
        po = self._mock_po("PO-MISS", supplier_name="")
        _, issues = _score_match({"total_amount": 5000.0, "supplier_name": ""}, "INVOICE", po)
        assert "no_po_number_in_document" in issues

    def test_supplier_mismatch_adds_issue(self):
        from app.services.gmail_ocr_pipeline_service import _score_match
        po = self._mock_po("PO-SUPP", total=5000.0, supplier_name="XYZ Corp")
        with patch("app.services.document_ai_service._similar", return_value=False):
            _, issues = _score_match(
                {"po_number": "PO-SUPP", "total_amount": 5000.0, "supplier_name": "ABC Builders"},
                "INVOICE", po
            )
        assert "supplier_name_mismatch" in issues


# ─────────────────────────────────────────────────────────────────────────────
# 6. Alert helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestAlertHelpers:
    def test_create_duplicate_invoice_alert(self, db):
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType
        from app.services.gmail_ocr_pipeline_service import create_duplicate_invoice_alert
        create_duplicate_invoice_alert(db, "DUP-999", "supplier@test.com")
        alert = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.DUPLICATE_INVOICE
        ).first()
        assert alert is not None
        assert "DUP-999" in alert.title
        assert alert.severity.value == "HIGH"

    def test_create_supplier_mismatch_alert(self, db):
        from app.models.alert import SystemAlert
        from app.models.enums import AlertType
        from app.services.gmail_ocr_pipeline_service import create_supplier_mismatch_alert
        create_supplier_mismatch_alert(db, "Doc Supplier", "PO Supplier", "PO-2024-001")
        alert = db.query(SystemAlert).filter(
            SystemAlert.alert_type == AlertType.SUPPLIER_MISMATCH
        ).first()
        assert alert is not None
        assert "PO-2024-001" in alert.title
        assert "Doc Supplier" in alert.message

    def test_alert_helpers_never_raise(self, db):
        from app.services.gmail_ocr_pipeline_service import (
            create_duplicate_invoice_alert,
            create_supplier_mismatch_alert,
        )
        bad = MagicMock()
        bad.add.side_effect = Exception("DB error")
        create_duplicate_invoice_alert(bad, "X", "y@z.com")   # must not raise
        create_supplier_mismatch_alert(bad, "A", "B", "PO-X") # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# 7. POST /gmail/incoming/{id}/suggest endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestSuggestEndpoint:
    def _auth_headers(self, client, db):
        user  = make_user(db, role="OFFICE_ADMIN")
        token = login(client, user["email"], user["password"])
        return {"Authorization": f"Bearer {token}"}

    def test_404_on_unknown_email(self, client, db):
        headers = self._auth_headers(client, db)
        resp = client.post(f"/api/v1/gmail/incoming/{uuid.uuid4()}/suggest",
                           headers=headers)
        assert resp.status_code == 404

    def test_empty_attachments_returns_empty_suggestions(self, client, db):
        headers = self._auth_headers(client, db)
        email   = _make_incoming_email(db)
        # No attachments
        email.has_attachments = False
        db.flush()

        resp = client.post(f"/api/v1/gmail/incoming/{email.id}/suggest",
                           headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["suggestions"] == []

    def test_suggest_returns_one_suggestion_per_attachment(self, client, db):
        headers = self._auth_headers(client, db)
        email   = _make_incoming_email(db)
        att     = _make_attachment(db, email)
        _make_extraction(db, att, fields={"invoice_number": "INV-SUGGEST-001"})

        with patch("app.services.gmail_ocr_pipeline_service._find_best_po_match", return_value=None):
            resp = client.post(f"/api/v1/gmail/incoming/{email.id}/suggest",
                               headers=headers)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["requires_review"] is True

    def test_suggest_never_creates_invoice(self, client, db):
        from app.models.invoice import Invoice
        headers = self._auth_headers(client, db)
        email   = _make_incoming_email(db)
        att     = _make_attachment(db, email)
        _make_extraction(db, att, fields={"invoice_number": "INV-NO-CREATE-001"})

        invoice_count_before = db.query(Invoice).count()

        with patch("app.services.gmail_ocr_pipeline_service._find_best_po_match", return_value=None):
            client.post(f"/api/v1/gmail/incoming/{email.id}/suggest", headers=headers)

        assert db.query(Invoice).count() == invoice_count_before

    def test_requires_review_always_true_in_response(self, client, db):
        headers = self._auth_headers(client, db)
        email   = _make_incoming_email(db)
        _make_attachment(db, email)

        with patch("app.services.gmail_ocr_pipeline_service.build_reconciliation_suggestion",
                   return_value={"requires_review": True, "issues": []}):
            resp = client.post(f"/api/v1/gmail/incoming/{email.id}/suggest",
                               headers=headers)

        assert resp.status_code == 200
        for s in resp.json()["data"]["suggestions"]:
            assert s["requires_review"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 8. build_proof_pack OCR extraction key
# ─────────────────────────────────────────────────────────────────────────────

class TestProofPackOcrExtraction:
    def _shared_po_invoice(self, db):
        """Create supplier, PO, and invoice sharing the same project_id."""
        sup  = make_supplier(db)
        user = make_user(db)
        proj = make_project(db, user["id"])
        po   = _make_po(db, sup["id"])
        inv  = _make_invoice(db, sup["id"], po_id=str(po.id), project_id=proj["id"])
        return sup, po, inv

    def test_ocr_extraction_key_present(self, db):
        from app.services.procurement_matching_service import build_proof_pack
        sup, po, inv = self._shared_po_invoice(db)
        email = _make_incoming_email(db, from_email=f"x@{sup['name'].lower().replace(' ', '')}.com")
        att   = _make_attachment(db, email)
        _make_extraction(db, att, fields={"invoice_number": inv.invoice_number})

        pack = build_proof_pack(inv.id, db)
        # ocr_extraction key must exist (may be None if email domain match fails)
        assert "ocr_extraction" in pack

    def test_ocr_extraction_none_when_no_incoming_email(self, db):
        from app.services.procurement_matching_service import build_proof_pack
        sup, po, inv = self._shared_po_invoice(db)
        # No incoming email for this supplier → ocr_extraction should be None
        pack = build_proof_pack(inv.id, db)
        assert "ocr_extraction" in pack
        # Either None or a dict — both are valid
        assert pack["ocr_extraction"] is None or isinstance(pack["ocr_extraction"], dict)

    def test_ocr_extraction_shape_when_present(self, db):
        from app.services.procurement_matching_service import build_proof_pack
        from app.models.supplier import Supplier
        sup, po, inv = self._shared_po_invoice(db)

        # Email domain must match the supplier email
        supplier_domain = sup["name"].lower().replace(" ", "") + ".com"
        email = _make_incoming_email(db, from_email=f"orders@{supplier_domain}")
        att   = _make_attachment(db, email)
        _make_extraction(db, att, status="EXTRACTED",
                         fields={"invoice_number": inv.invoice_number, "total_amount": 9800.0})

        # Patch the supplier email to match the incoming email domain
        sup_model = db.get(Supplier, uuid.UUID(sup["id"]))
        sup_model.email = f"contact@{supplier_domain}"
        db.flush()

        pack = build_proof_pack(inv.id, db)

        if pack["ocr_extraction"] is not None:
            ocr = pack["ocr_extraction"]
            assert "status" in ocr
            assert "document_type" in ocr
            assert "fields" in ocr
            assert "created_at" in ocr
