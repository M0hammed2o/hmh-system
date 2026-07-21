# Programme Plan — Design Document

**Implementation date:** 2026-07-19  
**Status:** Implemented and verified

---

## Purpose

The Programme Plan module provides Gantt-style activity planning for construction projects. Each activity has planned and actual dates, a status, and a progress percentage. Activities can be linked to specific lots and stage statuses, enabling progress propagation from weekly plan items.

---

## Data Model

### ProgrammeActivity
- Auto-numbered `activity_number` per project (ACT-YYYY-NNN)
- `activity_type`: `CONSTRUCTION | PROCUREMENT | INSPECTION | ADMIN | MILESTONE`
- `planned_start_date` / `planned_finish_date` — the original planned window
- `baseline_start_date` / `baseline_finish_date` — frozen via `POST /.../baseline`, immutable after set
- `actual_start_date` / `actual_finish_date` — set when status moves to IN_PROGRESS/COMPLETED
- `progress_pct` — 0–100, updated by propagation or direct PATCH
- `status`: `NOT_STARTED → IN_PROGRESS → COMPLETED | DELAYED | BLOCKED | CANCELLED | VERIFIED`
- `is_critical_path` — boolean flag (manual, no automated CPM)
- `is_milestone` — boolean flag for zero-duration milestones
- `predecessor_id` / `lag_days` — optional dependency links
- `stage_status_id` — links the activity to a `ProjectStageStatus` record for propagation

---

## Baseline Locking

`POST /api/v1/programme/{activity_id}/baseline` with `{ "confirm": true }` freezes the current `planned_start_date` and `planned_finish_date` into `baseline_start_date` / `baseline_finish_date`.

Rules:
- Only allowed when status is `NOT_STARTED` and no baseline has been set yet
- Baseline fields are read-only after setting
- Enables variance analysis: baseline vs current planned dates

---

## Progress Propagation Inbound

When a `WeeklyPlanItem` is marked done, `propagate_from_plan_item()` is called:

```
WeeklyPlanItem.actual_progress_pct
  → ProgrammeActivity.progress_pct  (if linked via programme_activity_id)
    → ProjectStageStatus.progress_pct  (if linked via stage_status_id)
      → Lot.progress_pct [if field exists — currently does not]
        → Project.progress_pct [if field exists — currently does not]
```

Progress only moves forward — it is never decreased by a single update.

---

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/projects/{project_id}/programme` | List all activities for a project |
| POST | `/api/v1/projects/{project_id}/programme` | Create a new activity |
| GET | `/api/v1/programme/{activity_id}` | Get single activity |
| PATCH | `/api/v1/programme/{activity_id}` | Update fields (progress, status, dates) |
| DELETE | `/api/v1/programme/{activity_id}` | Delete activity |
| POST | `/api/v1/programme/{activity_id}/baseline` | Freeze baseline dates |

---

## Frontend

`ProgrammePlanPage.tsx` — project picker, activity list with progress bars, create modal, inline progress dropdown for IN_PROGRESS activities, baseline button for NOT_STARTED activities without a baseline.
