"""
Vehicle repair history: pagination, and correcting a captured repair.

Two reported problems drive these tests.

Staff could see only ten repairs. The cap was never in the database — both
the repair list and the cost list returned everything and the screens showed
the first ten — so the fix is real pagination, and these tests pin the
properties that make it trustworthy: nothing hidden, nothing repeated, an
honest total, and filters that search the whole history rather than the page.

Staff could not correct a repair after saving it. Editing now exists, but it
must not become a way to quietly rewrite figures the books have acted on, and
every accepted change has to be attributable.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from tests.conftest import (
    auth, login, make_project, make_site, make_user,
)


def _now():
    return datetime.now(timezone.utc)


def _vehicle(db, *, registration=None, name="Tipper"):
    from app.models.vehicle import Vehicle

    v = Vehicle(
        registration=registration or f"ND {uuid.uuid4().hex[:5].upper()}",
        name=name,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(v)
    db.flush()
    return v


def _repair(db, vehicle, *, title="Brake pads", opened=None, status="OPEN",
            workshop="Durban Diesel", description=None, odometer=None, notes=None):
    from app.models.vehicle import RepairJob

    j = RepairJob(
        vehicle_id=vehicle.id,
        title=title,
        description=description,
        status=status,
        workshop_name=workshop,
        date_opened=opened or date(2026, 1, 1),
        odometer_at_repair=odometer,
        notes=notes,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(j)
    db.flush()
    return j


def _cost(db, vehicle, *, repair=None, amount=100, cost_type="REPAIR",
          when=None, description=None):
    from app.models.vehicle import VehicleCost

    c = VehicleCost(
        vehicle_id=vehicle.id,
        repair_job_id=repair.id if repair else None,
        cost_type=cost_type,
        amount=amount,
        description=description,
        cost_date=when or date(2026, 1, 1),
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
    vehicle = _vehicle(db)
    db.commit()
    return {"owner": owner, "project": project, "site": site, "vehicle": vehicle}


def _token(client, world):
    return login(client, world["owner"]["email"], "Test@1234")


def _get(client, token, url):
    r = client.get(url, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ── The thirty-five repairs the brief asks for ───────────────────────────────

@pytest.fixture()
def thirty_five(db, world):
    """35 repairs on one vehicle, each on a distinct day, newest = Feb 4."""
    jobs = []
    for i in range(35):
        jobs.append(_repair(
            db, world["vehicle"],
            title=f"Repair {i:02d}",
            description=f"Work item {i:02d}",
            opened=date(2026, 1, 1) + timedelta(days=i),
            status="CLOSED" if i % 3 == 0 else "OPEN",
            workshop="Durban Diesel" if i % 2 == 0 else "Pinetown Motors",
        ))
    db.commit()
    return jobs


def test_all_thirty_five_repairs_are_reachable(client, world, thirty_five):
    """
    The reported bug: more than ten repairs exist, the rest are unreachable.
    Walking the pages must yield every record exactly once.
    """
    token = _token(client, world)
    vid = world["vehicle"].id

    seen: list[str] = []
    page = 1
    while True:
        data = _get(client, token, f"/api/v1/vehicles/{vid}/repairs?page={page}&limit=10")
        assert data["total"] == 35
        seen.extend(item["id"] for item in data["items"])
        if page >= data["total_pages"]:
            break
        page += 1

    assert len(seen) == 35, f"walked the pages and found {len(seen)} of 35"
    assert len(set(seen)) == 35, "a repair appeared on more than one page"
    assert set(seen) == {str(j.id) for j in thirty_five}


def test_the_total_is_the_whole_history_not_the_page(client, world, thirty_five):
    token = _token(client, world)
    data = _get(client, token,
                f"/api/v1/vehicles/{world['vehicle'].id}/repairs?page=1&limit=10")
    assert data["total"] == 35
    assert len(data["items"]) == 10
    assert data["total_pages"] == 4


def test_pages_do_not_overlap(client, world, thirty_five):
    token = _token(client, world)
    vid = world["vehicle"].id

    p1 = _get(client, token, f"/api/v1/vehicles/{vid}/repairs?page=1&limit=10")
    p2 = _get(client, token, f"/api/v1/vehicles/{vid}/repairs?page=2&limit=10")

    ids1 = {i["id"] for i in p1["items"]}
    ids2 = {i["id"] for i in p2["items"]}
    assert not (ids1 & ids2), "the same repair appeared on two pages"


def test_the_newest_repair_comes_first(client, world, thirty_five):
    token = _token(client, world)
    data = _get(client, token,
                f"/api/v1/vehicles/{world['vehicle'].id}/repairs?page=1&limit=10")
    dates = [i["date_opened"] for i in data["items"]]
    assert dates == sorted(dates, reverse=True)
    assert dates[0] == "2026-02-04"


def test_repairs_opened_on_the_same_day_still_paginate_cleanly(db, client, world):
    """
    Ordering by date alone is not a stable sort. Thirty repairs on one day
    could reshuffle between queries, hiding some and repeating others.
    """
    for i in range(30):
        _repair(db, world["vehicle"], title=f"Same day {i:02d}", opened=date(2026, 5, 5))
    db.commit()

    token = _token(client, world)
    vid = world["vehicle"].id
    seen = []
    for page in (1, 2, 3):
        data = _get(client, token, f"/api/v1/vehicles/{vid}/repairs?page={page}&limit=10")
        seen.extend(i["id"] for i in data["items"])

    assert len(set(seen)) == 30


@pytest.mark.parametrize("limit", [10, 25, 50])
def test_the_offered_page_sizes_all_work(client, world, thirty_five, limit):
    token = _token(client, world)
    data = _get(client, token,
                f"/api/v1/vehicles/{world['vehicle'].id}/repairs?page=1&limit={limit}")
    assert data["total"] == 35
    assert len(data["items"]) == min(limit, 35)


def test_a_page_past_the_end_is_empty_not_an_error(client, world, thirty_five):
    token = _token(client, world)
    data = _get(client, token,
                f"/api/v1/vehicles/{world['vehicle'].id}/repairs?page=99&limit=10")
    assert data["items"] == []
    assert data["total"] == 35


def test_an_unbounded_page_size_is_refused(client, world, thirty_five):
    """Nothing should be able to ask for the entire history in one response."""
    r = client.get(f"/api/v1/vehicles/{world['vehicle'].id}/repairs?limit=100000",
                   headers=_token_header(client, world))
    assert r.status_code == 422


def _token_header(client, world):
    return auth(login(client, world["owner"]["email"], "Test@1234"))


# ── Search and filters reach the whole history, not just the page ────────────

def test_search_finds_a_repair_that_is_not_on_the_first_page(client, world, thirty_five):
    token = _token(client, world)
    data = _get(client, token,
                f"/api/v1/vehicles/{world['vehicle'].id}/repairs?search=Repair%2000&limit=10")
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Repair 00"


def test_search_matches_the_workshop_name(client, world, thirty_five):
    token = _token(client, world)
    data = _get(client, token,
                f"/api/v1/vehicles/{world['vehicle'].id}/repairs?search=Pinetown&limit=50")
    assert data["total"] == 17
    assert all("Pinetown" in i["workshop_name"] for i in data["items"])


def test_search_is_case_insensitive(client, world, thirty_five):
    token = _token(client, world)
    data = _get(client, token,
                f"/api/v1/vehicles/{world['vehicle'].id}/repairs?search=pinetown&limit=50")
    assert data["total"] == 17


def test_status_filter_counts_the_whole_history(client, world, thirty_five):
    token = _token(client, world)
    data = _get(client, token,
                f"/api/v1/vehicles/{world['vehicle'].id}/repairs?status=CLOSED&limit=10")
    assert data["total"] == 12          # i % 3 == 0 for i in range(35)
    assert all(i["status"] == "CLOSED" for i in data["items"])


def test_date_filters_narrow_the_history(client, world, thirty_five):
    token = _token(client, world)
    data = _get(client, token,
                f"/api/v1/vehicles/{world['vehicle'].id}/repairs"
                f"?date_from=2026-01-01&date_to=2026-01-10&limit=50")
    assert data["total"] == 10


def test_another_vehicles_repairs_never_appear(db, client, world, thirty_five):
    other = _vehicle(db, name="Bakkie")
    _repair(db, other, title="Not mine")
    db.commit()

    token = _token(client, world)
    data = _get(client, token,
                f"/api/v1/vehicles/{world['vehicle'].id}/repairs?limit=50")
    assert data["total"] == 35
    assert "Not mine" not in [i["title"] for i in data["items"]]


# ── Costs were the list actually capped at ten on screen ─────────────────────

def test_all_thirty_five_costs_are_reachable(db, client, world):
    for i in range(35):
        _cost(db, world["vehicle"], amount=100 + i,
              when=date(2026, 1, 1) + timedelta(days=i),
              description=f"Cost {i:02d}")
    db.commit()

    token = _token(client, world)
    vid = world["vehicle"].id
    seen = []
    page = 1
    while True:
        data = _get(client, token, f"/api/v1/vehicles/{vid}/costs?page={page}&limit=10")
        assert data["total"] == 35
        seen.extend(i["id"] for i in data["items"])
        if page >= data["total_pages"]:
            break
        page += 1

    assert len(set(seen)) == 35


def test_costs_can_be_filtered_by_type(db, client, world):
    for i in range(12):
        _cost(db, world["vehicle"], cost_type="FUEL" if i % 2 else "REPAIR",
              when=date(2026, 1, 1) + timedelta(days=i))
    db.commit()

    token = _token(client, world)
    data = _get(client, token,
                f"/api/v1/vehicles/{world['vehicle'].id}/costs?cost_type=REPAIR&limit=50")
    assert data["total"] == 6


# ── Editing a repair ─────────────────────────────────────────────────────────

def test_a_captured_repair_can_be_corrected(db, client, world):
    job = _repair(db, world["vehicle"], title="Brake pads", odometer=10000)
    db.commit()
    token = _token(client, world)

    r = client.patch(f"/api/v1/vehicles/repairs/{job.id}",
                     json={"title": "Brake discs and pads", "odometer_at_repair": 101500},
                     headers=auth(token))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["title"] == "Brake discs and pads"
    assert data["odometer_at_repair"] == 101500


def test_editing_does_not_create_a_second_repair(db, client, world):
    from app.models.vehicle import RepairJob

    job = _repair(db, world["vehicle"])
    db.commit()
    token = _token(client, world)

    client.patch(f"/api/v1/vehicles/repairs/{job.id}",
                 json={"title": "Corrected"}, headers=auth(token))

    assert db.query(RepairJob).filter(
        RepairJob.vehicle_id == world["vehicle"].id).count() == 1


def test_every_change_is_written_to_the_audit_trail(db, client, world):
    from app.models.audit import AuditEvent

    job = _repair(db, world["vehicle"], title="Brake pads", notes=None)
    db.commit()
    token = _token(client, world)

    client.patch(f"/api/v1/vehicles/repairs/{job.id}",
                 json={"title": "Brake discs", "notes": "Front axle only"},
                 headers=auth(token))

    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.entity_type == "repair_job", AuditEvent.entity_id == job.id)
        .all()
    )
    assert len(events) == 1
    e = events[0]
    assert e.actor_id == uuid.UUID(world["owner"]["id"])
    assert e.created_at is not None
    assert e.before_value["title"] == "Brake pads"
    assert e.after_value["title"] == "Brake discs"
    assert e.before_value["notes"] is None
    assert e.after_value["notes"] == "Front axle only"


def test_resubmitting_the_same_values_is_not_recorded_as_a_change(db, client, world):
    """
    The edit form posts every field. Saving without touching anything must
    not fill the audit trail with changes that did not happen.
    """
    from app.models.audit import AuditEvent

    job = _repair(db, world["vehicle"], title="Brake pads", odometer=10000)
    db.commit()
    token = _token(client, world)

    r = client.patch(f"/api/v1/vehicles/repairs/{job.id}",
                     json={"title": "Brake pads", "odometer_at_repair": 10000},
                     headers=auth(token))
    assert r.status_code == 200

    assert db.query(AuditEvent).filter(
        AuditEvent.entity_type == "repair_job", AuditEvent.entity_id == job.id).count() == 0


def test_only_the_fields_that_changed_are_recorded(db, client, world):
    from app.models.audit import AuditEvent

    job = _repair(db, world["vehicle"], title="Brake pads", odometer=10000)
    db.commit()
    token = _token(client, world)

    client.patch(f"/api/v1/vehicles/repairs/{job.id}",
                 json={"title": "Brake pads", "odometer_at_repair": 12345},
                 headers=auth(token))

    e = db.query(AuditEvent).filter(
        AuditEvent.entity_type == "repair_job", AuditEvent.entity_id == job.id).one()
    assert set(e.before_value) == {"odometer_at_repair"}


def test_an_older_repair_deep_in_the_history_can_still_be_edited(client, db, world, thirty_five):
    """A record on page 4 must be as editable as one on page 1."""
    oldest = thirty_five[0]
    token = _token(client, world)

    r = client.patch(f"/api/v1/vehicles/repairs/{oldest.id}",
                     json={"notes": "Corrected months later"}, headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["notes"] == "Corrected months later"


def test_editing_an_unknown_repair_is_a_404(client, world):
    token = _token(client, world)
    r = client.patch(f"/api/v1/vehicles/repairs/{uuid.uuid4()}",
                     json={"title": "x"}, headers=auth(token))
    assert r.status_code == 404


def test_site_staff_cannot_edit_a_repair(db, client, world):
    job = _repair(db, world["vehicle"])
    db.commit()
    user = make_user(db, role="SITE_STAFF")
    db.commit()
    token = login(client, user["email"], "Test@1234")

    r = client.patch(f"/api/v1/vehicles/repairs/{job.id}",
                     json={"title": "x"}, headers=auth(token))
    assert r.status_code == 403


# ── Financial history is not silently rewritten ──────────────────────────────

def test_a_repair_with_recorded_costs_cannot_be_moved_to_another_vehicle(db, client, world):
    """
    Moving the repair would move the spend with it, quietly changing what
    each vehicle has cost.
    """
    job = _repair(db, world["vehicle"])
    _cost(db, world["vehicle"], repair=job, amount=4500)
    other = _vehicle(db, name="Other")
    db.commit()
    token = _token(client, world)

    r = client.patch(f"/api/v1/vehicles/repairs/{job.id}",
                     json={"vehicle_id": str(other.id)}, headers=auth(token))
    assert r.status_code == 409
    assert "recorded cost" in r.json()["detail"]


def test_that_refusal_explains_itself(db, client, world):
    job = _repair(db, world["vehicle"])
    _cost(db, world["vehicle"], repair=job, amount=4500)
    other = _vehicle(db, name="Other")
    db.commit()
    token = _token(client, world)

    detail = client.patch(f"/api/v1/vehicles/repairs/{job.id}",
                          json={"vehicle_id": str(other.id)},
                          headers=auth(token)).json()["detail"]
    # Names the obstacle and the way forward, not just "forbidden".
    assert "Reverse the costs" in detail


def test_a_repair_with_costs_can_still_have_its_description_corrected(db, client, world):
    """The lock is narrow: only the fields the money depends on."""
    job = _repair(db, world["vehicle"], title="Brake pads")
    _cost(db, world["vehicle"], repair=job, amount=4500)
    db.commit()
    token = _token(client, world)

    r = client.patch(f"/api/v1/vehicles/repairs/{job.id}",
                     json={"title": "Brake discs", "notes": "typo"}, headers=auth(token))
    assert r.status_code == 200, r.text


def test_approved_amounts_cannot_be_edited(db, client, world):
    job = _repair(db, world["vehicle"])
    job.quote_amount = 5000
    job.approval_stage = 2
    db.commit()
    token = _token(client, world)

    r = client.patch(f"/api/v1/vehicles/repairs/{job.id}",
                     json={"quote_amount": 9999}, headers=auth(token))
    assert r.status_code == 409
    assert "approved" in r.json()["detail"].lower()


def test_an_unapproved_quote_can_be_corrected(db, client, world):
    job = _repair(db, world["vehicle"])
    job.quote_amount = 5000
    db.commit()
    token = _token(client, world)

    r = client.patch(f"/api/v1/vehicles/repairs/{job.id}",
                     json={"quote_amount": 5500}, headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["quote_amount"] == 5500


def test_resending_a_locked_field_unchanged_is_allowed(db, client, world):
    """
    The edit form posts the whole record. A locked field that is not actually
    being changed must not block an edit to a field that is.
    """
    job = _repair(db, world["vehicle"], title="Brake pads")
    _cost(db, world["vehicle"], repair=job, amount=4500)
    db.commit()
    token = _token(client, world)

    r = client.patch(
        f"/api/v1/vehicles/repairs/{job.id}",
        json={"vehicle_id": str(world["vehicle"].id), "title": "Brake discs"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["title"] == "Brake discs"


def test_moving_a_repair_to_a_vehicle_that_does_not_exist_is_a_404(db, client, world):
    job = _repair(db, world["vehicle"])
    db.commit()
    token = _token(client, world)

    r = client.patch(f"/api/v1/vehicles/repairs/{job.id}",
                     json={"vehicle_id": str(uuid.uuid4())}, headers=auth(token))
    assert r.status_code == 404
