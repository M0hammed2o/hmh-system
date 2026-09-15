"""
Site Clerk material request — per-request supplier selection.

Requirements covered (client review, 2026-09-15):
 1. BOQ search returns the BOQ item's default supplier to the Site Clerk.
 2. Site Clerk can request a different existing supplier; it is stored on the
    request line (and on the request header).
 3. Requesting a different supplier does NOT change the BOQ item's default supplier.
 4. Procurement/Office sees the requested supplier (MR read + pipeline view).
 5. Keeping the BOQ default supplier still works; no supplier is still allowed.
 6. Supplier must be an existing supplier record — unknown or inactive ids are
    rejected server-side; no supplier rows are created.
 7. A BOQ default supplier that was later deactivated remains requestable.
 8. Quantity, needed-by date, notes and submission are preserved.
 9. Fuel request workflow is unchanged.
"""

import uuid

import pytest
from sqlalchemy import update

from tests.conftest import (
    auth, login, make_boq_item, make_item, make_lot, make_project, make_site,
    make_supplier, make_user, make_user_project_access,
)


@pytest.fixture
def setup(db, client):
    from app.models.boq import BOQItem

    owner   = make_user(db, role="OWNER")
    clerk   = make_user(db, role="SITE_STAFF")
    office  = make_user(db, role="OFFICE_USER")
    project = make_project(db, owner_id=owner["id"])
    site    = make_site(db, project_id=project["id"])
    lot     = make_lot(db, project_id=project["id"], site_id=site["id"])
    item    = make_item(db, name="Cement 42.5R")
    boq     = make_boq_item(db, project["id"], lot["id"], item["id"], qty=200)
    default_supplier = make_supplier(db, name=f"Default Cement Co {uuid.uuid4().hex[:4]}")
    other_supplier   = make_supplier(db, name=f"Other Cement Co {uuid.uuid4().hex[:4]}")
    description = f"Cement 42.5R {uuid.uuid4().hex[:6]}"
    db.execute(
        update(BOQItem)
        .where(BOQItem.id == uuid.UUID(boq["boq_item_id"]))
        .values(supplier_id=uuid.UUID(default_supplier["id"]), raw_description=description)
    )
    db.flush()
    make_user_project_access(db, clerk["id"], project["id"])

    return dict(
        project_id=project["id"], site_id=site["id"], lot_id=lot["id"],
        boq_item_id=boq["boq_item_id"], description=description,
        default_supplier=default_supplier, other_supplier=other_supplier,
        clerk_tok=login(client, clerk["email"], clerk["password"]),
        office_tok=login(client, office["email"], office["password"]),
    )


def _create_mr(client, s, line_supplier_id, header_supplier_id=None, **overrides):
    body = {
        "site_id": s["site_id"],
        "lot_id": s["lot_id"],
        "procurement_category": "MATERIAL",
        "delivery_destination": "SITE_STORE",
        "needed_by_date": "2026-10-01",
        "notes": "Needed for slab pour",
        "preferred_supplier_id": header_supplier_id,
        "items": [{
            "description": s["description"],
            "quantity_requested": 25,
            "unit": "bag",
            "boq_item_id": s["boq_item_id"],
            "preferred_supplier_id": line_supplier_id,
            "notes": None,
        }],
    }
    body.update(overrides)
    return client.post(
        f"/api/v1/projects/{s['project_id']}/material-requests/",
        json=body, headers=auth(s["clerk_tok"]),
    )


def _boq_supplier_id(db, boq_item_id):
    from app.models.boq import BOQItem
    db.expire_all()
    return db.get(BOQItem, uuid.UUID(boq_item_id)).supplier_id


class TestRequestedSupplier:

    def test_boq_search_shows_default_supplier_to_site_clerk(self, client, setup):
        s = setup
        r = client.get(
            f"/api/v1/projects/{s['project_id']}/boq/items/search",
            params={"q": s["description"]}, headers=auth(s["clerk_tok"]),
        )
        assert r.status_code == 200, r.text
        hit = next(x for x in r.json()["data"] if x["id"] == s["boq_item_id"])
        assert hit["preferred_supplier_id"] == s["default_supplier"]["id"]
        assert hit["supplier_name"] == s["default_supplier"]["name"]

    def test_clerk_can_request_a_different_supplier(self, client, db, setup):
        from app.models.material_request import MaterialRequestItem
        s = setup
        other = s["other_supplier"]["id"]

        r = _create_mr(client, s, line_supplier_id=other, header_supplier_id=other)
        assert r.status_code == 201, r.text
        mr = r.json()["data"]
        assert mr["preferred_supplier_id"] == other
        assert mr["items"][0]["preferred_supplier_id"] == other

        line = db.get(MaterialRequestItem, uuid.UUID(mr["items"][0]["id"]))
        assert str(line.preferred_supplier_id) == other

        sub = client.post(f"/api/v1/material-requests/{mr['id']}/submit", headers=auth(s["clerk_tok"]))
        assert sub.status_code == 200, sub.text
        assert sub.json()["data"]["status"] == "SUBMITTED"
        assert sub.json()["data"]["items"][0]["preferred_supplier_id"] == other

    def test_requesting_other_supplier_does_not_change_boq_default(self, client, db, setup):
        s = setup
        r = _create_mr(client, s, line_supplier_id=s["other_supplier"]["id"],
                       header_supplier_id=s["other_supplier"]["id"])
        assert r.status_code == 201, r.text
        client.post(f"/api/v1/material-requests/{r.json()['data']['id']}/submit", headers=auth(s["clerk_tok"]))

        assert str(_boq_supplier_id(db, s["boq_item_id"])) == s["default_supplier"]["id"]
        search = client.get(
            f"/api/v1/projects/{s['project_id']}/boq/items/search",
            params={"q": s["description"]}, headers=auth(s["clerk_tok"]),
        ).json()["data"]
        assert next(x for x in search if x["id"] == s["boq_item_id"])["preferred_supplier_id"] == s["default_supplier"]["id"]

    def test_office_sees_requested_supplier(self, client, setup):
        s = setup
        other = s["other_supplier"]["id"]
        mr_id = _create_mr(client, s, line_supplier_id=other, header_supplier_id=other).json()["data"]["id"]
        client.post(f"/api/v1/material-requests/{mr_id}/submit", headers=auth(s["clerk_tok"]))

        r = client.get(f"/api/v1/material-requests/{mr_id}", headers=auth(s["office_tok"]))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["items"][0]["preferred_supplier_id"] == other

        p = client.get(f"/api/v1/procurement/mrs/{mr_id}/pipeline", headers=auth(s["office_tok"]))
        assert p.status_code == 200, p.text
        data = p.json()["data"]
        assert data["items"][0]["preferred_supplier_id"] == other
        assert data["supplier"]["id"] == other
        assert data["supplier"]["name"] == s["other_supplier"]["name"]

    def test_keeping_boq_default_supplier_is_stored(self, client, setup):
        s = setup
        default = s["default_supplier"]["id"]
        r = _create_mr(client, s, line_supplier_id=default, header_supplier_id=default)
        assert r.status_code == 201, r.text
        assert r.json()["data"]["items"][0]["preferred_supplier_id"] == default

    def test_no_supplier_is_still_allowed(self, client, setup):
        s = setup
        r = _create_mr(client, s, line_supplier_id=None, header_supplier_id=None)
        assert r.status_code == 201, r.text
        assert r.json()["data"]["items"][0]["preferred_supplier_id"] is None

    def test_quantity_date_and_notes_preserved(self, client, setup):
        s = setup
        r = _create_mr(client, s, line_supplier_id=s["other_supplier"]["id"])
        assert r.status_code == 201, r.text
        mr = r.json()["data"]
        assert mr["needed_by_date"] == "2026-10-01"
        assert mr["notes"] == "Needed for slab pour"
        assert float(mr["items"][0]["requested_quantity"]) == pytest.approx(25)
        assert mr["items"][0]["boq_item_id"] == s["boq_item_id"]

    def test_unknown_supplier_rejected_and_nothing_created(self, client, db, setup):
        from app.models.material_request import MaterialRequest
        from app.models.supplier import Supplier
        s = setup
        mrs_before = db.query(MaterialRequest).filter(MaterialRequest.project_id == uuid.UUID(s["project_id"])).count()
        suppliers_before = db.query(Supplier).count()

        r = _create_mr(client, s, line_supplier_id=str(uuid.uuid4()))
        assert r.status_code == 422, r.text

        r = _create_mr(client, s, line_supplier_id=None, header_supplier_id=str(uuid.uuid4()))
        assert r.status_code == 422, r.text

        assert db.query(MaterialRequest).filter(MaterialRequest.project_id == uuid.UUID(s["project_id"])).count() == mrs_before
        assert db.query(Supplier).count() == suppliers_before
        assert str(_boq_supplier_id(db, s["boq_item_id"])) == s["default_supplier"]["id"]

    def test_inactive_non_default_supplier_rejected(self, client, db, setup):
        from app.models.supplier import Supplier
        s = setup
        db.get(Supplier, uuid.UUID(s["other_supplier"]["id"])).is_active = False
        db.flush()

        r = _create_mr(client, s, line_supplier_id=s["other_supplier"]["id"])
        assert r.status_code == 422, r.text

    def test_inactive_boq_default_supplier_still_requestable(self, client, db, setup):
        from app.models.supplier import Supplier
        s = setup
        default = s["default_supplier"]["id"]
        db.get(Supplier, uuid.UUID(default)).is_active = False
        db.flush()

        r = _create_mr(client, s, line_supplier_id=default, header_supplier_id=default)
        assert r.status_code == 201, r.text
        assert r.json()["data"]["items"][0]["preferred_supplier_id"] == default


class TestFuelRequestUnchanged:

    def _fuel(self, client, s, **item_overrides):
        item = {"description": "Diesel", "quantity_requested": 500, "unit": "L"}
        item.update(item_overrides)
        return client.post(
            f"/api/v1/projects/{s['project_id']}/material-requests/",
            json={
                "site_id": s["site_id"], "lot_id": None,
                "procurement_category": "FUEL", "delivery_destination": "SITE_STORE",
                "needed_by_date": None, "notes": "Generator", "items": [item],
            },
            headers=auth(s["clerk_tok"]),
        )

    def test_fuel_request_create_and_submit(self, client, setup):
        s = setup
        r = self._fuel(client, s)
        assert r.status_code == 201, r.text
        mr = r.json()["data"]
        assert mr["procurement_category"] == "FUEL"
        assert mr["preferred_supplier_id"] is None
        assert mr["items"][0]["boq_item_id"] is None

        sub = client.post(f"/api/v1/material-requests/{mr['id']}/submit", headers=auth(s["clerk_tok"]))
        assert sub.status_code == 200, sub.text
        assert sub.json()["data"]["status"] == "SUBMITTED"

    def test_fuel_request_still_cannot_link_boq_item(self, client, setup):
        s = setup
        r = self._fuel(client, s, boq_item_id=s["boq_item_id"])
        assert r.status_code == 422, r.text
