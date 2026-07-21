# Municipality Progress Claim — Current State Verification

**Date:** 2026-07-19  
**Author:** Principal Architect — Phase 1b Inspection  
**Classification:** L2 — Pre-implementation evidence record  
**Purpose:** Document verified state of the repository before any implementation begins, so future decisions can be traced to confirmed facts rather than assumptions.

---

## Confidence key

| Label | Meaning |
|-------|---------|
| `Verified` | Confirmed by direct file inspection or tool output in this session |
| `Derived` | Calculated from two or more verified facts |
| `Likely` | Strong basis, not directly confirmed by file read |
| `Requires Business Decision` | Implementation cannot proceed without owner input |
| `Unknown` | Settling this requires information not in the repository |

---

## 1 — Existing Municipality Invoice System

### 1.1 MunicipalityInvoice model

`Verified` — `hmh-backend/app/models/municipality_invoice.py`

```
Table: municipality_invoices
├─ id (UUID PK)
├─ invoice_number (VARCHAR, UNIQUE)
├─ cert_number (VARCHAR, nullable)
├─ project_id (UUID FK → projects, CASCADE DELETE)
├─ invoice_date (DATE)
├─ due_date (DATE, nullable)
├─ client_name (VARCHAR, default "Ethekweni Municipality")
├─ client_vat_no (VARCHAR, nullable)
├─ client_address (VARCHAR, nullable)
├─ subtotal (NUMERIC 14,2)
├─ previously_paid (NUMERIC 14,2, default 0)
├─ vat_rate (NUMERIC 5,4, default 0.15)
├─ vat_amount (NUMERIC 14,2)
├─ total_due (NUMERIC 14,2)
├─ notes (TEXT, nullable)
├─ bank_name, account_number, branch_name, branch_code (all nullable)
├─ status (VARCHAR 20) — "DRAFT" or "FINALISED" (no typed enum)
├─ created_by (UUID FK → users, SET NULL)
├─ created_at, updated_at (TIMESTAMPTZ)
└─ items → list[MunicipalityInvoiceItem]
```

**Critical gaps confirmed:**
- No link to ProjectStageStatus, SubcontractorWorkDone, or JobCard
- No link to any new ProgressClaim entity
- No typed enum for `status` — stored as raw VARCHAR
- Pure financial / manual data entry system

### 1.2 Router registration

`Verified` — `hmh-backend/app/api/v1/muni_invoice.py` lines 1–289

- `project_muni_router`: `GET /projects/{project_id}/municipality-invoices/template`, `GET /projects/{project_id}/municipality-invoices`, `POST /projects/{project_id}/municipality-invoices`
- `muni_router`: `GET /{id}`, `PATCH /{id}`, `DELETE /{id}`, `GET /{id}/export/excel`
- All schemas are **inline** in the route file (no separate `schemas/muni_invoice.py`)

**Decision for new system:** New entities use dedicated `schemas/progress_claim.py`, `schemas/programme.py`, `schemas/weekly_plan.py` files, not inline.

---

## 2 — Canonical Operational Sources for Claim Generation

### 2.1 SubcontractorWorkDone

`Verified` — `hmh-backend/app/models/work_done.py`

```
Table: subcontractor_work_done
├─ work_done_number (VARCHAR, unique)
├─ project_id, site_id (FKs)
├─ lot_id (UUID FK → lots, nullable)
├─ stage_status_id (UUID FK → project_stage_status, nullable)
├─ supplier_id (UUID FK → suppliers)
├─ job_card_id (UUID FK → job_cards, nullable)
├─ work_description, quantity, unit, rate, amount
├─ month (DATE — stored as 1st of month, represents billing period)
└─ status (WorkDoneStatus enum)
```

Status flow: `DRAFT → SUBMITTED → SITE_APPROVED → OFFICE_APPROVED → PAID / REJECTED`

**Inclusion rule for claim generation:**
- `status IN (SITE_APPROVED, OFFICE_APPROVED, PAID)` AND `month` within claim period

### 2.2 JobCard

`Verified` — `hmh-backend/app/models/job_card.py`

```
Table: job_cards
├─ job_card_number (VARCHAR, unique)
├─ project_id, site_id, lot_id, stage_id (FKs)
├─ work_description, work_type, worker_name, team_name
├─ quantity, unit, rate, total_amount
├─ work_date (DATE — the date the work was performed)
└─ status (JobCardStatus enum)
```

Status flow: `DRAFT → SUBMITTED → SITE_APPROVED → OFFICE_APPROVED → OWNER_APPROVED → PAYMENT_APPROVED → PAID / REJECTED`

**Inclusion rule for claim generation:**
- `status IN (OWNER_APPROVED, PAYMENT_APPROVED, PAID)` AND `work_date` within claim period

### 2.3 ProjectStageStatus (Milestone source)

`Verified` — `hmh-backend/app/models/stage.py`

```
Table: project_stage_status
├─ project_id, site_id, lot_id (FKs)
├─ stage_id (FK → stage_master)
├─ status (StageStatus enum)
├─ progress_pct (SmallInteger, default 0)
├─ planned_completion_date (DATE, nullable — added migration 0026)
├─ completion_notes, completed_by_name
├─ completed_at, started_at (TIMESTAMPTZ, nullable)
└─ blocked_reason (TEXT, nullable)
```

`StageStatus` values: `NOT_STARTED, IN_PROGRESS, BLOCKED, AWAITING_INSPECTION, COMPLETED, CERTIFIED`

**Inclusion rule for claim generation:**
- `status IN (COMPLETED, CERTIFIED)` AND `completed_at` within claim period

### 2.4 Attachment (Evidence source)

`Verified` — `hmh-backend/app/models/attachment.py`

Polymorphic — any attachment can be linked to a claim line via `entity_type` + `entity_id`.
The new `PROGRESS_CLAIM` entity type will be added to `AttachmentEntity` enum.

---

## 3 — Missing Entities (to be implemented)

### 3.1 MunicipalityProgressClaim

`Verified absent` — no file or table matching "progress_claim" exists in the repository.

**Planned design:**
```
Table: municipality_progress_claims
├─ id (UUID PK)
├─ claim_number (VARCHAR, generated, unique)
├─ project_id (UUID FK → projects)
├─ site_id (UUID FK → sites, nullable — project-wide or site-specific)
├─ period_start, period_end (DATE — defines the billing period)
├─ reporting_cutoff_date (DATE — latest date for new work evidence)
├─ status (ProgressClaimStatus enum)
├─ claim_title (VARCHAR — human-readable label e.g. "June 2026 Progress Claim")
├─ municipality_name (VARCHAR, default "Ethekweni Municipality")
├─ cert_number (VARCHAR, nullable — linked to municipal certification)
├─ notes (TEXT, nullable)
├─ generation_summary (JSONB — counts and source breakdown from auto-generation)
├─ snapshot_json (JSONB — immutable copy written at APPROVED status)
├─ linked_invoice_id (UUID FK → municipality_invoices, nullable — for pricing follow-up)
├─ generated_at (TIMESTAMPTZ, nullable)
├─ approved_at (TIMESTAMPTZ, nullable)
├─ exported_at (TIMESTAMPTZ, nullable)
├─ created_by (UUID FK → users)
├─ created_at, updated_at (TIMESTAMPTZ)
└─ lines → list[ProgressClaimLine]
```

**Status machine:**
```
DRAFT → GENERATED → UNDER_REVIEW → READY_FOR_PRICING → APPROVED → EXPORTED
                                                                  ↘ CANCELLED (any state)
```

### 3.2 ProgressClaimLine

**Planned design:**
```
Table: progress_claim_lines
├─ id (UUID PK)
├─ claim_id (UUID FK → municipality_progress_claims, CASCADE)
├─ source_type (ClaimSourceType enum: STAGE_MILESTONE | WORK_DONE | JOB_CARD)
├─ lot_id (UUID FK → lots, nullable)
├─ stage_status_id (UUID FK → project_stage_status, nullable)
├─ work_done_id (UUID FK → subcontractor_work_done, nullable)
├─ job_card_id (UUID FK → job_cards, nullable)
├─ description (TEXT — human-readable work description)
├─ stage_name (VARCHAR — denormalised for export stability)
├─ lot_number (VARCHAR — denormalised)
├─ work_date (DATE — when the work was done / period end)
├─ quantity (NUMERIC, nullable — from source record, NOT a price)
├─ unit (VARCHAR, nullable — from source record)
├─ progress_pct (SmallInteger, nullable — from stage_status if source is milestone)
├─ is_included (BOOLEAN, default true — reviewer can exclude lines)
├─ is_system_generated (BOOLEAN, default true)
├─ reviewer_notes (TEXT, nullable)
└─ sort_order (INTEGER, default 0)
```

**Anti-double-counting rule:** A (lot_id, stage_status_id, source_type) triple is unique per claim. If both WORK_DONE and STAGE_MILESTONE reference the same lot+stage, they appear as separate rows with different source_types.

**No pricing rule:** `rate`, `unit_price`, `claim_amount`, `total` fields are deliberately absent. Pricing is added only after READY_FOR_PRICING status by a human.

### 3.3 ProgressClaimEvidence

**Planned design:**
```
Table: progress_claim_evidence
├─ id (UUID PK)
├─ claim_id (UUID FK → municipality_progress_claims, CASCADE)
├─ line_id (UUID FK → progress_claim_lines, CASCADE, nullable — claim-level or line-level)
├─ attachment_id (UUID FK → attachments, nullable — link to existing attachment)
├─ evidence_type (VARCHAR — PHOTO, PDF, COMPLETION_CERTIFICATE, etc.)
├─ caption (VARCHAR, nullable)
├─ is_included (BOOLEAN, default true)
└─ added_by (UUID FK → users)
```

### 3.4 ProgrammeActivity

`Verified absent` — no file, table, or route matching "programme_activity" or "programme" exists.

**Planned design:**
```
Table: programme_activities
├─ id (UUID PK)
├─ project_id (UUID FK → projects, CASCADE)
├─ site_id (UUID FK → sites, nullable)
├─ lot_id (UUID FK → lots, nullable)
├─ stage_status_id (UUID FK → project_stage_status, nullable)
├─ activity_number (VARCHAR, auto-generated, unique)
├─ title (VARCHAR — human label for the activity)
├─ description (TEXT, nullable)
├─ activity_type (VARCHAR — CONSTRUCTION | PROCUREMENT | INSPECTION | ADMIN | MILESTONE)
├─ planned_start_date, planned_finish_date (DATE)
├─ actual_start_date, actual_finish_date (DATE, nullable)
├─ baseline_start_date, baseline_finish_date (DATE, nullable — original plan, immutable after baseline set)
├─ duration_days (INTEGER, derived)
├─ progress_pct (SmallInteger, default 0)
├─ status (ProgrammeActivityStatus enum)
├─ predecessor_id (UUID FK → programme_activities SELF, nullable — Gantt dependency)
├─ lag_days (INTEGER, default 0 — days after predecessor finishes)
├─ is_critical_path (BOOLEAN, default false)
├─ is_milestone (BOOLEAN, default false)
├─ responsible_team (VARCHAR, nullable)
├─ notes (TEXT, nullable)
├─ created_by (UUID FK → users)
└─ created_at, updated_at (TIMESTAMPTZ)
```

### 3.5 WeeklyPlan and WeeklyPlanItem

`Verified absent`

**Planned design:**
```
Table: weekly_plans
├─ id (UUID PK)
├─ plan_number (VARCHAR, auto-generated, unique)
├─ project_id (UUID FK → projects)
├─ site_id (UUID FK → sites, nullable)
├─ week_start_date (DATE — always Monday)
├─ week_end_date (DATE — always Sunday)
├─ status (WeeklyPlanStatus enum)
├─ submitted_by (UUID FK → users, nullable)
├─ approved_by (UUID FK → users, nullable)
├─ submitted_at, approved_at (TIMESTAMPTZ, nullable)
├─ notes (TEXT, nullable)
└─ created_at, updated_at (TIMESTAMPTZ)

Table: weekly_plan_items
├─ id (UUID PK)
├─ plan_id (UUID FK → weekly_plans, CASCADE)
├─ programme_activity_id (UUID FK → programme_activities, nullable)
├─ stage_status_id (UUID FK → project_stage_status, nullable)
├─ lot_id (UUID FK → lots, nullable)
├─ description (TEXT)
├─ planned_progress_pct (SmallInteger — target progress by week end)
├─ actual_progress_pct (SmallInteger, nullable — filled when marking done)
├─ carry_forward (BOOLEAN, default false — not completed last week)
├─ completion_notes (TEXT, nullable)
├─ completed_at (TIMESTAMPTZ, nullable)
└─ sort_order (INTEGER, default 0)
```

---

## 4 — Existing Enums

### 4.1 Enums that need additions

`Verified` — `hmh-backend/app/models/enums.py`

**AlertType** — needs: `CLAIM_READY_FOR_PRICING`, `CLAIM_APPROVED`, `WEEKLY_PLAN_DUE`

**AttachmentEntity** — needs: `PROGRESS_CLAIM`, `PROGRAMME_ACTIVITY`, `WEEKLY_PLAN`

**AuditAction** — current values adequate: `CREATE`, `UPDATE`, `APPROVE`, `REJECT`. No new values needed.

### 4.2 New enums required

```python
class ProgressClaimStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    GENERATED = "GENERATED"
    UNDER_REVIEW = "UNDER_REVIEW"
    READY_FOR_PRICING = "READY_FOR_PRICING"
    APPROVED = "APPROVED"
    EXPORTED = "EXPORTED"
    CANCELLED = "CANCELLED"

class ClaimSourceType(str, enum.Enum):
    STAGE_MILESTONE = "STAGE_MILESTONE"
    WORK_DONE = "WORK_DONE"
    JOB_CARD = "JOB_CARD"

class ProgrammeActivityStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    DELAYED = "DELAYED"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    VERIFIED = "VERIFIED"
    CANCELLED = "CANCELLED"

class WeeklyPlanStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    REVIEWED = "REVIEWED"
    CANCELLED = "CANCELLED"
```

---

## 5 — Frontend Current State

### 5.1 Existing municipality routes

`Verified` — `hmh-frontend/src/routes/AppRouter.tsx`

```
/municipality-invoices   → MunicipalityInvoicePage
/milestones             → MilestonesPage
/timeline               → TimelinePage  (placeholder — renders empty or stub)
/work-done              → WorkDonePage
```

### 5.2 Sidebar

`Verified` — `hmh-frontend/src/components/layout/AppSidebar.tsx` (inspected)

Sidebar items are defined as an array of objects with `icon`, `label`, `path`. New items for Progress Claims, Programme Plan, and Weekly Work Plan will be added to the "Projects" section.

### 5.3 No existing progress-claim pages

`Verified absent` — no file matching `ProgressClaim` or `progress_claim` or `programme` (frontend) exists in `hmh-frontend/src/`.

---

## 6 — Migration Chain

`Verified` — `hmh-backend/alembic/versions/`

Latest migration: `0067_supplier_payment_due_days.py` (revision = "0067", down_revision = "0066")

Pattern (raw SQL, IF NOT EXISTS guards):
```python
def upgrade():
    op.execute(text("ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS payment_due_days INTEGER"))
def downgrade():
    op.execute(text("ALTER TABLE suppliers DROP COLUMN IF EXISTS payment_due_days"))
```

New migration will be `0068_progress_claim_programme_weekly_plan.py`, down_revision = "0067".

---

## 7 — Router Registration Pattern

`Verified` — `hmh-backend/main.py` lines 282–381

```python
app.include_router(project_muni_router, prefix="/api/v1")
app.include_router(muni_router, prefix="/api/v1")
```

New routers will follow the same pattern:
```python
app.include_router(progress_claim_project_router, prefix="/api/v1")
app.include_router(progress_claim_router, prefix="/api/v1")
app.include_router(programme_project_router, prefix="/api/v1")
app.include_router(programme_router, prefix="/api/v1")
app.include_router(weekly_plan_project_router, prefix="/api/v1")
app.include_router(weekly_plan_router, prefix="/api/v1")
```

---

## 8 — Permission Model

`Verified` — roles from `UserRole` enum and pattern from `require_roles()` dependency

| Action | Allowed roles |
|--------|--------------|
| Create / generate claim | OWNER, OFFICE_ADMIN, OFFICE_USER |
| Review claim (include/exclude lines) | OWNER, OFFICE_ADMIN, OFFICE_USER |
| Advance to READY_FOR_PRICING | OWNER, OFFICE_ADMIN |
| Approve claim | OWNER |
| Export claim PDF | OWNER, OFFICE_ADMIN, OFFICE_USER |
| Create programme activity | OWNER, OFFICE_ADMIN, SITE_MANAGER |
| Update programme activity | OWNER, OFFICE_ADMIN, SITE_MANAGER |
| Create weekly plan | SITE_MANAGER, OFFICE_ADMIN |
| Submit weekly plan | SITE_MANAGER |
| Approve weekly plan | OWNER, OFFICE_ADMIN |
| Mark weekly plan items done | SITE_MANAGER, SITE_STAFF |

---

## 9 — Business Decisions Required Before Implementation

`Requires Business Decision` — The following items have no obvious technical answer:

1. **Claim number format** — e.g. `PC-2026-001` or `{project_code}-PC-001`? Implementation will default to `PC-{YYYY}-{sequence:04d}` and this can be changed.

2. **Programme activity number format** — e.g. `ACT-001` per project? Implementation will default to `ACT-{project_code}-{seq:03d}`.

3. **Weekly plan number format** — e.g. `WP-2026-W28`? Implementation will use ISO week number: `WP-{YYYY}-W{week:02d}-{project_code}`.

4. **Can a single claim cover multiple sites?** — Implementation defaults to: one claim = one project, optionally filtered to one site. Multi-site claims are not supported in Phase 1.

5. **What happens when a claim is CANCELLED?** — Lines and evidence are retained for audit. The cancelled claim is not deleted. This is the implementation default.

6. **Does approving a claim automatically create a MunicipalityInvoice?** — Implementation default: No. The `linked_invoice_id` FK allows manual linking after the claim is priced, but no automatic creation. This preserves the existing invoice workflow.

---

## 10 — Architecture Compliance Checklist

Each new entity is checked against the 15 Architecture Principles before implementation:

| Principle | Compliance plan |
|-----------|----------------|
| AP-01: One canonical owner | ProgressClaim owns all claim data; MunicipalityInvoice owns financial data |
| AP-02: Audit on every status change | Every `claim.status =` call will call `audit_service.write_event()` |
| AP-03: Terminal states | EXPORTED, CANCELLED are terminal states |
| AP-04: Notifications after commit | All `enqueue_direct()` calls follow `db.flush()` in the service |
| AP-05: No duplicate logic | New vote/approval logic uses existing `require_roles()` dependency |
| AP-06: One transaction | Each service function performs one atomic transaction |
| AP-07: Financial traceability | ProgressClaim → linked_invoice_id → MunicipalityInvoice; claim lines → source FKs |
| AP-08: Contributes to financial summary | Out of scope for Phase 1 — claim is operational, not financial |
| AP-09: Alembic migration | Migration 0068 follows the IF NOT EXISTS pattern |
| AP-10: Idempotency | claim_number has UNIQUE constraint; generation is idempotent |
| AP-11: Backward compat | Existing municipality_invoices unchanged; new entities are additions |
| AP-14: AI is enhancement layer | No AI in Phase 1 claim generation |
| AP-15: Test coverage matches risk | 28+ tests planned; financial and state-change routes get adversarial tests |
