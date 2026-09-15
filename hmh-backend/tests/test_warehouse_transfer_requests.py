"""
Site Clerk project transfers go through the vote-based warehouse transfer request.

Client rule (2026-09-15): a Site Clerk may capture deliveries and transfer or
request transfer of stock, but may not manually add, adjust, write off, remove
or delete stock.

Requirements covered:
 1. Site Clerk can submit a project-to-project transfer request.
 2. Submitting alone moves no stock (request stays PENDING, ledger untouched).
 3. Site Clerk cannot execute the transfer: vote, override, reject and the direct
    transfer-to-project route are all refused, and stock stays put.
 4. Below the approval threshold, stock is unchanged; duplicate votes are refused.
 5. The existing office approval (3 votes) or owner override executes the transfer.
 6. A rejected request never moves stock.
 7. Destination-project authorization: a Site Clerk cannot request a transfer
    into, or send main-warehouse stock to a site on, a project they cannot access.
"""

import uuid
from datetime import datetime, timezone

import pytest

from tests.conftest import (
    auth, login, make_item, make_project, make_site, make_stock, make_user,
    make_user_project_access,
)


@pytest.fixture
def setup(db, client):
    owner     = make_user(db, role="OWNER")
    clerk     = make_user(db, role="SITE_STAFF")
    voters    = [make_user(db, role=r) for r in ("OFFICE_USER", "OFFICE_ADMIN", "PROCUREMENT_LEAD")]
    project_a = make_project(db, owner_id=owner["id"])
    project_b = make_project(db, owner_id=owner["id"])
    project_c = make_project(db, owner_id=owner["id"])  # clerk has no access
    item      = make_item(db, name="Paving Blocks")
    make_stock(db, project_a["id"], None, item["id"], qty=40)
    make_stock(db, project_c["id"], None, item["id"], qty=40)
    make_user_project_access(db, clerk["id"], project_a["id"])
    make_user_project_access(db, clerk["id"], project_b["id"])

    return dict(
        a=project_a["id"], b=project_b["id"], c=project_c["id"], item_id=item["id"],
        clerk_tok=login(client, clerk["email"], clerk["password"]),
        owner_tok=login(client, owner["email"], owner["password"]),
        voter_toks=[login(client, v["email"], v["password"]) for v in voters],
    )


def _on_hand(db, project_id, item_id):
    from sqlalchemy import text
    db.expire_all()
    row = db.execute(text("""
        SELECT COALESCE(SUM(quantity_in) - SUM(quantity_out), 0)
        FROM stock_ledger
        WHERE project_id = :p AND item_id = :i AND site_id IS NULL AND lot_id IS NULL
    """), {"p": project_id, "i": item_id}).scalar()
    return float(row)


def _ledger_count(db):
    from app.models.stock import StockLedger
    return db.query(StockLedger).count()


def _submit(client, s, tok=None, from_project=None, to_project=None, quantity=15):
    return client.post(
        f"/api/v1/projects/{from_project or s['a']}/warehouse-transfers/",
        json={"to_project_id": to_project or s["b"], "item_id": s["item_id"],
              "quantity": quantity, "reason": "Needed on project B"},
        headers=auth(tok or s["clerk_tok"]),
    )


def _vote(client, transfer_id, tok):
    return client.post(f"/api/v1/warehouse-transfers/{transfer_id}/vote", json={}, headers=auth(tok))


class TestSiteClerkSubmitsRequest:

    def test_submit_creates_pending_request_and_moves_no_stock(self, client, db, setup):
        from app.models.warehouse_transfer import WarehouseTransferRequest
        s = setup
        ledger_before = _ledger_count(db)

        r = _submit(client, s)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["status"] == "PENDING"
        assert data["vote_count"] == 0
        assert data["votes_required"] == 3
        assert data["from_project_id"] == s["a"] and data["to_project_id"] == s["b"]
        assert data["quantity"] == pytest.approx(15)

        assert db.get(WarehouseTransferRequest, uuid.UUID(data["id"])) is not None
        assert _ledger_count(db) == ledger_before
        assert _on_hand(db, s["a"], s["item_id"]) == pytest.approx(40)
        assert _on_hand(db, s["b"], s["item_id"]) == pytest.approx(0)

    def test_request_above_on_hand_is_refused(self, client, db, setup):
        from app.models.warehouse_transfer import WarehouseTransferRequest
        s = setup
        before = db.query(WarehouseTransferRequest).count()
        r = _submit(client, s, quantity=100)
        assert r.status_code == 400, r.text
        assert db.query(WarehouseTransferRequest).count() == before


class TestSiteClerkCannotExecute:

    def test_clerk_cannot_vote_override_or_reject(self, client, db, setup):
        s = setup
        transfer_id = _submit(client, s).json()["data"]["id"]
        ledger_before = _ledger_count(db)

        assert _vote(client, transfer_id, s["clerk_tok"]).status_code == 403
        r = client.post(f"/api/v1/warehouse-transfers/{transfer_id}/override", json={}, headers=auth(s["clerk_tok"]))
        assert r.status_code == 403, r.text
        r = client.post(f"/api/v1/warehouse-transfers/{transfer_id}/reject",
                        json={"reason": "changed my mind"}, headers=auth(s["clerk_tok"]))
        assert r.status_code == 403, r.text

        r = client.get(f"/api/v1/warehouse-transfers/{transfer_id}", headers=auth(s["owner_tok"]))
        assert r.json()["data"]["status"] == "PENDING"
        assert r.json()["data"]["vote_count"] == 0
        assert _ledger_count(db) == ledger_before
        assert _on_hand(db, s["a"], s["item_id"]) == pytest.approx(40)

    def test_clerk_cannot_use_direct_transfer_to_project(self, client, db, setup):
        s = setup
        ledger_before = _ledger_count(db)
        r = client.post(
            f"/api/v1/projects/{s['a']}/warehouse/transfer-to-project",
            json={"to_project_id": s["b"], "item_id": s["item_id"], "quantity": 15},
            headers=auth(s["clerk_tok"]),
        )
        assert r.status_code == 403, r.text
        assert _ledger_count(db) == ledger_before
        assert _on_hand(db, s["b"], s["item_id"]) == pytest.approx(0)


class TestOfficeApproval:

    def test_insufficient_votes_leave_stock_unchanged(self, client, db, setup):
        s = setup
        transfer_id = _submit(client, s).json()["data"]["id"]

        for tok in s["voter_toks"][:2]:
            r = _vote(client, transfer_id, tok)
            assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "PENDING"
        assert r.json()["data"]["vote_count"] == 2

        dup = _vote(client, transfer_id, s["voter_toks"][0])
        assert dup.status_code == 409, dup.text

        assert _on_hand(db, s["a"], s["item_id"]) == pytest.approx(40)
        assert _on_hand(db, s["b"], s["item_id"]) == pytest.approx(0)

    def test_third_office_vote_executes_transfer(self, client, db, setup):
        from app.models.stock import StockLedger
        s = setup
        transfer_id = _submit(client, s).json()["data"]["id"]

        for tok in s["voter_toks"]:
            r = _vote(client, transfer_id, tok)
            assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "EXECUTED"

        assert _on_hand(db, s["a"], s["item_id"]) == pytest.approx(25)
        assert _on_hand(db, s["b"], s["item_id"]) == pytest.approx(15)
        rows = db.query(StockLedger).filter(
            StockLedger.item_id == uuid.UUID(s["item_id"]),
            StockLedger.reference_type == "project_to_project_transfer",
        ).all()
        assert sorted(r.movement_type.value for r in rows) == ["TRANSFER_IN", "TRANSFER_OUT"]

    def test_owner_override_executes_transfer(self, client, db, setup):
        s = setup
        transfer_id = _submit(client, s).json()["data"]["id"]
        r = client.post(f"/api/v1/warehouse-transfers/{transfer_id}/override", json={}, headers=auth(s["owner_tok"]))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "EXECUTED"
        assert _on_hand(db, s["a"], s["item_id"]) == pytest.approx(25)
        assert _on_hand(db, s["b"], s["item_id"]) == pytest.approx(15)

    def test_rejected_request_moves_no_stock(self, client, db, setup):
        s = setup
        transfer_id = _submit(client, s).json()["data"]["id"]
        r = client.post(f"/api/v1/warehouse-transfers/{transfer_id}/reject",
                        json={"reason": "Not needed"}, headers=auth(s["voter_toks"][0]))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "REJECTED"
        assert _vote(client, transfer_id, s["voter_toks"][1]).status_code == 400
        assert _on_hand(db, s["a"], s["item_id"]) == pytest.approx(40)
        assert _on_hand(db, s["b"], s["item_id"]) == pytest.approx(0)


class TestDestinationProjectAuthorization:

    def test_clerk_cannot_request_transfer_into_inaccessible_project(self, client, db, setup):
        from app.models.warehouse_transfer import WarehouseTransferRequest
        s = setup
        before = db.query(WarehouseTransferRequest).count()
        r = _submit(client, s, to_project=s["c"])
        assert r.status_code == 403, r.text
        assert db.query(WarehouseTransferRequest).count() == before

    def test_clerk_cannot_request_transfer_out_of_inaccessible_project(self, client, setup):
        s = setup
        r = _submit(client, s, from_project=s["c"], to_project=s["a"])
        assert r.status_code == 403, r.text

    def test_office_can_request_between_any_projects(self, client, setup):
        s = setup
        r = _submit(client, s, tok=s["voter_toks"][0], to_project=s["c"])
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "PENDING"

    def _seed_global_stock(self, db, item_id, qty=30):
        from app.models.enums import MovementType
        from app.models.stock import StockLedger
        now = datetime.now(timezone.utc)
        db.add(StockLedger(
            project_id=None, site_id=None, lot_id=None, item_id=uuid.UUID(item_id),
            movement_type=MovementType.OPENING_BALANCE, reference_type="test_opening",
            quantity_in=qty, quantity_out=0, unit="ea", movement_date=now, entered_by=None, created_at=now,
        ))
        db.flush()

    def test_global_transfer_to_site_enforces_destination_project_access(self, client, db, setup):
        s = setup
        self._seed_global_stock(db, s["item_id"])
        site_a = make_site(db, s["a"], name="Site A Store")
        site_c = make_site(db, s["c"], name="Site C Store")
        body = lambda site_id: {"item_id": s["item_id"], "site_id": site_id, "quantity": 5}
        ledger_before = _ledger_count(db)

        r = client.post("/api/v1/warehouse/main/transfer-to-site", json=body(site_c["id"]), headers=auth(s["clerk_tok"]))
        assert r.status_code == 403, r.text
        assert _ledger_count(db) == ledger_before

        r = client.post("/api/v1/warehouse/main/transfer-to-site", json=body(site_a["id"]), headers=auth(s["clerk_tok"]))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["new_balance"] == pytest.approx(25)

        r = client.post("/api/v1/warehouse/main/transfer-to-site", json=body(site_c["id"]), headers=auth(s["voter_toks"][0]))
        assert r.status_code == 200, r.text
