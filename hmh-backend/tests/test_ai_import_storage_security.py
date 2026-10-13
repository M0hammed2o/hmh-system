"""
AI Document Import — upload, storage and retention hardening.

Covers what happens to a document's bytes: whether a file is what it claims
to be, whether a scanner can refuse it, where it is stored, who can reach it,
and when it is removed.

The Supabase code paths are exercised with the storage layer stubbed —
no live bucket is contacted.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core import upload_scanning
from app.core.config import settings
from app.core.upload_scanning import ScanResult, UnsafeUpload, verify_declared_type
from app.models.enums import AIImportDocumentStatus, AIImportDocumentType
from app.services import ai_import_posting_service as posting
from app.services import ai_import_service
from tests.conftest import (
    auth, login, make_item, make_project, make_site, make_supplier, make_user,
)
from tests.ai_import_fixtures import make_import_document, supplier_invoice
from tests.test_ai_import_posting import _payload

PDF = b"%PDF-1.4\n" + b"0" * 256
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 256
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 256


def _user_obj(db, role="OFFICE_ADMIN"):
    from app.models.user import User
    row = make_user(db, role=role)
    return db.get(User, uuid.UUID(row["id"])), row


# ── Content verification ──────────────────────────────────────────────────────

@pytest.mark.parametrize("content,mime", [
    (PDF, "application/pdf"),
    (PNG, "image/png"),
    (JPEG, "image/jpeg"),
    (b"GIF89a" + b"0" * 64, "image/gif"),
    (b"RIFF" + b"\x00" * 4 + b"WEBP" + b"0" * 64, "image/webp"),
])
def test_a_genuine_file_is_accepted(content, mime):
    verify_declared_type(content, mime, "document")


def test_an_executable_renamed_as_a_pdf_is_refused():
    """
    The existing MIME and extension checks are both client-supplied. This is
    what actually stops a renamed binary.
    """
    with pytest.raises(UnsafeUpload) as exc:
        verify_declared_type(b"MZ\x90\x00" + b"0" * 256, "application/pdf", "invoice.pdf")
    assert "executable" in str(exc.value)


@pytest.mark.parametrize("content,label", [
    (b"\x7fELF" + b"0" * 64, "Linux executable"),
    (b"PK\x03\x04" + b"0" * 64, "ZIP archive"),
    (b"#!/bin/sh\nrm -rf /", "script"),
    (b"\x1f\x8b" + b"0" * 64, "gzip"),
])
def test_forbidden_formats_are_refused_whatever_they_claim(content, label):
    with pytest.raises(UnsafeUpload):
        verify_declared_type(content, "application/pdf", "thing.pdf")


def test_a_png_claiming_to_be_a_pdf_is_refused():
    with pytest.raises(UnsafeUpload) as exc:
        verify_declared_type(PNG, "application/pdf", "scan.pdf")
    assert "does not look like" in str(exc.value)


def test_an_empty_file_is_refused():
    with pytest.raises(UnsafeUpload):
        verify_declared_type(b"", "application/pdf", "empty.pdf")


def test_verification_runs_on_the_real_upload_path(db, client):
    """A renamed binary must be rejected by the endpoint, not merely by the helper."""
    owner, owner_row = _user_obj(db, role="OWNER")
    db.commit()
    token = login(client, owner_row["email"], owner_row["password"])
    batch_id = client.post(
        "/api/v1/ai-import/batches", json={}, headers=auth(token),
    ).json()["data"]["id"]

    response = client.post(
        f"/api/v1/ai-import/batches/{batch_id}/documents",
        files=[("files", ("invoice.pdf", b"MZ\x90\x00" + b"0" * 128, "application/pdf"))],
        headers=auth(token),
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["accepted"] == []
    assert len(data["rejected"]) == 1
    assert "executable" in data["rejected"][0]["reason"]


# ── Malware scanning ──────────────────────────────────────────────────────────

def test_no_scanner_configured_means_no_scan_and_no_block(monkeypatch):
    monkeypatch.setattr(settings, "AI_IMPORT_SCAN_ENABLED", False)
    result = upload_scanning.scan_for_malware(PDF, "x.pdf")
    assert result.scanned is False and result.infected is False


def test_a_clean_verdict_is_accepted(monkeypatch):
    monkeypatch.setattr(settings, "AI_IMPORT_SCAN_ENABLED", True)
    monkeypatch.setattr(settings, "AI_IMPORT_SCAN_URL", "http://scanner.invalid/scan")

    class _Response:
        content = b"{}"
        @staticmethod
        def raise_for_status(): ...
        @staticmethod
        def json(): return {"infected": False, "status": "clean"}

    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Response())

    result = upload_scanning.scan_for_malware(PDF, "x.pdf")
    assert result.scanned is True and result.infected is False


def test_an_infected_verdict_refuses_the_upload(monkeypatch):
    monkeypatch.setattr(settings, "AI_IMPORT_SCAN_ENABLED", True)
    monkeypatch.setattr(settings, "AI_IMPORT_SCAN_URL", "http://scanner.invalid/scan")

    class _Response:
        content = b"{}"
        @staticmethod
        def raise_for_status(): ...
        @staticmethod
        def json(): return {"infected": True, "virus": "Eicar-Test-Signature"}

    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Response())

    with pytest.raises(UnsafeUpload) as exc:
        upload_scanning.scan_for_malware(PDF, "payload.pdf")
    assert "Eicar-Test-Signature" in str(exc.value)


def test_an_unreachable_scanner_refuses_the_upload_by_default(monkeypatch):
    """An unavailable scanner is not evidence that a file is clean."""
    monkeypatch.setattr(settings, "AI_IMPORT_SCAN_ENABLED", True)
    monkeypatch.setattr(settings, "AI_IMPORT_SCAN_URL", "http://scanner.invalid/scan")
    monkeypatch.setattr(settings, "AI_IMPORT_SCAN_FAIL_OPEN", False)

    import httpx
    def boom(*a, **k):
        raise httpx.ConnectError("no route to host")
    monkeypatch.setattr(httpx, "post", boom)

    with pytest.raises(UnsafeUpload) as exc:
        upload_scanning.scan_for_malware(PDF, "x.pdf")
    assert "could not be virus-scanned" in str(exc.value)


def test_fail_open_is_available_but_must_be_chosen(monkeypatch):
    monkeypatch.setattr(settings, "AI_IMPORT_SCAN_ENABLED", True)
    monkeypatch.setattr(settings, "AI_IMPORT_SCAN_URL", "http://scanner.invalid/scan")
    monkeypatch.setattr(settings, "AI_IMPORT_SCAN_FAIL_OPEN", True)

    import httpx
    def boom(*a, **k):
        raise httpx.ConnectError("no route to host")
    monkeypatch.setattr(httpx, "post", boom)

    result = upload_scanning.scan_for_malware(PDF, "x.pdf")
    assert result.scanned is False
    assert "fail-open" in (result.detail or "")


# ── Storage paths ─────────────────────────────────────────────────────────────

def test_stored_paths_are_scoped_to_their_batch_and_cannot_traverse(db, monkeypatch):
    """
    The stored path is built from the batch id and a fresh uuid, so one
    batch's upload cannot be written into another's area, and a hostile
    filename cannot climb out of the prefix.
    """
    captured: list[str] = []

    def fake_save(content, relative_path, private=False):
        captured.append(relative_path)
        assert private is True, "import documents must be stored privately"
        return f"supabase://{relative_path}"

    monkeypatch.setattr(ai_import_service, "save_upload", fake_save)

    actor, actor_row = _user_obj(db)
    batch = ai_import_service.create_batch(db, uuid.UUID(actor_row["id"]))

    class _Upload:
        filename = "../../../etc/passwd.pdf"
        content_type = "application/pdf"

        def __init__(self):
            import io as _io
            self.file = _io.BytesIO(PDF)

    ai_import_service.upload_document(db, batch, _Upload(), uuid.UUID(actor_row["id"]))

    path = captured[0]
    assert path.startswith(f"ai_import/{batch.id}/")
    assert ".." not in path
    assert "/etc/" not in path


def test_the_file_route_issues_a_signed_url_and_logs_the_access(db, client, monkeypatch):
    from app.models.audit import AuditEvent

    owner, owner_row = _user_obj(db, role="OWNER")
    project = make_project(db, owner_row["id"])
    document = make_import_document(
        db, uploaded_by=owner_row["id"], project_id=project["id"],
    )
    db.commit()

    monkeypatch.setattr(
        ai_import_service, "create_signed_url",
        lambda path, expires_in=None: f"https://storage.invalid/{path}?token=abc&expires={expires_in}",
    )

    token = login(client, owner_row["email"], owner_row["password"])
    response = client.get(
        f"/api/v1/ai-import/documents/{document.id}/file", headers=auth(token),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert "token=" in data["url"], "the URL must be signed, not a bare bucket path"
    assert data["expires_in_seconds"] == settings.EVIDENCE_SIGNED_URL_EXPIRY_SECONDS

    event = (
        db.query(AuditEvent)
        .filter(AuditEvent.entity_type == "ai_import_document_file",
                AuditEvent.entity_id == document.id)
        .first()
    )
    assert event is not None and event.action == "ACCESS"


def test_a_storage_failure_is_reported_not_swallowed(db, client, monkeypatch):
    owner, owner_row = _user_obj(db, role="OWNER")
    project = make_project(db, owner_row["id"])
    document = make_import_document(
        db, uploaded_by=owner_row["id"], project_id=project["id"],
    )
    db.commit()

    def boom(path, expires_in=None):
        raise RuntimeError("bucket unreachable")

    monkeypatch.setattr(ai_import_service, "create_signed_url", boom)

    token = login(client, owner_row["email"], owner_row["password"])
    response = client.get(
        f"/api/v1/ai-import/documents/{document.id}/file", headers=auth(token),
    )
    assert response.status_code == 503
    assert "could not be retrieved" in response.json()["detail"]


# ── Retention ─────────────────────────────────────────────────────────────────

def _age(db, document, days):
    document.created_at = datetime.now(timezone.utc) - timedelta(days=days)
    db.flush()


def test_retention_removes_the_file_but_keeps_the_record(db, monkeypatch):
    deleted: list[str] = []
    monkeypatch.setattr(
        "app.core.storage.delete_upload", lambda path: deleted.append(path) or True,
    )

    actor, actor_row = _user_obj(db)
    project = make_project(db, actor_row["id"])
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"],
    )
    original_path = document.stored_path
    _age(db, document, settings.AI_IMPORT_RETENTION_DAYS + 1)

    result = ai_import_service.purge_expired_documents(db, dry_run=False)

    assert str(document.id) in result["purged"]
    assert deleted == [original_path]
    # The row, its history and its audit trail survive.
    db.refresh(document)
    assert document.stored_path == ""
    assert "retention policy" in document.failure_reason


def test_retention_leaves_a_recent_document_alone(db):
    actor, actor_row = _user_obj(db)
    project = make_project(db, actor_row["id"])
    document = make_import_document(
        db, uploaded_by=actor_row["id"], project_id=project["id"],
    )
    result = ai_import_service.purge_expired_documents(db, dry_run=True)
    assert str(document.id) not in result["purged"]


def test_the_retention_cron_endpoint_is_guarded_and_defaults_to_a_dry_run(db, client, monkeypatch):
    monkeypatch.setattr(settings, "CRON_SECRET", "")
    assert client.post("/api/v1/internal/ai-import-retention").status_code == 404

    monkeypatch.setattr(settings, "CRON_SECRET", "the-secret")
    assert client.post(
        "/api/v1/internal/ai-import-retention",
        headers={"X-Cron-Secret": "wrong"},
    ).status_code == 403

    import app.db.session as _session_module

    class _Borrowed:
        def __init__(self, inner): self._inner = inner
        def __getattr__(self, name): return getattr(self._inner, name)
        def close(self): pass

    monkeypatch.setattr(_session_module, "SessionLocal", lambda: _Borrowed(db))

    response = client.post(
        "/api/v1/internal/ai-import-retention",
        headers={"X-Cron-Secret": "the-secret"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True, "the schedule must not delete unless asked"
    assert "retention_days" in body
