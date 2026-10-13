"""
AI Document Import — the provider request contract.

Everything about the Anthropic request that can be established without
sending it: the SDK surface, the content-block shapes, the documented size
and page limits, the output schema, and how an unusable response is reported.

These are the checks that stand in for live validation. They do NOT establish
that the model reads real documents correctly — nothing offline can.
"""

import base64
import json

import pytest

from app.core.config import settings
from app.schemas.ai_import import COMMON_FIELDS
from app.services import ai_import_extraction_service as extraction


# ── SDK surface ───────────────────────────────────────────────────────────────

def test_installed_sdk_accepts_every_parameter_the_code_sends():
    """
    `output_config` is not in older anthropic releases. If the installed SDK
    lacks it, every extraction fails with TypeError at runtime — so the
    requirements floor and the code must agree.
    """
    import inspect

    import anthropic

    params = set(inspect.signature(anthropic.Anthropic(api_key="x").messages.create).parameters)
    for required in ("model", "max_tokens", "system", "messages", "output_config"):
        assert required in params, (
            f"anthropic {anthropic.__version__} does not accept '{required}'; "
            f"raise the floor in requirements.txt"
        )


def test_requirements_floor_is_not_below_the_verified_version():
    from pathlib import Path

    text = Path(__file__).resolve().parents[1].joinpath("requirements.txt").read_text()
    line = next(l for l in text.splitlines() if l.strip().startswith("anthropic"))
    assert ">=0.109.1" in line or "==" in line, (
        "the anthropic pin must not allow a release without output_config support"
    )


# ── Output schema ─────────────────────────────────────────────────────────────

def test_output_schema_is_a_closed_object_with_everything_required():
    schema = extraction._OUTPUT_SCHEMA
    json.dumps(schema)                                  # must be serialisable
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == set(schema["required"])


def test_schema_field_enum_matches_the_allowed_field_set():
    """
    The model is told which field names exist via the schema enum, and
    `_normalise` discards anything outside COMMON_FIELDS. If the two drift,
    the model is invited to return names that are then silently dropped.
    """
    enum_names = set(
        extraction._OUTPUT_SCHEMA["properties"]["fields"]["items"]["properties"]["name"]["enum"]
    )
    assert enum_names == set(COMMON_FIELDS)


# ── Content blocks ────────────────────────────────────────────────────────────

def _capture_blocks(monkeypatch, file_bytes: bytes, mime: str) -> list[dict]:
    captured: dict = {}

    def capture(content_blocks, mode):
        captured["blocks"] = content_blocks
        raise RuntimeError("captured")

    monkeypatch.setattr(extraction, "_call_model", capture)
    monkeypatch.setattr(extraction, "ai_available", lambda: True)
    with pytest.raises(RuntimeError):
        extraction._extract_vision(file_bytes, mime)
    return captured["blocks"]


def test_a_pdf_is_sent_as_a_base64_document_block(monkeypatch):
    raw = b"%PDF-1.4\n" + b"0" * 512
    blocks = _capture_blocks(monkeypatch, raw, "application/pdf")

    doc = next(b for b in blocks if b["type"] == "document")
    assert doc["source"]["type"] == "base64"
    assert doc["source"]["media_type"] == "application/pdf"
    assert base64.standard_b64decode(doc["source"]["data"]) == raw
    # The API rejects base64 containing newlines.
    assert "\n" not in doc["source"]["data"]
    # The instruction must accompany the document.
    assert any(b["type"] == "text" for b in blocks)


@pytest.mark.parametrize("mime", ["image/jpeg", "image/png", "image/gif", "image/webp"])
def test_supported_images_are_sent_as_image_blocks(monkeypatch, mime):
    blocks = _capture_blocks(monkeypatch, b"\xff\xd8\xff" + b"0" * 64, mime)
    img = next(b for b in blocks if b["type"] == "image")
    assert img["source"]["media_type"] == mime


@pytest.mark.parametrize("mime", ["image/heic", "image/heif", "application/msword", ""])
def test_unsupported_types_are_refused_before_any_request(monkeypatch, mime):
    """The provider cannot read these, so no request is made at all."""
    monkeypatch.setattr(extraction, "ai_available", lambda: True)
    monkeypatch.setattr(
        extraction, "_call_model",
        lambda *a, **k: pytest.fail("a request was sent for an unsupported type"),
    )
    with pytest.raises(extraction.ExtractionUnavailable):
        extraction._extract_vision(b"x", mime)


# ── Documented provider limits ────────────────────────────────────────────────

def test_the_upload_cap_cannot_exceed_the_providers_request_limit():
    """
    base64 inflates a file by 4/3 and the provider caps a request at 32 MB.
    An upload cap above that produces files that are accepted and then always
    fail at the provider.
    """
    encoded = settings.AI_IMPORT_MAX_UPLOAD_MB * 1024 * 1024 * 4 / 3
    assert encoded + extraction._REQUEST_OVERHEAD_BYTES <= extraction._API_REQUEST_LIMIT_BYTES, (
        f"AI_IMPORT_MAX_UPLOAD_MB={settings.AI_IMPORT_MAX_UPLOAD_MB} encodes to "
        f"{encoded / 1024 / 1024:.1f} MB, over the provider's 32 MB request limit"
    )


def test_an_oversized_file_is_refused_locally(monkeypatch):
    monkeypatch.setattr(extraction, "ai_available", lambda: True)
    monkeypatch.setattr(
        extraction, "_call_model",
        lambda *a, **k: pytest.fail("an oversized request was sent"),
    )
    oversized = b"0" * (extraction._MAX_VISION_BYTES + 1)
    with pytest.raises(extraction.ExtractionUnavailable) as exc:
        extraction._extract_vision(oversized, "application/pdf")
    assert "exceeds" in str(exc.value)


def test_a_pdf_over_the_page_limit_is_refused_locally(monkeypatch):
    monkeypatch.setattr(extraction, "ai_available", lambda: True)
    monkeypatch.setattr(extraction, "_pdf_page_count", lambda _: extraction._MAX_PDF_PAGES + 1)
    monkeypatch.setattr(
        extraction, "_call_model",
        lambda *a, **k: pytest.fail("a too-long PDF was sent"),
    )
    with pytest.raises(extraction.ExtractionUnavailable) as exc:
        extraction._extract_vision(b"%PDF-1.4", "application/pdf")
    assert "pages" in str(exc.value)


def test_a_pdf_within_the_page_limit_is_sent(monkeypatch):
    """The guard must not block ordinary documents."""
    monkeypatch.setattr(extraction, "_pdf_page_count", lambda _: 12)
    blocks = _capture_blocks(monkeypatch, b"%PDF-1.4", "application/pdf")
    assert any(b["type"] == "document" for b in blocks)


def test_an_unreadable_page_count_does_not_block_the_document(monkeypatch):
    """A page count we cannot determine is not evidence the document is too long."""
    monkeypatch.setattr(extraction, "_pdf_page_count", lambda _: None)
    blocks = _capture_blocks(monkeypatch, b"%PDF-1.4", "application/pdf")
    assert any(b["type"] == "document" for b in blocks)


# ── Response handling ─────────────────────────────────────────────────────────

class _FakeUsage:
    input_tokens = 1000
    output_tokens = 500


class _FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeResponse:
    def __init__(self, stop_reason, text='{"document_type":"UNKNOWN"}'):
        self.stop_reason = stop_reason
        self.content = [_FakeBlock(text)]
        self.usage = _FakeUsage()


def _patch_client(monkeypatch, response):
    class _Messages:
        @staticmethod
        def create(**kwargs):
            _patch_client.last_kwargs = kwargs
            return response

    class _Client:
        messages = _Messages()

    monkeypatch.setattr(extraction, "_anthropic_client", lambda: _Client())


def test_hitting_the_output_cap_is_reported_as_such(monkeypatch):
    """
    A truncated response must not be reported as a generic parse failure.
    Thinking shares the output budget on current models, so this is reachable
    on a long document.
    """
    _patch_client(monkeypatch, _FakeResponse("max_tokens", '{"document_type": "SUPP'))
    with pytest.raises(extraction.ExtractionUnavailable) as exc:
        extraction._call_model([{"type": "text", "text": "x"}], mode="text")
    message = str(exc.value)
    assert "output limit" in message
    assert str(extraction.max_output_tokens()) in message


def test_a_refusal_is_reported_as_a_refusal(monkeypatch):
    _patch_client(monkeypatch, _FakeResponse("refusal"))
    with pytest.raises(extraction.ExtractionUnavailable) as exc:
        extraction._call_model([{"type": "text", "text": "x"}], mode="text")
    assert "declined" in str(exc.value)


def test_a_normal_response_records_usage_and_cost(monkeypatch):
    _patch_client(monkeypatch, _FakeResponse("end_turn"))
    payload = extraction._call_model([{"type": "text", "text": "x"}], mode="text")

    assert payload.input_tokens == 1000
    assert payload.output_tokens == 500
    expected = extraction._cost_usd(extraction.ai_model(), 1000, 500)
    assert payload.cost_usd == expected
    assert payload.duration_ms is not None


def test_the_output_token_budget_is_configurable(monkeypatch):
    monkeypatch.setattr(settings, "AI_IMPORT_MAX_OUTPUT_TOKENS", 4321)
    assert extraction.max_output_tokens() == 4321

    _patch_client(monkeypatch, _FakeResponse("end_turn"))
    extraction._call_model([{"type": "text", "text": "x"}], mode="text")
    assert _patch_client.last_kwargs["max_tokens"] == 4321


def test_the_request_carries_the_structured_output_schema(monkeypatch):
    _patch_client(monkeypatch, _FakeResponse("end_turn"))
    extraction._call_model([{"type": "text", "text": "x"}], mode="text")

    sent = _patch_client.last_kwargs
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert sent["output_config"]["format"]["schema"] is extraction._OUTPUT_SCHEMA
    assert sent["model"] == extraction.ai_model()
    assert sent["system"] is extraction._SYSTEM_PROMPT


# ── Credentials ───────────────────────────────────────────────────────────────

def test_no_api_key_literal_appears_in_the_source():
    from pathlib import Path

    for name in ("ai_import_extraction_service.py", "ai_import_service.py"):
        src = Path(__file__).resolve().parents[1].joinpath("app/services", name).read_text()
        assert "sk-ant" not in src


def test_the_key_is_read_from_settings_not_the_environment_directly(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    assert extraction.ai_available() is False
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "configured")
    assert extraction.ai_available() is True
