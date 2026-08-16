"""
FINAL-2.5G — Attachment API test coverage.

Tests:
  - single upload with caption
  - multi-upload (all succeed, each in sequence)
  - partial batch: one invalid MIME rejected client-side (server 415)
  - MIME rejection (415)
  - oversize rejection (413)
  - invalid entity_type → 422
  - invalid attachment_type → 422
  - SITE_STAFF can delete their own upload
  - SITE_STAFF cannot delete another user's upload (403)
  - pagination: limit / offset
  - attachment_type filter
  - audit log entry created on upload
  - unauthenticated access → 401
  - STAGE_STATUS project-access isolation
"""

import io
import uuid
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

import httpx

from app.core.exceptions import StorageError
from app.core import storage as storage_module
from app.models.attachment import Attachment
from app.models.enums import AttachmentEntity, AttachmentType
from tests.conftest import (
    auth, login,
    make_user, make_project, make_site, make_supplier,
    make_user_project_access,
)

# ── Shared helpers ─────────────────────────────────────────────────────────────

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"           # PNG signature
    b"\x00\x00\x00\rIHDR"          # IHDR chunk length + type
    b"\x00\x00\x00\x01"            # width  = 1
    b"\x00\x00\x00\x01"            # height = 1
    b"\x08\x02\x00\x00\x00"        # bit depth=8, colour type=2
    b"\x90wS\xde"                  # IHDR CRC
    b"\x00\x00\x00\x0cIDATx\x9c"   # IDAT chunk
    b"c\xf8\x0f\x00\x00\x01\x01"   # zlib-compressed 1×1 pixel
    b"\x00\x05\x18\xd8N"           # IDAT CRC
    b"\x00\x00\x00\x00IEND"        # IEND
    b"\xaeB`\x82"                  # IEND CRC
)
TINY_PDF = b"%PDF-1.0\n1 0 obj<</Type/Catalog>>endobj\nxref\n0 0\ntrailer<<>>\n%%EOF\n"


def _upload_file(
    client,
    token: str,
    entity_type: str,
    entity_id: str,
    content: bytes = TINY_PNG,
    mime: str = "image/png",
    filename: str = "test.png",
    attachment_type: str = "PHOTO",
    caption: str | None = None,
) -> dict:
    """Helper: POST /attachments/upload and return the JSON data dict."""
    files: dict = {
        "file":            (filename, io.BytesIO(content), mime),
        "entity_type":     (None, entity_type),
        "entity_id":       (None, entity_id),
        "attachment_type": (None, attachment_type),
    }
    if caption is not None:
        files["caption"] = (None, caption)
    r = client.post("/api/v1/attachments/upload", files=files, headers=auth(token))
    return r


# ── Upload tests ───────────────────────────────────────────────────────────────

def test_single_upload_with_caption(db, client):
    """Upload a PNG with a caption; verify all fields are returned correctly."""
    user     = make_user(db, role="OFFICE_USER")
    token    = login(client, user["email"], user["password"])
    supplier = make_supplier(db)

    r = _upload_file(
        client, token,
        entity_type="SUPPLIER", entity_id=supplier["id"],
        caption="Before works started",
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["entity_type"] == "SUPPLIER"
    assert data["attachment_type"] == "PHOTO"
    assert data["caption"] == "Before works started"
    assert data["is_image"] is True
    assert data["is_active"] is True
    assert data["uploaded_role"] == "OFFICE_USER"
    assert data["download_url"].startswith("/api/v1/attachments/") or data["download_url"].startswith("http")


def test_upload_sets_uploaded_role(db, client):
    """uploaded_role must reflect the uploader's role."""
    user  = make_user(db, role="SITE_MANAGER")
    token = login(client, user["email"], user["password"])
    sup   = make_supplier(db)

    r = _upload_file(client, token, "SUPPLIER", sup["id"])
    assert r.status_code == 201, r.text
    assert r.json()["data"]["uploaded_role"] == "SITE_MANAGER"


def test_multi_upload_all_succeed(db, client):
    """Upload three files in separate calls; all should appear in list."""
    user  = make_user(db, role="OFFICE_ADMIN")
    token = login(client, user["email"], user["password"])
    sup   = make_supplier(db)

    for i in range(3):
        r = _upload_file(
            client, token, "SUPPLIER", sup["id"],
            filename=f"photo_{i}.png", caption=f"Photo {i}"
        )
        assert r.status_code == 201, r.text

    r_list = client.get(
        "/api/v1/attachments/",
        params={"entity_type": "SUPPLIER", "entity_id": sup["id"]},
        headers=auth(token),
    )
    assert r_list.status_code == 200
    data = r_list.json()["data"]
    assert len(data) >= 3


def test_upload_pdf_attachment(db, client):
    """PDF uploads should succeed and is_image should be False."""
    user  = make_user(db, role="OFFICE_USER")
    token = login(client, user["email"], user["password"])
    sup   = make_supplier(db)

    r = _upload_file(
        client, token, "SUPPLIER", sup["id"],
        content=TINY_PDF, mime="application/pdf", filename="doc.pdf",
        attachment_type="PDF",
    )
    assert r.status_code == 201, r.text
    d = r.json()["data"]
    assert d["is_image"] is False
    assert d["attachment_type"] == "PDF"


def test_upload_rejected_invalid_mime(db, client):
    """Executable/script MIME type must be rejected with HTTP 415."""
    user  = make_user(db, role="OFFICE_USER")
    token = login(client, user["email"], user["password"])
    sup   = make_supplier(db)

    r = _upload_file(
        client, token, "SUPPLIER", sup["id"],
        content=b"malicious", mime="application/x-executable", filename="evil.exe",
    )
    assert r.status_code == 415, r.text


def test_upload_rejected_blocked_extension(db, client):
    """Files with blocked extensions must be rejected regardless of MIME."""
    user  = make_user(db, role="OFFICE_USER")
    token = login(client, user["email"], user["password"])
    sup   = make_supplier(db)

    r = _upload_file(
        client, token, "SUPPLIER", sup["id"],
        content=b"@echo off", mime="image/jpeg", filename="malware.bat",
    )
    assert r.status_code == 415, r.text


def test_upload_rejected_oversize(db, client):
    """Files exceeding MAX_UPLOAD_SIZE_MB must be rejected with HTTP 413."""
    user  = make_user(db, role="OFFICE_USER")
    token = login(client, user["email"], user["password"])
    sup   = make_supplier(db)

    big = io.BytesIO(b"A" * (6 * 1024 * 1024))   # 6 MB > 5 MB limit
    files = {
        "file":            ("big.png", big, "image/png"),
        "entity_type":     (None, "SUPPLIER"),
        "entity_id":       (None, sup["id"]),
        "attachment_type": (None, "PHOTO"),
    }
    r = client.post("/api/v1/attachments/upload", files=files, headers=auth(token))
    assert r.status_code == 413, r.text


def test_upload_rejected_invalid_entity_type(db, client):
    """Unknown entity_type must return HTTP 422."""
    user  = make_user(db, role="OFFICE_USER")
    token = login(client, user["email"], user["password"])

    files = {
        "file":            ("x.png", io.BytesIO(TINY_PNG), "image/png"),
        "entity_type":     (None, "TOTALLY_FAKE"),
        "entity_id":       (None, str(uuid.uuid4())),
        "attachment_type": (None, "PHOTO"),
    }
    r = client.post("/api/v1/attachments/upload", files=files, headers=auth(token))
    assert r.status_code == 422, r.text


def test_upload_rejected_invalid_attachment_type(db, client):
    """Unknown attachment_type must return HTTP 422."""
    user  = make_user(db, role="OFFICE_USER")
    token = login(client, user["email"], user["password"])
    sup   = make_supplier(db)

    files = {
        "file":            ("x.png", io.BytesIO(TINY_PNG), "image/png"),
        "entity_type":     (None, "SUPPLIER"),
        "entity_id":       (None, sup["id"]),
        "attachment_type": (None, "NOT_A_REAL_TYPE"),
    }
    r = client.post("/api/v1/attachments/upload", files=files, headers=auth(token))
    assert r.status_code == 422, r.text


def test_upload_unauthenticated(client):
    """Unauthenticated upload must return HTTP 401/403."""
    files = {
        "file":            ("x.png", io.BytesIO(TINY_PNG), "image/png"),
        "entity_type":     (None, "SUPPLIER"),
        "entity_id":       (None, str(uuid.uuid4())),
        "attachment_type": (None, "PHOTO"),
    }
    r = client.post("/api/v1/attachments/upload", files=files)
    assert r.status_code in (401, 403), r.text


# ── List / filter / pagination ────────────────────────────────────────────────

def test_list_with_attachment_type_filter(db, client):
    """attachment_type query param must filter results correctly."""
    user  = make_user(db, role="OFFICE_ADMIN")
    token = login(client, user["email"], user["password"])
    sup   = make_supplier(db)

    # Upload PHOTO and PDF
    _upload_file(client, token, "SUPPLIER", sup["id"], attachment_type="PHOTO")
    _upload_file(
        client, token, "SUPPLIER", sup["id"],
        content=TINY_PDF, mime="application/pdf", filename="doc.pdf",
        attachment_type="PDF",
    )

    r = client.get(
        "/api/v1/attachments/",
        params={"entity_type": "SUPPLIER", "entity_id": sup["id"], "attachment_type": "PDF"},
        headers=auth(token),
    )
    assert r.status_code == 200
    items = r.json()["data"]
    assert all(a["attachment_type"] == "PDF" for a in items)
    assert len(items) >= 1


def test_list_pagination_limit_offset(db, client):
    """limit and offset params should correctly page results."""
    user  = make_user(db, role="OFFICE_ADMIN")
    token = login(client, user["email"], user["password"])
    sup   = make_supplier(db)

    # Create 5 uploads
    for i in range(5):
        _upload_file(client, token, "SUPPLIER", sup["id"], filename=f"p{i}.png")

    def _list(limit=None, offset=0):
        params = {"entity_type": "SUPPLIER", "entity_id": sup["id"], "offset": offset}
        if limit is not None:
            params["limit"] = limit
        return client.get("/api/v1/attachments/", params=params, headers=auth(token)).json()["data"]

    all_items  = _list()
    first_two  = _list(limit=2, offset=0)
    next_two   = _list(limit=2, offset=2)

    assert len(all_items) >= 5
    assert len(first_two) == 2
    assert len(next_two) == 2
    # Ensure no overlap between pages
    first_ids = {a["id"] for a in first_two}
    next_ids  = {a["id"] for a in next_two}
    assert first_ids.isdisjoint(next_ids)


def test_list_unauthenticated(client):
    """Unauthenticated list must return 401/403."""
    r = client.get(
        "/api/v1/attachments/",
        params={"entity_type": "SUPPLIER", "entity_id": str(uuid.uuid4())},
    )
    assert r.status_code in (401, 403), r.text


# ── Delete / permission tests ─────────────────────────────────────────────────

def test_office_user_can_delete_any_attachment(db, client):
    """OFFICE_USER (non-site) can delete any attachment."""
    user  = make_user(db, role="OFFICE_USER")
    token = login(client, user["email"], user["password"])
    sup   = make_supplier(db)

    r = _upload_file(client, token, "SUPPLIER", sup["id"])
    att_id = r.json()["data"]["id"]

    r_del = client.delete(f"/api/v1/attachments/{att_id}", headers=auth(token))
    assert r_del.status_code == 200


def test_site_staff_can_delete_own_upload(db, client):
    """SITE_STAFF can delete attachments they personally uploaded."""
    user  = make_user(db, role="SITE_STAFF")
    token = login(client, user["email"], user["password"])
    proj  = make_project(db, user["id"])
    make_user_project_access(db, user["id"], proj["id"])
    sup   = make_supplier(db)

    r = _upload_file(client, token, "SUPPLIER", sup["id"])
    att_id = r.json()["data"]["id"]

    r_del = client.delete(f"/api/v1/attachments/{att_id}", headers=auth(token))
    assert r_del.status_code == 200


def test_site_staff_cannot_delete_other_users_upload(db, client):
    """SITE_STAFF must receive 403 when trying to delete another user's upload."""
    uploader    = make_user(db, role="OFFICE_ADMIN")
    site_staff  = make_user(db, role="SITE_STAFF")
    token_up    = login(client, uploader["email"],   uploader["password"])
    token_staff = login(client, site_staff["email"], site_staff["password"])
    sup         = make_supplier(db)

    # OFFICE_ADMIN uploads
    r = _upload_file(client, token_up, "SUPPLIER", sup["id"])
    att_id = r.json()["data"]["id"]

    # SITE_STAFF tries to delete it
    r_del = client.delete(f"/api/v1/attachments/{att_id}", headers=auth(token_staff))
    assert r_del.status_code == 403, r_del.text
    assert "own" in r_del.json()["detail"].lower()


def test_delete_nonexistent_attachment(db, client):
    """Deleting a non-existent attachment should return 404."""
    user  = make_user(db, role="OFFICE_ADMIN")
    token = login(client, user["email"], user["password"])

    r = client.delete(f"/api/v1/attachments/{uuid.uuid4()}", headers=auth(token))
    assert r.status_code == 404


def test_delete_is_soft(db, client):
    """After delete, the attachment should not appear in subsequent list results."""
    user  = make_user(db, role="OFFICE_ADMIN")
    token = login(client, user["email"], user["password"])
    sup   = make_supplier(db)

    r = _upload_file(client, token, "SUPPLIER", sup["id"])
    att_id = r.json()["data"]["id"]

    client.delete(f"/api/v1/attachments/{att_id}", headers=auth(token))

    r_list = client.get(
        "/api/v1/attachments/",
        params={"entity_type": "SUPPLIER", "entity_id": sup["id"]},
        headers=auth(token),
    )
    ids = [a["id"] for a in r_list.json()["data"]]
    assert att_id not in ids


# ── Audit log ────────────────────────────────────────────────────────────────

def test_upload_creates_audit_event(db, client):
    """Every upload must create an audit_events record with action=UPLOAD."""
    from app.models.audit import AuditEvent

    user  = make_user(db, role="OFFICE_USER")
    token = login(client, user["email"], user["password"])
    sup   = make_supplier(db)

    r = _upload_file(client, token, "SUPPLIER", sup["id"])
    att_id = r.json()["data"]["id"]

    event = (
        db.query(AuditEvent)
        .filter(AuditEvent.entity_id == uuid.UUID(att_id))
        .first()
    )
    assert event is not None, "Audit event must be created on upload"
    assert event.action == "UPLOAD"


# ── STAGE_STATUS project isolation ───────────────────────────────────────────

def test_stage_status_attachment_requires_project_access(db, client):
    """Listing STAGE_STATUS attachments must require project membership.

    The outsider must be a SITE-level role (SITE_STAFF/SITE_MANAGER/...).
    Office-level roles (OWNER, OFFICE_ADMIN, OFFICE_USER, PROCUREMENT_LEAD,
    READ_ONLY) are intentionally company-wide across the whole app —
    check_project_access() bypasses the project check for them by design
    (see app/dependencies.py:_PROJECT_ACCESS_BYPASS), consistently for every
    project-scoped resource, not just attachments. Using an office role here
    previously made this test fail even though STAGE_STATUS -> project_id
    resolution (_entity_project_id) and the underlying check were both
    correct — confirmed by cross-checking a SITE_STAFF outsider, who is
    correctly blocked. See KNOWN_BUGS.md.
    """
    from app.models.stage import ProjectStageStatus
    from app.services.stage_service import seed_default_stages

    owner    = make_user(db, role="OFFICE_ADMIN")
    outsider = make_user(db, role="SITE_STAFF")   # site-level role: requires explicit UserProjectAccess
    other_proj = make_project(db, owner["id"])
    tok_owner    = login(client, owner["email"],    owner["password"])
    tok_outsider = login(client, outsider["email"], outsider["password"])

    proj  = make_project(db, owner["id"])
    make_user_project_access(db, owner["id"], proj["id"])
    make_user_project_access(db, outsider["id"], other_proj["id"])  # access to a DIFFERENT project only

    seed_default_stages(db)
    db.flush()

    # Get a stage master
    r = client.get("/api/v1/stages/", headers=auth(tok_owner))
    stage_id = r.json()["data"][0]["id"]

    # Create a stage status record
    import uuid as _uuid
    pss = ProjectStageStatus(
        project_id=_uuid.UUID(proj["id"]),
        stage_id=_uuid.UUID(stage_id),
    )
    db.add(pss)
    db.flush()

    # Owner can list (even with no attachments — empty list)
    r_ok = client.get(
        "/api/v1/attachments/",
        params={"entity_type": "STAGE_STATUS", "entity_id": str(pss.id)},
        headers=auth(tok_owner),
    )
    assert r_ok.status_code == 200

    # Outsider without project access must be forbidden
    r_denied = client.get(
        "/api/v1/attachments/",
        params={"entity_type": "STAGE_STATUS", "entity_id": str(pss.id)},
        headers=auth(tok_outsider),
    )
    assert r_denied.status_code in (403, 404), (
        f"Outsider should not access STAGE_STATUS attachments, got {r_denied.status_code}"
    )


# ── 2026-08-03 evidence-privacy hardening ───────────────────────────────────
#
# Fuel evidence and generic Attachment-table uploads (attachment_service /
# the /attachments/upload endpoint above) now route through a private
# Supabase bucket via save_upload(..., private=True). stored_path is never a
# directly fetchable URL for these — access is only via a fresh signed URL
# through the permission-checked GET /attachments/{id}/download endpoint.
# Legacy public-bucket records (private=False callers: delivery notes,
# signatures, stage-status raw evidence, stock usage evidence, generated
# MR/PO PDFs) are untouched by this hardening — see docs/fuel-management-gap-closure.md.

@pytest.fixture()
def attachment_ctx(db, client):
    owner = make_user(db, role="OWNER")
    site_user = make_user(db, role="SITE_STAFF")
    outsider = make_user(db, role="SITE_STAFF")
    project = make_project(db, owner["id"])
    other_project = make_project(db, owner["id"])
    make_user_project_access(db, site_user["id"], project["id"])
    make_user_project_access(db, outsider["id"], other_project["id"])
    db.commit()
    headers = {
        "owner": auth(login(client, owner["email"], owner["password"])),
        "site": auth(login(client, site_user["email"], site_user["password"])),
        "outsider": auth(login(client, outsider["email"], outsider["password"])),
    }
    return {"owner": owner, "site_user": site_user, "outsider": outsider,
            "project": project, "other_project": other_project, "headers": headers}


def _make_attachment(db, *, entity_id, stored_path, uploaded_by):
    att = Attachment(
        entity_type=AttachmentEntity.PROJECT, entity_id=entity_id, file_name="evidence.jpg",
        stored_path=stored_path, file_url=stored_path, mime_type="image/jpeg",
        file_size_bytes=100, attachment_type=AttachmentType.PHOTO,
        uploaded_by=uploaded_by, uploaded_at=datetime.now(timezone.utc), is_active=True,
    )
    db.add(att); db.commit(); db.refresh(att)
    return att


# ── download_url never leaks a raw storage URL ─────────────────────────────

def test_download_url_always_points_to_protected_endpoint(db, attachment_ctx):
    c = attachment_ctx
    from app.schemas.attachment import AttachmentRead
    owner_id = uuid.UUID(c["owner"]["id"])
    project_id = uuid.UUID(c["project"]["id"])
    local = _make_attachment(db, entity_id=project_id, stored_path="/uploads/attachments/x.jpg", uploaded_by=owner_id)
    private = _make_attachment(db, entity_id=project_id, stored_path="supabase://attachments/x.jpg", uploaded_by=owner_id)
    legacy = _make_attachment(
        db, entity_id=project_id,
        stored_path="https://legacy.supabase.co/storage/v1/object/public/hmh-uploads/x.jpg",
        uploaded_by=owner_id,
    )
    for att in (local, private, legacy):
        read = AttachmentRead.model_validate(att)
        assert read.download_url == f"/api/v1/attachments/{att.id}/download"


# ── /attachments/{id}/download: permission and project isolation ──────────

def test_download_authorised_local_file_streams(db, client, attachment_ctx, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    rel = "attachments/test/evid.jpg"
    full = tmp_path / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(b"fake-image-bytes")
    c = attachment_ctx
    att = _make_attachment(db, entity_id=uuid.UUID(c["project"]["id"]), stored_path=f"/uploads/{rel}",
                            uploaded_by=uuid.UUID(c["owner"]["id"]))
    r = client.get(f"/api/v1/attachments/{att.id}/download", headers=c["headers"]["site"])
    assert r.status_code == 200
    assert r.content == b"fake-image-bytes"


def test_download_unauthorised_user_gets_403(db, client, attachment_ctx):
    c = attachment_ctx
    att = _make_attachment(db, entity_id=uuid.UUID(c["project"]["id"]), stored_path="/uploads/attachments/x.jpg",
                            uploaded_by=uuid.UUID(c["owner"]["id"]))
    r = client.get(f"/api/v1/attachments/{att.id}/download", headers=c["headers"]["outsider"])
    assert r.status_code == 403


def test_download_cross_project_attachment_rejected(db, client, attachment_ctx):
    """`outsider` is assigned to other_project only; the attachment belongs to project."""
    c = attachment_ctx
    att = _make_attachment(db, entity_id=uuid.UUID(c["project"]["id"]), stored_path="/uploads/attachments/x.jpg",
                            uploaded_by=uuid.UUID(c["owner"]["id"]))
    r = client.get(f"/api/v1/attachments/{att.id}/download", headers=c["headers"]["outsider"])
    assert r.status_code == 403


def test_download_missing_attachment_returns_controlled_404(client, attachment_ctx):
    c = attachment_ctx
    r = client.get(f"/api/v1/attachments/{uuid.uuid4()}/download", headers=c["headers"]["owner"])
    assert r.status_code == 404


def test_download_soft_deleted_attachment_returns_404(db, client, attachment_ctx):
    c = attachment_ctx
    att = _make_attachment(db, entity_id=uuid.UUID(c["project"]["id"]), stored_path="/uploads/attachments/x.jpg",
                            uploaded_by=uuid.UUID(c["owner"]["id"]))
    att.is_active = False
    db.commit()
    r = client.get(f"/api/v1/attachments/{att.id}/download", headers=c["headers"]["site"])
    assert r.status_code == 404


# ── private (supabase://) redirects to a fresh signed URL ─────────────────

def test_download_private_attachment_redirects_to_signed_url(db, client, attachment_ctx, monkeypatch):
    c = attachment_ctx
    from app.api.v1 import attachments as attachments_route
    monkeypatch.setattr(
        attachments_route, "create_signed_url",
        lambda path, expires_in=None: "https://proj.supabase.co/storage/v1/object/sign/hmh-evidence-private/x.jpg?token=abc",
    )
    att = _make_attachment(db, entity_id=uuid.UUID(c["project"]["id"]), stored_path="supabase://attachments/x.jpg",
                            uploaded_by=uuid.UUID(c["owner"]["id"]))
    r = client.get(f"/api/v1/attachments/{att.id}/download", headers=c["headers"]["site"], follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "https://proj.supabase.co/storage/v1/object/sign/hmh-evidence-private/x.jpg?token=abc"


def test_download_private_attachment_still_permission_checked_before_signing(db, client, attachment_ctx, monkeypatch):
    """An unauthorised caller must be rejected before a signed URL is ever generated."""
    c = attachment_ctx
    from app.api.v1 import attachments as attachments_route
    calls = []
    monkeypatch.setattr(attachments_route, "create_signed_url", lambda path, expires_in=None: calls.append(path) or "unused")
    att = _make_attachment(db, entity_id=uuid.UUID(c["project"]["id"]), stored_path="supabase://attachments/x.jpg",
                            uploaded_by=uuid.UUID(c["owner"]["id"]))
    r = client.get(f"/api/v1/attachments/{att.id}/download", headers=c["headers"]["outsider"])
    assert r.status_code == 403
    assert calls == []


def test_download_legacy_public_url_still_redirects_unchanged(db, client, attachment_ctx):
    """Pre-2026-08-03 records with a raw public URL keep working exactly as before."""
    c = attachment_ctx
    legacy_url = "https://legacy.supabase.co/storage/v1/object/public/hmh-uploads/x.jpg"
    att = _make_attachment(db, entity_id=uuid.UUID(c["project"]["id"]), stored_path=legacy_url,
                            uploaded_by=uuid.UUID(c["owner"]["id"]))
    r = client.get(f"/api/v1/attachments/{att.id}/download", headers=c["headers"]["site"], follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == legacy_url


# ── storage.create_signed_url ──────────────────────────────────────────────

def test_create_signed_url_calls_supabase_sign_endpoint(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "svc-key")
    captured = {}

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"signedURL": "/object/sign/hmh-evidence-private/attachments/x.jpg?token=abc"}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(storage_module.httpx, "post", fake_post)
    result = storage_module.create_signed_url("supabase://attachments/x.jpg")
    assert result == "https://proj.supabase.co/storage/v1/object/sign/hmh-evidence-private/attachments/x.jpg?token=abc"
    assert captured["json"] == {"expiresIn": 300}
    assert "/storage/v1/object/sign/hmh-evidence-private/attachments/x.jpg" in captured["url"]


def test_create_signed_url_respects_configured_expiry(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "svc-key")
    monkeypatch.setattr(settings, "EVIDENCE_SIGNED_URL_EXPIRY_SECONDS", 60)
    captured = {}

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"signedURL": "/object/sign/hmh-evidence-private/x.jpg?token=abc"}

    monkeypatch.setattr(storage_module.httpx, "post", lambda url, json, headers, timeout: captured.update(json=json) or FakeResponse())
    storage_module.create_signed_url("supabase://x.jpg")
    assert captured["json"] == {"expiresIn": 60}


def test_create_signed_url_rejects_non_private_paths():
    with pytest.raises(ValueError):
        storage_module.create_signed_url("/uploads/x.jpg")
    with pytest.raises(ValueError):
        storage_module.create_signed_url("https://legacy.supabase.co/storage/v1/object/public/hmh-uploads/x.jpg")


def test_create_signed_url_raises_storage_error_when_supabase_unconfigured(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "")
    with pytest.raises(StorageError):
        storage_module.create_signed_url("supabase://attachments/x.jpg")


def test_create_signed_url_raises_storage_error_on_supabase_failure(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "svc-key")

    def fake_post(*a, **k):
        raise httpx.ConnectError("simulated network failure")

    monkeypatch.setattr(storage_module.httpx, "post", fake_post)
    with pytest.raises(StorageError):
        storage_module.create_signed_url("supabase://attachments/x.jpg")


# ── storage.save_upload(private=True): no silent local fallback outside dev ─

def test_save_upload_private_raises_when_supabase_unreachable_outside_dev(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "svc-key")
    monkeypatch.setattr(settings, "APP_ENV", "production")

    def fake_put(*a, **k):
        raise httpx.ConnectError("simulated network failure")

    monkeypatch.setattr(storage_module.httpx, "put", fake_put)
    with pytest.raises(StorageError):
        storage_module.save_upload(b"data", "attachments/x.jpg", private=True)


def test_save_upload_private_raises_when_supabase_not_configured_outside_dev(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "")
    monkeypatch.setattr(settings, "APP_ENV", "production")
    with pytest.raises(StorageError):
        storage_module.save_upload(b"data", "attachments/x.jpg", private=True)


def test_save_upload_private_falls_back_to_disk_only_in_development(monkeypatch, tmp_path):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "svc-key")
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    def fake_put(*a, **k):
        raise httpx.ConnectError("simulated network failure")

    monkeypatch.setattr(storage_module.httpx, "put", fake_put)
    result = storage_module.save_upload(b"data", "attachments/x.jpg", private=True)
    assert result == "/uploads/attachments/x.jpg"
    assert (tmp_path / "attachments" / "x.jpg").read_bytes() == b"data"


def test_save_upload_private_succeeds_via_supabase_returns_internal_reference(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "svc-key")

    class FakeResponse:
        def raise_for_status(self): pass

    def fake_put(url, content, headers, timeout):
        assert "hmh-evidence-private" in url
        return FakeResponse()

    monkeypatch.setattr(storage_module.httpx, "put", fake_put)
    result = storage_module.save_upload(b"data", "attachments/x.jpg", private=True)
    assert result == "supabase://attachments/x.jpg"


def test_save_upload_non_private_unaffected_by_production_guard(monkeypatch, tmp_path):
    """private=False (legacy callers: delivery notes, signatures, stage photos,
    stock usage evidence) must keep their existing dev-fallback behaviour
    unchanged by this hardening, even in a production-labelled environment."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "")
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    result = storage_module.save_upload(b"data", "delivery_notes/x.pdf")
    assert result == "/uploads/delivery_notes/x.pdf"


# ── storage.delete_upload: private-bucket cleanup ──────────────────────────

def test_delete_upload_removes_private_supabase_object(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "svc-key")
    captured = {}

    class FakeResponse:
        status_code = 200

    def fake_delete(url, headers, timeout):
        captured["url"] = url
        return FakeResponse()

    monkeypatch.setattr(storage_module.httpx, "delete", fake_delete)
    assert storage_module.delete_upload("supabase://attachments/x.jpg") is True
    assert "hmh-evidence-private/attachments/x.jpg" in captured["url"]


def test_delete_upload_private_without_supabase_configured_reports_failure(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "")
    assert storage_module.delete_upload("supabase://attachments/x.jpg") is False


# ── storage.verify_private_storage: preflight-style checks ─────────────────

def test_verify_private_storage_flags_a_public_bucket_as_misconfigured(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "svc-key")

    class FakeResponse:
        status_code = 200
        def json(self): return {"public": True}

    monkeypatch.setattr(storage_module.httpx, "get", lambda *a, **k: FakeResponse())
    result = storage_module.verify_private_storage()
    assert result["ok"] is False
    assert "private" in result["error"].lower() or "public" in result["error"].lower()


def test_verify_private_storage_ok_when_bucket_is_private(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "svc-key")

    class FakeResponse:
        status_code = 200
        def json(self): return {"public": False}

    monkeypatch.setattr(storage_module.httpx, "get", lambda *a, **k: FakeResponse())
    result = storage_module.verify_private_storage()
    assert result["ok"] is True


def test_verify_private_storage_reports_missing_bucket(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "svc-key")

    class FakeResponse:
        status_code = 404
        def json(self): return {}

    monkeypatch.setattr(storage_module.httpx, "get", lambda *a, **k: FakeResponse())
    result = storage_module.verify_private_storage()
    assert result["ok"] is False
    assert "not found" in result["error"].lower()


def test_verify_private_storage_without_credentials(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "")
    result = storage_module.verify_private_storage()
    assert result["ok"] is False


# ── 2026-08-03 fix: PROGRESS_CLAIM / PROGRAMME_ACTIVITY / WEEKLY_PLAN never
# resolved to a project_id in _entity_project_id, so every attachment
# operation on them (list/download/delete) skipped check_project_access
# entirely — any authenticated user, any role, any project could reach
# them. Unrelated to the STAGE_STATUS test-persona fix above; found while
# auditing every AttachmentEntity value for a resolvable project. ─────────

def _make_project_scoped_entity(db, entity_type: str, project_id):
    import uuid as _uuid
    from datetime import date

    if entity_type == "PROGRESS_CLAIM":
        from app.models.progress_claim import MunicipalityProgressClaim
        obj = MunicipalityProgressClaim(
            claim_number=f"PC-{_uuid.uuid4().hex[:8]}", project_id=project_id,
            claim_title="Test claim", period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31), reporting_cutoff_date=date(2026, 1, 31),
        )
    elif entity_type == "PROGRAMME_ACTIVITY":
        from app.models.programme import ProgrammeActivity
        obj = ProgrammeActivity(
            activity_number=f"ACT-{_uuid.uuid4().hex[:8]}", project_id=project_id,
            title="Test activity", planned_start_date=date(2026, 1, 1),
            planned_finish_date=date(2026, 1, 31),
        )
    elif entity_type == "WEEKLY_PLAN":
        from app.models.weekly_plan import WeeklyPlan
        obj = WeeklyPlan(
            plan_number=f"WP-{_uuid.uuid4().hex[:8]}", project_id=project_id,
            week_start_date=date(2026, 1, 5), week_end_date=date(2026, 1, 11),
        )
    else:
        raise ValueError(entity_type)
    db.add(obj); db.flush()
    return obj


@pytest.mark.parametrize("entity_type", ["PROGRESS_CLAIM", "PROGRAMME_ACTIVITY", "WEEKLY_PLAN"])
def test_previously_unresolved_entity_types_now_enforce_project_isolation(db, client, entity_type):
    owner = make_user(db, role="OFFICE_ADMIN")
    outsider = make_user(db, role="SITE_STAFF")  # site-level: requires explicit UserProjectAccess
    tok_owner = login(client, owner["email"], owner["password"])
    tok_outsider = login(client, outsider["email"], outsider["password"])

    proj = make_project(db, owner["id"])
    other_proj = make_project(db, owner["id"])
    make_user_project_access(db, owner["id"], proj["id"])
    make_user_project_access(db, outsider["id"], other_proj["id"])
    db.commit()

    entity = _make_project_scoped_entity(db, entity_type, uuid.UUID(proj["id"]))
    db.commit()

    r_ok = client.get(
        "/api/v1/attachments/",
        params={"entity_type": entity_type, "entity_id": str(entity.id)},
        headers=auth(tok_owner),
    )
    assert r_ok.status_code == 200

    r_denied = client.get(
        "/api/v1/attachments/",
        params={"entity_type": entity_type, "entity_id": str(entity.id)},
        headers=auth(tok_outsider),
    )
    assert r_denied.status_code == 403, (
        f"{entity_type} attachment listing must enforce project isolation, got {r_denied.status_code}"
    )

    # Upload and delete share the same _entity_project_id resolution, so the
    # fix must apply uniformly across every attachment operation, not just list.
    upload_files = {
        "file": ("x.png", io.BytesIO(TINY_PNG), "image/png"),
        "entity_type": (None, entity_type),
        "entity_id": (None, str(entity.id)),
        "attachment_type": (None, "PHOTO"),
    }
    r_upload_denied = client.post("/api/v1/attachments/upload", files=upload_files, headers=auth(tok_outsider))
    assert r_upload_denied.status_code == 403, (
        f"{entity_type} attachment upload must enforce project isolation, got {r_upload_denied.status_code}"
    )
    r_upload_ok = client.post("/api/v1/attachments/upload", files=upload_files, headers=auth(tok_owner))
    assert r_upload_ok.status_code == 201, r_upload_ok.text
    att_id = r_upload_ok.json()["data"]["id"]

    r_delete_denied = client.delete(f"/api/v1/attachments/{att_id}", headers=auth(tok_outsider))
    assert r_delete_denied.status_code == 403, (
        f"{entity_type} attachment delete must enforce project isolation, got {r_delete_denied.status_code}"
    )
