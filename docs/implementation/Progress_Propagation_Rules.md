# Progress Propagation Rules

**Implementation date:** 2026-07-19  
**File:** `hmh-backend/app/services/progress_propagation_service.py`

---

## The Propagation Chain

Progress flows upward through 5 levels:

```
WeeklyPlanItem.actual_progress_pct        (set by mark_done)
  → ProgrammeActivity.progress_pct        (if item.programme_activity_id set)
    → ProjectStageStatus.progress_pct     (if activity.stage_status_id set)
      → Lot.progress_pct                  (if stage_status.lot_id set AND Lot.progress_pct column exists)
        → Project.progress_pct            (if Lot.progress_pct was updated AND Project.progress_pct column exists)
```

---

## Rules

### Rule 1: Progress Never Decreases
Every step checks `if new_pct > (current_pct or 0)` before writing. A single late update cannot reduce progress.

### Rule 2: Propagation is Non-Fatal
Each propagation step is wrapped in try/except in the route handler. A failure in propagation does not roll back the parent `mark_done` transaction.

### Rule 3: Links Are Optional
Propagation only flows to a level if the linking foreign key is set:
- Item → Activity: only if `item.programme_activity_id` is not null
- Activity → Stage Status: only if `activity.stage_status_id` is not null
- Stage Status → Lot: only if `ss.lot_id` is not null
- Lot → Project: only if `Lot.progress_pct` column exists and lot was updated

### Rule 4: `completed_at` Is Not Set by Propagation
When `ProjectStageStatus.progress_pct` reaches 100, propagation sets status to `AWAITING_INSPECTION` — it does **not** set `completed_at`. That field is set only when a user explicitly transitions the status to `COMPLETED` or `CERTIFIED` via the milestones/stage service. This preserves the inspection step.

### Rule 5: Lot and Project Progress Are Not Stored (Currently)
The `Lot` model has no `progress_pct` column. The propagation service uses `hasattr(lot, "progress_pct")` before writing. Similarly for `Project`. Both are currently computed on-read:
- `GET /api/v1/lots/{lot_id}/progress` — computes from `ProjectStageStatus` records for the lot (weighted average of `progress_pct` fields, and simple milestone completion count)
- Project-level progress is visible on the dashboard via aggregation queries

Because there is no stored `Lot.progress_pct`, the dashboard is never stale — it always computes from live stage data.

---

## Entry Points

| Entry point | When called |
|-------------|-------------|
| `propagate_from_plan_item(db, item, actual_pct)` | When `POST .../items/{item_id}/done` succeeds |
| `propagate_stage_status_update(db, stage_status)` | After direct `PATCH` on a `ProjectStageStatus.progress_pct` |

---

## What Does NOT Trigger Propagation

- Creating a weekly plan item (no progress yet)
- Approving a weekly plan (no item is completed)
- Updating a programme activity directly (only if `propagate_stage_status_update` is called explicitly)
- Creating a progress claim (claims read progress, they do not set it)
- Approving a progress claim (snapshot is taken, no propagation)

---

## Lot Progress Computation (On-Read)

`GET /api/v1/lots/{lot_id}/progress` returns:

| Field | Calculation |
|-------|-------------|
| `total_milestones` | Count of `ProjectStageStatus` for the lot |
| `completed_milestones` | Count where `status IN (COMPLETED, CERTIFIED)` |
| `blocked_milestones` | Count where `status = BLOCKED` |
| `in_progress_milestones` | Count where `status IN (IN_PROGRESS, AWAITING_INSPECTION)` |
| `progress_pct` | `AVG(progress_pct)` of all `ProjectStageStatus` for the lot |
| `completion_pct` | `completed_milestones / total_milestones * 100` |

This is always computed fresh — no stale data risk.
