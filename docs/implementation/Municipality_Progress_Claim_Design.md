# Municipality Progress Claim — Design Document

**Implementation date:** 2026-07-19  
**Status:** Implemented and verified

---

## Purpose

The Municipality Progress Claim module allows HMH Group to compile monthly progress claims to be submitted to the municipality for housing projects. The claim documents **physical work evidence only** — no monetary amounts are stored or exported at this level. Pricing is added separately by the client after the claim is reviewed.

---

## State Machine

```
DRAFT → GENERATED → UNDER_REVIEW → READY_FOR_PRICING → APPROVED → EXPORTED
  └──────────────────────────────────────────────────────────────── CANCELLED
```

| Status | Who transitions | What it means |
|--------|----------------|----------------|
| DRAFT | System (on create) | Claim header exists, no lines yet |
| GENERATED | Any OFFICE_AND_ABOVE | Lines auto-generated from work evidence |
| UNDER_REVIEW | Any OFFICE_AND_ABOVE | Line inclusion/exclusion review in progress |
| READY_FOR_PRICING | Any OFFICE_AND_ABOVE | Evidence review complete; ready for pricing team |
| APPROVED | OWNER or OFFICE_ADMIN only | Claim formally approved; snapshot frozen |
| EXPORTED | OWNER or OFFICE_ADMIN only | PDF exported and submitted to municipality |
| CANCELLED | Any OFFICE_AND_ABOVE | Claim abandoned; cannot be reactivated |

---

## Data Model

### MunicipalityProgressClaim
- Scoped to `project_id` (with optional `site_id` for site-specific claims)
- Auto-numbered `claim_number` per project (PC-YYYY-NNN)
- `period_start` / `period_end` — the reporting window
- `reporting_cutoff_date` — defaults to `period_end`; records up to this date are included
- `generation_summary` (JSONB) — counts lines added per source, duplicates skipped
- `snapshot_json` (JSONB) — immutable copy of included lines at approval time

### ProgressClaimLine
- `source_type`: `STAGE_MILESTONE` | `WORK_DONE` | `JOB_CARD`
- Linked to `lot_id`, `stage_status_id`, `work_done_id`, or `job_card_id`
- UniqueConstraint `uq_claim_line_lot_stage_source` on `(claim_id, lot_id, stage_status_id, source_type)` — prevents duplicate lines
- `is_included` (bool) — reviewer can toggle individual lines
- **No monetary fields** — `rate`, `unit_price`, `claim_amount` are absent by design

### ProgressClaimEvidence
- Optional evidence records linking attachments to specific claim lines
- Used for photo evidence, delivery notes, etc.

---

## Line Generation

`generate_lines()` queries three sources within the claim period:

1. **Stage Milestones** — `ProjectStageStatus` records with status `COMPLETED` or `CERTIFIED` within the period
2. **Work Done** — `SubcontractorWorkDone` records with status `SITE_APPROVED`, `OFFICE_APPROVED`, or `PAID` within the period
3. **Job Cards** — `JobCard` records with status `OWNER_APPROVED`, `PAYMENT_APPROVED`, or `PAID` within the period

Each source has a separate toggle (`include_milestones`, `include_work_done`, `include_job_cards`). All default to `True`.

Duplicate prevention: the UniqueConstraint rejects re-insertion of the same lot+stage+source combination.

Regeneration guard: APPROVED and EXPORTED claims cannot have lines regenerated (raises `ValueError`).

---

## PDF Export

- Generated via reportlab on demand
- A4 page, 2 cm margins
- Header: claim number, title, municipality, period, status, certificate number
- No-pricing notice in body: *"No monetary amounts are included — pricing is added separately"*
- Table columns: `#, Type, Lot, Stage / Description, Date, Qty, Unit, Progress`
- Only `is_included=True` lines appear in the table
- Long descriptions are word-wrapped in the description column
- Footer: total included line count, generation timestamp

---

## Security

- All endpoints require JWT authentication
- `check_project_access()` enforces tenant isolation on every request
- Only `OWNER` or `OFFICE_ADMIN` can approve (transition to `APPROVED`)
- Approved/exported claims are frozen against further modification
