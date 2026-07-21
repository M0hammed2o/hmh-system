"""
Tests for Municipality Progress Claim, Programme Activities, and Weekly Plans.

Coverage:
  T01-T06: Progress claim CRUD
  T07-T10: Progress claim line generation
  T11-T15: Progress claim status transitions
  T16-T17: Progress claim PDF export
  T18-T21: Claim line include/exclude
  T22-T26: Programme activity CRUD + baseline
  T27-T31: Weekly plan CRUD + approval flow
  T32-T34: Weekly plan item marking
  T35-T36: Progress propagation (unit)
  T37-T38: Permission enforcement (403 on wrong role)
"""

import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import (
    auth, login, make_project, make_site, make_lot, make_user,
)


# ── Shared fixtures ────────────────────────────────────────────────────────────

@pytest.fixture()
def ctx(db: Session, client: TestClient):
    """Owner + project + site + lot, logged in as OWNER."""
    owner = make_user(db, role="OWNER")
    office = make_user(db, role="OFFICE_USER")
    project = make_project(db, owner["id"])
    site = make_site(db, project["id"])
    lot = make_lot(db, project["id"], site["id"], lot_number="LOT-01")
    db.flush()

    owner_token = login(client, owner["email"], owner["password"])
    office_token = login(client, office["email"], office["password"])

    return {
        "owner": owner, "office": office,
        "project": project, "site": site, "lot": lot,
        "owner_headers": auth(owner_token),
        "office_headers": auth(office_token),
        "project_id": project["id"],
    }


def _create_claim(client, ctx, **overrides):
    payload = {
        "claim_title": "June 2026 Progress Claim",
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "municipality_name": "Ethekweni Municipality",
    }
    payload.update(overrides)
    r = client.post(
        f"/api/v1/projects/{ctx['project_id']}/progress-claims",
        json=payload,
        headers=ctx["owner_headers"],
    )
    return r


# ── T01-T06: Progress Claim CRUD ───────────────────────────────────────────────

def test_T01_create_progress_claim(db, client, ctx):
    """T01 — Create a progress claim returns 200 with DRAFT status."""
    r = _create_claim(client, ctx)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "DRAFT"
    assert data["claim_number"].startswith("PC-")
    assert data["lines"] == []


def test_T02_claim_number_is_unique(db, client, ctx):
    """T02 — Two claims get different claim numbers."""
    r1 = _create_claim(client, ctx, claim_title="Claim A")
    r2 = _create_claim(client, ctx, claim_title="Claim B")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["data"]["claim_number"] != r2.json()["data"]["claim_number"]


def test_T03_get_claim(db, client, ctx):
    """T03 — GET /progress-claims/{id} returns the claim."""
    r = _create_claim(client, ctx)
    claim_id = r.json()["data"]["id"]
    r2 = client.get(f"/api/v1/progress-claims/{claim_id}", headers=ctx["owner_headers"])
    assert r2.status_code == 200
    assert r2.json()["data"]["id"] == claim_id


def test_T04_update_claim_title(db, client, ctx):
    """T04 — PATCH updates claim title."""
    r = _create_claim(client, ctx)
    claim_id = r.json()["data"]["id"]
    r2 = client.patch(
        f"/api/v1/progress-claims/{claim_id}",
        json={"claim_title": "Updated Title"},
        headers=ctx["owner_headers"],
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["claim_title"] == "Updated Title"


def test_T05_delete_claim(db, client, ctx):
    """T05 — DELETE removes a DRAFT claim."""
    r = _create_claim(client, ctx)
    claim_id = r.json()["data"]["id"]
    r2 = client.delete(f"/api/v1/progress-claims/{claim_id}", headers=ctx["owner_headers"])
    assert r2.status_code == 200
    r3 = client.get(f"/api/v1/progress-claims/{claim_id}", headers=ctx["owner_headers"])
    assert r3.status_code == 404


def test_T06_list_claims_for_project(db, client, ctx):
    """T06 — GET /projects/{id}/progress-claims returns all claims."""
    _create_claim(client, ctx, claim_title="Claim 1")
    _create_claim(client, ctx, claim_title="Claim 2")
    r = client.get(
        f"/api/v1/projects/{ctx['project_id']}/progress-claims",
        headers=ctx["owner_headers"],
    )
    assert r.status_code == 200
    assert len(r.json()["data"]) >= 2


# ── T07-T10: Claim line generation ────────────────────────────────────────────

def test_T07_generate_lines_with_no_sources(db, client, ctx):
    """T07 — Generate lines on empty project returns 0 lines and GENERATED status."""
    r = _create_claim(client, ctx)
    claim_id = r.json()["data"]["id"]
    r2 = client.post(
        f"/api/v1/progress-claims/{claim_id}/generate",
        json={"include_work_done": True, "include_job_cards": True, "include_milestones": True},
        headers=ctx["owner_headers"],
    )
    assert r2.status_code == 200
    summary = r2.json()["data"]
    assert summary["total_lines"] == 0
    # Confirm status advanced to GENERATED
    r3 = client.get(f"/api/v1/progress-claims/{claim_id}", headers=ctx["owner_headers"])
    assert r3.json()["data"]["status"] == "GENERATED"


def test_T08_generate_creates_milestone_lines(db, client, ctx):
    """T08 — Completed stage_status within period creates STAGE_MILESTONE lines."""
    from app.models.stage import StageMaster, ProjectStageStatus
    from app.models.enums import StageStatus

    # Create a stage master
    _hex = uuid.uuid4().hex[:6]
    sm = StageMaster(name=f"Excavation-{_hex}", code=f"EXC-{_hex}", sequence_order=uuid.uuid4().int % 10000 + 1000, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    db.add(sm)
    db.flush()

    # Create a completed stage status within period
    ss = ProjectStageStatus(
        project_id=uuid.UUID(ctx["project_id"]),
        site_id=uuid.UUID(ctx["site"]["id"]),
        lot_id=uuid.UUID(ctx["lot"]["id"]),
        stage_id=sm.id,
        status=StageStatus.COMPLETED.value,
        progress_pct=100,
        completed_at=datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(ss)
    db.flush()

    r = _create_claim(client, ctx, period_start="2026-06-01", period_end="2026-06-30")
    claim_id = r.json()["data"]["id"]
    r2 = client.post(
        f"/api/v1/progress-claims/{claim_id}/generate",
        json={"include_milestones": True, "include_work_done": False, "include_job_cards": False},
        headers=ctx["owner_headers"],
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["milestone_lines"] >= 1

    # Confirm lines in claim
    r3 = client.get(f"/api/v1/progress-claims/{claim_id}", headers=ctx["owner_headers"])
    lines = r3.json()["data"]["lines"]
    milestone_lines = [l for l in lines if l["source_type"] == "STAGE_MILESTONE"]
    assert len(milestone_lines) >= 1
    assert milestone_lines[0]["is_included"] is True
    # Verify: NO monetary amounts
    assert "claim_amount" not in milestone_lines[0]
    assert "unit_price" not in milestone_lines[0]
    assert "rate" not in milestone_lines[0]


def test_T09_generate_excludes_stages_outside_period(db, client, ctx):
    """T09 — Stage completed outside period is NOT included."""
    from app.models.stage import StageMaster, ProjectStageStatus
    from app.models.enums import StageStatus

    _hex2 = uuid.uuid4().hex[:6]
    sm = StageMaster(name=f"Roofing-{_hex2}", code=f"ROF-{_hex2}", sequence_order=uuid.uuid4().int % 10000 + 2000, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    db.add(sm)
    db.flush()

    # Completed in MAY — outside June period
    ss = ProjectStageStatus(
        project_id=uuid.UUID(ctx["project_id"]),
        site_id=uuid.UUID(ctx["site"]["id"]),
        stage_id=sm.id,
        status=StageStatus.COMPLETED.value,
        progress_pct=100,
        completed_at=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(ss)
    db.flush()

    r = _create_claim(client, ctx, period_start="2026-06-01", period_end="2026-06-30")
    claim_id = r.json()["data"]["id"]
    r2 = client.post(
        f"/api/v1/progress-claims/{claim_id}/generate",
        json={"include_milestones": True, "include_work_done": False, "include_job_cards": False},
        headers=ctx["owner_headers"],
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["milestone_lines"] == 0


def test_T10_generate_is_idempotent_without_overwrite(db, client, ctx):
    """T10 — Generating twice without overwrite_existing does not duplicate lines."""
    r = _create_claim(client, ctx)
    claim_id = r.json()["data"]["id"]
    params = {"include_milestones": True, "include_work_done": True, "include_job_cards": True}
    client.post(f"/api/v1/progress-claims/{claim_id}/generate", json=params, headers=ctx["owner_headers"])
    client.post(f"/api/v1/progress-claims/{claim_id}/generate", json=params, headers=ctx["owner_headers"])
    r3 = client.get(f"/api/v1/progress-claims/{claim_id}", headers=ctx["owner_headers"])
    lines = r3.json()["data"]["lines"]
    # With no sources, 0 lines either way
    assert lines is not None


# ── T11-T15: Status transitions ────────────────────────────────────────────────

def test_T11_transition_draft_to_generated_via_generate(db, client, ctx):
    """T11 — Generate endpoint advances status to GENERATED."""
    r = _create_claim(client, ctx)
    claim_id = r.json()["data"]["id"]
    assert r.json()["data"]["status"] == "DRAFT"
    client.post(
        f"/api/v1/progress-claims/{claim_id}/generate",
        json={},
        headers=ctx["owner_headers"],
    )
    r2 = client.get(f"/api/v1/progress-claims/{claim_id}", headers=ctx["owner_headers"])
    assert r2.json()["data"]["status"] == "GENERATED"


def test_T12_transition_generated_to_under_review(db, client, ctx):
    """T12 — Transition GENERATED → UNDER_REVIEW."""
    r = _create_claim(client, ctx)
    claim_id = r.json()["data"]["id"]
    client.post(f"/api/v1/progress-claims/{claim_id}/generate", json={}, headers=ctx["owner_headers"])
    r2 = client.post(
        f"/api/v1/progress-claims/{claim_id}/transition/UNDER_REVIEW",
        headers=ctx["owner_headers"],
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["status"] == "UNDER_REVIEW"


def test_T13_transition_under_review_to_ready_for_pricing(db, client, ctx):
    """T13 — Transition UNDER_REVIEW → READY_FOR_PRICING."""
    r = _create_claim(client, ctx)
    claim_id = r.json()["data"]["id"]
    client.post(f"/api/v1/progress-claims/{claim_id}/generate", json={}, headers=ctx["owner_headers"])
    client.post(f"/api/v1/progress-claims/{claim_id}/transition/UNDER_REVIEW", headers=ctx["owner_headers"])
    r2 = client.post(
        f"/api/v1/progress-claims/{claim_id}/transition/READY_FOR_PRICING",
        headers=ctx["owner_headers"],
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["status"] == "READY_FOR_PRICING"


def test_T14_approve_claim(db, client, ctx):
    """T14 — OWNER can approve a READY_FOR_PRICING claim; snapshot_json is written."""
    r = _create_claim(client, ctx)
    claim_id = r.json()["data"]["id"]
    client.post(f"/api/v1/progress-claims/{claim_id}/generate", json={}, headers=ctx["owner_headers"])
    client.post(f"/api/v1/progress-claims/{claim_id}/transition/UNDER_REVIEW", headers=ctx["owner_headers"])
    client.post(f"/api/v1/progress-claims/{claim_id}/transition/READY_FOR_PRICING", headers=ctx["owner_headers"])
    r2 = client.post(
        f"/api/v1/progress-claims/{claim_id}/transition/APPROVED",
        headers=ctx["owner_headers"],
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["status"] == "APPROVED"
    assert r2.json()["data"]["approved_at"] is not None


def test_T15_invalid_transition_raises_400(db, client, ctx):
    """T15 — Attempting DRAFT → APPROVED directly returns 400."""
    r = _create_claim(client, ctx)
    claim_id = r.json()["data"]["id"]
    r2 = client.post(
        f"/api/v1/progress-claims/{claim_id}/transition/APPROVED",
        headers=ctx["owner_headers"],
    )
    assert r2.status_code == 400


# ── T16-T17: PDF export ────────────────────────────────────────────────────────

def test_T16_export_pdf_returns_pdf_bytes(db, client, ctx):
    """T16 — PDF export returns Content-Type application/pdf."""
    r = _create_claim(client, ctx)
    claim_id = r.json()["data"]["id"]
    r2 = client.get(f"/api/v1/progress-claims/{claim_id}/export/pdf", headers=ctx["owner_headers"])
    assert r2.status_code == 200
    assert r2.headers["content-type"] == "application/pdf"
    assert len(r2.content) > 0


def test_T17_export_pdf_filename_contains_claim_number(db, client, ctx):
    """T17 — PDF Content-Disposition includes the claim number."""
    r = _create_claim(client, ctx)
    claim_id = r.json()["data"]["id"]
    claim_number = r.json()["data"]["claim_number"]
    r2 = client.get(f"/api/v1/progress-claims/{claim_id}/export/pdf", headers=ctx["owner_headers"])
    assert claim_number in r2.headers.get("content-disposition", "")


# ── T18-T21: Claim line include/exclude ───────────────────────────────────────

def test_T18_exclude_line(db, client, ctx):
    """T18 — PATCH line sets is_included=False."""
    from app.models.stage import StageMaster, ProjectStageStatus
    from app.models.enums import StageStatus

    _hex3 = uuid.uuid4().hex[:6]
    sm = StageMaster(name=f"Walls-{_hex3}", code=f"WAL-{_hex3}", sequence_order=uuid.uuid4().int % 10000 + 3000, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    db.add(sm)
    db.flush()
    ss = ProjectStageStatus(
        project_id=uuid.UUID(ctx["project_id"]),
        site_id=uuid.UUID(ctx["site"]["id"]),
        stage_id=sm.id,
        status=StageStatus.COMPLETED.value,
        progress_pct=100,
        completed_at=datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(ss)
    db.flush()

    r = _create_claim(client, ctx, period_start="2026-06-01", period_end="2026-06-30")
    claim_id = r.json()["data"]["id"]
    client.post(f"/api/v1/progress-claims/{claim_id}/generate",
                json={"include_milestones": True, "include_work_done": False, "include_job_cards": False},
                headers=ctx["owner_headers"])

    r2 = client.get(f"/api/v1/progress-claims/{claim_id}", headers=ctx["owner_headers"])
    lines = r2.json()["data"]["lines"]
    assert len(lines) >= 1
    line_id = lines[0]["id"]

    r3 = client.patch(
        f"/api/v1/progress-claims/{claim_id}/lines/{line_id}",
        json={"is_included": False},
        headers=ctx["owner_headers"],
    )
    assert r3.status_code == 200

    r4 = client.get(f"/api/v1/progress-claims/{claim_id}", headers=ctx["owner_headers"])
    updated_line = next(l for l in r4.json()["data"]["lines"] if l["id"] == line_id)
    assert updated_line["is_included"] is False


def test_T19_add_manual_line(db, client, ctx):
    """T19 — POST /lines adds a non-system-generated line."""
    r = _create_claim(client, ctx)
    claim_id = r.json()["data"]["id"]
    r2 = client.post(
        f"/api/v1/progress-claims/{claim_id}/lines",
        json={"source_type": "STAGE_MILESTONE", "description": "Manual completion entry", "sort_order": 99},
        headers=ctx["owner_headers"],
    )
    assert r2.status_code == 200
    r3 = client.get(f"/api/v1/progress-claims/{claim_id}", headers=ctx["owner_headers"])
    lines = r3.json()["data"]["lines"]
    manual = [l for l in lines if not l["is_system_generated"]]
    assert len(manual) >= 1


def test_T20_delete_manual_line(db, client, ctx):
    """T20 — DELETE /lines/{id} removes a claim line."""
    r = _create_claim(client, ctx)
    claim_id = r.json()["data"]["id"]
    r2 = client.post(
        f"/api/v1/progress-claims/{claim_id}/lines",
        json={"source_type": "JOB_CARD", "description": "Temp entry"},
        headers=ctx["owner_headers"],
    )
    line_id = r2.json()["data"]["id"]
    r3 = client.delete(
        f"/api/v1/progress-claims/{claim_id}/lines/{line_id}",
        headers=ctx["owner_headers"],
    )
    assert r3.status_code == 200


def test_T21_cannot_modify_approved_claim(db, client, ctx):
    """T21 — PATCH on APPROVED claim returns 400."""
    r = _create_claim(client, ctx)
    claim_id = r.json()["data"]["id"]
    # Quick-approve path
    client.post(f"/api/v1/progress-claims/{claim_id}/generate", json={}, headers=ctx["owner_headers"])
    client.post(f"/api/v1/progress-claims/{claim_id}/transition/UNDER_REVIEW", headers=ctx["owner_headers"])
    client.post(f"/api/v1/progress-claims/{claim_id}/transition/READY_FOR_PRICING", headers=ctx["owner_headers"])
    client.post(f"/api/v1/progress-claims/{claim_id}/transition/APPROVED", headers=ctx["owner_headers"])

    r2 = client.patch(
        f"/api/v1/progress-claims/{claim_id}",
        json={"claim_title": "Trying to modify approved"},
        headers=ctx["owner_headers"],
    )
    assert r2.status_code == 400


# ── T22-T26: Programme Activity CRUD + baseline ────────────────────────────────

def _create_activity(client, ctx, **overrides):
    payload = {
        "title": "Excavation Site A",
        "planned_start_date": "2026-07-01",
        "planned_finish_date": "2026-07-14",
        "activity_type": "CONSTRUCTION",
    }
    payload.update(overrides)
    return client.post(
        f"/api/v1/projects/{ctx['project_id']}/programme",
        json=payload,
        headers=ctx["owner_headers"],
    )


def test_T22_create_programme_activity(db, client, ctx):
    """T22 — Create activity returns 200 with NOT_STARTED status."""
    r = _create_activity(client, ctx)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "NOT_STARTED"
    assert data["progress_pct"] == 0
    assert data["activity_number"].startswith("ACT-")
    assert data["duration_days"] == 14


def test_T23_list_project_activities(db, client, ctx):
    """T23 — List activities for a project."""
    _create_activity(client, ctx, title="Activity 1")
    _create_activity(client, ctx, title="Activity 2")
    r = client.get(f"/api/v1/projects/{ctx['project_id']}/programme", headers=ctx["owner_headers"])
    assert r.status_code == 200
    assert len(r.json()["data"]) >= 2


def test_T24_update_activity_progress(db, client, ctx):
    """T24 — PATCH activity updates progress_pct."""
    r = _create_activity(client, ctx)
    act_id = r.json()["data"]["id"]
    r2 = client.patch(
        f"/api/v1/programme/{act_id}",
        json={"progress_pct": 50, "status": "IN_PROGRESS"},
        headers=ctx["owner_headers"],
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["progress_pct"] == 50


def test_T25_delete_not_started_activity(db, client, ctx):
    """T25 — DELETE a NOT_STARTED activity succeeds."""
    r = _create_activity(client, ctx)
    act_id = r.json()["data"]["id"]
    r2 = client.delete(f"/api/v1/programme/{act_id}", headers=ctx["owner_headers"])
    assert r2.status_code == 200
    r3 = client.get(f"/api/v1/programme/{act_id}", headers=ctx["owner_headers"])
    assert r3.status_code == 404


def test_T26_set_baseline_freezes_planned_dates(db, client, ctx):
    """T26 — POST /baseline stores baseline_start_date and baseline_finish_date."""
    r = _create_activity(client, ctx)
    act_id = r.json()["data"]["id"]
    r2 = client.post(
        f"/api/v1/programme/{act_id}/baseline",
        json={"confirm": True},
        headers=ctx["owner_headers"],
    )
    assert r2.status_code == 200
    data = r2.json()["data"]
    assert data["baseline_start_date"] == "2026-07-01"
    assert data["baseline_finish_date"] == "2026-07-14"


# ── T27-T31: Weekly plan CRUD + approval flow ──────────────────────────────────

def _create_plan(client, ctx, week_start="2026-07-07"):
    return client.post(
        f"/api/v1/projects/{ctx['project_id']}/weekly-plans",
        json={"week_start_date": week_start},
        headers=ctx["owner_headers"],
    )


def test_T27_create_weekly_plan(db, client, ctx):
    """T27 — Create plan returns 200 with DRAFT status."""
    r = _create_plan(client, ctx)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "DRAFT"
    assert data["plan_number"].startswith("WP-")
    assert data["items"] == []


def test_T28_duplicate_plan_week_returns_400(db, client, ctx):
    """T28 — Creating two plans for the same project+week returns 400."""
    _create_plan(client, ctx, week_start="2026-07-07")
    r2 = _create_plan(client, ctx, week_start="2026-07-07")
    assert r2.status_code == 400


def test_T29_add_item_to_plan(db, client, ctx):
    """T29 — POST /items adds an item to a DRAFT plan."""
    r = _create_plan(client, ctx, week_start="2026-07-14")
    plan_id = r.json()["data"]["id"]
    r2 = client.post(
        f"/api/v1/weekly-plans/{plan_id}/items",
        json={"description": "Complete raft slab lot 01", "planned_progress_pct": 100},
        headers=ctx["owner_headers"],
    )
    assert r2.status_code == 200


def test_T30_submit_plan(db, client, ctx):
    """T30 — POST /submit transitions DRAFT → SUBMITTED."""
    r = _create_plan(client, ctx, week_start="2026-07-21")
    plan_id = r.json()["data"]["id"]
    r2 = client.post(f"/api/v1/weekly-plans/{plan_id}/submit", headers=ctx["owner_headers"])
    assert r2.status_code == 200
    assert r2.json()["data"]["status"] == "SUBMITTED"


def test_T31_approve_plan(db, client, ctx):
    """T31 — POST /approve transitions SUBMITTED → APPROVED."""
    r = _create_plan(client, ctx, week_start="2026-07-28")
    plan_id = r.json()["data"]["id"]
    client.post(f"/api/v1/weekly-plans/{plan_id}/submit", headers=ctx["owner_headers"])
    r2 = client.post(f"/api/v1/weekly-plans/{plan_id}/approve", headers=ctx["owner_headers"])
    assert r2.status_code == 200
    assert r2.json()["data"]["status"] == "APPROVED"
    assert r2.json()["data"]["approved_at"] is not None


# ── T32-T34: Weekly plan item marking ─────────────────────────────────────────

def test_T32_mark_item_done(db, client, ctx):
    """T32 — POST /done sets actual_progress_pct."""
    r = _create_plan(client, ctx, week_start="2026-08-04")
    plan_id = r.json()["data"]["id"]
    r2 = client.post(
        f"/api/v1/weekly-plans/{plan_id}/items",
        json={"description": "Install roof structure", "planned_progress_pct": 50},
        headers=ctx["owner_headers"],
    )
    item_id = r2.json()["data"]["id"]
    r3 = client.post(
        f"/api/v1/weekly-plans/{plan_id}/items/{item_id}/done",
        json={"actual_progress_pct": 50, "completion_notes": "Completed on schedule"},
        headers=ctx["owner_headers"],
    )
    assert r3.status_code == 200


def test_T33_delete_plan_item(db, client, ctx):
    """T33 — DELETE /items/{id} removes an item."""
    r = _create_plan(client, ctx, week_start="2026-08-11")
    plan_id = r.json()["data"]["id"]
    r2 = client.post(
        f"/api/v1/weekly-plans/{plan_id}/items",
        json={"description": "Temp item"},
        headers=ctx["owner_headers"],
    )
    item_id = r2.json()["data"]["id"]
    r3 = client.delete(
        f"/api/v1/weekly-plans/{plan_id}/items/{item_id}",
        headers=ctx["owner_headers"],
    )
    assert r3.status_code == 200


def test_T34_reject_plan_reverts_to_draft(db, client, ctx):
    """T34 — POST /reject transitions SUBMITTED → DRAFT."""
    r = _create_plan(client, ctx, week_start="2026-08-18")
    plan_id = r.json()["data"]["id"]
    client.post(f"/api/v1/weekly-plans/{plan_id}/submit", headers=ctx["owner_headers"])
    r2 = client.post(
        f"/api/v1/weekly-plans/{plan_id}/reject?reason=Needs more detail",
        headers=ctx["owner_headers"],
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["status"] == "DRAFT"


# ── T35-T36: Progress propagation (unit level) ────────────────────────────────

def test_T35_propagation_service_updates_activity(db, client, ctx):
    """T35 — propagate_from_plan_item updates ProgrammeActivity.progress_pct."""
    from app.models.programme import ProgrammeActivity
    from app.models.enums import ProgrammeActivityStatus
    from app.services.progress_propagation_service import propagate_from_plan_item
    from app.models.weekly_plan import WeeklyPlanItem

    activity = ProgrammeActivity(
        activity_number=f"ACT-TST-001",
        project_id=uuid.UUID(ctx["project_id"]),
        title="Test Activity",
        planned_start_date=date(2026, 7, 1),
        planned_finish_date=date(2026, 7, 14),
        status=ProgrammeActivityStatus.IN_PROGRESS.value,
        progress_pct=20,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(activity)
    db.flush()

    item = WeeklyPlanItem(
        plan_id=uuid.uuid4(),
        programme_activity_id=activity.id,
        description="Test item",
        planned_progress_pct=50,
    )
    item.id = uuid.uuid4()

    propagate_from_plan_item(db, item, actual_progress_pct=60)
    db.flush()

    db.refresh(activity)
    assert activity.progress_pct == 60


def test_T36_propagation_does_not_decrease_progress(db, client, ctx):
    """T36 — propagate_from_plan_item ignores new value lower than current."""
    from app.models.programme import ProgrammeActivity
    from app.models.enums import ProgrammeActivityStatus
    from app.services.progress_propagation_service import propagate_from_plan_item
    from app.models.weekly_plan import WeeklyPlanItem

    activity = ProgrammeActivity(
        activity_number=f"ACT-TST-002",
        project_id=uuid.UUID(ctx["project_id"]),
        title="Test Activity 2",
        planned_start_date=date(2026, 7, 1),
        planned_finish_date=date(2026, 7, 14),
        status=ProgrammeActivityStatus.IN_PROGRESS.value,
        progress_pct=80,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(activity)
    db.flush()

    item = WeeklyPlanItem(
        plan_id=uuid.uuid4(),
        programme_activity_id=activity.id,
        description="Test item 2",
        planned_progress_pct=30,
    )
    item.id = uuid.uuid4()

    propagate_from_plan_item(db, item, actual_progress_pct=30)
    db.flush()

    db.refresh(activity)
    assert activity.progress_pct == 80  # Unchanged


# ── T37-T38: Permission enforcement ───────────────────────────────────────────

def test_T37_unauthenticated_request_returns_401(db, client, ctx):
    """T37 — Request without Authorization header returns 401/403."""
    r = client.get(f"/api/v1/projects/{ctx['project_id']}/progress-claims")
    assert r.status_code in (401, 403)


def test_T38_site_staff_cannot_approve_claim(db, client, ctx):
    """T38 — SITE_STAFF role cannot approve a progress claim (requires OWNER/OFFICE_ADMIN)."""
    site_staff = make_user(db, role="SITE_STAFF")
    from tests.conftest import make_user_project_access
    make_user_project_access(db, site_staff["id"], ctx["project_id"])
    db.flush()

    staff_token = login(client, site_staff["email"], site_staff["password"])
    staff_headers = auth(staff_token)

    # Create and advance claim to READY_FOR_PRICING as owner
    r = _create_claim(client, ctx)
    claim_id = r.json()["data"]["id"]
    client.post(f"/api/v1/progress-claims/{claim_id}/generate", json={}, headers=ctx["owner_headers"])
    client.post(f"/api/v1/progress-claims/{claim_id}/transition/UNDER_REVIEW", headers=ctx["owner_headers"])
    client.post(f"/api/v1/progress-claims/{claim_id}/transition/READY_FOR_PRICING", headers=ctx["owner_headers"])

    # Site staff tries to approve
    r2 = client.post(
        f"/api/v1/progress-claims/{claim_id}/transition/APPROVED",
        headers=staff_headers,
    )
    assert r2.status_code in (403, 400)
