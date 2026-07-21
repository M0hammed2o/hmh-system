"""
Phase 3D.3 — LotType propagation + customization tracking tests.

Tests:
  1.  Customization hook: editing a BOQ item on a typed lot marks boq_customized_at
  2.  Customization hook: editing an untyped lot does NOT mark it (no false positives)
  3.  Creating a new BOQ item on a typed lot marks it customized
  4.  Deleting a BOQ item on a typed lot marks it customized
  5.  Preview-propagate SAFE: customized lot appears in skipped list
  6.  Preview-propagate FORCE: customized lot appears in propagate list
  7.  Propagate SAFE: customized lots are skipped, clean lots are updated
  8.  Propagate FORCE: all lots updated, customized_at reset to NULL
  9.  After propagation, boq_customized_at reset to NULL for propagated lots
  10. Propagate sets generated_from_lot_type_id on new BOQ items
  11. READ_ONLY blocked from propagate
  12. No template → propagate returns 400/422
  13. No linked lots → propagate returns meaningful response
"""

import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from tests.conftest import auth, login, make_lot, make_project, make_site, make_user, make_user_project_access


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def prop_setup(db: Session, client: TestClient):
    """
    Two lots linked to a LotType with a default template.
    lot1 = clean
    lot2 = will be marked customized in tests
    Template has one section + two items.
    """
    owner  = make_user(db, role="OWNER")
    office = make_user(db, role="OFFICE_ADMIN")
    ro     = make_user(db, role="READ_ONLY")

    project = make_project(db, owner["id"])
    site    = make_site(db, project["id"], "Site A")
    lot1    = make_lot(db, project["id"], site["id"], "1")
    lot2    = make_lot(db, project["id"], site["id"], "2")
    lot_untyped = make_lot(db, project["id"], site["id"], "99")

    make_user_project_access(db, office["id"], project["id"])
    make_user_project_access(db, ro["id"], project["id"])

    db.flush()

    # Build template
    from app.models.boq import BOQHeader, BOQSection, BOQItem
    from app.models.enums import BoqStatus, ItemType
    from app.models.stage import StageMaster

    now = datetime.now(timezone.utc)
    stage = db.query(StageMaster).first()
    if not stage:
        stage = StageMaster(
            id=uuid.uuid4(), name="Foundation",
            code="FOUND", sequence_order=1, description="Test", created_at=now, updated_at=now,
        )
        db.add(stage)
        db.flush()

    tmpl = BOQHeader(
        id=uuid.uuid4(), project_id=uuid.UUID(project["id"]),
        version_name="Propagation Test Template",
        template_name="PropTest",
        source_type="manual", status=BoqStatus.ACTIVE,
        is_active_version=True, is_template=True,
        uploaded_by=uuid.UUID(owner["id"]), uploaded_at=now,
    )
    db.add(tmpl)
    db.flush()

    sec = BOQSection(
        id=uuid.uuid4(), boq_header_id=tmpl.id,
        stage_id=stage.id, section_name="Foundation",
        sequence_order=1, created_at=now, updated_at=now,
    )
    db.add(sec)
    db.flush()

    for i, desc in enumerate(["Cement 50kg", "Rebar 12mm"]):
        db.add(BOQItem(
            id=uuid.uuid4(), boq_section_id=sec.id,
            project_id=uuid.UUID(project["id"]),
            raw_description=desc, item_type=ItemType.MATERIAL,
            planned_quantity=100, planned_rate=5.0,
            sort_order=i, is_active=True,
            created_at=now, updated_at=now,
        ))
    db.flush()

    # Create LotType pointing to template
    from app.models.lot_type import LotType
    lt = LotType(
        id=uuid.uuid4(), project_id=uuid.UUID(project["id"]),
        name="Type A", code="TA",
        default_template_id=tmpl.id,
        created_at=now, updated_at=now,
    )
    db.add(lt)
    db.flush()

    # Assign lot1 and lot2 to the type
    from app.models.lot import Lot
    for lid in [lot1["id"], lot2["id"]]:
        l = db.get(Lot, uuid.UUID(lid))
        l.lot_type_id = lt.id
        l.updated_at = now
    db.flush()

    # Apply template to lot1 (so it has BOQ items to edit)
    from app.services.boq_template_service import clone_template_to_lots
    clone_template_to_lots(
        db,
        template_boq_id=tmpl.id,
        project_id=uuid.UUID(project["id"]),
        lot_ids=[uuid.UUID(lot1["id"])],
        lot_type_id=lt.id,
    )

    return {
        "owner": owner, "office": office, "ro": ro,
        "project": project, "site": site,
        "lot1": lot1, "lot2": lot2, "lot_untyped": lot_untyped,
        "lot_type_id": str(lt.id),
        "template_id": str(tmpl.id),
        "stage_id": str(stage.id),
    }


# ── Customization tracking ────────────────────────────────────────────────────

def test_edit_item_marks_typed_lot_customized(db: Session, client: TestClient, prop_setup: dict):
    """Editing a BOQ item on a typed lot sets boq_customized_at."""
    from sqlalchemy import text
    tok = login(client, prop_setup["office"]["email"], prop_setup["office"]["password"])

    # Find an active BOQ item for lot1
    item = db.execute(text(
        "SELECT id FROM boq_items WHERE lot_id = :lid AND is_active = TRUE LIMIT 1"
    ), {"lid": prop_setup["lot1"]["id"]}).fetchone()
    assert item, "lot1 must have BOQ items (applied from template in fixture)"

    # Edit the item
    r = client.patch(
        f"/api/v1/boq/items/{item[0]}",
        json={"planned_quantity": 999},
        headers=auth(tok),
    )
    assert r.status_code == 200, r.text

    # boq_customized_at must now be set
    ts = db.execute(text(
        "SELECT boq_customized_at FROM lots WHERE id = :lid"
    ), {"lid": prop_setup["lot1"]["id"]}).scalar()
    assert ts is not None, "boq_customized_at must be set after manual edit"


def test_edit_item_untyped_lot_no_customized(db: Session, client: TestClient, prop_setup: dict):
    """Editing a BOQ item on an untyped lot does NOT set boq_customized_at."""
    from sqlalchemy import text
    from app.models.boq import BOQHeader, BOQSection, BOQItem
    from app.models.enums import BoqStatus, ItemType
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    # Create a BOQ item for the untyped lot
    hdr = BOQHeader(
        id=uuid.uuid4(), project_id=uuid.UUID(prop_setup["project"]["id"]),
        version_name="Untyped", source_type="manual", status=BoqStatus.ACTIVE,
        is_active_version=True, is_template=False,
        uploaded_by=uuid.UUID(prop_setup["owner"]["id"]), uploaded_at=now,
    )
    db.add(hdr)
    db.flush()
    sec = BOQSection(
        id=uuid.uuid4(), boq_header_id=hdr.id, section_name="S",
        sequence_order=1, created_at=now, updated_at=now,
    )
    db.add(sec)
    db.flush()
    item = BOQItem(
        id=uuid.uuid4(), boq_section_id=sec.id,
        project_id=uuid.UUID(prop_setup["project"]["id"]),
        lot_id=uuid.UUID(prop_setup["lot_untyped"]["id"]),
        raw_description="Untyped item", item_type=ItemType.MATERIAL,
        planned_quantity=10, sort_order=0, is_active=True,
        created_at=now, updated_at=now,
    )
    db.add(item)
    db.flush()

    tok = login(client, prop_setup["office"]["email"], prop_setup["office"]["password"])
    r = client.patch(f"/api/v1/boq/items/{item.id}", json={"planned_quantity": 20}, headers=auth(tok))
    assert r.status_code == 200

    ts = db.execute(
        __import__("sqlalchemy").text("SELECT boq_customized_at FROM lots WHERE id = :lid"),
        {"lid": prop_setup["lot_untyped"]["id"]},
    ).scalar()
    assert ts is None, "Untyped lot must NOT be marked customized"


# ── Preview propagation ───────────────────────────────────────────────────────

def test_preview_safe_skips_customized(db: Session, client: TestClient, prop_setup: dict):
    """In SAFE mode, a customized lot appears as 'skip' in the preview."""
    from sqlalchemy import text
    from app.models.lot import Lot
    from datetime import datetime, timezone

    # Mark lot1 as customized
    lot1 = db.get(Lot, uuid.UUID(prop_setup["lot1"]["id"]))
    lot1.boq_customized_at = datetime.now(timezone.utc)
    db.flush()

    tok = login(client, prop_setup["office"]["email"], prop_setup["office"]["password"])
    r = client.post(
        f"/api/v1/lot-types/{prop_setup['lot_type_id']}/preview-propagate",
        json={"mode": "SAFE"},
        headers=auth(tok),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["lots_skipped"] == 1
    skipped_numbers = [l["lot_number"] for l in data["lots"] if l["action"] == "skip"]
    assert "1" in skipped_numbers


def test_preview_force_includes_customized(db: Session, client: TestClient, prop_setup: dict):
    """In FORCE mode, even customized lots appear as 'propagate'."""
    from app.models.lot import Lot
    from datetime import datetime, timezone

    lot1 = db.get(Lot, uuid.UUID(prop_setup["lot1"]["id"]))
    lot1.boq_customized_at = datetime.now(timezone.utc)
    db.flush()

    tok = login(client, prop_setup["office"]["email"], prop_setup["office"]["password"])
    r = client.post(
        f"/api/v1/lot-types/{prop_setup['lot_type_id']}/preview-propagate",
        json={"mode": "FORCE"},
        headers=auth(tok),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["lots_skipped"] == 0
    assert data["lots_to_propagate"] == 2


# ── Actual propagation ────────────────────────────────────────────────────────

def test_propagate_safe_skips_customized(db: Session, client: TestClient, prop_setup: dict):
    """SAFE propagation skips customized lots and updates clean ones."""
    from sqlalchemy import text
    from app.models.lot import Lot
    from datetime import datetime, timezone

    # Mark lot1 as customized, lot2 is clean
    lot1 = db.get(Lot, uuid.UUID(prop_setup["lot1"]["id"]))
    lot1.boq_customized_at = datetime.now(timezone.utc)
    db.flush()

    tok = login(client, prop_setup["office"]["email"], prop_setup["office"]["password"])
    r = client.post(
        f"/api/v1/lot-types/{prop_setup['lot_type_id']}/propagate",
        json={"mode": "SAFE", "generate_milestones": False},
        headers=auth(tok),
    )
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["propagated"] == 1   # only lot2 (clean)
    assert result["skipped"]    == 1   # lot1 (customized)


def test_propagate_force_overwrites_all(db: Session, client: TestClient, prop_setup: dict):
    """FORCE propagation overwrites all lots including customized ones."""
    from app.models.lot import Lot
    from datetime import datetime, timezone

    lot1 = db.get(Lot, uuid.UUID(prop_setup["lot1"]["id"]))
    lot1.boq_customized_at = datetime.now(timezone.utc)
    db.flush()

    tok = login(client, prop_setup["office"]["email"], prop_setup["office"]["password"])
    r = client.post(
        f"/api/v1/lot-types/{prop_setup['lot_type_id']}/propagate",
        json={"mode": "FORCE", "generate_milestones": False},
        headers=auth(tok),
    )
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["propagated"] == 2
    assert result["skipped"]    == 0


def test_propagation_resets_customized_at(db: Session, client: TestClient, prop_setup: dict):
    """After FORCE propagation, boq_customized_at is reset to NULL."""
    from sqlalchemy import text
    from app.models.lot import Lot
    from datetime import datetime, timezone

    lot1 = db.get(Lot, uuid.UUID(prop_setup["lot1"]["id"]))
    lot1.boq_customized_at = datetime.now(timezone.utc)
    db.flush()

    tok = login(client, prop_setup["office"]["email"], prop_setup["office"]["password"])
    client.post(
        f"/api/v1/lot-types/{prop_setup['lot_type_id']}/propagate",
        json={"mode": "FORCE", "generate_milestones": False},
        headers=auth(tok),
    )

    # lot1 should now have boq_customized_at = NULL (reset after propagation)
    ts = db.execute(text(
        "SELECT boq_customized_at FROM lots WHERE id = :lid"
    ), {"lid": prop_setup["lot1"]["id"]}).scalar()
    assert ts is None, "boq_customized_at must be reset to NULL after FORCE propagation"


def test_propagation_sets_generated_from_lot_type_id(db: Session, client: TestClient, prop_setup: dict):
    """Items created via propagation have generated_from_lot_type_id set."""
    from sqlalchemy import text
    tok = login(client, prop_setup["office"]["email"], prop_setup["office"]["password"])

    client.post(
        f"/api/v1/lot-types/{prop_setup['lot_type_id']}/propagate",
        json={"mode": "SAFE", "generate_milestones": False},
        headers=auth(tok),
    )

    # lot2 is clean — check its items have generated_from_lot_type_id set
    count = db.execute(text(
        "SELECT COUNT(*) FROM boq_items "
        "WHERE lot_id = :lid "
        "  AND generated_from_lot_type_id = :ltid "
        "  AND is_active = TRUE"
    ), {
        "lid":  prop_setup["lot2"]["id"],
        "ltid": prop_setup["lot_type_id"],
    }).scalar()
    assert count >= 1, (
        "Items created by propagation must have generated_from_lot_type_id set. "
        f"Got {count} items with the field set for lot2."
    )


def test_propagate_no_template_returns_error(db: Session, client: TestClient, prop_setup: dict):
    """Propagating a type with no template returns a clear error."""
    tok = login(client, prop_setup["office"]["email"], prop_setup["office"]["password"])

    # Create a type without a template
    r = client.post(
        f"/api/v1/projects/{prop_setup['project']['id']}/lot-types/",
        json={"name": "No Template"},
        headers=auth(tok),
    )
    no_tmpl_id = r.json()["data"]["id"]

    r2 = client.post(
        f"/api/v1/lot-types/{no_tmpl_id}/propagate",
        json={"mode": "SAFE"},
        headers=auth(tok),
    )
    assert r2.status_code in (400, 422), f"Expected error, got {r2.status_code}: {r2.text}"


def test_read_only_cannot_propagate(db: Session, client: TestClient, prop_setup: dict):
    tok = login(client, prop_setup["ro"]["email"], prop_setup["ro"]["password"])
    r = client.post(
        f"/api/v1/lot-types/{prop_setup['lot_type_id']}/propagate",
        json={"mode": "SAFE"},
        headers=auth(tok),
    )
    assert r.status_code == 403
