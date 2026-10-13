"""
Delivery-note cleanup utility — `scripts/cleanup_project_delivery_notes.py`.

The utility exists to undo duplicate delivery notes on one project. These
tests cover the properties that make it safe to point at real data:

  * it classifies correctly — a genuine note is never treated as a duplicate;
  * the dry run changes nothing;
  * reversal actually corrects the figure the duplicate inflated, which means
    the BOQ delivered quantity, not merely stock on hand;
  * nothing is deleted — invoices, purchase orders and the original ledger
    rows all survive;
  * other projects are untouched;
  * running it twice does not reverse twice.
"""

import importlib.util
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.models.enums import MovementType, RecordStatus
from tests.conftest import (
    auth, login, make_item, make_lot, make_project, make_site, make_supplier,
    make_user,
)
from tests.test_site_dashboard_boq_duplication import _boq_header_section, _boq_item

# Loaded by path: scripts/ is not a package on the test path.
_SPEC = importlib.util.spec_from_file_location(
    "cleanup_project_delivery_notes",
    Path(__file__).resolve().parents[1] / "scripts" / "cleanup_project_delivery_notes.py",
)
cleanup = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cleanup)


def _now():
    return datetime.now(timezone.utc)


# deliveries.received_by_user_id is NOT NULL; the fixture fills this in.
_RECEIVER: dict = {"id": None}


def _delivery(db, project, site, supplier, *, note_number, number=None, po_id=None,
              when=None, received_by=None):
    from app.models.delivery import Delivery

    d = Delivery(
        project_id=uuid.UUID(project["id"]),
        site_id=uuid.UUID(site["id"]) if site else None,
        supplier_id=uuid.UUID(supplier["id"]),
        purchase_order_id=po_id,
        delivery_number=number or f"DN-{uuid.uuid4().hex[:6].upper()}",
        supplier_delivery_note_number=note_number,
        delivery_date=when or date(2026, 3, 18),
        delivery_status=RecordStatus.RECEIVED,
        received_by_user_id=uuid.UUID(received_by) if received_by else _RECEIVER["id"],
        created_at=_now(), updated_at=_now(),
    )
    db.add(d)
    db.flush()
    return d


def _ledger(db, project, lot, item, delivery, qty, *, boq_item_id=None):
    from app.models.stock import StockLedger

    row = StockLedger(
        project_id=uuid.UUID(project["id"]),
        site_id=None,
        lot_id=uuid.UUID(lot["id"]),
        item_id=uuid.UUID(item["id"]),
        boq_item_id=boq_item_id,
        movement_type=MovementType.DELIVERY_RECEIVED,
        reference_type="delivery",
        reference_id=delivery.id,
        quantity_in=qty,
        quantity_out=0,
        unit="bag",
        movement_date=_now(),
        entered_by=None,
        created_at=_now(),
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def world(db):
    owner = make_user(db, role="OWNER")
    _RECEIVER["id"] = uuid.UUID(owner["id"])
    project = make_project(db, owner["id"])
    site = make_site(db, project["id"])
    lot = make_lot(db, project["id"], site["id"], lot_number="12")
    item = make_item(db, name="Cement 42.5N 50kg bag", unit="bag")
    supplier = make_supplier(db, name="Umhlanga Building Supplies CC")
    header, section = _boq_header_section(db, project["id"])
    _boq_item(db, project["id"], section, description="Cement 42.5N 50kg bag",
              unit="bag", qty=500, item_id=item["id"], lot_id=lot["id"],
              site_id=site["id"])
    db.commit()
    return {"owner": owner, "project": project, "site": site, "lot": lot,
            "item": item, "supplier": supplier, "section": section}


def _project_id(world):
    return uuid.UUID(world["project"]["id"])


def _delivered(client, token, world):
    r = client.get(
        f"/api/v1/site-dashboard/{world['site']['id']}/lots/{world['lot']['id']}"
        f"/material-summary",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    return sum(float(x["delivered_qty"]) for x in rows)


def _used(client, token, world):
    r = client.get(
        f"/api/v1/site-dashboard/{world['site']['id']}/lots/{world['lot']['id']}"
        f"/material-summary",
        headers=auth(token),
    )
    rows = r.json()["data"]
    return sum(float(x["used_qty"]) for x in rows)


# ── Classification ────────────────────────────────────────────────────────────

def test_a_single_genuine_delivery_is_not_flagged(db, world):
    d = _delivery(db, world["project"], world["site"], world["supplier"],
                  note_number="DN-9001")
    _ledger(db, world["project"], world["lot"], world["item"], d, 100)
    db.commit()

    report = cleanup.classify(db, _project_id(world))

    assert report["totals"]["delivery_notes"] == 1
    assert report["totals"]["genuine"] == 1
    assert report["delivery_notes"][0]["verdict"] == cleanup.GENUINE
    assert cleanup.plan(report) == []


def test_the_same_supplier_note_recorded_twice_is_flagged_once(db, world):
    """The earlier note is the genuine one; only the later is a candidate."""
    first = _delivery(db, world["project"], world["site"], world["supplier"],
                      note_number="DN-9001", when=date(2026, 3, 18))
    _ledger(db, world["project"], world["lot"], world["item"], first, 100)
    second = _delivery(db, world["project"], world["site"], world["supplier"],
                       note_number="DN-9001", when=date(2026, 3, 20))
    _ledger(db, world["project"], world["lot"], world["item"], second, 100)
    db.commit()

    report = cleanup.classify(db, _project_id(world))
    by_id = {r["delivery_id"]: r for r in report["delivery_notes"]}

    assert by_id[str(first.id)]["verdict"] == cleanup.GENUINE
    assert by_id[str(second.id)]["verdict"] == cleanup.DUPLICATE_OF_NOTE
    assert report["totals"]["duplicate_note_number"] == 1

    actions = cleanup.plan(report)
    assert [a["delivery_id"] for a in actions] == [str(second.id)]
    assert actions[0]["action"] == "REVERSE_AND_ARCHIVE"


def test_note_numbers_are_matched_case_and_space_insensitively(db, world):
    _delivery(db, world["project"], world["site"], world["supplier"],
              note_number="dn-9001 ", when=date(2026, 3, 18))
    _delivery(db, world["project"], world["site"], world["supplier"],
              note_number="DN-9001", when=date(2026, 3, 20))
    db.commit()

    report = cleanup.classify(db, _project_id(world))
    assert report["totals"]["duplicate_note_number"] == 1


def test_the_same_note_number_from_a_different_supplier_is_not_a_duplicate(db, world):
    other = make_supplier(db, name="Durban Hardware")
    _delivery(db, world["project"], world["site"], world["supplier"],
              note_number="DN-100")
    _delivery(db, world["project"], world["site"], other, note_number="DN-100")
    db.commit()

    report = cleanup.classify(db, _project_id(world))
    assert report["totals"]["genuine"] == 2
    assert report["totals"]["duplicate_note_number"] == 0


def test_one_delivery_posting_stock_twice_is_flagged(db, world):
    """No duplicate note number — the duplicate is in the ledger."""
    d = _delivery(db, world["project"], world["site"], world["supplier"],
                  note_number="DN-7777")
    _ledger(db, world["project"], world["lot"], world["item"], d, 100)
    _ledger(db, world["project"], world["lot"], world["item"], d, 100)
    db.commit()

    report = cleanup.classify(db, _project_id(world))
    row = report["delivery_notes"][0]

    assert row["verdict"] == cleanup.DUPLICATE_LEDGER
    assert row["stock_movements"] == 2
    assert row["stock_in_total"] == 200.0


def test_notes_without_a_supplier_number_are_never_paired(db, world):
    """Blank note numbers must not all collapse into one duplicate set."""
    for _ in range(3):
        _delivery(db, world["project"], world["site"], world["supplier"],
                  note_number=None)
    db.commit()

    report = cleanup.classify(db, _project_id(world))
    assert report["totals"]["genuine"] == 3


def test_an_unknown_project_is_refused(db):
    with pytest.raises(SystemExit):
        cleanup.classify(db, uuid.uuid4())


# ── The dry run ───────────────────────────────────────────────────────────────

def test_classify_and_plan_change_nothing(db, client, world):
    from app.models.stock import StockLedger

    first = _delivery(db, world["project"], world["site"], world["supplier"],
                      note_number="DN-9001", when=date(2026, 3, 18))
    _ledger(db, world["project"], world["lot"], world["item"], first, 100)
    second = _delivery(db, world["project"], world["site"], world["supplier"],
                       note_number="DN-9001", when=date(2026, 3, 20))
    _ledger(db, world["project"], world["lot"], world["item"], second, 100)
    db.commit()

    before = db.query(StockLedger).count()
    report = cleanup.classify(db, _project_id(world))
    cleanup.plan(report)

    assert db.query(StockLedger).count() == before
    assert db.get(type(second), second.id).delivery_status == RecordStatus.RECEIVED


# ── Applying it ───────────────────────────────────────────────────────────────

def test_reversal_corrects_the_boq_delivered_quantity(db, client, world):
    """
    The point of the exercise. Stock on hand and the BOQ delivered figure are
    computed differently; the reversal has to correct both.
    """
    token = login(client, world["owner"]["email"], "Test@1234")

    first = _delivery(db, world["project"], world["site"], world["supplier"],
                      note_number="DN-9001", when=date(2026, 3, 18))
    _ledger(db, world["project"], world["lot"], world["item"], first, 100)
    second = _delivery(db, world["project"], world["site"], world["supplier"],
                       note_number="DN-9001", when=date(2026, 3, 20))
    _ledger(db, world["project"], world["lot"], world["item"], second, 100)
    db.commit()

    assert _delivered(client, token, world) == 200.0

    report = cleanup.classify(db, _project_id(world))
    cleanup.apply_cleanup(db, _project_id(world), report,
                          uuid.UUID(world["owner"]["id"]), "test")

    assert _delivered(client, token, world) == 100.0


def test_reversal_does_not_show_up_as_consumption(db, client, world):
    """A quantity_out adjustment would have inflated used_qty instead."""
    token = login(client, world["owner"]["email"], "Test@1234")

    first = _delivery(db, world["project"], world["site"], world["supplier"],
                      note_number="DN-9001", when=date(2026, 3, 18))
    _ledger(db, world["project"], world["lot"], world["item"], first, 100)
    second = _delivery(db, world["project"], world["site"], world["supplier"],
                       note_number="DN-9001", when=date(2026, 3, 20))
    _ledger(db, world["project"], world["lot"], world["item"], second, 100)
    db.commit()

    report = cleanup.classify(db, _project_id(world))
    cleanup.apply_cleanup(db, _project_id(world), report,
                          uuid.UUID(world["owner"]["id"]), "test")

    assert _used(client, token, world) == 0.0


def test_reversal_corrects_stock_on_hand(db, world):
    from sqlalchemy import text

    first = _delivery(db, world["project"], world["site"], world["supplier"],
                      note_number="DN-9001", when=date(2026, 3, 18))
    _ledger(db, world["project"], world["lot"], world["item"], first, 100)
    second = _delivery(db, world["project"], world["site"], world["supplier"],
                       note_number="DN-9001", when=date(2026, 3, 20))
    _ledger(db, world["project"], world["lot"], world["item"], second, 100)
    db.commit()

    report = cleanup.classify(db, _project_id(world))
    cleanup.apply_cleanup(db, _project_id(world), report,
                          uuid.UUID(world["owner"]["id"]), "test")

    on_hand = db.execute(
        text("SELECT COALESCE(SUM(quantity_in) - SUM(quantity_out), 0) "
             "FROM stock_ledger WHERE project_id = :p AND item_id = :i"),
        {"p": _project_id(world), "i": uuid.UUID(world["item"]["id"])},
    ).scalar()
    assert float(on_hand) == 100.0


def test_nothing_is_deleted(db, world):
    """History is the audit trail. The duplicate's original rows must survive."""
    from app.models.stock import StockLedger

    first = _delivery(db, world["project"], world["site"], world["supplier"],
                      note_number="DN-9001", when=date(2026, 3, 18))
    _ledger(db, world["project"], world["lot"], world["item"], first, 100)
    second = _delivery(db, world["project"], world["site"], world["supplier"],
                       note_number="DN-9001", when=date(2026, 3, 20))
    original = _ledger(db, world["project"], world["lot"], world["item"], second, 100)
    db.commit()

    report = cleanup.classify(db, _project_id(world))
    cleanup.apply_cleanup(db, _project_id(world), report,
                          uuid.UUID(world["owner"]["id"]), "test")

    assert db.get(StockLedger, original.id) is not None
    assert db.get(type(second), second.id) is not None
    # Archived, not removed.
    assert db.get(type(second), second.id).delivery_status == RecordStatus.CANCELLED


def test_an_audit_event_is_written(db, world):
    from app.models.audit import AuditEvent

    first = _delivery(db, world["project"], world["site"], world["supplier"],
                      note_number="DN-9001", when=date(2026, 3, 18))
    _ledger(db, world["project"], world["lot"], world["item"], first, 100)
    second = _delivery(db, world["project"], world["site"], world["supplier"],
                       note_number="DN-9001", when=date(2026, 3, 20))
    _ledger(db, world["project"], world["lot"], world["item"], second, 100)
    db.commit()

    report = cleanup.classify(db, _project_id(world))
    cleanup.apply_cleanup(db, _project_id(world), report,
                          uuid.UUID(world["owner"]["id"]), "test")

    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.entity_type == "delivery_cleanup",
                AuditEvent.entity_id == second.id)
        .all()
    )
    assert len(events) == 1
    assert events[0].actor_id == uuid.UUID(world["owner"]["id"])


def test_running_it_twice_does_not_reverse_twice(db, client, world):
    token = login(client, world["owner"]["email"], "Test@1234")

    first = _delivery(db, world["project"], world["site"], world["supplier"],
                      note_number="DN-9001", when=date(2026, 3, 18))
    _ledger(db, world["project"], world["lot"], world["item"], first, 100)
    second = _delivery(db, world["project"], world["site"], world["supplier"],
                       note_number="DN-9001", when=date(2026, 3, 20))
    _ledger(db, world["project"], world["lot"], world["item"], second, 100)
    db.commit()

    for _ in range(2):
        report = cleanup.classify(db, _project_id(world))
        cleanup.apply_cleanup(db, _project_id(world), report,
                              uuid.UUID(world["owner"]["id"]), "test")

    assert _delivered(client, token, world) == 100.0


def test_a_duplicate_carrying_an_invoice_is_skipped_not_reversed(db, client, world):
    """
    Reversing a receipt an invoice was raised against changes what the
    paperwork says was delivered. That is a human decision, not a script's.
    """
    from app.models.invoice import Invoice
    from app.models.purchase_order import PurchaseOrder

    token = login(client, world["owner"]["email"], "Test@1234")

    po = PurchaseOrder(
        project_id=_project_id(world),
        site_id=uuid.UUID(world["site"]["id"]),
        supplier_id=uuid.UUID(world["supplier"]["id"]),
        po_number=f"PO-{uuid.uuid4().hex[:6].upper()}",
        po_date=date(2026, 3, 15),
        created_by=uuid.UUID(world["owner"]["id"]),
        status=RecordStatus.ORDERED,
        subtotal_amount=1000, vat_amount=150, total_amount=1150,
        created_at=_now(), updated_at=_now(),
    )
    db.add(po)
    db.flush()
    db.add(Invoice(
        project_id=_project_id(world),
        site_id=uuid.UUID(world["site"]["id"]),
        supplier_id=uuid.UUID(world["supplier"]["id"]),
        purchase_order_id=po.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:6].upper()}",
        invoice_date=date(2026, 3, 21),
        captured_by=uuid.UUID(world["owner"]["id"]),
        captured_at=_now(),
        status=RecordStatus.INVOICED,
        subtotal_amount=1000, vat_amount=150, total_amount=1150,
        created_at=_now(), updated_at=_now(),
    ))

    first = _delivery(db, world["project"], world["site"], world["supplier"],
                      note_number="DN-9001", when=date(2026, 3, 18))
    _ledger(db, world["project"], world["lot"], world["item"], first, 100)
    second = _delivery(db, world["project"], world["site"], world["supplier"],
                       note_number="DN-9001", when=date(2026, 3, 20), po_id=po.id)
    _ledger(db, world["project"], world["lot"], world["item"], second, 100)
    db.commit()

    report = cleanup.classify(db, _project_id(world))
    row = next(r for r in report["delivery_notes"] if r["delivery_id"] == str(second.id))
    assert row["needs_human_decision"] is True
    assert row["linked_invoices"]

    actions = cleanup.plan(report)
    assert [a["action"] for a in actions] == ["SKIP"]

    result = cleanup.apply_cleanup(db, _project_id(world), report,
                                   uuid.UUID(world["owner"]["id"]), "test")
    assert result["reversed"] == []
    # Untouched: still RECEIVED, still double-counted, awaiting a decision.
    assert db.get(type(second), second.id).delivery_status == RecordStatus.RECEIVED
    assert _delivered(client, token, world) == 200.0


def test_another_project_is_untouched(db, world):
    """The utility is scoped to one project by id and must stay there."""
    from app.models.stock import StockLedger

    other_project = make_project(db, world["owner"]["id"])
    other_site = make_site(db, other_project["id"])
    other_lot = make_lot(db, other_project["id"], other_site["id"], lot_number="1")
    other_supplier = make_supplier(db, name="Somewhere Else Pty")

    a = _delivery(db, other_project, other_site, other_supplier,
                  note_number="DN-SAME", when=date(2026, 3, 18))
    _ledger(db, other_project, other_lot, world["item"], a, 50)
    b = _delivery(db, other_project, other_site, other_supplier,
                  note_number="DN-SAME", when=date(2026, 3, 20))
    _ledger(db, other_project, other_lot, world["item"], b, 50)

    first = _delivery(db, world["project"], world["site"], world["supplier"],
                      note_number="DN-9001", when=date(2026, 3, 18))
    _ledger(db, world["project"], world["lot"], world["item"], first, 100)
    second = _delivery(db, world["project"], world["site"], world["supplier"],
                       note_number="DN-9001", when=date(2026, 3, 20))
    _ledger(db, world["project"], world["lot"], world["item"], second, 100)
    db.commit()

    report = cleanup.classify(db, _project_id(world))
    assert {r["delivery_id"] for r in report["delivery_notes"]} == {
        str(first.id), str(second.id)
    }

    cleanup.apply_cleanup(db, _project_id(world), report,
                          uuid.UUID(world["owner"]["id"]), "test")

    # The other project's duplicate is still there, still a duplicate.
    assert db.get(type(b), b.id).delivery_status == RecordStatus.RECEIVED
    other_on_hand = (
        db.query(StockLedger)
        .filter(StockLedger.project_id == uuid.UUID(other_project["id"]))
        .count()
    )
    assert other_on_hand == 2


# ── Prevention: the same note cannot be posted twice ──────────────────────────

def _create_payload(world, *, note_number, qty=100):
    """The real schema, so the test exercises what the API actually sends."""
    from app.schemas.delivery import DeliveryCreate, DeliveryItemCreate

    return DeliveryCreate(
        supplier_id=uuid.UUID(world["supplier"]["id"]),
        site_id=uuid.UUID(world["site"]["id"]),
        delivery_date=datetime(2026, 3, 18, tzinfo=timezone.utc),
        supplier_delivery_note_number=note_number,
        receiver_name="Site Clerk",
        items=[DeliveryItemCreate(
            description="Cement 42.5N 50kg bag",
            item_id=uuid.UUID(world["item"]["id"]),
            quantity_received=qty,
            unit="bag",
        )],
    )


def test_the_same_supplier_note_cannot_be_recorded_twice(db, world):
    """
    A double-tapped submit, a retried request or a re-imported historical
    document must not create a second delivery — that is what put two sets
    of stock movements behind one physical delivery.
    """
    from app.core.exceptions import ConflictError
    from app.services import delivery_service

    actor = uuid.UUID(world["owner"]["id"])
    pid = _project_id(world)

    delivery_service.create_delivery(db, pid, _create_payload(world, note_number="DN-5150"), actor)
    db.commit()

    with pytest.raises(ConflictError) as exc:
        delivery_service.create_delivery(db, pid, _create_payload(world, note_number="DN-5150"), actor)
    assert "DN-5150" in str(exc.value)
    db.rollback()


def test_the_guard_ignores_case_and_surrounding_space(db, world):
    from app.core.exceptions import ConflictError
    from app.services import delivery_service

    actor = uuid.UUID(world["owner"]["id"])
    pid = _project_id(world)

    delivery_service.create_delivery(db, pid, _create_payload(world, note_number="DN-5150"), actor)
    db.commit()

    with pytest.raises(ConflictError):
        delivery_service.create_delivery(db, pid, _create_payload(world, note_number=" dn-5150 "), actor)
    db.rollback()


def test_deliveries_without_a_note_number_are_still_allowed(db, world):
    """Plenty of deliveries arrive without one; blanks must not collide."""
    from app.services import delivery_service

    actor = uuid.UUID(world["owner"]["id"])
    pid = _project_id(world)

    delivery_service.create_delivery(db, pid, _create_payload(world, note_number=None), actor)
    delivery_service.create_delivery(db, pid, _create_payload(world, note_number=""), actor)
    db.commit()

    from app.models.delivery import Delivery
    assert db.query(Delivery).filter(Delivery.project_id == pid).count() == 2


def test_the_same_note_number_on_another_project_is_allowed(db, world):
    from app.services import delivery_service

    actor = uuid.UUID(world["owner"]["id"])
    other_project = make_project(db, world["owner"]["id"])
    other_site = make_site(db, other_project["id"])
    db.commit()

    delivery_service.create_delivery(
        db, _project_id(world), _create_payload(world, note_number="DN-5150"), actor)

    payload = _create_payload(world, note_number="DN-5150")
    payload.site_id = uuid.UUID(other_site["id"])
    delivery_service.create_delivery(
        db, uuid.UUID(other_project["id"]), payload, actor)
    db.commit()


def test_a_cancelled_duplicate_does_not_block_recapture(db, world):
    """
    After the cleanup utility archives a duplicate, the operator must still
    be able to capture the delivery correctly.
    """
    from app.models.delivery import Delivery
    from app.services import delivery_service

    actor = uuid.UUID(world["owner"]["id"])
    pid = _project_id(world)

    d = delivery_service.create_delivery(
        db, pid, _create_payload(world, note_number="DN-5150"), actor)
    d.delivery_status = RecordStatus.CANCELLED
    db.commit()

    delivery_service.create_delivery(
        db, pid, _create_payload(world, note_number="DN-5150"), actor)
    db.commit()

    assert db.query(Delivery).filter(Delivery.project_id == pid).count() == 2
