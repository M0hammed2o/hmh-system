"""
Phase 3K — Universal attachment system tests.

Tests:
  1.  Upload to MATERIAL_REQUEST entity works
  2.  Upload to LOT entity works (new Phase 3K)
  3.  Upload to PROJECT entity works (new Phase 3K)
  4.  Upload with PROGRESS_PHOTO attachment type
  5.  Upload with PROOF_OF_WORK attachment type
  6.  Upload with FUEL_SLIP attachment type
  7.  Upload with QUOTATION attachment type
  8.  Multiple files to same entity
  9.  Soft delete — is_active=False
  10. List only returns active attachments
  11. uploaded_by_name populated in list response
  12. READ_ONLY cannot upload
  13. READ_ONLY cannot delete
  14. WRITE_ROLES can upload
  15. Attachment for freestanding lot (site_id=None)
"""

import io
import uuid
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from tests.conftest import auth, login, make_lot, make_project, make_site, make_user, make_user_project_access


def _upload(client, tok, entity_type: str, entity_id: str, att_type: str = "PHOTO"):
    fake = io.BytesIO(b"\x89PNG\r\n" + b"\x00" * 20)
    return client.post(
        "/api/v1/attachments/upload",
        data={
            "entity_type": entity_type,
            "entity_id":   entity_id,
            "attachment_type": att_type,
        },
        files={"file": ("test.png", fake, "image/png")},
        headers=auth(tok),
    )


@pytest.fixture()
def att_setup(db: Session, client: TestClient):
    owner  = make_user(db, role="OWNER")
    office = make_user(db, role="OFFICE_ADMIN")
    ro     = make_user(db, role="READ_ONLY")
    site_s = make_user(db, role="SITE_STAFF")

    project   = make_project(db, owner["id"])
    site      = make_site(db, project["id"])
    lot       = make_lot(db, project["id"], site["id"], "7")
    lot_free  = make_lot(db, project["id"], None, "F99")   # freestanding
    make_user_project_access(db, office["id"], project["id"])
    make_user_project_access(db, site_s["id"], project["id"])
    db.flush()

    return {
        "owner": owner, "office": office, "ro": ro, "site_staff": site_s,
        "project": project, "site": site, "lot": lot, "lot_free": lot_free,
    }


def test_upload_to_material_request(db: Session, client: TestClient, att_setup: dict):
    tok = login(client, att_setup["office"]["email"], att_setup["office"]["password"])
    pid = att_setup["project"]["id"]
    sid = att_setup["site"]["id"]

    r = client.post(f"/api/v1/projects/{pid}/material-requests/",
        json={"site_id": sid, "items": [{"description": "Cement", "requested_quantity": 5}]},
        headers=auth(tok))
    mr_id = r.json()["data"]["id"]

    r2 = _upload(client, tok, "MATERIAL_REQUEST", mr_id, "PROOF_OF_WORK")
    assert r2.status_code == 201, r2.text
    assert r2.json()["data"]["attachment_type"] == "PROOF_OF_WORK"


def test_upload_to_lot(db: Session, client: TestClient, att_setup: dict):
    """LOT entity type now supported (Phase 3K)."""
    tok = login(client, att_setup["office"]["email"], att_setup["office"]["password"])
    lot_id = att_setup["lot"]["id"]

    r = _upload(client, tok, "LOT", lot_id, "PROGRESS_PHOTO")
    assert r.status_code == 201, r.text
    assert r.json()["data"]["entity_type"] == "LOT"


def test_upload_to_project(db: Session, client: TestClient, att_setup: dict):
    """PROJECT entity type now supported (Phase 3K)."""
    tok = login(client, att_setup["office"]["email"], att_setup["office"]["password"])
    pid = att_setup["project"]["id"]

    r = _upload(client, tok, "PROJECT", pid, "PDF")
    assert r.status_code == 201, r.text
    assert r.json()["data"]["entity_type"] == "PROJECT"


def test_new_attachment_types(db: Session, client: TestClient, att_setup: dict):
    """All Phase 3K attachment types can be used."""
    tok = login(client, att_setup["office"]["email"], att_setup["office"]["password"])
    pid = att_setup["project"]["id"]

    for att_type in ["PROGRESS_PHOTO", "PROOF_OF_WORK", "FUEL_SLIP", "QUOTATION", "PO_DOCUMENT"]:
        r = _upload(client, tok, "PROJECT", pid, att_type)
        assert r.status_code == 201, f"{att_type}: {r.text}"
        assert r.json()["data"]["attachment_type"] == att_type


def test_multiple_files_same_entity(db: Session, client: TestClient, att_setup: dict):
    """Multiple files can be uploaded to the same entity."""
    tok = login(client, att_setup["office"]["email"], att_setup["office"]["password"])
    lot_id = att_setup["lot"]["id"]

    ids = []
    for i in range(3):
        r = _upload(client, tok, "LOT", lot_id, "PROGRESS_PHOTO")
        assert r.status_code == 201
        ids.append(r.json()["data"]["id"])

    r2 = client.get(f"/api/v1/attachments/?entity_type=LOT&entity_id={lot_id}", headers=auth(tok))
    listed_ids = {a["id"] for a in r2.json()["data"]}
    assert all(i in listed_ids for i in ids)


def test_soft_delete_hides_attachment(db: Session, client: TestClient, att_setup: dict):
    tok = login(client, att_setup["office"]["email"], att_setup["office"]["password"])
    pid = att_setup["project"]["id"]

    r = _upload(client, tok, "PROJECT", pid, "PHOTO")
    att_id = r.json()["data"]["id"]

    r2 = client.delete(f"/api/v1/attachments/{att_id}", headers=auth(tok))
    assert r2.status_code == 200

    r3 = client.get(f"/api/v1/attachments/?entity_type=PROJECT&entity_id={pid}", headers=auth(tok))
    listed_ids = {a["id"] for a in r3.json()["data"]}
    assert att_id not in listed_ids, "Soft-deleted attachment must not appear in list"


def test_uploaded_by_name_in_response(db: Session, client: TestClient, att_setup: dict):
    """List attachments includes uploaded_by_name."""
    tok = login(client, att_setup["office"]["email"], att_setup["office"]["password"])
    pid = att_setup["project"]["id"]

    _upload(client, tok, "PROJECT", pid, "PHOTO")

    r = client.get(f"/api/v1/attachments/?entity_type=PROJECT&entity_id={pid}", headers=auth(tok))
    data = r.json()["data"]
    assert len(data) >= 1
    # uploaded_by_name should be a non-None string for office user
    assert data[0].get("uploaded_by_name") is not None, \
        "uploaded_by_name must be populated in list response"


def test_read_only_cannot_upload(db: Session, client: TestClient, att_setup: dict):
    tok = login(client, att_setup["ro"]["email"], att_setup["ro"]["password"])
    pid = att_setup["project"]["id"]

    r = _upload(client, tok, "PROJECT", pid, "PHOTO")
    assert r.status_code == 403


def test_read_only_cannot_delete(db: Session, client: TestClient, att_setup: dict):
    # Upload as office
    office_tok = login(client, att_setup["office"]["email"], att_setup["office"]["password"])
    pid = att_setup["project"]["id"]
    r = _upload(client, office_tok, "PROJECT", pid, "PHOTO")
    att_id = r.json()["data"]["id"]

    # Try delete as READ_ONLY
    ro_tok = login(client, att_setup["ro"]["email"], att_setup["ro"]["password"])
    r2 = client.delete(f"/api/v1/attachments/{att_id}", headers=auth(ro_tok))
    assert r2.status_code == 403


def test_freestanding_lot_attachment(db: Session, client: TestClient, att_setup: dict):
    """Attachments work for freestanding lots (site_id=None)."""
    tok = login(client, att_setup["office"]["email"], att_setup["office"]["password"])
    lot_id = att_setup["lot_free"]["id"]

    r = _upload(client, tok, "LOT", lot_id, "PROGRESS_PHOTO")
    assert r.status_code == 201, r.text
    att = r.json()["data"]
    assert att["entity_type"] == "LOT"
    assert att["entity_id"] == lot_id


def test_site_staff_can_upload(db: Session, client: TestClient, att_setup: dict):
    """SITE_STAFF should be able to upload attachments."""
    tok = login(client, att_setup["site_staff"]["email"], att_setup["site_staff"]["password"])
    lot_id = att_setup["lot"]["id"]

    r = _upload(client, tok, "LOT", lot_id, "PROGRESS_PHOTO")
    assert r.status_code == 201, f"Site staff must be able to upload: {r.text}"
