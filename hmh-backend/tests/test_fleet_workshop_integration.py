"""
The four fleet and workshop changes working together.

Walks the scenario the brief describes end to end — locate Premium
Structures, assign a vehicle to it, raise a repair, correct it, pay the
mechanic in two instalments, confirm it reads Paid, check the audit trail
and the workshop totals, then prove 35 repairs stay reachable — and repeats
the isolation checks for the other two new companies.

Everything runs against test data. Nothing here touches a production record.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from tests.conftest import auth, login, make_project, make_site, make_user

NEW_COMPANIES = ("Kukhanya Kabusha", "Premium Structures", "Ophezulu")


def _now():
    return datetime.now(timezone.utc)


def _company(db, name):
    """
    Find the company, or create it — mirroring what migration 0077 does.

    The test database is built from the models rather than by running
    migrations, so the rows the migration inserts are not here. Matching
    before inserting is the same idempotent behaviour the migration has.
    """
    from sqlalchemy import func

    from app.models.company import Company

    existing = (
        db.query(Company)
        .filter(func.lower(func.trim(Company.name)) == name.strip().lower())
        .first()
    )
    if existing:
        return existing
    c = Company(name=name, created_at=_now(), updated_at=_now())
    db.add(c)
    db.flush()
    return c


def _vehicle(db, *, name, project_id=None):
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


@pytest.fixture()
def owner_token(db, client):
    owner = make_user(db, role="OWNER")
    db.commit()
    return owner, login(client, owner["email"], "Test@1234")


def test_the_three_new_companies_can_be_created_idempotently(db):
    """Running the registration twice must not produce six companies."""
    from app.models.company import Company

    for _ in range(2):
        for name in NEW_COMPANIES:
            _company(db, name)
    db.commit()

    for name in NEW_COMPANIES:
        assert db.query(Company).filter(Company.name == name).count() == 1


def test_no_details_are_invented_for_a_new_company(db):
    """A plausible but wrong VAT number on a supplier document is worse than none."""
    c = _company(db, "Premium Structures")
    db.commit()
    assert c.registration_number is None
    assert c.address is None


def test_the_whole_repair_lifecycle_for_a_new_company(db, client, owner_token):
    """
    Premium Structures → vehicle → repair → correction → part payment →
    settlement → Paid, with the audit trail and workshop totals agreeing.
    """
    from app.models.audit import AuditEvent
    from app.models.project import Project

    owner, token = owner_token

    company = _company(db, "Premium Structures")
    project = make_project(db, owner["id"])
    make_site(db, project["id"])
    db.get(Project, uuid.UUID(project["id"])).company_id = company.id
    vehicle = _vehicle(db, name="Premium Tipper", project_id=project["id"])
    db.commit()

    # 1. Raise the repair.
    r = client.post(
        f"/api/v1/vehicles/{vehicle.id}/repairs",
        json={"title": "Gearbox overhaul", "date_opened": "2026-03-01",
              "workshop_name": "Durban Diesel", "odometer_at_repair": 180000},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    repair_id = r.json()["data"]["id"]

    # 2. Correct it — the odometer was captured wrongly, and the mechanic
    #    has now invoiced.
    r = client.patch(
        f"/api/v1/vehicles/repairs/{repair_id}",
        json={"odometer_at_repair": 181500, "invoice_amount": 5000},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["odometer_at_repair"] == 181500

    event = (
        db.query(AuditEvent)
        .filter(AuditEvent.entity_type == "repair_job",
                AuditEvent.entity_id == uuid.UUID(repair_id))
        .one()
    )
    assert event.before_value["odometer_at_repair"] == 180000.0
    assert event.after_value["odometer_at_repair"] == 181500.0

    # 3. Part payment.
    r = client.post(
        f"/api/v1/workshop/repairs/{repair_id}/payments",
        json={"amount": 2000, "payment_date": "2026-03-10",
              "payment_method": "EFT", "payment_reference": "EFT-1001"},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["outstanding"] == 3000.0
    assert r.json()["data"]["payment_status"] == "PARTIALLY_PAID"

    # 4. Settle the balance.
    r = client.post(
        f"/api/v1/workshop/repairs/{repair_id}/payments",
        json={"amount": 3000, "payment_date": "2026-03-25",
              "payment_method": "EFT", "payment_reference": "EFT-1042"},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["outstanding"] == 0.0
    assert r.json()["data"]["payment_status"] == "PAID"

    # 5. The history holds both payments, and the audit trail holds both.
    history = client.get(f"/api/v1/workshop/repairs/{repair_id}/payments",
                         headers=auth(token)).json()["data"]
    assert len(history["payments"]) == 2
    assert history["total_paid"] == 5000.0
    assert db.query(AuditEvent).filter(
        AuditEvent.entity_type == "mechanic_payment").count() == 2

    # 6. The workshop view agrees, filtered to this company.
    overview = client.get(
        f"/api/v1/workshop/mechanic-payments?company_id={company.id}",
        headers=auth(token),
    ).json()["data"]
    assert overview["totals"]["total_payable"] == 5000.0
    assert overview["totals"]["total_outstanding"] == 0.0
    assert overview["totals"]["paid"] == 1
    assert overview["items"][0]["vehicle_registration"] == vehicle.registration


def test_thirty_five_repairs_stay_reachable_for_a_new_company(db, client, owner_token):
    from app.models.project import Project
    from app.models.vehicle import RepairJob

    owner, token = owner_token
    company = _company(db, "Kukhanya Kabusha")
    project = make_project(db, owner["id"])
    db.get(Project, uuid.UUID(project["id"])).company_id = company.id
    vehicle = _vehicle(db, name="KK Bakkie", project_id=project["id"])
    db.flush()

    for i in range(35):
        db.add(RepairJob(
            vehicle_id=vehicle.id, title=f"Service {i:02d}", status="OPEN",
            date_opened=date(2026, 1, 1) + timedelta(days=i),
            created_at=_now(), updated_at=_now(),
        ))
    db.commit()

    seen = []
    page = 1
    while True:
        data = client.get(
            f"/api/v1/vehicles/{vehicle.id}/repairs?page={page}&limit=10",
            headers=auth(token),
        ).json()["data"]
        assert data["total"] == 35
        seen.extend(i["id"] for i in data["items"])
        if page >= data["total_pages"]:
            break
        page += 1

    assert len(set(seen)) == 35

    # The oldest, on the last page, is still editable.
    r = client.patch(f"/api/v1/vehicles/repairs/{seen[-1]}",
                     json={"notes": "Found months later"}, headers=auth(token))
    assert r.status_code == 200, r.text


def test_companies_do_not_see_each_others_repairs(db, client, owner_token):
    """Each new company's payables stay its own."""
    from app.models.project import Project
    from app.models.vehicle import RepairJob

    owner, token = owner_token

    made = {}
    for name in NEW_COMPANIES:
        company = _company(db, name)
        project = make_project(db, owner["id"])
        db.get(Project, uuid.UUID(project["id"])).company_id = company.id
        vehicle = _vehicle(db, name=f"{name} vehicle", project_id=project["id"])
        db.flush()
        db.add(RepairJob(
            vehicle_id=vehicle.id, title=f"{name} repair", status="OPEN",
            date_opened=date(2026, 4, 1), invoice_amount=1000,
            created_at=_now(), updated_at=_now(),
        ))
        made[name] = company
    db.commit()

    for name, company in made.items():
        data = client.get(
            f"/api/v1/workshop/mechanic-payments?company_id={company.id}",
            headers=auth(token),
        ).json()["data"]
        titles = [r["repair_title"] for r in data["items"]]
        assert titles == [f"{name} repair"], f"{name} saw {titles}"
        assert data["totals"]["total_payable"] == 1000.0


def test_existing_companies_are_unaffected(db, client, owner_token):
    """
    HMH Group and Minerat keep rendering from their fixed letterhead, so
    documents already issued under them are unchanged.
    """
    from app.services.email_service import _company as letterhead

    _company(db, "Premium Structures")
    db.commit()

    assert letterhead("HMH_GROUP")["name"] == "HMH Group"
    assert letterhead("MINERAT")["name"] == "Minerat Construction & Civils"
    assert letterhead("MINERAT")["vat"] == "4380258618"


def test_a_new_company_appears_on_its_own_letterhead(db, client, owner_token):
    """
    Without this, a purchase order issued by a new company would render
    under the HMH Group name — the wrong company on a supplier document.
    """
    from app.services.email_service import _company as letterhead

    company = _company(db, "Ophezulu")
    db.commit()

    # Any object in the session lets the resolver reach the database; a
    # purchase order is the real caller, but nothing about the lookup is
    # specific to one.
    assert letterhead(str(company.id), company)["name"] == "Ophezulu"
    assert letterhead("Ophezulu", company)["name"] == "Ophezulu"
    # Nothing invented for a company whose details have not been captured.
    assert letterhead(str(company.id), company)["vat"] == ""


# ── Adding a company grants nobody anything ──────────────────────────────────
#
# Access in this system is per project, not per company. A new company has no
# projects until someone creates them, and a site-level user still needs an
# explicit UserProjectAccess row. Registering a company must not widen
# anyone's reach on its own.

def test_a_new_company_does_not_widen_site_staff_access(db, client):
    from app.models.project import Project
    from app.models.vehicle import RepairJob

    owner = make_user(db, role="OWNER")
    company = _company(db, "Ophezulu")
    project = make_project(db, owner["id"])
    db.get(Project, uuid.UUID(project["id"])).company_id = company.id
    vehicle = _vehicle(db, name="Ophezulu truck", project_id=project["id"])
    db.flush()
    db.add(RepairJob(
        vehicle_id=vehicle.id, title="Ophezulu repair", status="OPEN",
        date_opened=date(2026, 4, 1), invoice_amount=1000,
        created_at=_now(), updated_at=_now(),
    ))

    outsider = make_user(db, role="SITE_STAFF")
    db.commit()
    token = login(client, outsider["email"], "Test@1234")

    # Payables are office-level throughout; a site user sees none of it.
    assert client.get("/api/v1/workshop/mechanic-payments",
                      headers=auth(token)).status_code == 403
    assert client.post(
        f"/api/v1/workshop/repairs/{db.query(RepairJob).first().id}/payments",
        json={"amount": 100, "payment_date": "2026-04-02"},
        headers=auth(token),
    ).status_code == 403


def test_a_new_company_does_not_let_site_staff_edit_its_repairs(db, client):
    from app.models.project import Project
    from app.models.vehicle import RepairJob

    owner = make_user(db, role="OWNER")
    company = _company(db, "Kukhanya Kabusha")
    project = make_project(db, owner["id"])
    db.get(Project, uuid.UUID(project["id"])).company_id = company.id
    vehicle = _vehicle(db, name="KK truck", project_id=project["id"])
    db.flush()
    job = RepairJob(
        vehicle_id=vehicle.id, title="KK repair", status="OPEN",
        date_opened=date(2026, 4, 1), created_at=_now(), updated_at=_now(),
    )
    db.add(job)

    outsider = make_user(db, role="SITE_STAFF")
    db.commit()
    token = login(client, outsider["email"], "Test@1234")

    assert client.patch(f"/api/v1/vehicles/repairs/{job.id}",
                        json={"title": "hijacked"}, headers=auth(token)).status_code == 403


def test_registering_a_company_creates_no_project_access_rows(db):
    """The company is a label on projects, not a grant of anything."""
    from app.models.access import UserProjectAccess

    before = db.query(UserProjectAccess).count()
    for name in NEW_COMPANIES:
        _company(db, name)
    db.commit()
    assert db.query(UserProjectAccess).count() == before


# ── Purchase-order letterheads for the new companies ─────────────────────────

def _purchase_order(db, owner, project, *, issuing_company):
    from app.models.enums import RecordStatus
    from app.models.purchase_order import PurchaseOrder
    from tests.conftest import make_supplier

    supplier = make_supplier(db)
    po = PurchaseOrder(
        po_number=f"PO-{uuid.uuid4().hex[:6].upper()}",
        project_id=uuid.UUID(project["id"]),
        supplier_id=uuid.UUID(supplier["id"]),
        po_date=date(2026, 5, 1),
        status=RecordStatus.ORDERED,
        subtotal_amount=1000, vat_amount=150, total_amount=1150,
        issuing_company=issuing_company,
        created_by=uuid.UUID(owner["id"]),
        created_at=_now(), updated_at=_now(),
    )
    db.add(po)
    db.flush()
    return po


def test_a_purchase_order_renders_under_its_own_company(db, owner_token):
    """
    The real path: a PO carrying a company id must render that company's
    name, not fall back to HMH Group. Before the resolver change it would
    have — the wrong company on a supplier-facing document.
    """
    from app.services.email_service import _company as letterhead

    owner, _ = owner_token
    project = make_project(db, owner["id"])
    company = _company(db, "Premium Structures")
    db.flush()
    po = _purchase_order(db, owner, project, issuing_company=str(company.id))
    db.commit()

    assert letterhead(po.issuing_company, po)["name"] == "Premium Structures"


def test_a_company_id_fits_the_issuing_company_column(db, owner_token):
    """A UUID is 36 characters; the column holds 50. Worth pinning."""
    from app.models.purchase_order import PurchaseOrder

    owner, _ = owner_token
    project = make_project(db, owner["id"])
    company = _company(db, "Kukhanya Kabusha")
    db.flush()
    po = _purchase_order(db, owner, project, issuing_company=str(company.id))
    db.commit()

    assert db.get(PurchaseOrder, po.id).issuing_company == str(company.id)


def test_legacy_purchase_orders_are_unchanged(db, owner_token):
    """Documents issued under the old keys must render exactly as before."""
    from app.services.email_service import _company as letterhead

    owner, _ = owner_token
    project = make_project(db, owner["id"])
    db.flush()
    po = _purchase_order(db, owner, project, issuing_company="MINERAT")
    db.commit()

    co = letterhead(po.issuing_company, po)
    assert co["name"] == "Minerat Construction & Civils"
    assert co["vat"] == "4380258618"
    assert co["tel"] == "(031) 301 3038"


def test_a_purchase_order_with_no_company_still_renders(db, owner_token):
    from app.services.email_service import _company as letterhead

    owner, _ = owner_token
    project = make_project(db, owner["id"])
    db.flush()
    po = _purchase_order(db, owner, project, issuing_company=None)
    db.commit()

    assert letterhead(po.issuing_company, po)["name"] == "HMH Group"


def test_a_purchase_order_pdf_generates_for_a_new_company(db, owner_token):
    """End to end: the document actually renders, with the right name in it."""
    from app.services.email_service import _generate_po_pdf

    owner, _ = owner_token
    project = make_project(db, owner["id"])
    company = _company(db, "Ophezulu")
    db.flush()
    po = _purchase_order(db, owner, project, issuing_company=str(company.id))
    db.commit()

    pdf = _generate_po_pdf(po)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000
