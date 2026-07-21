# Municipality Progress Claim — Data Source Map

**Implementation date:** 2026-07-19

---

## Automatic Claim-Line Sources

Lines are automatically generated from three operational data tables. This table shows what each source contributes and what it does NOT contribute.

| Source | Auto claim-line | Supporting evidence | Context only | Not integrated |
|--------|----------------|---------------------|--------------|----------------|
| `ProjectStageStatus` (COMPLETED/CERTIFIED) | **Yes** — `STAGE_MILESTONE` lines | — | stage name, lot number | statuses below COMPLETED |
| `SubcontractorWorkDone` (SITE_APPROVED+) | **Yes** — `WORK_DONE` lines | — | description, qty, unit, month | PENDING/SUBMITTED records |
| `JobCard` (OWNER_APPROVED+) | **Yes** — `JOB_CARD` lines | — | description, qty, unit, work_date | unapproved job cards |
| `Attachment` / Document Centre | No | **Yes** — via `ProgressClaimEvidence` | — | not auto-linked to lines |
| Delivery / Delivery Notes | No | No | — | not integrated |
| BOQ | No | No | — | not integrated |
| `ProgrammeActivity` | No | No | planned vs actual context | not auto-sourced |
| `WeeklyPlanItem` | No | No | indirect (propagates to StageStatus) | not auto-sourced |
| Site captures (photos) | No | Manual only | — | not auto-linked |

---

## Filter Criteria Per Source

### STAGE_MILESTONE
- `ProjectStageStatus.project_id == claim.project_id`
- `status IN ('COMPLETED', 'CERTIFIED')`
- `completed_at BETWEEN period_start AND cutoff_date`
- Optional: `site_id == claim.site_id` if claim is site-scoped

### WORK_DONE
- `SubcontractorWorkDone.project_id == claim.project_id`
- `status IN ('SITE_APPROVED', 'OFFICE_APPROVED', 'PAID')`
- `month BETWEEN date(period_start) AND date(cutoff_date)`
- Optional: `site_id == claim.site_id`

### JOB_CARD
- `JobCard.project_id == claim.project_id`
- `status IN ('OWNER_APPROVED', 'PAYMENT_APPROVED', 'PAID')`
- `work_date BETWEEN period_start AND cutoff_date`
- Optional: `site_id == claim.site_id`

---

## What Is Deliberately Excluded

- **Deliveries / delivery notes** — these are procurement documents, not construction evidence
- **BOQ items** — planned quantities; not evidence of completion
- **Programme activities** — planning artefacts; progress propagated indirectly via StageStatus
- **Weekly plan items** — internal planning; progress propagated indirectly via StageStatus
- **Pending/unapproved work** — only approved records qualify as evidence
- **All monetary fields** — no rate, unit price, claim amount, VAT, retention, or total

---

## Manual Line Addition

Users with `OFFICE_AND_ABOVE` role can manually add lines to a claim in `GENERATED` or `UNDER_REVIEW` status via `POST /api/v1/progress-claims/{claim_id}/lines`. These lines have `is_system_generated=False` and are not subject to the duplicate UniqueConstraint in the same way.
