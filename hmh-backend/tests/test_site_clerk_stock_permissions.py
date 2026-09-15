"""
Site Clerk stock permissions — server-side enforcement.

Requirements covered (client review, 2026-09-15):
 1. Site Clerk cannot manually create warehouse stock through the API
    (project add-material, main-warehouse receive, main-warehouse add-tool).
 2. Site Clerk cannot remove/write off stock through the API
    (project and main-warehouse adjustments), and cannot deactivate catalog items.
 3. Rejected calls write no stock ledger rows.
 4. Office roles keep the manual main-warehouse routes.
 5. Site Clerk can still transfer stock (site → lot, tool return, project
    transfer request) and still capture deliveries via the receiving workflow.
Site Manager is included for the manual routes because those routes are now
office-only, matching the existing project-level add-material/adjust guard.
"""

import json
import uuid

import pytest

from tests.conftest import (
    auth, login, make_item, make_lot, make_project, make_site, make_stock,
    make_supplier, make_user, make_user_project_access,
)

SITE_ROLES = ["SITE_STAFF", "SITE_MANAGER"]


@pytest.fixture
def setup(db, client):
    owner     = make_user(db, role="OWNER")
    office    = make_user(db, role="OFFICE_USER")
    project   = make_project(db, owner_id=owner["id"])
    project_b = make_project(db, owner_id=owner["id"])
    site      = make_site(db, project_id=project["id"])
    lot       = make_lot(db, project_id=project["id"], site_id=site["id"])
    item      = make_item(db, name="Brick Maxi")

    tokens = {"OFFICE_USER": login(client, office["email"], office["password"])}
    for role in SITE_ROLES:
        u = make_user(db, role=role)
        make_user_project_access(db, u["id"], project["id"])
        make_user_project_access(db, u["id"], project_b["id"])
        tokens[role] = login(client, u["email"], u["password"])

    return dict(
        project_id=project["id"], project_b_id=project_b["id"],
        site_id=site["id"], lot_id=lot["id"], item_id=item["id"], tokens=tokens,
    )


def _ledger_count(db):
    from app.models.stock import StockLedger
    return db.query(StockLedger).count()


def _manual_stock_calls(s):
    """(POST path, body) for every manual stock add/remove route."""
    return [
        (f"/api/v1/projects/{s['project_id']}/warehouse/add-material",
         {"name": "Clerk Added Cement", "quantity": 10, "unit": "bags"}),
        (f"/api/v1/projects/{s['project_id']}/warehouse/adjust",
         {"item_id": s["item_id"], "adjustment_type": "CORRECTION_SUB", "quantity": 5}),
        ("/api/v1/warehouse/main/receive",
         {"item_id": s["item_id"], "quantity": 10}),
        ("/api/v1/warehouse/main/adjust",
         {"item_id": s["item_id"], "adjustment_type": "CORRECTION_SUB", "quantity": 5}),
        ("/api/v1/warehouse/main/adjust",
         {"item_id": s["item_id"], "adjustment_type": "DAMAGED", "quantity": 5}),
        ("/api/v1/warehouse/main/add-tool",
         {"name": "Clerk Added Grinder", "quantity": 1}),
    ]


class TestSiteRolesCannotManipulateStock:

    @pytest.mark.parametrize("role", SITE_ROLES)
    def test_manual_stock_routes_forbidden(self, client, db, setup, role):
        s = setup
        make_stock(db, s["project_id"], None, s["item_id"], qty=100)
        before = _ledger_count(db)

        for path, body in _manual_stock_calls(s):
            r = client.post(path, json=body, headers=auth(s["tokens"][role]))
            assert r.status_code == 403, f"{role} {path} {body.get('adjustment_type', '')}: {r.status_code} {r.text}"

        assert _ledger_count(db) == before, "a forbidden call must not write stock ledger rows"

    def test_project_warehouse_balance_unchanged_after_clerk_write_off_attempt(self, client, db, setup):
        s = setup
        make_stock(db, s["project_id"], None, s["item_id"], qty=100)
        tok = s["tokens"]["SITE_STAFF"]

        for adj in ("CORRECTION_SUB", "DAMAGED", "LOST"):
            r = client.post(
                f"/api/v1/projects/{s['project_id']}/warehouse/adjust",
                json={"item_id": s["item_id"], "adjustment_type": adj, "quantity": 100},
                headers=auth(tok),
            )
            assert r.status_code == 403, r.text

        stock = client.get(f"/api/v1/projects/{s['project_id']}/warehouse/", headers=auth(tok)).json()["data"]
        row = next(x for x in stock if x["item_id"] == s["item_id"])
        assert row["on_hand"] == pytest.approx(100)

    def test_clerk_cannot_deactivate_catalog_item(self, client, setup):
        s = setup
        r = client.patch(f"/api/v1/items/{s['item_id']}", json={"is_active": False},
                         headers=auth(s["tokens"]["SITE_STAFF"]))
        assert r.status_code == 403, r.text


class TestOfficeKeepsManualMainWarehouseRoutes:

    def test_office_can_receive_adjust_and_add_tool(self, client, db, setup):
        s = setup
        tok = s["tokens"]["OFFICE_USER"]

        r = client.post("/api/v1/warehouse/main/receive",
                        json={"item_id": s["item_id"], "quantity": 20}, headers=auth(tok))
        assert r.status_code == 201, r.text

        r = client.post("/api/v1/warehouse/main/adjust",
                        json={"item_id": s["item_id"], "adjustment_type": "DAMAGED", "quantity": 2},
                        headers=auth(tok))
        assert r.status_code == 201, r.text

        r = client.post("/api/v1/warehouse/main/add-tool",
                        json={"name": f"Office Drill {uuid.uuid4().hex[:4]}", "quantity": 1},
                        headers=auth(tok))
        assert r.status_code == 201, r.text


class TestSiteClerkTransfersAndReceivingStillWork:

    def test_site_warehouse_to_lot_transfer(self, client, db, setup):
        s = setup
        make_stock(db, s["project_id"], s["site_id"], s["item_id"], qty=50)
        tok = s["tokens"]["SITE_STAFF"]

        r = client.post(f"/api/v1/sites/{s['site_id']}/warehouse/transfer",
                        json={"item_id": s["item_id"], "lot_id": s["lot_id"], "quantity": 10},
                        headers=auth(tok))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["new_balance"] == pytest.approx(40)

        stock = client.get(f"/api/v1/sites/{s['site_id']}/warehouse/", headers=auth(tok)).json()["data"]
        assert next(x for x in stock if x["item_id"] == s["item_id"])["on_hand"] == pytest.approx(40)

    def test_tool_return_to_main_warehouse(self, client, db, setup):
        s = setup
        tool = make_item(db, name="Angle Grinder", unit="ea", item_type="TOOL")
        make_stock(db, s["project_id"], s["site_id"], tool["id"], qty=2)

        r = client.post(f"/api/v1/sites/{s['site_id']}/warehouse/return-tools",
                        json={"item_id": tool["id"], "quantity": 1},
                        headers=auth(s["tokens"]["SITE_STAFF"]))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["new_balance"] == pytest.approx(1)

    def test_project_transfer_request(self, client, db, setup):
        s = setup
        make_stock(db, s["project_id"], None, s["item_id"], qty=40)

        r = client.post(f"/api/v1/projects/{s['project_id']}/warehouse-transfers/",
                        json={"to_project_id": s["project_b_id"], "item_id": s["item_id"],
                              "quantity": 15, "reason": "Needed on project B"},
                        headers=auth(s["tokens"]["SITE_STAFF"]))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "PENDING"

    def test_clerk_can_capture_delivery_via_receiving_workflow(self, client, db, setup):
        s = setup
        supplier = make_supplier(db)
        r = client.post(
            "/api/v1/deliveries/receive-with-document",
            data={
                "project_id": s["project_id"],
                "site_id": s["site_id"],
                "supplier_id": supplier["id"],
                "delivery_note_number": f"DN-{uuid.uuid4().hex[:6]}",
                "items_json": json.dumps([{"description": "Brick Maxi", "unit": "ea",
                                           "quantity_expected": 500, "quantity_received": 500,
                                           "quantity_rejected": 0}]),
                "receiver_name": "Site Clerk",
                "receiver_signature": "SC",
            },
            headers=auth(s["tokens"]["SITE_STAFF"]),
        )
        assert r.status_code == 201, r.text
