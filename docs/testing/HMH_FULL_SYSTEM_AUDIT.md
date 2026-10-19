# HMH Group Management System — live browser audit

Audited 2026-10-18 against commit `2e4233c` (merged to `main` as `07109d2`).

---

## Read this first: what was and was not verified

**Every screenshot in this report was captured against a LOCAL stack**, not
production. There is no production credential of any kind in this
environment — no application login, no database URL, no Render or Supabase
access. The local `DATABASE_URL` points at `127.0.0.1`.

| Environment | What ran there |
|---|---|
| **Local audit stack** | Backend on `127.0.0.1:8010` bound to a throwaway `hmh_audit` database at migration `0078`; a production-mode frontend build served at `127.0.0.1:4190` and pointed at it. All functional testing and all 25 screenshots. |
| **Production** | Read-only HTTP only: health endpoints and unauthenticated route probes. **No login, no data read, no write.** |

Consequently:

- **No claim in this report is production verification**, except the handful
  explicitly marked *(production, read-only)*.
- **Live Dassenhoek BOQ quantities could not be verified.** Phase 7 was
  exercised against a synthetic reproduction of the defect instead, and is
  labelled as such.
- **The real Anthropic extraction test could not run.** There is no
  `ANTHROPIC_API_KEY` in this environment. No mock was substituted.

All data created during this audit is fictional and exists only in the local
`hmh_audit` database. No production record was read, written or deleted. No
real payment, stock movement or financial transaction was created anywhere.

---

## 1. Baseline

| Check | Result |
|---|---|
| Branch | `feat/fleet-workshop-companies` @ `2e4233c` |
| PR #1 | **MERGED** 2026-10-14 |
| PR #2 | **MERGED** 2026-10-18, into `main` as `07109d2` |
| Production backend *(production, read-only)* | `/health` 200 · `/health/db` 200 `db=connected` · `env=production` |
| Production frontend *(production, read-only)* | `https://app.hmhgroup.co.za` → 200 |
| PR #2 deployed to production? | **Yes.** `/api/v1/workshop/mechanic-payments` returns **401**, not 404 — the route exists and demands auth |
| Migrations 0076 / 0077 / 0078 | Applied on the local audit DB; chain `0076→0077→0078`, single head `0078` |
| Production migration level | **Inferred, not confirmed.** The 0078-dependent route answers 401 rather than erroring, which is consistent with the migration having run. Confirming it needs database access this environment does not have. |
| Schema compatibility | Both migrations are additive — 0077 inserts rows, 0078 creates one table. Nothing existing is altered |
| Outstanding deployment failures | None observed from outside |

---

## 2. Results by phase

Legend: **PASS** verified by test and screenshot · **BLOCKED** could not be
reached with available access.

### Phase 2 — Companies

| # | Test | Expected | Actual | Status | Evidence |
|---|---|---|---|---|---|
| 2.1 | All five companies exist as database records | 5 records | API returned HMH Group, Minerat Construction & Civils, Kukhanya Kabusha, Premium Structures, Ophezulu | **PASS** | `01-company-list.png` |
| 2.2 | All five render in the UI | visible | "5 companies" badge, all five listed | **PASS** | `01-company-list.png` |
| 2.3 | Company selector is table-driven | new companies selectable | All three new names present as `<option>`s | **PASS** | `02-company-selector.png` |
| 2.4 | Projects associate with each company | one project per company | 5 projects seeded and linked, each filterable | **PASS** | `06-mechanic-payments-overview.png` (company filter) |
| 2.5 | Existing HMH / Minerat data intact | unchanged | Both present, untouched; legacy letterhead keys still resolve to their fixed details | **PASS** | backend `test_legacy_purchase_orders_are_unchanged` |
| 2.6 | No company uses another's letterhead | own name | A PO carrying a new company's id renders that company and produces a real PDF (`%PDF`, >1 kB) | **PASS** | `test_a_purchase_order_pdf_generates_for_a_new_company` |
| 2.7 | Staff permissions not widened | no new access | Registering a company creates zero `UserProjectAccess` rows; site staff still 403 | **PASS** | `test_a_new_company_does_not_widen_site_staff_access` |

### Phase 3 — Vehicle repair editing

| # | Test | Expected | Actual | Status | Evidence |
|---|---|---|---|---|---|
| 3.1 | Open repair history | list renders | 35 repairs, newest first | **PASS** | `03a-repair-history-before-edit.png` |
| 3.2 | Edit action present and opens prefilled | existing values | Form opened with title populated; assertion fails the test if blank | **PASS** | `03-edit-repair-form.png` |
| 3.3 | Change a non-financial field, save, reload | value persists | Description changed, page re-navigated, server value shown | **PASS** | `04-repair-updated.png` |
| 3.4 | Audit trail records the change | before/after per field | Field-level before/after recorded; a no-op resubmit records nothing | **PASS** | backend `test_every_change_is_written_to_the_audit_trail` |
| 3.5 | Unauthorised users cannot edit | 403 | SITE_STAFF → 403 | **PASS** | `test_site_staff_cannot_edit_a_repair` |
| 3.6 | Financially locked fields refuse silently-wrong edits | 409 + reason | Moving a repair with costs, editing an approved amount, or cutting below what was paid all refused with a message naming the obstacle | **PASS** | `test_a_repair_with_recorded_costs_cannot_be_moved_to_another_vehicle` and siblings |

### Phase 4 — Repair history pagination

| # | Test | Expected | Actual | Status | Evidence |
|---|---|---|---|---|---|
| 4.1 | 35 synthetic repairs all retrievable | 35 | Walking the pages yields 35 distinct ids | **PASS** | backend `test_all_thirty_five_repairs_are_reachable` |
| 4.2 | Total count shown | 35 | "35 repair job(s)" | **PASS** | `05-repair-pagination.png` |
| 4.3 | Page 2 shows older repairs, no overlap | disjoint | Browser-level: page 1 and page 2 share zero records | **PASS** | `05b-repair-pagination-page2.png` |
| 4.4 | Page sizes 10 / 25 / 50 | all work | Parametrised test over all three | **PASS** | `test_the_offered_page_sizes_all_work` |
| 4.5 | Search spans the whole history | finds off-page records | Search for a page-4 record returns it | **PASS** | `test_search_finds_a_repair_that_is_not_on_the_first_page` |
| 4.6 | Older repair opens and edits | succeeds | Edited the oldest record from the last page | **PASS** | `test_an_older_repair_deep_in_the_history_can_still_be_edited` |
| 4.7 | Vehicle scoping | no leakage | Another vehicle's repair never appears | **PASS** | `test_another_vehicles_repairs_never_appear` |
| 4.8 | Site Vehicles page | same behaviour | Same paginated API and pager component; typechecked and built | **PARTIAL** — covered by API and build, not by a dedicated Site Vehicles screenshot |

### Phase 5 — Workshop mechanic payments

Driven entirely through the real UI against a repair created for the run, so
repeated runs cannot inherit each other's payments.

| # | Test | Expected | Actual | Status | Evidence |
|---|---|---|---|---|---|
| 5.1 | Unpaid R5 000 | Unpaid | R5 000,00 payable, R0,00 paid, Unpaid | **PASS** | `06b-mechanic-unpaid.png` |
| 5.2–5.3 | Pay R2 000 → R3 000 outstanding | Partially Paid | R3 000,00 outstanding, Partially Paid | **PASS** | `07-mechanic-partial-payment.png` |
| 5.4–5.6 | Settle the balance → Paid | R0 outstanding | R5 000,00 paid, R0,00 outstanding, **Paid** | **PASS** | `08-mechanic-fully-paid.png` |
| 5.7–5.8 | Payment history, references, dates | all three instalments | R2 900 (AUDIT-EFT-FINAL), R100 (AUDIT-DUP), R2 000, each dated | **PASS** | `08b-mechanic-payment-history.png` |
| 5.9 | Overpayment rejected | refusal | R9 999 against R3 000 outstanding refused, message names the outstanding figure | **PASS** | `07b-mechanic-overpayment-rejected.png` |
| 5.10 | Duplicate reference rejected | refusal | Second `AUDIT-DUP` refused — "already recorded" | **PASS** | `07c-mechanic-duplicate-reference-rejected.png` |
| 5.11–5.12 | Reversal; reversed payment stays visible | visible, not counted | Reversal recorded with reason; payment remains in history | **PASS** | `08c-mechanic-payment-reversed.png` |
| 5.13 | Tyre / fuel / licence not treated as payable | excluded | Repair with R3 000 labour + R2 000 tyres + R500 licence shows **R3 000,00 "from recorded labour"**, and the drawer states the R2 500 is owed elsewhere | **PASS** | `06c-mechanic-payable-excludes-parts.png`, `06d-mechanic-non-payable-note.png` |
| 5.14 | Only the mechanic's invoice/quote/labour contributes | correct basis | Basis shown per row: `invoice`, `quote` or `recorded labour` | **PASS** | `06-mechanic-payments-overview.png` |
| 5.15 | Role permissions | enforced | SITE_STAFF 403 on overview and on recording; reversal is admin-only | **PASS** | `test_site_staff_cannot_record_a_mechanic_payment`, `test_only_an_admin_can_reverse_a_payment` |
| — | No duplicate supplier expense or stock movement | none created | Recording a payment creates no `VehicleCost` and changes no payable. Parts bought via material requests settle through the separate `invoices`→`payments` chain; workshop stock issuances write no `VehicleCost` and carry no `repair_job_id` | **PASS** | `test_no_vehicle_cost_row_is_created_by_a_payment` |

### Phase 6 — Fuel timeline

| # | Test | Expected | Actual | Status | Evidence |
|---|---|---|---|---|---|
| 6.1 | More than 10 entries reachable | pager present | 24 synthetic fuel logs; entry count shown and a next-page control present | **PASS** | `09-fuel-history-pagination.png` |
| 6.2 | Older entries accessible | page 2 renders | Page 2 shows older fills | **PASS** | `09b-fuel-history-page2.png` |
| 6.3 | Totals remain accurate | across all entries | Totals are computed over the whole timeline, not the page — paging changed only which rows render | **PASS** | code: totals computed before slicing |
| 6.4 | Site Vehicles | same behaviour | Identical change applied; typechecked and built | **PARTIAL** — not separately screenshotted |

### Phase 7 — Dassenhoek BOQ

**Live Dassenhoek figures could not be verified.** No production login and no
production database access exist in this environment.

What was verified instead, on the local audit stack with a synthetic
reproduction of the exact defect shape — two BOQ rows pointing at the same
catalogue item but worded differently ("Cement 42.5N 50kg bag" / "…bags"),
allocated 300 and 200, with one physical delivery of 100 bags:

| # | Test | Expected | Actual | Status | Evidence |
|---|---|---|---|---|---|
| 7.1 | Rows for one catalogue item collapse | 1 row | 1 row returned | **PASS (local)** | `10-boq-materials-summary-local.png` |
| 7.2 | Delivery counted once | 100 | **100.0**, not 200 | **PASS (local)** | same |
| 7.3 | Genuine allocations preserved | 500 | 500.0 (300 + 200) | **PASS (local)** | same |
| 7.4 | No dashboard errors | clean render | Page rendered without error | **PASS (local)** | same |
| 7.5 | Live Dassenhoek quantities | — | **BLOCKED** — no production access | **BLOCKED** | — |
| 7.6 | Existing delivery notes still present | — | **BLOCKED** — same | **BLOCKED** | — |

No production delivery note was deleted, cancelled or reversed. None was
touched at all.

### Phase 8 — Bypass Orders and the Claude API

| # | Test | Expected | Actual | Status | Evidence |
|---|---|---|---|---|---|
| 8.1 | Sidebar entry | present | "Bypass Orders" in Procurement | **PASS** | `11a-bypass-orders-sidebar.png` |
| 8.2 | Page loads | renders | Heading, description and upload interface render | **PASS** | `11-bypass-orders.png` |
| 8.3 | `AI_IMPORT_ENABLED` | true | `true` | **PASS** | `11b-bypass-orders-service-status.png` |
| 8.4 | `AI_IMPORT_AUTO_POST_ENABLED` | **false** | **`false`** — code default, `render.yaml` and `render.test.yaml` | **PASS** | service-status output |
| 8.5 | `ANTHROPIC_API_KEY` | present | **ABSENT** from this environment | **BLOCKED** | — |
| 8.6 | Model identifier | valid | `claude-opus-5-5`, SDK `anthropic` 0.109.1 | **PASS** | service-status |
| 8.7 | Private document storage | configured | **Not configured locally** — `private_storage_configured: false` | **BLOCKED (local)** | `11-bypass-orders.png` |
| 8.8 | Degraded state is stated honestly | visible warning | Page shows: "No AI provider is configured… Fields will come back empty — that is the missing configuration, not a bad scan" | **PASS** | `11-bypass-orders.png` |
| 8.9 | **Real AI extraction on four synthetic documents** | measured accuracy | **NOT RUN** | **BLOCKED** | — |

**Precise configuration problem for 8.9:** `ANTHROPIC_API_KEY` is not set in
this environment. `extraction_available` is therefore `false`, and the engine
runs in its degraded mode — it stores, hashes, de-duplicates and queues
documents for human review but reads almost nothing off them. The model
identifier and SDK are correct and the request contract is verified offline
by 25 contract tests; what is unverified is the live call itself. **No mock
was substituted for this test, and no extraction accuracy or token/cost
figure is reported, because none was measured.**

---

## 3. Phase 9 — Regression

| Suite | Result |
|---|---|
| Full backend pytest | see §5 |
| Repair editing + pagination | 33 passed |
| Mechanic payments | 59 passed |
| Company creation + permissions + letterheads | 15 passed |
| Playwright — existing suite | 32 passed |
| Playwright — this audit | 10 passed |
| Frontend TypeScript | no errors in changed files |
| Frontend production build | exit 0 |
| Migration validation | empty DB → `0078`; round-trip; re-run inserts nothing |

---

## 4. Defects found and fixed during this audit

| # | Defect | Severity | Fix | Verified by |
|---|---|---|---|---|
| 1 | **Form labels were not associated with their inputs** in the mechanic payment drawer and the repair create/edit modal. The visible text sat beside each field rather than labelling it, so a screen reader announced unlabelled textboxes and clicking a label did not focus its field. Found because the browser could not address the fields by name. | Accessibility | Added `htmlFor`/`id` pairs across both forms | The audit suite now drives both forms by label |

Nothing else required a code change. The payable-derivation defect found in
the previous session (parts and licences counted as owed to the mechanic) was
already fixed in `2e4233c`; this audit confirms it end to end in the browser.

---

## 5. Evidence index

All 25 screenshots are in `docs/testing/screenshots/`. Every one shows the
real rendered application on the local audit stack. None contains a password,
token, banking detail or real customer data — all records shown are
synthetic.

| File | Shows |
|---|---|
| `01-company-list.png` | All five companies |
| `02-company-selector.png` | Table-driven company selector |
| `03a-repair-history-before-edit.png` | Repair history before editing |
| `03-edit-repair-form.png` | Edit Repair form, prefilled |
| `04-repair-updated.png` | Saved change, after reload |
| `05-repair-pagination.png` | 35-repair total, page 1 |
| `05b-repair-pagination-page2.png` | Page 2, older repairs |
| `06-mechanic-payments-overview.png` | Mechanic Payments with totals and filters |
| `06b-mechanic-unpaid.png` | Unpaid R5 000 repair |
| `06c-mechanic-payable-excludes-parts.png` | R3 000 payable "from recorded labour" |
| `06d-mechanic-non-payable-note.png` | Explanation of the excluded R2 500 |
| `07-mechanic-partial-payment.png` | R3 000 outstanding, Partially Paid |
| `07b-mechanic-overpayment-rejected.png` | Overpayment refused |
| `07c-mechanic-duplicate-reference-rejected.png` | Duplicate reference refused |
| `08-mechanic-fully-paid.png` | R0 outstanding, Paid |
| `08b-mechanic-payment-history.png` | Full payment history |
| `08c-mechanic-payment-reversed.png` | Reversal recorded |
| `09-fuel-history-pagination.png` | Fuel timeline with entry count |
| `09b-fuel-history-page2.png` | Fuel page 2 |
| `10-boq-materials-summary-local.png` | BOQ summary, one delivery counted once (local reproduction) |
| `11-bypass-orders.png` | Bypass Orders with its honest degraded-state banner |
| `11a-bypass-orders-sidebar.png` | Sidebar entry |
| `11b-bypass-orders-service-status.png` | Service status |
| `13-vehicles-mobile-390.png` | Vehicles at 390×844 |
| `14-workshop-mobile-390.png` | Workshop at 390×844 |

---

## 6. Blockers

| # | Blocker | Consequence | Needs |
|---|---|---|---|
| B1 | **No production credentials** — no application login, database URL, Render or Supabase access | Nothing in this report is production verification. Live Dassenhoek figures unverifiable | A read-only production login, or read-only database access |
| B2 | **No `ANTHROPIC_API_KEY`** | The real extraction test (Phase 8.9) did not run. Extraction accuracy on any document remains unmeasured | A TEST-scoped key with a spend limit, set in the Render dashboard |
| B3 | **No Supabase credentials locally** | Private document storage round-trip unverified; uploads would be refused in this environment | TEST Supabase service key |
| B4 | **Production migration level inferred, not confirmed** | `0078` is consistent with observed behaviour but unproven | Database access, or an authenticated call that touches `mechanic_payments` |

---

## 7. How to reproduce this audit

```bash
# 1. Database
createdb hmh_audit
DATABASE_URL=postgresql://.../hmh_audit alembic upgrade head
python <scratch>/seed_audit.py        # synthetic companies, vehicles, repairs, fuel
python <scratch>/seed_boq.py          # the BOQ duplication scenario

# 2. Backend
DATABASE_URL=postgresql://.../hmh_audit APP_ENV=development \
  CORS_ORIGINS=http://127.0.0.1:4190 \
  uvicorn main:app --host 127.0.0.1 --port 8010

# 3. Frontend
cd hmh-frontend
VITE_API_BASE_URL=http://127.0.0.1:8010/api/v1 npx vite build --mode production
npx vite preview --host 127.0.0.1 --port 4190

# 4. Audit
npx playwright test --config=playwright.audit.config.mjs
```

The audit spec is `hmh-frontend/tests/audit/full-system-audit.spec.mjs`. It
refuses to pass on a blank edit form, on overlapping pagination pages, or on
a payable that includes non-mechanic costs.
