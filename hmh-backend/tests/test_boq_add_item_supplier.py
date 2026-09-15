"""
BOQ builder — supplier chosen during initial item creation.

Requirements covered (client review, 2026-09-15):
 1. A new BOQ item created with a supplier persists that supplier (and specification).
 2. The full BOQ view the builder's edit form reads returns the same supplier.
 3. Supplier stays optional on create.
 4. Existing BOQ items and supplier records are unaffected.
"""

import uuid

import pytest
from sqlalchemy import update

from tests.conftest import (
    auth, login, make_boq_item, make_item, make_lot, make_project, make_site,
    make_supplier, make_user,
)


@pytest.fixture
def setup(db, client):
    from app.models.boq import BOQItem

    admin   = make_user(db, role="OFFICE_ADMIN")
    project = make_project(db, owner_id=admin["id"])
    site    = make_site(db, project_id=project["id"])
    lot     = make_lot(db, project_id=project["id"], site_id=site["id"])
    item    = make_item(db, name="Existing Sand")
    existing = make_boq_item(db, project["id"], lot["id"], item["id"])
    existing_supplier = make_supplier(db, name=f"Existing Sand Co {uuid.uuid4().hex[:4]}")
    new_supplier      = make_supplier(db, name=f"New Steel Co {uuid.uuid4().hex[:4]}")
    db.execute(
        update(BOQItem)
        .where(BOQItem.id == uuid.UUID(existing["boq_item_id"]))
        .values(supplier_id=uuid.UUID(existing_supplier["id"]))
    )
    db.flush()
    return dict(
        project_id=project["id"], header_id=existing["header_id"], section_id=existing["section_id"],
        existing_item_id=existing["boq_item_id"],
        existing_supplier=existing_supplier, new_supplier=new_supplier,
        tok=login(client, admin["email"], admin["password"]),
    )


def _create(client, s, **fields):
    body = {
        "raw_description": f"Y12 rebar {uuid.uuid4().hex[:4]}",
        "item_type": "MATERIAL", "unit": "t", "planned_quantity": 4, "planned_rate": 18500,
    }
    body.update(fields)
    return client.post(f"/api/v1/boq/sections/{s['section_id']}/items/", json=body, headers=auth(s["tok"]))


def _full_items(client, s):
    r = client.get(f"/api/v1/projects/{s['project_id']}/boq/{s['header_id']}/full", headers=auth(s["tok"]))
    assert r.status_code == 200, r.text
    return {i["id"]: i for sec in r.json()["data"]["sections"] for i in sec["items"]}


class TestAddItemWithSupplier:

    def test_supplier_and_specification_persist_on_create(self, client, db, setup):
        from app.models.boq import BOQItem
        s = setup
        r = _create(client, s, supplier_id=s["new_supplier"]["id"], specification="SANS 920 high-yield")
        assert r.status_code == 201, r.text
        created = r.json()["data"]
        assert created["supplier_id"] == s["new_supplier"]["id"]
        assert created["specification"] == "SANS 920 high-yield"

        db.expire_all()
        row = db.get(BOQItem, uuid.UUID(created["id"]))
        assert str(row.supplier_id) == s["new_supplier"]["id"]

    def test_full_boq_used_by_edit_form_shows_same_supplier(self, client, setup):
        s = setup
        created = _create(client, s, supplier_id=s["new_supplier"]["id"]).json()["data"]
        items = _full_items(client, s)
        assert items[created["id"]]["supplier_id"] == s["new_supplier"]["id"]

    def test_supplier_optional_on_create(self, client, setup):
        s = setup
        r = _create(client, s)
        assert r.status_code == 201, r.text
        assert r.json()["data"]["supplier_id"] is None

    def test_existing_items_and_suppliers_unaffected(self, client, db, setup):
        from app.models.supplier import Supplier
        s = setup
        suppliers_before = {(str(x.id), x.name, x.is_active) for x in db.query(Supplier).all()}

        assert _create(client, s, supplier_id=s["new_supplier"]["id"]).status_code == 201

        items = _full_items(client, s)
        assert items[s["existing_item_id"]]["supplier_id"] == s["existing_supplier"]["id"]
        db.expire_all()
        assert {(str(x.id), x.name, x.is_active) for x in db.query(Supplier).all()} == suppliers_before
