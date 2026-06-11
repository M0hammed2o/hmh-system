"""
Tests for Phase 6A — AI OCR service and endpoint.

Tests are fully self-contained:
- Claude API is always mocked via unittest.mock.patch.
- No real API calls are made; no ANTHROPIC_API_KEY required.
- The ai-extract endpoint is tested via a real TestClient with a rolled-back DB session.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from tests.conftest import make_user, login


# ─── Helpers ────────────────────────────────────────────────────────────────

SAMPLE_INVOICE_TEXT = """
ABC Building Supplies (Pty) Ltd
VAT Reg: 4890123456
Invoice No: INV-2024-0987
Date: 15 January 2024
PO Number: PO-2024-0056

Billed To: HMH Construction

Description           Qty   Unit Rate   Total
Concrete mix 25MPa     50   450.00      22500.00
Steel reinforcing      100  120.00      12000.00

Subtotal:   34500.00
VAT (15%):   5175.00
Total Due:  39675.00
"""

VALID_AI_RESPONSE = {
    "header": {
        "supplier_name":  {"value": "ABC Building Supplies (Pty) Ltd", "confidence": 0.95},
        "invoice_number": {"value": "INV-2024-0987", "confidence": 0.98},
        "invoice_date":   {"value": "2024-01-15",   "confidence": 0.92},
        "po_number":      {"value": "PO-2024-0056", "confidence": 0.90},
        "vat_number":     {"value": "4890123456",   "confidence": 0.88},
        "net_amount":     {"value": 34500.00,       "confidence": 0.96},
        "vat_amount":     {"value": 5175.00,        "confidence": 0.95},
        "gross_amount":   {"value": 39675.00,       "confidence": 0.97},
    },
    "line_items": [
        {"description": "Concrete mix 25MPa", "quantity": 50, "unit_rate": 450.00, "total": 22500.00, "confidence": 0.88},
        {"description": "Steel reinforcing",  "quantity": 100, "unit_rate": 120.00, "total": 12000.00, "confidence": 0.85},
    ],
}

LOW_CONF_AI_RESPONSE = {
    "header": {
        "supplier_name":  {"value": None, "confidence": 0.0},
        "invoice_number": {"value": "INV-???", "confidence": 0.30},
        "invoice_date":   {"value": None,      "confidence": 0.0},
        "po_number":      {"value": None,      "confidence": 0.0},
        "vat_number":     {"value": None,      "confidence": 0.0},
        "net_amount":     {"value": None,      "confidence": 0.0},
        "vat_amount":     {"value": None,      "confidence": 0.0},
        "gross_amount":   {"value": None,      "confidence": 0.0},
    },
    "line_items": [],
}


def _make_mock_message(response_dict: dict):
    """Build a fake anthropic.Message with the given JSON body."""
    content_block = MagicMock()
    content_block.text = json.dumps(response_dict)
    msg = MagicMock()
    msg.content = [content_block]
    return msg


# ─── Unit tests: ai_ocr_service ─────────────────────────────────────────────

class TestExtractInvoiceFieldsWithAI:

    def test_returns_needs_review_when_no_api_key(self):
        from app.services.ai_ocr_service import extract_invoice_fields_with_ai
        from app.core.config import settings as real_settings
        original = real_settings.ANTHROPIC_API_KEY
        try:
            real_settings.ANTHROPIC_API_KEY = ""
            result = extract_invoice_fields_with_ai(SAMPLE_INVOICE_TEXT)
        finally:
            real_settings.ANTHROPIC_API_KEY = original
        assert result["status"] == "NEEDS_REVIEW"
        assert any("ANTHROPIC_API_KEY" in w for w in result["warnings"])

    def test_returns_needs_review_when_empty_text(self):
        from app.services.ai_ocr_service import extract_invoice_fields_with_ai
        result = extract_invoice_fields_with_ai("")
        assert result["status"] == "NEEDS_REVIEW"

    def test_successful_extraction_high_confidence(self):
        from app.services.ai_ocr_service import extract_invoice_fields_with_ai

        mock_msg = _make_mock_message(VALID_AI_RESPONSE)

        with patch("app.core.config.settings") as mock_settings, \
             patch("anthropic.Anthropic") as MockAnthropicClass:
            mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"
            mock_client = MockAnthropicClass.return_value
            mock_client.messages.create.return_value = mock_msg

            result = extract_invoice_fields_with_ai(SAMPLE_INVOICE_TEXT)

        assert result["status"] == "AI_EXTRACTED"
        assert result["overall_confidence"] > 0.80
        assert result["header"]["supplier_name"]["value"] == "ABC Building Supplies (Pty) Ltd"
        assert result["header"]["invoice_number"]["value"] == "INV-2024-0987"
        assert result["header"]["gross_amount"]["value"] == 39675.00
        assert len(result["line_items"]) == 2
        assert result["low_confidence_fields"] == []

    def test_low_confidence_fields_detected(self):
        from app.services.ai_ocr_service import extract_invoice_fields_with_ai

        mock_msg = _make_mock_message(LOW_CONF_AI_RESPONSE)

        with patch("app.core.config.settings") as mock_settings, \
             patch("anthropic.Anthropic") as MockAnthropicClass:
            mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"
            mock_client = MockAnthropicClass.return_value
            mock_client.messages.create.return_value = mock_msg

            result = extract_invoice_fields_with_ai(SAMPLE_INVOICE_TEXT)

        assert result["status"] == "NEEDS_REVIEW"
        assert len(result["low_confidence_fields"]) >= 7
        assert any("Low confidence" in w for w in result["warnings"])

    def test_handles_invalid_json_from_claude(self):
        from app.services.ai_ocr_service import extract_invoice_fields_with_ai

        bad_content = MagicMock()
        bad_content.text = "Sorry, I cannot extract this document."
        mock_msg = MagicMock()
        mock_msg.content = [bad_content]

        with patch("app.core.config.settings") as mock_settings, \
             patch("anthropic.Anthropic") as MockAnthropicClass:
            mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"
            mock_client = MockAnthropicClass.return_value
            mock_client.messages.create.return_value = mock_msg

            result = extract_invoice_fields_with_ai(SAMPLE_INVOICE_TEXT)

        assert result["status"] == "NEEDS_REVIEW"
        assert any("JSON" in w for w in result["warnings"])

    def test_handles_markdown_fenced_json(self):
        from app.services.ai_ocr_service import extract_invoice_fields_with_ai

        fenced_content = MagicMock()
        fenced_content.text = f"```json\n{json.dumps(VALID_AI_RESPONSE)}\n```"
        mock_msg = MagicMock()
        mock_msg.content = [fenced_content]

        with patch("app.core.config.settings") as mock_settings, \
             patch("anthropic.Anthropic") as MockAnthropicClass:
            mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"
            mock_client = MockAnthropicClass.return_value
            mock_client.messages.create.return_value = mock_msg

            result = extract_invoice_fields_with_ai(SAMPLE_INVOICE_TEXT)

        assert result["status"] == "AI_EXTRACTED"
        assert result["header"]["invoice_number"]["value"] == "INV-2024-0987"

    def test_handles_api_exception(self):
        from app.services.ai_ocr_service import extract_invoice_fields_with_ai

        with patch("app.core.config.settings") as mock_settings, \
             patch("anthropic.Anthropic") as MockAnthropicClass:
            mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"
            mock_client = MockAnthropicClass.return_value
            mock_client.messages.create.side_effect = RuntimeError("API timeout")

            result = extract_invoice_fields_with_ai(SAMPLE_INVOICE_TEXT)

        assert result["status"] == "FAILED"
        assert any("AI extraction error" in w for w in result["warnings"])


class TestMergeAIWithRegex:

    def test_merges_high_confidence_fields(self):
        from app.services.ai_ocr_service import merge_ai_with_regex

        regex_result = {
            "fields": {"invoice_number": "OLD", "total_amount": 100.0},
            "items": [],
        }
        ai_result = {
            "status": "AI_EXTRACTED",
            "header": {
                "invoice_number": {"value": "INV-NEW",  "confidence": 0.95},
                "gross_amount":   {"value": 39675.0,    "confidence": 0.97},
                "supplier_name":  {"value": "ABC Ltd",  "confidence": 0.88},
                "invoice_date":   {"value": "2024-01-15", "confidence": 0.92},
                "po_number":      {"value": "PO-001",   "confidence": 0.80},
                "vat_number":     {"value": "4890123456", "confidence": 0.88},
                "net_amount":     {"value": 34500.0,    "confidence": 0.96},
                "vat_amount":     {"value": 5175.0,     "confidence": 0.95},
            },
            "line_items": [
                {"description": "Concrete", "quantity": 50, "unit_rate": 450.0, "total": 22500.0, "confidence": 0.88},
            ],
            "overall_confidence": 0.91,
            "low_confidence_fields": [],
        }

        merged = merge_ai_with_regex(regex_result, ai_result)

        assert merged["fields"]["invoice_number"] == "INV-NEW"
        assert merged["fields"]["total_amount"] == 39675.0
        assert len(merged["items"]) == 1
        assert merged["confidence_score"] == 0.91
        assert "ai_extraction" in merged

    def test_skips_low_confidence_fields(self):
        from app.services.ai_ocr_service import merge_ai_with_regex

        regex_result = {"fields": {"invoice_number": "ORIGINAL"}, "items": []}
        ai_result = {
            "status": "AI_EXTRACTED",
            "header": {
                "invoice_number": {"value": "AI-VALUE", "confidence": 0.30},  # below threshold
                "supplier_name":  {"value": None,       "confidence": 0.0},
                "invoice_date":   {"value": None,       "confidence": 0.0},
                "po_number":      {"value": None,       "confidence": 0.0},
                "vat_number":     {"value": None,       "confidence": 0.0},
                "net_amount":     {"value": None,       "confidence": 0.0},
                "vat_amount":     {"value": None,       "confidence": 0.0},
                "gross_amount":   {"value": None,       "confidence": 0.0},
            },
            "line_items": [],
            "overall_confidence": 0.10,
            "low_confidence_fields": ["invoice_number"],
        }

        merged = merge_ai_with_regex(regex_result, ai_result)
        # Low-confidence AI value should not override the regex value
        assert merged["fields"]["invoice_number"] == "ORIGINAL"


# ─── Integration tests: /document-ai/ai-extract endpoint ─────────────────────

class TestAIExtractEndpoint:

    def _make_extraction(self, db, attachment_id: uuid.UUID, raw_text: str = SAMPLE_INVOICE_TEXT):
        """Create a DocumentExtraction record for a Gmail attachment."""
        from app.models.document_extraction import DocumentExtraction
        now = datetime.now(timezone.utc)
        ext = DocumentExtraction(
            source_type="gmail_attachment",
            source_id=attachment_id,
            file_path=f"/uploads/test_{attachment_id}.pdf",
            document_type="INVOICE",
            status="EXTRACTED",
            raw_text=raw_text,
            created_at=now,
        )
        db.add(ext)
        db.flush()
        return ext

    def test_returns_404_when_no_extraction_record(self, client: TestClient, db):
        user = make_user(db, role="OFFICE_ADMIN")
        db.commit()
        token = login(client, user["email"], user["password"])
        headers = {"Authorization": f"Bearer {token}"}

        missing_id = str(uuid.uuid4())
        r = client.post(f"/api/v1/document-ai/ai-extract/{missing_id}", headers=headers)
        assert r.status_code == 404

    def test_returns_404_on_get_when_not_run(self, client: TestClient, db):
        user = make_user(db, role="OFFICE_ADMIN")
        att_id = uuid.uuid4()
        self._make_extraction(db, att_id)
        db.commit()
        token = login(client, user["email"], user["password"])
        headers = {"Authorization": f"Bearer {token}"}

        r = client.get(f"/api/v1/document-ai/ai-extract/{att_id}", headers=headers)
        assert r.status_code == 404
        assert "not been run" in r.json()["detail"]

    def test_ai_extract_post_succeeds_with_mock(self, client: TestClient, db):
        user = make_user(db, role="OFFICE_ADMIN")
        att_id = uuid.uuid4()
        self._make_extraction(db, att_id)
        db.commit()
        token = login(client, user["email"], user["password"])
        headers = {"Authorization": f"Bearer {token}"}

        mock_msg = _make_mock_message(VALID_AI_RESPONSE)

        with patch("app.core.config.settings") as mock_settings, \
             patch("anthropic.Anthropic") as MockAnthropicClass:
            mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"
            mock_settings.RECONCILIATION_VARIANCE_THRESHOLD = 1.0
            mock_client = MockAnthropicClass.return_value
            mock_client.messages.create.return_value = mock_msg

            r = client.post(f"/api/v1/document-ai/ai-extract/{att_id}", headers=headers)

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "AI_EXTRACTED"
        assert data["overall_confidence"] > 0.80
        assert data["header"]["supplier_name"]["value"] == "ABC Building Supplies (Pty) Ltd"
        assert data["header"]["invoice_number"]["value"] == "INV-2024-0987"
        assert data["header"]["gross_amount"]["value"] == 39675.0
        assert len(data["line_items"]) == 2
        assert data["low_confidence_fields"] == []

    def test_ai_extract_returns_needs_review_when_no_key(self, client: TestClient, db):
        user = make_user(db, role="OFFICE_ADMIN")
        att_id = uuid.uuid4()
        self._make_extraction(db, att_id)
        db.commit()
        token = login(client, user["email"], user["password"])
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.services.ai_ocr_service.extract_invoice_fields_with_ai") as mock_extract:
            mock_extract.return_value = {
                "status": "NEEDS_REVIEW",
                "model": "claude-haiku-4-5-20251001",
                "header": {f: {"value": None, "confidence": 0.0} for f in [
                    "supplier_name", "invoice_number", "invoice_date", "po_number",
                    "vat_number", "net_amount", "vat_amount", "gross_amount",
                ]},
                "line_items": [],
                "overall_confidence": 0.0,
                "low_confidence_fields": ["supplier_name", "invoice_number"],
                "warnings": ["ANTHROPIC_API_KEY is not set"],
            }
            r = client.post(f"/api/v1/document-ai/ai-extract/{att_id}", headers=headers)

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "NEEDS_REVIEW"
        assert any("ANTHROPIC_API_KEY" in w for w in data["warnings"])

    def test_get_returns_stored_result(self, client: TestClient, db):
        user = make_user(db, role="OFFICE_ADMIN")
        att_id = uuid.uuid4()
        ext = self._make_extraction(db, att_id)

        stored_ai = {
            "status": "AI_EXTRACTED",
            "model": "claude-haiku-4-5-20251001",
            "header": {"supplier_name": {"value": "Test Co", "confidence": 0.9}},
            "line_items": [],
            "overall_confidence": 0.9,
            "low_confidence_fields": [],
            "warnings": [],
        }
        ext.ai_extraction_json = json.dumps(stored_ai)
        db.commit()

        token = login(client, user["email"], user["password"])
        headers = {"Authorization": f"Bearer {token}"}

        r = client.get(f"/api/v1/document-ai/ai-extract/{att_id}", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "AI_EXTRACTED"
        assert data["header"]["supplier_name"]["value"] == "Test Co"

    def test_requires_authentication(self, client: TestClient, db):
        att_id = str(uuid.uuid4())
        r = client.post(f"/api/v1/document-ai/ai-extract/{att_id}")
        assert r.status_code in (401, 403)


# ─── Confidence threshold helper tests ────────────────────────────────────────

class TestConfidenceHelpers:

    def test_compute_overall_confidence(self):
        from app.services.ai_ocr_service import _compute_overall_confidence
        header = {
            "supplier_name":  {"value": "A", "confidence": 0.90},
            "invoice_number": {"value": "B", "confidence": 0.80},
            "invoice_date":   {"value": "C", "confidence": 0.70},
            "po_number":      {"value": "D", "confidence": 0.60},
            "vat_number":     {"value": "E", "confidence": 0.50},
            "net_amount":     {"value": 100, "confidence": 0.95},
            "vat_amount":     {"value": 15,  "confidence": 0.90},
            "gross_amount":   {"value": 115, "confidence": 0.95},
        }
        overall = _compute_overall_confidence(header)
        expected = round((0.90+0.80+0.70+0.60+0.50+0.95+0.90+0.95) / 8, 3)
        assert overall == expected

    def test_find_low_confidence_fields(self):
        from app.services.ai_ocr_service import _find_low_confidence_fields
        header = {
            "supplier_name":  {"value": "A", "confidence": 0.90},  # high
            "invoice_number": {"value": "B", "confidence": 0.30},  # low
            "invoice_date":   {"value": None, "confidence": 0.0},  # low
            "po_number":      {"value": "D", "confidence": 0.60},  # ok
            "vat_number":     {"value": "E", "confidence": 0.45},  # low (< 0.50)
            "net_amount":     {"value": 100, "confidence": 0.95},  # high
            "vat_amount":     {"value": 15,  "confidence": 0.55},  # ok
            "gross_amount":   {"value": 115, "confidence": 0.95},  # high
        }
        low = _find_low_confidence_fields(header)
        assert "invoice_number" in low
        assert "invoice_date" in low
        assert "vat_number" in low
        assert "supplier_name" not in low
        assert "net_amount" not in low

    def test_normalise_header_field_clips_confidence(self):
        from app.services.ai_ocr_service import _normalise_header_field
        # Confidence values outside [0,1] are clipped
        assert _normalise_header_field({"value": "X", "confidence": 1.5})["confidence"] == 1.0
        assert _normalise_header_field({"value": "X", "confidence": -0.5})["confidence"] == 0.0

    def test_normalise_header_field_handles_missing(self):
        from app.services.ai_ocr_service import _normalise_header_field
        f = _normalise_header_field(None)
        assert f["value"] is None
        assert f["confidence"] == 0.0
