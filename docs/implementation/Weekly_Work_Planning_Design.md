# Weekly Work Planning — Design Document

**Implementation date:** 2026-07-19  
**Status:** Implemented and verified

---

## Purpose

The Weekly Work Plan module provides operational week-by-week task planning. Site supervisors create a plan for each work week, listing the tasks to be done and the expected progress percentage for each. Office managers approve the plan. At week end, site staff mark each item done with the actual progress achieved. Completion triggers upward propagation to programme activities and stage statuses.

---

## Data Model

### WeeklyPlan
- Auto-numbered `plan_number` per project (WP-YYYY-NNN)
- `week_start_date` — always a Monday; adjusted automatically if non-Monday is entered
- `week_end_date` — always `week_start_date + 6 days`
- `status`: `DRAFT → SUBMITTED → APPROVED → IN_PROGRESS → COMPLETED | REVIEWED | CANCELLED`
- `submitted_by` / `approved_by` — UUID references to users
- Contains a list of `WeeklyPlanItem`

### WeeklyPlanItem
- `programme_activity_id` — optional link to a programme activity (enables propagation)
- `stage_status_id` — optional link to a stage status (enables propagation)
- `lot_id` — optional lot scope
- `description` — what the task is
- `planned_progress_pct` — expected completion % for this week
- `actual_progress_pct` — set when the item is marked done
- `carry_forward` — flag for incomplete items carried to the next week
- `completed_at` — timestamp when marked done

---

## Workflow

```
DRAFT → SUBMITTED → APPROVED → IN_PROGRESS
  └─ site adds items     └─ mark items done → COMPLETED
```

1. Site supervisor creates plan (DRAFT), adds items
2. Submits for approval (SUBMITTED)
3. Office manager approves (APPROVED)
4. Site marks items done during the week (IN_PROGRESS)
5. When all items are done, plan moves to COMPLETED

---

## Progress Propagation

When `POST /api/v1/weekly-plans/{plan_id}/items/{item_id}/done` is called:

1. `WeeklyPlanItem.actual_progress_pct` is set
2. If item has `programme_activity_id`:
   - `ProgrammeActivity.progress_pct` is updated if new value > current
   - If `progress_pct >= 100`: activity status → `COMPLETED`, `actual_finish_date` set
3. If that activity has `stage_status_id`:
   - `ProjectStageStatus.progress_pct` is updated if new value > current
   - If `progress_pct >= 100`: stage status → `AWAITING_INSPECTION`
4. If that stage status has `lot_id`:
   - `_propagate_to_lot()` calculates average `progress_pct` of all stage statuses for the lot
   - `Lot.progress_pct` is updated only if that field exists (`hasattr` guard)
5. If lot was updated and `Project.progress_pct` exists:
   - Average of all lots is written to project (`hasattr` guard)

**Key constraint:** progress never decreases. Each step only writes if `new_pct > current_pct`.

---

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/projects/{project_id}/weekly-plans` | List plans for project |
| POST | `/api/v1/projects/{project_id}/weekly-plans` | Create plan |
| GET | `/api/v1/weekly-plans/{plan_id}` | Get plan with items |
| PATCH | `/api/v1/weekly-plans/{plan_id}` | Update plan metadata |
| POST | `/api/v1/weekly-plans/{plan_id}/submit` | Submit for approval |
| POST | `/api/v1/weekly-plans/{plan_id}/approve` | Approve (OFFICE_AND_ABOVE) |
| POST | `/api/v1/weekly-plans/{plan_id}/reject` | Reject with reason |
| POST | `/api/v1/weekly-plans/{plan_id}/items` | Add item to plan |
| PATCH | `/api/v1/weekly-plans/{plan_id}/items/{item_id}` | Update item |
| DELETE | `/api/v1/weekly-plans/{plan_id}/items/{item_id}` | Remove item |
| POST | `/api/v1/weekly-plans/{plan_id}/items/{item_id}/done` | Mark item done |

---

## Frontend

`WeeklyPlanPage.tsx` — project picker, plan list (left panel), plan detail with items (right panel). Items can be added in DRAFT/APPROVED/IN_PROGRESS status. Each item has a "Mark done" dropdown. Submit and Approve buttons are context-sensitive to the current plan status.
