"""
Security API tests — verify project isolation at the HTTP layer.

Site Staff assigned to Project A must NOT be able to access Project B
resources at the API level (not just filtered in the UI).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import (
    make_user, make_project, make_site,
    make_user_project_access, login, auth,
)


# ── Project list isolation ─────────────────────────────────────────────────────

def test_site_staff_only_sees_assigned_project(client, db):
    owner = make_user(db, role="OWNER")
    staff = make_user(db, role="SITE_STAFF")
    proj_a = make_project(db, owner["id"])
    proj_b = make_project(db, owner["id"])
    make_user_project_access(db, staff["id"], proj_a["id"])

    token = login(client, staff["email"], staff["password"])
    r = client.get("/api/v1/projects/", headers=auth(token))
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()["data"]["items"]]
    assert proj_a["id"] in ids
    assert proj_b["id"] not in ids


def test_site_staff_sees_all_zero_projects_when_none_assigned(client, db):
    owner = make_user(db, role="OWNER")
    staff = make_user(db, role="SITE_STAFF")
    make_project(db, owner["id"])
    make_project(db, owner["id"])
    # No make_user_project_access call — staff has no assigned projects

    token = login(client, staff["email"], staff["password"])
    r = client.get("/api/v1/projects/", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 0


# ── Project detail isolation ───────────────────────────────────────────────────

def test_site_staff_can_access_assigned_project(client, db):
    owner = make_user(db, role="OWNER")
    staff = make_user(db, role="SITE_STAFF")
    proj_a = make_project(db, owner["id"])
    make_user_project_access(db, staff["id"], proj_a["id"])

    token = login(client, staff["email"], staff["password"])
    r = client.get(f"/api/v1/projects/{proj_a['id']}", headers=auth(token))
    assert r.status_code == 200


def test_site_staff_cannot_access_unassigned_project(client, db):
    owner = make_user(db, role="OWNER")
    staff = make_user(db, role="SITE_STAFF")
    proj_a = make_project(db, owner["id"])
    proj_b = make_project(db, owner["id"])
    make_user_project_access(db, staff["id"], proj_a["id"])

    token = login(client, staff["email"], staff["password"])
    r = client.get(f"/api/v1/projects/{proj_b['id']}", headers=auth(token))
    assert r.status_code == 403


# ── Material request isolation ─────────────────────────────────────────────────

def test_site_staff_can_list_mrs_for_assigned_project(client, db):
    owner = make_user(db, role="OWNER")
    staff = make_user(db, role="SITE_STAFF")
    proj_a = make_project(db, owner["id"])
    make_user_project_access(db, staff["id"], proj_a["id"])

    token = login(client, staff["email"], staff["password"])
    r = client.get(f"/api/v1/projects/{proj_a['id']}/material-requests/", headers=auth(token))
    assert r.status_code == 200


def test_site_staff_cannot_list_mrs_for_unassigned_project(client, db):
    owner = make_user(db, role="OWNER")
    staff = make_user(db, role="SITE_STAFF")
    proj_a = make_project(db, owner["id"])
    proj_b = make_project(db, owner["id"])
    make_user_project_access(db, staff["id"], proj_a["id"])

    token = login(client, staff["email"], staff["password"])
    r = client.get(f"/api/v1/projects/{proj_b['id']}/material-requests/", headers=auth(token))
    assert r.status_code == 403


# ── BOQ isolation ─────────────────────────────────────────────────────────────

def test_site_staff_cannot_search_boq_for_unassigned_project(client, db):
    owner = make_user(db, role="OWNER")
    staff = make_user(db, role="SITE_STAFF")
    proj_a = make_project(db, owner["id"])
    proj_b = make_project(db, owner["id"])
    make_user_project_access(db, staff["id"], proj_a["id"])

    token = login(client, staff["email"], staff["password"])
    r = client.get(f"/api/v1/projects/{proj_b['id']}/boq/items/search", headers=auth(token))
    assert r.status_code == 403


def test_site_staff_can_search_boq_for_assigned_project(client, db):
    owner = make_user(db, role="OWNER")
    staff = make_user(db, role="SITE_STAFF")
    proj_a = make_project(db, owner["id"])
    make_user_project_access(db, staff["id"], proj_a["id"])

    token = login(client, staff["email"], staff["password"])
    r = client.get(f"/api/v1/projects/{proj_a['id']}/boq/items/search", headers=auth(token))
    assert r.status_code == 200


# ── Warehouse isolation ───────────────────────────────────────────────────────

def test_site_staff_cannot_access_warehouse_boq_for_unassigned_project(client, db):
    owner = make_user(db, role="OWNER")
    staff = make_user(db, role="SITE_STAFF")
    proj_a = make_project(db, owner["id"])
    proj_b = make_project(db, owner["id"])
    make_user_project_access(db, staff["id"], proj_a["id"])

    token = login(client, staff["email"], staff["password"])
    r = client.get(f"/api/v1/projects/{proj_b['id']}/warehouse/boq-summary", headers=auth(token))
    assert r.status_code == 403


# ── SITE_MANAGER_VIEW isolation ───────────────────────────────────────────────

def test_site_manager_view_can_access_assigned_project(client, db):
    owner = make_user(db, role="OWNER")
    viewer = make_user(db, role="SITE_MANAGER_VIEW")
    proj_a = make_project(db, owner["id"])
    make_user_project_access(db, viewer["id"], proj_a["id"])

    token = login(client, viewer["email"], viewer["password"])
    r = client.get(f"/api/v1/projects/{proj_a['id']}", headers=auth(token))
    assert r.status_code == 200


def test_site_manager_view_cannot_access_unassigned_project(client, db):
    owner = make_user(db, role="OWNER")
    viewer = make_user(db, role="SITE_MANAGER_VIEW")
    proj_a = make_project(db, owner["id"])
    proj_b = make_project(db, owner["id"])
    make_user_project_access(db, viewer["id"], proj_a["id"])

    token = login(client, viewer["email"], viewer["password"])
    r = client.get(f"/api/v1/projects/{proj_b['id']}", headers=auth(token))
    assert r.status_code == 403


def test_site_manager_view_cannot_write_to_assigned_project(client, db):
    """SITE_MANAGER_VIEW is read-only — cannot create an MR even for an assigned project."""
    owner = make_user(db, role="OWNER")
    viewer = make_user(db, role="SITE_MANAGER_VIEW")
    proj_a = make_project(db, owner["id"])
    site = make_site(db, proj_a["id"])
    make_user_project_access(db, viewer["id"], proj_a["id"])

    token = login(client, viewer["email"], viewer["password"])
    r = client.post(
        f"/api/v1/projects/{proj_a['id']}/material-requests/",
        headers=auth(token),
        json={
            "site_id": site["id"],
            "items": [{"description": "Test Item", "requested_quantity": 1}],
        },
    )
    assert r.status_code == 403
