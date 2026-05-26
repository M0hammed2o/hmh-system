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
    """Listing STAGE_STATUS attachments must require project membership."""
    from app.models.stage import ProjectStageStatus
    from app.services.stage_service import seed_default_stages

    owner   = make_user(db, role="OFFICE_ADMIN")
    outsider = make_user(db, role="OFFICE_USER")   # no project access
    tok_owner    = login(client, owner["email"],    owner["password"])
    tok_outsider = login(client, outsider["email"], outsider["password"])

    proj  = make_project(db, owner["id"])
    make_user_project_access(db, owner["id"], proj["id"])

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
