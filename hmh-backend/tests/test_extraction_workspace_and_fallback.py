"""
Extraction: workspace-scoped keys, and what happens when vision cannot run.

A production upload reached storage correctly and then read nothing. The
provider had refused every request — the API key belonged to the
organisation rather than a workspace — and because the stored file lives in
Supabase rather than on disk, the OCR and deterministic strategies could not
even be attempted. Vision was the only option, so one refusal meant total
failure, reported to the operator as if the scan were at fault.

Three properties follow, and these tests hold them:

  * a key that needs a workspace gets one, and a key that does not is left
    alone;
  * a remote file is staged on disk so every strategy can read it, and the
    staged copy never outlives the request;
  * an extraction that read nothing is recorded as a failure that names the
    cause, not as an ordinary document awaiting review.
"""

import os
import uuid

import pytest

from app.core.config import settings
from app.services import ai_import_extraction_service as extraction
from app.services import ai_import_service


# ── The workspace header ─────────────────────────────────────────────────────

@pytest.fixture()
def workspace(monkeypatch):
    def _set(value):
        monkeypatch.setattr(settings, "ANTHROPIC_WORKSPACE_ID", value, raising=False)
    return _set


def test_no_header_when_the_key_already_belongs_to_a_workspace(workspace):
    """A workspace-scoped key carries its own context; an empty header would be wrong."""
    workspace("")
    assert extraction.workspace_headers() == {}


def test_the_header_is_sent_when_a_workspace_is_configured(workspace):
    workspace("wrkspc_01ABCDEF")
    assert extraction.workspace_headers() == {"anthropic-workspace-id": "wrkspc_01ABCDEF"}


def test_surrounding_whitespace_is_trimmed(workspace):
    """A value pasted from a dashboard often arrives padded."""
    workspace("   wrkspc_01ABCDEF \n")
    assert extraction.workspace_headers() == {"anthropic-workspace-id": "wrkspc_01ABCDEF"}


def test_whitespace_only_counts_as_unset(workspace):
    workspace("   ")
    assert extraction.workspace_headers() == {}


def test_the_client_is_built_with_the_header(workspace, monkeypatch):
    """The header has to reach the SDK, not merely be computable."""
    workspace("wrkspc_01ABCDEF")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-not-a-real-key", raising=False)

    captured = {}

    class FakeAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)

    extraction._anthropic_client()
    assert captured["default_headers"] == {"anthropic-workspace-id": "wrkspc_01ABCDEF"}


def test_the_client_sends_no_header_when_unset(workspace, monkeypatch):
    workspace("")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-not-a-real-key", raising=False)

    captured = {}

    class FakeAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)

    extraction._anthropic_client()
    assert captured["default_headers"] is None


def test_the_workspace_id_is_never_a_credential(workspace):
    """
    It identifies a workspace; it authorises nothing. Worth stating, because
    it travels in a header beside the key and must not be treated as secret
    in logs — while the key always must.
    """
    workspace("wrkspc_01ABCDEF")
    assert "sk-ant" not in str(extraction.workspace_headers())


# ── Staging a remote file so every strategy can read it ──────────────────────

def _pdf_bytes() -> bytes:
    """A small PDF carrying real, extractable text."""
    from io import BytesIO

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica", 12)
    c.drawString(60, 760, "DELIVERY NOTE")
    c.drawString(60, 735, "Delivery note no.: ZZTEST-DN-0001")
    c.drawString(60, 710, "Date: 2026-10-21")
    c.drawString(60, 685, "Supplier: ZZ TEST SUPPLIES CC")
    c.drawString(60, 660, "Order reference: ZZTEST-PO-0001")
    c.showPage()
    c.save()
    return buf.getvalue()


def test_a_remote_file_is_staged_on_disk():
    path = ai_import_service._stage_temp_copy(_pdf_bytes(), "delivery-note.pdf")
    try:
        assert path, "no temporary copy was staged"
        assert os.path.isfile(path)
        assert path.endswith(".pdf"), "the extension is needed by the parser strategies"
        with open(path, "rb") as fh:
            assert fh.read(4) == b"%PDF"
    finally:
        ai_import_service.discard_local_copy(path)


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows does not carry POSIX mode bits; production runs on Linux, "
           "where mkstemp creates the file 0600. Asserted there.",
)
def test_the_staged_copy_is_not_world_readable():
    """Evidence can be commercially sensitive and shares a temp directory."""
    path = ai_import_service._stage_temp_copy(_pdf_bytes(), "delivery-note.pdf")
    try:
        mode = os.stat(path).st_mode
        assert not (mode & 0o077), f"staged copy is readable by others: {oct(mode)}"
    finally:
        ai_import_service.discard_local_copy(path)


def test_the_staged_copy_is_removed():
    path = ai_import_service._stage_temp_copy(_pdf_bytes(), "delivery-note.pdf")
    ai_import_service.discard_local_copy(path)
    assert not os.path.exists(path)


def test_discarding_is_safe_to_repeat():
    path = ai_import_service._stage_temp_copy(_pdf_bytes(), "x.pdf")
    ai_import_service.discard_local_copy(path)
    ai_import_service.discard_local_copy(path)          # must not raise
    ai_import_service.discard_local_copy(None)


def test_a_stored_document_is_never_deleted_as_if_it_were_temporary(tmp_path):
    """
    The same helper runs whether the file was staged or was already on the
    upload disk. Only what this module staged may be removed.
    """
    kept = tmp_path / "real-evidence.pdf"
    kept.write_bytes(_pdf_bytes())

    ai_import_service.discard_local_copy(str(kept))
    assert kept.exists(), "a stored document was deleted as though it were temporary"


# ── Fallback extraction actually runs, with no provider at all ──────────────

def test_a_pdf_is_parsed_without_any_ai_provider(monkeypatch):
    """
    The property that was missing in production: when vision cannot run, the
    deterministic strategies still read the file — provided they are given a
    path, which staging now guarantees.
    """
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "", raising=False)

    content = _pdf_bytes()
    path = ai_import_service._stage_temp_copy(content, "delivery-note.pdf")
    try:
        payload = extraction.analyse_document(
            file_bytes=content,
            mime_type="application/pdf",
            file_path=path,
            file_name="delivery-note.pdf",
        )
    finally:
        ai_import_service.discard_local_copy(path)

    assert payload.extraction_mode != "none", (
        "no strategy ran even with a readable file: " + "; ".join(payload.warnings or [])
    )


def test_without_a_path_there_is_no_fallback_at_all(monkeypatch):
    """
    Pins the production failure itself. Bytes alone leave vision as the only
    option — which is exactly why the download is now staged on disk.
    """
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "", raising=False)

    payload = extraction.analyse_document(
        file_bytes=_pdf_bytes(),
        mime_type="application/pdf",
        file_path=None,
        file_name="delivery-note.pdf",
    )
    assert payload.extraction_mode == "none"


# ── An empty extraction is a failure, and says why ──────────────────────────

def test_a_provider_refusal_is_reported_as_configuration_not_a_bad_scan():
    class Payload:
        warnings = [
            "vision failed: Error code: 400 - {'type': 'error', 'error': "
            "{'message': 'This API key is not scoped to a workspace'}}",
            "text mode unavailable: no text could be read from the file.",
        ]

    reason = ai_import_service._extraction_failure_reason(Payload())
    assert "not scoped to a workspace" in reason
    assert "configuration" in reason.lower()


def test_an_unreadable_file_is_not_blamed_on_the_provider():
    class Payload:
        warnings = ["text mode unavailable: no text could be read from the file."]

    reason = ai_import_service._extraction_failure_reason(Payload())
    assert "provider refused" not in reason.lower()


def test_a_silent_failure_still_produces_a_usable_message():
    class Payload:
        warnings = []

    reason = ai_import_service._extraction_failure_reason(Payload())
    assert reason.strip()
    assert "by hand" in reason or "manual" in reason.lower()


def test_an_empty_extraction_marks_the_document_failed(db, monkeypatch):
    """
    Previously this went to AWAITING_REVIEW, which reads as "a person should
    check the scan" when in fact nothing had been read and nothing could be.
    """
    from app.models.ai_import import AIImportBatch, AIImportDocument
    from app.models.enums import AIImportDocumentStatus, AIImportDocumentType
    from app.services.ai_import_extraction_service import DocumentExtractionPayload
    from tests.conftest import make_user

    owner = make_user(db, role="OWNER")
    batch = AIImportBatch(reference=f"T-{uuid.uuid4().hex[:6]}", uploaded_by=uuid.UUID(owner["id"]))
    db.add(batch)
    db.flush()
    doc = AIImportDocument(
        batch_id=batch.id, file_name="unreadable.pdf",
        stored_path="supabase://ai_import/x/unreadable.pdf",
        mime_type="application/pdf", file_size_bytes=100,
        checksum_sha256=uuid.uuid4().hex * 2,
        status=AIImportDocumentStatus.QUEUED,
        document_type=AIImportDocumentType.UNKNOWN,
        uploaded_by=uuid.UUID(owner["id"]),
    )
    db.add(doc)
    db.commit()

    empty = DocumentExtractionPayload(provider="none", extraction_mode="none")
    empty.warnings = ["vision failed: Error code: 400 - not scoped to a workspace"]

    monkeypatch.setattr(ai_import_service, "_local_copy", lambda d: ("/tmp/none", b"%PDF-1.4"))
    monkeypatch.setattr(ai_import_service, "discard_local_copy", lambda p: None)
    monkeypatch.setattr(
        ai_import_service.extraction, "analyse_document", lambda **kw: empty)

    result = ai_import_service.process_document(db, doc)

    assert result.status == AIImportDocumentStatus.FAILED, (
        f"an unreadable document was left as {result.status}")
    assert "not scoped to a workspace" in (result.failure_reason or "")


def test_the_temporary_copy_is_removed_even_when_extraction_raises(db, monkeypatch):
    """A provider outage must not leave evidence behind in a temp directory."""
    from app.models.ai_import import AIImportBatch, AIImportDocument
    from app.models.enums import AIImportDocumentStatus, AIImportDocumentType
    from tests.conftest import make_user

    owner = make_user(db, role="OWNER")
    batch = AIImportBatch(reference=f"T-{uuid.uuid4().hex[:6]}", uploaded_by=uuid.UUID(owner["id"]))
    db.add(batch)
    db.flush()
    doc = AIImportDocument(
        batch_id=batch.id, file_name="boom.pdf",
        stored_path="supabase://ai_import/x/boom.pdf",
        mime_type="application/pdf", file_size_bytes=100,
        checksum_sha256=uuid.uuid4().hex * 2,
        status=AIImportDocumentStatus.QUEUED,
        document_type=AIImportDocumentType.UNKNOWN,
        uploaded_by=uuid.UUID(owner["id"]),
    )
    db.add(doc)
    db.commit()

    staged = ai_import_service._stage_temp_copy(_pdf_bytes(), "boom.pdf")
    monkeypatch.setattr(ai_import_service, "_local_copy", lambda d: (staged, b"%PDF-1.4"))

    def explode(**kwargs):
        raise extraction.ExtractionTransientError("provider down")

    monkeypatch.setattr(ai_import_service.extraction, "analyse_document", explode)

    with pytest.raises(extraction.ExtractionTransientError):
        ai_import_service.process_document(db, doc)

    assert not os.path.exists(staged), "the staged copy outlived a failed extraction"
