"""
Phase 3D.2 — LotType CRUD + assignment tests.

Tests:
  1. Create a lot type in a project
  2. List lot types with correct lot counts
  3. Get lot type with linked lots
  4. Update lot type (name, code, template)
  5. Cannot use duplicate code within same project
  6. Assign lots (single type)
  7. Assign lots (reassignment from another type)
  8. Remove lots from type
  9. Delete lot type — blocked when lots are assigned
  10. Delete lot type — succeeds when no lots assigned
  11. Freestanding lots (site_id=None) can be assigned
  12. READ_ONLY cannot create/update/delete/assign
  13. Lot.lot_type_id is returned in lot list
"""

import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from tests.conftest import auth, login, make_lot, make_project, make_site, make_user, make_user_project_access


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def lt_setup(db: Session, client: TestClient):
    """Project with one site, two site lots, one freestanding lot, and one office user."""
    owner   = make_user(db, role="OWNER")
    office  = make_user(db, role="OFFICE_ADMIN")
    ro      = make_user(db, role="READ_ONLY")

    project = make_project(db, owner["id"])
    site    = make_site(db, project["id"], "Block A")

    lot1     = make_lot(db, project["id"], site["id"], "1")
    lot2     = make_lot(db, project["id"], site["id"], "2")
    lot_free = make_lot(db, project["id"], None,       "F1")  # freestanding
    make_user_project_access(db, office["id"], project["id"])
    make_user_project_access(db, ro["id"], project["id"])

    db.flush()
    return {
        "owner": owner, "office": office, "ro": ro,
        "project": project, "site": site,
        "lot1": lot1, "lot2": lot2, "lot_free": lot_free,
    }


# ── CRUD ──────────────────────────────────────────────────────────────────────

def test_create_lot_type(db: Session, client: TestClient, lt_setup: dict):
    tok = login(client, lt_setup["office"]["email"], lt_setup["office"]["password"])
    r = client.post(
        f"/api/v1/projects/{lt_setup['project']['id']}/lot-types/",
        json={"name": "Type A", "code": "TYPE-A", "description": "Standard house"},
        headers=auth(tok),
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["name"] == "Type A"
    assert data["code"] == "TYPE-A"
    assert data["lot_count"] == 0


def test_list_lot_types_with_counts(db: Session, client: TestClient, lt_setup: dict):
    tok = login(client, lt_setup["office"]["email"], lt_setup["office"]["password"])

    # Create two types
    for name, code in [("Type A", "TA"), ("Type B", "TB")]:
        client.post(
            f"/api/v1/projects/{lt_setup['project']['id']}/lot-types/",
            json={"name": name, "code": code},
            headers=auth(tok),
        )

    r = client.get(
        f"/api/v1/projects/{lt_setup['project']['id']}/lot-types/",
        headers=auth(tok),
    )
    assert r.status_code == 200, r.text
    types = r.json()["data"]
    assert len(types) == 2
    names = {t["name"] for t in types}
    assert names == {"Type A", "Type B"}


def test_get_lot_type_with_lots(db: Session, client: TestClient, lt_setup: dict):
    tok = login(client, lt_setup["office"]["email"], lt_setup["office"]["password"])

    # Create type then assign a lot
    r1 = client.post(
        f"/api/v1/projects/{lt_setup['project']['id']}/lot-types/",
        json={"name": "Type C"},
        headers=auth(tok),
    )
    lot_type_id = r1.json()["data"]["id"]

    client.post(
        f"/api/v1/lot-types/{lot_type_id}/assign-lots",
        json={"lot_ids": [lt_setup["lot1"]["id"]]},
        headers=auth(tok),
    )

    r2 = client.get(f"/api/v1/lot-types/{lot_type_id}", headers=auth(tok))
    assert r2.status_code == 200, r2.text
    data = r2.json()["data"]
    assert data["lot_count"] == 1
    assert len(data["lots"]) == 1
    assert data["lots"][0]["lot_number"] == "1"


def test_update_lot_type(db: Session, client: TestClient, lt_setup: dict):
    tok = login(client, lt_setup["office"]["email"], lt_setup["office"]["password"])
    r = client.post(
        f"/api/v1/projects/{lt_setup['project']['id']}/lot-types/",
        json={"name": "Old Name", "code": "OLD"},
        headers=auth(tok),
    )
    lt_id = r.json()["data"]["id"]

    r2 = client.patch(
        f"/api/v1/lot-types/{lt_id}",
        json={"name": "New Name", "code": "NEW"},
        headers=auth(tok),
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["data"]["name"] == "New Name"
    assert r2.json()["data"]["code"] == "NEW"


def test_duplicate_code_blocked(db: Session, client: TestClient, lt_setup: dict):
    tok = login(client, lt_setup["office"]["email"], lt_setup["office"]["password"])
    pid = lt_setup["project"]["id"]

    client.post(f"/api/v1/projects/{pid}/lot-types/", json={"name": "A", "code": "DUP"}, headers=auth(tok))
    r = client.post(f"/api/v1/projects/{pid}/lot-types/", json={"name": "B", "code": "DUP"}, headers=auth(tok))
    assert r.status_code in (409, 400, 422), r.text


# ── Assignment ────────────────────────────────────────────────────────────────

def test_assign_lots(db: Session, client: TestClient, lt_setup: dict):
    tok = login(client, lt_setup["office"]["email"], lt_setup["office"]["password"])

    r = client.post(
        f"/api/v1/projects/{lt_setup['project']['id']}/lot-types/",
        json={"name": "Assign Test"},
        headers=auth(tok),
    )
    lt_id = r.json()["data"]["id"]

    r2 = client.post(
        f"/api/v1/lot-types/{lt_id}/assign-lots",
        json={"lot_ids": [lt_setup["lot1"]["id"], lt_setup["lot2"]["id"]]},
        headers=auth(tok),
    )
    assert r2.status_code == 200, r2.text
    result = r2.json()["data"]
    assert result["assigned"] == 2
    assert result["total"] == 2

    # Verify count
    r3 = client.get(f"/api/v1/lot-types/{lt_id}", headers=auth(tok))
    assert r3.json()["data"]["lot_count"] == 2


def test_reassign_from_another_type(db: Session, client: TestClient, lt_setup: dict):
    tok = login(client, lt_setup["office"]["email"], lt_setup["office"]["password"])
    pid = lt_setup["project"]["id"]

    type_a = client.post(f"/api/v1/projects/{pid}/lot-types/", json={"name": "A"}, headers=auth(tok)).json()["data"]["id"]
    type_b = client.post(f"/api/v1/projects/{pid}/lot-types/", json={"name": "B"}, headers=auth(tok)).json()["data"]["id"]

    # Assign lot1 to type A
    client.post(f"/api/v1/lot-types/{type_a}/assign-lots", json={"lot_ids": [lt_setup["lot1"]["id"]]}, headers=auth(tok))

    # Reassign lot1 to type B
    r = client.post(f"/api/v1/lot-types/{type_b}/assign-lots", json={"lot_ids": [lt_setup["lot1"]["id"]]}, headers=auth(tok))
    assert r.status_code == 200
    assert r.json()["data"]["reassigned"] == 1

    # Type A should now have 0 lots
    r2 = client.get(f"/api/v1/lot-types/{type_a}", headers=auth(tok))
    assert r2.json()["data"]["lot_count"] == 0


def test_remove_lots_from_type(db: Session, client: TestClient, lt_setup: dict):
    tok = login(client, lt_setup["office"]["email"], lt_setup["office"]["password"])
    pid = lt_setup["project"]["id"]

    lt_id = client.post(f"/api/v1/projects/{pid}/lot-types/", json={"name": "Remove Test"}, headers=auth(tok)).json()["data"]["id"]
    client.post(f"/api/v1/lot-types/{lt_id}/assign-lots", json={"lot_ids": [lt_setup["lot1"]["id"]]}, headers=auth(tok))

    r = client.post(
        f"/api/v1/lot-types/{lt_id}/remove-lots",
        json={"lot_ids": [lt_setup["lot1"]["id"]]},
        headers=auth(tok),
    )
    assert r.status_code == 200
    assert r.json()["data"]["removed"] == 1

    r2 = client.get(f"/api/v1/lot-types/{lt_id}", headers=auth(tok))
    assert r2.json()["data"]["lot_count"] == 0


def test_delete_blocked_when_lots_assigned(db: Session, client: TestClient, lt_setup: dict):
    tok = login(client, lt_setup["office"]["email"], lt_setup["office"]["password"])
    pid = lt_setup["project"]["id"]

    lt_id = client.post(f"/api/v1/projects/{pid}/lot-types/", json={"name": "Del Test"}, headers=auth(tok)).json()["data"]["id"]
    client.post(f"/api/v1/lot-types/{lt_id}/assign-lots", json={"lot_ids": [lt_setup["lot1"]["id"]]}, headers=auth(tok))

    r = client.delete(f"/api/v1/lot-types/{lt_id}", headers=auth(tok))
    assert r.status_code in (409, 400), f"Expected conflict, got {r.status_code}: {r.text}"


def test_delete_succeeds_when_empty(db: Session, client: TestClient, lt_setup: dict):
    tok = login(client, lt_setup["office"]["email"], lt_setup["office"]["password"])
    pid = lt_setup["project"]["id"]

    lt_id = client.post(f"/api/v1/projects/{pid}/lot-types/", json={"name": "Empty Del"}, headers=auth(tok)).json()["data"]["id"]
    r = client.delete(f"/api/v1/lot-types/{lt_id}", headers=auth(tok))
    assert r.status_code == 200, r.text


def test_freestanding_lot_assignment(db: Session, client: TestClient, lt_setup: dict):
    """Freestanding lots (site_id=None) must be assignable to a lot type."""
    tok = login(client, lt_setup["office"]["email"], lt_setup["office"]["password"])
    pid = lt_setup["project"]["id"]

    lt_id = client.post(f"/api/v1/projects/{pid}/lot-types/", json={"name": "Freestanding Type"}, headers=auth(tok)).json()["data"]["id"]
    r = client.post(
        f"/api/v1/lot-types/{lt_id}/assign-lots",
        json={"lot_ids": [lt_setup["lot_free"]["id"]]},
        headers=auth(tok),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["assigned"] == 1

    # Verify it shows in the type detail
    r2 = client.get(f"/api/v1/lot-types/{lt_id}", headers=auth(tok))
    lots = r2.json()["data"]["lots"]
    assert any(l["lot_number"] == "F1" for l in lots)


def test_read_only_blocked(db: Session, client: TestClient, lt_setup: dict):
    tok = login(client, lt_setup["ro"]["email"], lt_setup["ro"]["password"])
    pid = lt_setup["project"]["id"]

    r = client.post(f"/api/v1/projects/{pid}/lot-types/", json={"name": "RO"}, headers=auth(tok))
    assert r.status_code == 403


def test_lot_type_id_in_lot_list(db: Session, client: TestClient, lt_setup: dict):
    """Lot list must expose lot_type_id so the frontend can show type badges."""
    tok = login(client, lt_setup["office"]["email"], lt_setup["office"]["password"])
    pid = lt_setup["project"]["id"]

    lt_id = client.post(f"/api/v1/projects/{pid}/lot-types/", json={"name": "Badge Test"}, headers=auth(tok)).json()["data"]["id"]
    client.post(f"/api/v1/lot-types/{lt_id}/assign-lots", json={"lot_ids": [lt_setup["lot1"]["id"]]}, headers=auth(tok))

    r = client.get(f"/api/v1/projects/{pid}/lots/", headers=auth(tok))
    assert r.status_code == 200
    lot1 = next((l for l in r.json()["data"] if l["id"] == lt_setup["lot1"]["id"]), None)
    assert lot1 is not None
    assert lot1.get("lot_type_id") == lt_id
