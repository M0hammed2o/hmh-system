"""
Flow E — Stage Tracking

Tests:
  - Update stage status
  - Add delay_reason → STAGE_DELAYED alert created
  - Notes persisted
  - Upsert creates record if not exists, updates if exists
  - List stage statuses returns enriched data
"""
import uuid
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from tests.conftest import auth, login, make_project, make_site, make_user


@pytest.fixture()
def stage_setup(db: Session, client: TestClient):
    from app.models.stage import StageMaster
    from app.services.stage_service import seed_default_stages

    owner = make_user(db, role="OWNER")
    office = make_user(db, role="OFFICE_USER")
    site_mgr = make_user(db, role="SITE_MANAGER")
    project = make_project(db, owner["id"])
    site = make_site(db, project["id"])
    db.flush()

    # Ensure stages exist
    seed_default_stages(db)

    # Get first stage
    stage = db.query(StageMaster).order_by(StageMaster.sequence_order).first()

    return {
        "owner": owner, "office": office, "site_mgr": site_mgr,
        "project": project, "site": site,
        "stage_id": str(stage.id) if stage else None,
        "stage_name": stage.name if stage else None,
    }


def test_stage_masters_exist(db: Session, client: TestClient, stage_setup: dict):
    """Stage master list returns at least 10 stages."""
    tok = login(client, stage_setup["office"]["email"], stage_setup["office"]["password"])
    r = client.get("/api/v1/stages/", headers=auth(tok))
    assert r.status_code == 200
    stages = r.json()["data"]
    assert len(stages) >= 10


def test_upsert_stage_status(db: Session, client: TestClient, stage_setup: dict):
    """Upserting a stage status creates a ProjectStageStatus record."""
    tok = login(client, stage_setup["site_mgr"]["email"], stage_setup["site_mgr"]["password"])
    project_id = stage_setup["project"]["id"]
    stage_id = stage_setup["stage_id"]

    assert stage_id is not None, "No stages seeded"

    r = client.post(
        f"/api/v1/projects/{project_id}/stage-statuses/",
        json={
            "stage_id": stage_id,
            "status": "IN_PROGRESS",
            "notes": "Foundation work started",
        },
        headers=auth(tok),
    )
    assert r.status_code in (200, 201), r.text
    data = r.json()["data"]
    assert data["status"] == "IN_PROGRESS"
    assert data["notes"] == "Foundation work started"


def test_stage_delay_creates_alert(db: Session, client: TestClient, stage_setup: dict):
    """Adding delay_reason triggers creation of a SITE_DELAY alert."""
    from app.models.alert import SystemAlert
    from app.models.enums import AlertType

    tok = login(client, stage_setup["site_mgr"]["email"], stage_setup["site_mgr"]["password"])
    project_id = stage_setup["project"]["id"]
    stage_id = stage_setup["stage_id"]

    before = db.query(SystemAlert).filter(
        SystemAlert.alert_type == AlertType.SITE_DELAY
    ).count()

    r = client.post(
        f"/api/v1/projects/{project_id}/stage-statuses/",
        json={
            "stage_id": stage_id,
            "status": "IN_PROGRESS",
            "delay_reason": "Material delivery delayed by supplier",
        },
        headers=auth(tok),
    )
    assert r.status_code in (200, 201), r.text

    after = db.query(SystemAlert).filter(
        SystemAlert.alert_type == AlertType.SITE_DELAY
    ).count()
    assert after > before, "Expected SITE_DELAY alert to be created"


def test_stage_upsert_is_idempotent(db: Session, client: TestClient, stage_setup: dict):
    """Calling upsert twice on same stage updates rather than creating duplicate."""
    from app.models.stage import ProjectStageStatus

    tok = login(client, stage_setup["site_mgr"]["email"], stage_setup["site_mgr"]["password"])
    project_id = stage_setup["project"]["id"]
    stage_id = stage_setup["stage_id"]

    client.post(
        f"/api/v1/projects/{project_id}/stage-statuses/",
        json={"stage_id": stage_id, "status": "NOT_STARTED"},
        headers=auth(tok),
    )
    client.post(
        f"/api/v1/projects/{project_id}/stage-statuses/",
        json={"stage_id": stage_id, "status": "IN_PROGRESS", "notes": "Updated"},
        headers=auth(tok),
    )

    records = db.query(ProjectStageStatus).filter(
        ProjectStageStatus.project_id == uuid.UUID(project_id),
        ProjectStageStatus.stage_id == uuid.UUID(stage_id),
    ).all()

    assert len(records) == 1, f"Expected 1 record, got {len(records)}"
    assert records[0].status.value == "IN_PROGRESS"
    assert "Updated" in (records[0].notes or "")


def test_list_stage_statuses(db: Session, client: TestClient, stage_setup: dict):
    """List stage statuses for project returns enriched data with stage_name."""
    tok = login(client, stage_setup["office"]["email"], stage_setup["office"]["password"])
    project_id = stage_setup["project"]["id"]
    stage_id = stage_setup["stage_id"]

    # Create one
    client.post(
        f"/api/v1/projects/{project_id}/stage-statuses/",
        json={"stage_id": stage_id, "status": "COMPLETED"},
        headers=auth(tok),
    )

    r = client.get(f"/api/v1/projects/{project_id}/stage-statuses/", headers=auth(tok))
    assert r.status_code == 200
    statuses = r.json()["data"]
    assert len(statuses) >= 1

    # Should have stage_name enriched
    found = [s for s in statuses if s["stage_id"] == stage_id]
    assert len(found) == 1
    assert found[0]["stage_name"] == stage_setup["stage_name"]
    assert found[0]["status"] == "COMPLETED"


def test_seed_stages_endpoint(db: Session, client: TestClient, stage_setup: dict):
    """POST /stages/seed is idempotent and returns all stages."""
    tok = login(client, stage_setup["office"]["email"], stage_setup["office"]["password"])
    r = client.post("/api/v1/stages/seed", headers=auth(tok))
    assert r.status_code in (200, 201), r.text
    stages = r.json()["data"]
    assert len(stages) >= 10
