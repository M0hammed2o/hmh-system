"""
Mechanic payment tracking.

The office needs to see what is still owed to each mechanic. The property
everything rests on: **what is owed is derived from the repair, never stored
again.** There is no status field anyone can set to "Paid" while money is
outstanding, and recording a payment never creates a second expense for a
cost the books have already recognised.
"""

import uuid
from datetime import date, datetime, timezone

import pytest

from tests.conftest import (
    auth, login, make_project, make_site, make_supplier, make_user,
)


def _now():
    return datetime.now(timezone.utc)


def _vehicle(db, *, name="Tipper", project_id=None):
    from app.models.vehicle import Vehicle

    v = Vehicle(
        registration=f"ND {uuid.uuid4().hex[:5].upper()}",
        name=name,
        assigned_project_id=uuid.UUID(project_id) if project_id else None,
        created_at=_now(), updated_at=_now(),
    )
    db.add(v)
    db.flush()
    return v


def _repair(db, vehicle, *, title="Gearbox overhaul", quote=None, invoice=None,
            workshop="Durban Diesel", opened=None):
    from app.models.vehicle import RepairJob

    j = RepairJob(
        vehicle_id=vehicle.id,
        title=title,
        status="OPEN",
        workshop_name=workshop,
        date_opened=opened or date(2026, 3, 1),
        quote_amount=quote,
        invoice_amount=invoice,
        created_at=_now(), updated_at=_now(),
    )
    db.add(j)
    db.flush()
    return j


def _cost(db, vehicle, repair, amount, *, cost_type="REPAIR"):
    from app.models.vehicle import VehicleCost

    c = VehicleCost(
        vehicle_id=vehicle.id,
        repair_job_id=repair.id,
        cost_type=cost_type,
        amount=amount,
        cost_date=date(2026, 3, 1),
        created_at=_now(),
    )
    db.add(c)
    db.flush()
    return c


@pytest.fixture()
def world(db):
    owner = make_user(db, role="OWNER")
    project = make_project(db, owner["id"])
    site = make_site(db, project["id"])
    vehicle = _vehicle(db, project_id=project["id"])
    db.commit()
    return {"owner": owner, "project": project, "site": site, "vehicle": vehicle}


def _token(client, world):
    return login(client, world["owner"]["email"], "Test@1234")


def _error_text(response) -> str:
    """
    The message, whichever envelope produced it.

    Service-raised HMHExceptions surface as `message`; FastAPI's own
    HTTPException uses `detail`. A test about what the user is told should
    not care which layer refused.
    """
    body = response.json()
    return str(body.get("message") or body.get("detail") or body)


def _pay(client, token, repair_id, amount, **kw):
    body = {"amount": amount, "payment_date": kw.pop("payment_date", "2026-03-10"), **kw}
    return client.post(f"/api/v1/workshop/repairs/{repair_id}/payments",
                       json=body, headers=auth(token))


def _history(client, token, repair_id):
    r = client.get(f"/api/v1/workshop/repairs/{repair_id}/payments", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ── The scenario from the brief ──────────────────────────────────────────────

def test_five_thousand_repair_paid_in_two_instalments(db, client, world):
    """
    Repair R5,000. Pay R2,000 → R3,000 outstanding, Partially Paid.
    Pay R3,000 → nothing outstanding, Paid.
    """
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)

    before = _history(client, token, job.id)
    assert before["total_payable"] == 5000.0
    assert before["total_paid"] == 0.0
    assert before["outstanding"] == 5000.0
    assert before["payment_status"] == "UNPAID"

    r = _pay(client, token, job.id, 2000)
    assert r.status_code == 201, r.text
    mid = r.json()["data"]
    assert mid["total_paid"] == 2000.0
    assert mid["outstanding"] == 3000.0
    assert mid["payment_status"] == "PARTIALLY_PAID"

    r = _pay(client, token, job.id, 3000, payment_date="2026-03-20")
    assert r.status_code == 201, r.text
    end = r.json()["data"]
    assert end["total_paid"] == 5000.0
    assert end["outstanding"] == 0.0
    assert end["payment_status"] == "PAID"


def test_one_repair_can_have_many_payments(db, client, world):
    job = _repair(db, world["vehicle"], invoice=900)
    db.commit()
    token = _token(client, world)

    for amount in (300, 300, 300):
        assert _pay(client, token, job.id, amount).status_code == 201

    history = _history(client, token, job.id)
    assert len(history["payments"]) == 3
    assert history["payment_status"] == "PAID"


# ── What is owed comes from the repair ───────────────────────────────────────

def test_the_invoice_is_what_is_owed_when_there_is_one(db, client, world):
    job = _repair(db, world["vehicle"], quote=4000, invoice=4600)
    db.commit()
    data = _history(client, _token(client, world), job.id)
    assert data["total_payable"] == 4600.0
    assert data["payable_basis"] == "invoice"


def test_the_quote_is_used_until_an_invoice_arrives(db, client, world):
    job = _repair(db, world["vehicle"], quote=4000)
    db.commit()
    data = _history(client, _token(client, world), job.id)
    assert data["total_payable"] == 4000.0
    assert data["payable_basis"] == "quote"


def test_booked_costs_are_used_when_there_is_no_paperwork(db, client, world):
    job = _repair(db, world["vehicle"])
    _cost(db, world["vehicle"], job, 1200)
    _cost(db, world["vehicle"], job, 800)
    db.commit()
    data = _history(client, _token(client, world), job.id)
    assert data["total_payable"] == 2000.0
    assert data["payable_basis"] == "recorded labour"


def test_recording_a_payment_does_not_add_to_what_the_repair_cost(db, client, world):
    """
    The crucial property: a payment settles a cost already recognised. If
    recording one changed the payable figure, the repair would be counted
    twice in the books.
    """
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)

    _pay(client, token, job.id, 2000)
    assert _history(client, token, job.id)["total_payable"] == 5000.0

    _pay(client, token, job.id, 1000, payment_reference="EFT-2")
    assert _history(client, token, job.id)["total_payable"] == 5000.0


def test_no_vehicle_cost_row_is_created_by_a_payment(db, client, world):
    from app.models.vehicle import VehicleCost

    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    before = db.query(VehicleCost).count()

    _pay(client, _token(client, world), job.id, 2000)
    assert db.query(VehicleCost).count() == before


# ── Status is derived, not chosen ────────────────────────────────────────────

@pytest.mark.parametrize("paid,expected", [
    (0, "UNPAID"),
    (1, "PARTIALLY_PAID"),
    (4999, "PARTIALLY_PAID"),
    (5000, "PAID"),
])
def test_status_follows_the_money(db, client, world, paid, expected):
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)
    if paid:
        assert _pay(client, token, job.id, paid).status_code == 201
    assert _history(client, token, job.id)["payment_status"] == expected


def test_a_fraction_of_a_cent_still_reads_as_paid(db, client, world):
    """Rounding must not leave a repair owing R0.004 for ever."""
    job = _repair(db, world["vehicle"], invoice=100.00)
    db.commit()
    token = _token(client, world)
    _pay(client, token, job.id, 33.33)
    _pay(client, token, job.id, 33.33, payment_reference="b")
    _pay(client, token, job.id, 33.34, payment_reference="c")
    assert _history(client, token, job.id)["payment_status"] == "PAID"


def test_there_is_no_way_to_set_the_status_by_hand(db, client, world):
    """A status field someone can set is a status that disagrees with the money."""
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)

    r = _pay(client, token, job.id, 100, payment_status="PAID", status="PAID")
    assert r.status_code == 201
    assert _history(client, token, job.id)["payment_status"] == "PARTIALLY_PAID"


# ── Refusals ─────────────────────────────────────────────────────────────────

def test_overpayment_is_refused(db, client, world):
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)
    _pay(client, token, job.id, 4000)

    r = _pay(client, token, job.id, 2000, payment_reference="second")
    assert r.status_code == 409
    assert "1000.00 is outstanding" in _error_text(r)


def test_a_single_payment_larger_than_the_repair_is_refused(db, client, world):
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    r = _pay(client, _token(client, world), job.id, 5000.01)
    assert r.status_code == 409


def test_a_negative_payment_is_refused(db, client, world):
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    r = _pay(client, _token(client, world), job.id, -100)
    assert r.status_code in (400, 422)


def test_a_zero_payment_is_refused(db, client, world):
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    r = _pay(client, _token(client, world), job.id, 0)
    assert r.status_code in (400, 422)


def test_the_same_reference_cannot_be_recorded_twice(db, client, world):
    """A double-tapped submit must not show the mechanic as paid twice."""
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)

    assert _pay(client, token, job.id, 1000, payment_reference="EFT-55012").status_code == 201
    r = _pay(client, token, job.id, 1000, payment_reference="EFT-55012")
    assert r.status_code == 409
    assert "already recorded" in _error_text(r)


def test_references_are_matched_ignoring_case_and_space(db, client, world):
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)

    _pay(client, token, job.id, 1000, payment_reference="EFT-55012")
    r = _pay(client, token, job.id, 1000, payment_reference=" eft-55012 ")
    assert r.status_code == 409


def test_payments_without_a_reference_do_not_collide(db, client, world):
    """Cash payments often have no reference; blanks must not block each other."""
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)

    assert _pay(client, token, job.id, 1000).status_code == 201
    assert _pay(client, token, job.id, 1000).status_code == 201
    assert _history(client, token, job.id)["total_paid"] == 2000.0


def test_a_repair_with_no_cost_recorded_cannot_be_paid(db, client, world):
    job = _repair(db, world["vehicle"])
    db.commit()
    r = _pay(client, _token(client, world), job.id, 500)
    assert r.status_code in (400, 422)
    assert "Nothing is owed to a mechanic" in _error_text(r)


def test_paying_an_unknown_repair_is_a_404(client, world):
    r = _pay(client, _token(client, world), uuid.uuid4(), 100)
    assert r.status_code == 404


# ── Reversal, not deletion ───────────────────────────────────────────────────

def test_a_payment_can_be_reversed_and_stops_counting(db, client, world):
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)

    pid = _pay(client, token, job.id, 2000).json()["data"]["payment"]["id"]
    assert _history(client, token, job.id)["total_paid"] == 2000.0

    r = client.post(f"/api/v1/workshop/mechanic-payments/{pid}/reverse",
                    json={"reason": "Captured against the wrong repair"},
                    headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["outstanding"] == 5000.0
    assert _history(client, token, job.id)["total_paid"] == 0.0


def test_a_reversed_payment_is_still_visible(db, client, world):
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)

    pid = _pay(client, token, job.id, 2000).json()["data"]["payment"]["id"]
    client.post(f"/api/v1/workshop/mechanic-payments/{pid}/reverse",
                json={"reason": "wrong repair"}, headers=auth(token))

    payments = _history(client, token, job.id)["payments"]
    assert len(payments) == 1
    assert payments[0]["is_reversed"] is True
    assert payments[0]["reversal_reason"] == "wrong repair"


def test_a_reversal_needs_a_reason(db, client, world):
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)
    pid = _pay(client, token, job.id, 2000).json()["data"]["payment"]["id"]

    r = client.post(f"/api/v1/workshop/mechanic-payments/{pid}/reverse",
                    json={"reason": "   "}, headers=auth(token))
    assert r.status_code in (400, 422)


def test_a_payment_cannot_be_reversed_twice(db, client, world):
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)
    pid = _pay(client, token, job.id, 2000).json()["data"]["payment"]["id"]

    client.post(f"/api/v1/workshop/mechanic-payments/{pid}/reverse",
                json={"reason": "a"}, headers=auth(token))
    r = client.post(f"/api/v1/workshop/mechanic-payments/{pid}/reverse",
                    json={"reason": "b"}, headers=auth(token))
    assert r.status_code == 409


def test_a_reversed_reference_can_be_used_again(db, client, world):
    """Correcting a mistake must not be blocked by the mistake."""
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)

    pid = _pay(client, token, job.id, 2000, payment_reference="EFT-1").json()["data"]["payment"]["id"]
    client.post(f"/api/v1/workshop/mechanic-payments/{pid}/reverse",
                json={"reason": "wrong amount"}, headers=auth(token))

    assert _pay(client, token, job.id, 2500, payment_reference="EFT-1").status_code == 201


def test_payments_are_audited(db, client, world):
    from app.models.audit import AuditEvent

    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)
    pid = _pay(client, token, job.id, 2000).json()["data"]["payment"]["id"]

    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.entity_type == "mechanic_payment",
                AuditEvent.entity_id == uuid.UUID(pid))
        .all()
    )
    assert len(events) == 1
    assert events[0].after_value["amount"] == 2000.0
    assert events[0].actor_id == uuid.UUID(world["owner"]["id"])


def test_reversals_are_audited(db, client, world):
    from app.models.audit import AuditEvent

    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)
    pid = _pay(client, token, job.id, 2000).json()["data"]["payment"]["id"]
    client.post(f"/api/v1/workshop/mechanic-payments/{pid}/reverse",
                json={"reason": "wrong repair"}, headers=auth(token))

    assert db.query(AuditEvent).filter(
        AuditEvent.entity_type == "mechanic_payment",
        AuditEvent.entity_id == uuid.UUID(pid)).count() == 2


def test_there_is_no_delete_endpoint(db, client, world):
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)
    pid = _pay(client, token, job.id, 2000).json()["data"]["payment"]["id"]

    r = client.delete(f"/api/v1/workshop/mechanic-payments/{pid}", headers=auth(token))
    assert r.status_code in (404, 405)


# ── Suppliers are reused, not replaced ───────────────────────────────────────

def test_a_mechanic_that_is_a_supplier_keeps_that_link(db, client, world):
    supplier = make_supplier(db, name="Durban Diesel CC")
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)

    r = _pay(client, token, job.id, 2000, supplier_id=supplier["id"])
    assert r.status_code == 201, r.text
    assert r.json()["data"]["payment"]["supplier_id"] == supplier["id"]


def test_a_mechanic_who_is_not_a_supplier_is_recorded_by_name(db, client, world):
    """Requiring a supplier record for every roadside repair would be worse."""
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    r = _pay(client, _token(client, world), job.id, 2000, mechanic_name="Sipho's Mobile Repairs")
    assert r.status_code == 201
    assert r.json()["data"]["payment"]["supplier_id"] is None
    assert r.json()["data"]["payment"]["mechanic_name"] == "Sipho's Mobile Repairs"


def test_the_mechanic_defaults_to_the_workshop_on_the_repair(db, client, world):
    job = _repair(db, world["vehicle"], invoice=5000, workshop="Pinetown Motors")
    db.commit()
    r = _pay(client, _token(client, world), job.id, 2000)
    assert r.json()["data"]["payment"]["mechanic_name"] == "Pinetown Motors"


# ── The overview ─────────────────────────────────────────────────────────────

def _overview(client, token, query=""):
    r = client.get(f"/api/v1/workshop/mechanic-payments{query}", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_the_overview_totals_what_is_owed(db, client, world):
    a = _repair(db, world["vehicle"], invoice=5000, title="A")
    b = _repair(db, world["vehicle"], invoice=3000, title="B")
    db.commit()
    token = _token(client, world)
    _pay(client, token, a.id, 2000)

    data = _overview(client, token)
    assert data["totals"]["total_payable"] == 8000.0
    assert data["totals"]["total_paid"] == 2000.0
    assert data["totals"]["total_outstanding"] == 6000.0
    assert data["totals"]["unpaid"] == 1
    assert data["totals"]["partially_paid"] == 1


def test_repairs_with_nothing_recognised_are_not_listed_as_payable(db, client, world):
    _repair(db, world["vehicle"], invoice=5000, title="Real")
    _repair(db, world["vehicle"], title="No cost captured")
    db.commit()

    data = _overview(client, _token(client, world))
    assert [r["repair_title"] for r in data["items"]] == ["Real"]


def test_unpaid_repairs_can_be_isolated(db, client, world):
    a = _repair(db, world["vehicle"], invoice=1000, title="Settled")
    _repair(db, world["vehicle"], invoice=2000, title="Owing")
    db.commit()
    token = _token(client, world)
    _pay(client, token, a.id, 1000)

    data = _overview(client, token, "?unpaid_only=true")
    assert [r["repair_title"] for r in data["items"]] == ["Owing"]


def test_the_overview_filters_by_status(db, client, world):
    a = _repair(db, world["vehicle"], invoice=1000, title="Settled")
    _repair(db, world["vehicle"], invoice=2000, title="Owing")
    db.commit()
    token = _token(client, world)
    _pay(client, token, a.id, 1000)

    data = _overview(client, token, "?status=PAID")
    assert [r["repair_title"] for r in data["items"]] == ["Settled"]


def test_the_overview_filters_by_mechanic(db, client, world):
    _repair(db, world["vehicle"], invoice=1000, title="X", workshop="Durban Diesel")
    _repair(db, world["vehicle"], invoice=2000, title="Y", workshop="Pinetown Motors")
    db.commit()

    data = _overview(client, _token(client, world), "?mechanic=Pinetown")
    assert [r["repair_title"] for r in data["items"]] == ["Y"]


def test_the_overview_filters_by_vehicle(db, client, world):
    other = _vehicle(db, name="Bakkie")
    _repair(db, world["vehicle"], invoice=1000, title="Mine")
    _repair(db, other, invoice=2000, title="Theirs")
    db.commit()

    data = _overview(client, _token(client, world),
                     f"?vehicle_id={world['vehicle'].id}")
    assert [r["repair_title"] for r in data["items"]] == ["Mine"]


def test_the_overview_filters_by_date(db, client, world):
    _repair(db, world["vehicle"], invoice=1000, title="Jan", opened=date(2026, 1, 5))
    _repair(db, world["vehicle"], invoice=2000, title="Jun", opened=date(2026, 6, 5))
    db.commit()

    data = _overview(client, _token(client, world),
                     "?date_from=2026-05-01&date_to=2026-12-31")
    assert [r["repair_title"] for r in data["items"]] == ["Jun"]


def test_the_overview_filters_by_company(db, client, world):
    """A vehicle belongs to a company through the project it is assigned to."""
    other_owner = make_user(db, role="OWNER")
    other_project = make_project(db, other_owner["id"])
    other_vehicle = _vehicle(db, name="Theirs", project_id=other_project["id"])
    _repair(db, world["vehicle"], invoice=1000, title="Mine")
    _repair(db, other_vehicle, invoice=2000, title="Theirs")
    db.commit()

    from app.models.company import Company
    company = Company(name=f"Premium Structures {uuid.uuid4().hex[:4]}",
                      created_at=_now(), updated_at=_now())
    db.add(company)
    db.flush()
    from app.models.project import Project
    db.get(Project, uuid.UUID(world["project"]["id"])).company_id = company.id
    db.commit()

    data = _overview(client, _token(client, world), f"?company_id={company.id}")
    assert [r["repair_title"] for r in data["items"]] == ["Mine"]


def test_the_overview_shows_the_last_payment_date(db, client, world):
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)
    _pay(client, token, job.id, 1000, payment_date="2026-03-10")
    _pay(client, token, job.id, 1000, payment_date="2026-04-02", payment_reference="b")

    data = _overview(client, token)
    assert data["items"][0]["last_payment_date"] == "2026-04-02"


def test_the_overview_is_paginated(db, client, world):
    for i in range(12):
        _repair(db, world["vehicle"], invoice=100 + i, title=f"R{i:02d}")
    db.commit()

    data = _overview(client, _token(client, world), "?page=1&limit=5")
    assert data["total"] == 12
    assert len(data["items"]) == 5
    assert data["total_pages"] == 3


def test_overview_totals_cover_everything_matched_not_just_the_page(db, client, world):
    for i in range(12):
        _repair(db, world["vehicle"], invoice=1000, title=f"R{i:02d}")
    db.commit()

    data = _overview(client, _token(client, world), "?page=1&limit=5")
    assert data["totals"]["total_payable"] == 12000.0


# ── Access ───────────────────────────────────────────────────────────────────

def test_site_staff_cannot_record_a_mechanic_payment(db, client, world):
    job = _repair(db, world["vehicle"], invoice=5000)
    user = make_user(db, role="SITE_STAFF")
    db.commit()
    token = login(client, user["email"], "Test@1234")

    r = _pay(client, token, job.id, 100)
    assert r.status_code == 403


def test_site_staff_cannot_see_the_payments_overview(db, client, world):
    user = make_user(db, role="SITE_STAFF")
    db.commit()
    token = login(client, user["email"], "Test@1234")

    r = client.get("/api/v1/workshop/mechanic-payments", headers=auth(token))
    assert r.status_code == 403


def test_the_overview_is_not_public(client):
    assert client.get("/api/v1/workshop/mechanic-payments").status_code in (401, 403)


def test_only_an_admin_can_reverse_a_payment(db, client, world):
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)
    pid = _pay(client, token, job.id, 2000).json()["data"]["payment"]["id"]

    user = make_user(db, role="OFFICE_USER")
    db.commit()
    weak = login(client, user["email"], "Test@1234")

    r = client.post(f"/api/v1/workshop/mechanic-payments/{pid}/reverse",
                    json={"reason": "nope"}, headers=auth(weak))
    assert r.status_code == 403


# ── Editing a repair that has been paid ──────────────────────────────────────

def test_a_paid_repair_cannot_be_moved_to_another_vehicle(db, client, world):
    job = _repair(db, world["vehicle"], invoice=5000)
    other = _vehicle(db, name="Other")
    db.commit()
    token = _token(client, world)
    _pay(client, token, job.id, 2000)

    r = client.patch(f"/api/v1/vehicles/repairs/{job.id}",
                     json={"vehicle_id": str(other.id)}, headers=auth(token))
    assert r.status_code == 409
    assert "paid to the mechanic" in _error_text(r)


def test_the_amount_cannot_be_cut_below_what_was_paid(db, client, world):
    """That would turn a settled repair into an overpayment that never happened."""
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)
    _pay(client, token, job.id, 4000)

    r = client.patch(f"/api/v1/vehicles/repairs/{job.id}",
                     json={"invoice_amount": 1000}, headers=auth(token))
    assert r.status_code == 409
    assert "4000.00 has already been paid" in _error_text(r)


def test_the_amount_can_still_be_corrected_above_what_was_paid(db, client, world):
    job = _repair(db, world["vehicle"], invoice=5000)
    db.commit()
    token = _token(client, world)
    _pay(client, token, job.id, 4000)

    r = client.patch(f"/api/v1/vehicles/repairs/{job.id}",
                     json={"invoice_amount": 4500}, headers=auth(token))
    assert r.status_code == 200, r.text
    assert _history(client, token, job.id)["outstanding"] == 500.0


def test_reversing_the_payment_releases_the_lock(db, client, world):
    job = _repair(db, world["vehicle"], invoice=5000)
    other = _vehicle(db, name="Other")
    db.commit()
    token = _token(client, world)
    pid = _pay(client, token, job.id, 2000).json()["data"]["payment"]["id"]

    client.post(f"/api/v1/workshop/mechanic-payments/{pid}/reverse",
                json={"reason": "wrong repair"}, headers=auth(token))

    r = client.patch(f"/api/v1/vehicles/repairs/{job.id}",
                     json={"vehicle_id": str(other.id)}, headers=auth(token))
    assert r.status_code == 200, r.text


# ── Only the mechanic's own work is payable to the mechanic ──────────────────
#
# A repair can carry any VehicleCost type — the capture form offers all seven.
# Tyres from a tyre dealer, a licence renewal, fuel: those are owed to
# whoever supplied them. Counting them as owed to the mechanic would both
# overstate the balance and invite paying the same money twice.

def test_parts_and_licence_costs_are_not_owed_to_the_mechanic(db, client, world):
    job = _repair(db, world["vehicle"])
    _cost(db, world["vehicle"], job, 3000, cost_type="REPAIR")
    _cost(db, world["vehicle"], job, 2000, cost_type="TYRE")
    _cost(db, world["vehicle"], job, 500, cost_type="LICENCE")
    db.commit()

    data = _history(client, _token(client, world), job.id)
    assert data["total_payable"] == 3000.0
    assert data["payable_basis"] == "recorded labour"
    assert data["other_costs_not_payable_to_mechanic"] == 2500.0


def test_service_costs_count_as_the_mechanics_work(db, client, world):
    job = _repair(db, world["vehicle"])
    _cost(db, world["vehicle"], job, 1200, cost_type="REPAIR")
    _cost(db, world["vehicle"], job, 800, cost_type="SERVICE")
    db.commit()

    assert _history(client, _token(client, world), job.id)["total_payable"] == 2000.0


def test_fuel_booked_against_a_repair_is_never_payable(db, client, world):
    job = _repair(db, world["vehicle"])
    _cost(db, world["vehicle"], job, 1500, cost_type="FUEL")
    db.commit()

    data = _history(client, _token(client, world), job.id)
    assert data["total_payable"] == 0.0
    r = _pay(client, _token(client, world), job.id, 100)
    assert r.status_code in (400, 422)
    assert "Nothing is owed to a mechanic" in _error_text(r)


def test_an_unclassified_cost_is_not_assumed_to_be_the_mechanics(db, client, world):
    """Overstating what is owed is the worse error, so OTHER is excluded."""
    job = _repair(db, world["vehicle"])
    _cost(db, world["vehicle"], job, 900, cost_type="OTHER")
    db.commit()

    assert _history(client, _token(client, world), job.id)["total_payable"] == 0.0


def test_an_invoice_from_the_mechanic_covers_whatever_it_includes(db, client, world):
    """
    Parts on the mechanic's own invoice ARE theirs to be paid for, so an
    invoiced repair is not filtered — only loose cost rows are.
    """
    job = _repair(db, world["vehicle"], invoice=7500)
    _cost(db, world["vehicle"], job, 2000, cost_type="TYRE")
    db.commit()

    data = _history(client, _token(client, world), job.id)
    assert data["total_payable"] == 7500.0
    assert data["payable_basis"] == "invoice"


def test_the_overview_excludes_non_mechanic_costs_too(db, client, world):
    job = _repair(db, world["vehicle"], title="Mixed")
    _cost(db, world["vehicle"], job, 3000, cost_type="REPAIR")
    _cost(db, world["vehicle"], job, 4000, cost_type="TYRE")
    db.commit()

    data = _overview(client, _token(client, world))
    assert data["totals"]["total_payable"] == 3000.0
    assert data["totals"]["total_outstanding"] == 3000.0


def test_paying_cannot_exceed_the_mechanics_share(db, client, world):
    """The overpayment guard must use the filtered figure, not the gross spend."""
    job = _repair(db, world["vehicle"])
    _cost(db, world["vehicle"], job, 3000, cost_type="REPAIR")
    _cost(db, world["vehicle"], job, 5000, cost_type="TYRE")
    db.commit()
    token = _token(client, world)

    assert _pay(client, token, job.id, 3000).status_code == 201
    r = _pay(client, token, job.id, 1, payment_reference="over")
    assert r.status_code == 409
