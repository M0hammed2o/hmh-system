# HMH Group Management System — live production audit

| | |
|---|---|
| **Frontend** | https://app.hmhgroup.co.za (Vercel) |
| **Backend** | https://hmh-backend-uhzu.onrender.com (Render) |
| **Date** | 2026-10-18 / 19 |
| **Browser** | Chromium via Playwright, 1440×900 and 390×844 |
| **Account** | An administrator login supplied by the system owner. Held in environment variables for the run; never written to a file, a report or a commit |
| **Mode** | **READ-ONLY.** No repair edit was saved, no payment recorded or reversed, no delivery note touched, no customer, stock or financial record altered |

---

## Overall: PARTIAL PASS — one production regression found and fixed

The headline result is good: **the Dassenhoek BOQ duplication is confirmed
fixed on live production data.** Both lots were checked against the real
database through the API, and neither shows the duplication signature.

One regression was found, caused by this work, and is fixed in a pull request
awaiting review. Several features are deployed and loading correctly but
**cannot be judged working in the field, because production holds no data for
them yet** — stated as unexercised rather than passing.

---

## The regression: HMH Group and Minerat vanished from the company selector

**Severity: high — it blocks an everyday workflow.**

### What happened

The two original trading names were never rows in the `companies` table.
They existed only as hardcoded `<option>` values written into
`projects.client_name`, and as fixed letterhead keys in `email_service`. The
companies table served a narrower purpose — linking approved suppliers — and
nobody had needed rows there.

Migration 0077 then added the three new companies, and the project company
selector was changed to read the table instead of its hardcoded list. On
production the table holds **exactly three rows**, so the selector now offers
only the new companies:

```
Production /api/v1/companies/  →  Kukhanya Kabusha, Ophezulu, Premium Structures
Production project selector    →  the same three. No HMH Group. No Minerat.
```

Staff creating a project can no longer choose either company they actually
trade as.

### What was NOT damaged

Both production projects still carry `client_name = "Minerat Construction &
Civils"`, intact. `CompanySelect` keeps an unrecognised saved value
selectable rather than discarding it, so opening and saving an existing
project could not silently blank its company. Procurement letterheads are
also unaffected — that selector retains the legacy `HMH_GROUP` and `MINERAT`
keys, and documents already issued render exactly as before.

### The fix

**Migration 0079** registers the two names, byte-identical to what the
retired hardcoded options wrote, so a project already carrying one matches a
real row instead of rendering as a leftover. Idempotent and additive like
0077; name only, because registration and VAT numbers appear on
supplier-facing documents and are not for a migration to invent.

Branch `fix/restore-hmh-minerat-companies`, with three regression tests
asserting all five names are selectable and that nothing is invented.
**Not merged, not deployed.**

---

## Production data volumes (read-only)

Measured through the API. These explain most of the results below.

| | |
|---|---|
| Projects | **2** — `DASS` (DASSENHOEK), `CORNUBIA` |
| Companies | **3** (the regression above) |
| Vehicles | **22** |
| **Repair jobs** | **0** |
| Vehicle costs | 102 |
| Fuel logs readable via `/fuel/?project_id=` | 0 |

With no repair jobs in production, repair editing, repair pagination and
mechanic payments have nothing to act on. Their screens load correctly; their
behaviour on real data is unexercised.

---

## Results

### 1. Companies — **FAIL (regression, fixed in PR)**

- **Expected:** all five selectable
- **Actual:** three. HMH Group and Minerat Construction & Civils absent
- **Evidence:** `A01-companies-live.png`, `A03-company-selector-live.png`, `A99-findings.json`
- **Status:** fix ready for review

### 2. Vehicle repair editing — **NOT EXERCISED**

- **Actual:** the Vehicles screen loads with all 22 vehicles. **No repair
  exists on any of them**, so no Edit control can appear and the edit form
  could not be opened against real data
- **Not a defect:** the Edit control is present in the deployed bundle
  (`Edit Repair Job`) and is proven working against a throwaway database in
  `tests/audit`
- **Evidence:** `A04-vehicles-live.png`, `A05-repair-history-live.png`
- **Writes:** none. No repair was created or modified on production

### 3. Repair history pagination — **NOT EXERCISED**

- **Actual:** no vehicle has more than 0 repairs, so there is no second page
  to reach. The paginated endpoint answers correctly and returns `total: 0`
- **Status:** correct behaviour, no data to prove the fix in the field

### 4. Workshop mechanic payments — **PASS (loads correctly; no data)**

- **Actual:** the Mechanic Payments tab is present and loads. Totals read
  R0,00 / R0,00 / R0,00, with the correct empty state: *"No repairs match
  these filters. Only repairs with a quoted, invoiced or recorded cost appear
  here — there is nothing to pay until one of those is captured."*
- The balance arithmetic assertion (`outstanding = payable − paid`) ran
  against every returned row; with zero rows it proved nothing, and is
  reported as such
- **Evidence:** `A07-mechanic-payments-live.png`
- **Writes:** none. No payment was recorded or reversed on production

### 5. Fuel history — **NOT EXERCISED**

- **Actual:** no fuel logs were readable for any production vehicle through
  the endpoint checked
- **Caveat worth stating:** the fuel timeline draws on fuel logs and fuel
  issues, and this check queried one source. "No fuel history visible to this
  account" is the honest reading, not "no fuel data exists"

### 6. **Dassenhoek BOQ — PASS (verified on live production data)**

The most valuable result in this audit.

- **Project:** `DASSENHOEK`, code `DASS`
- **Lots checked:** 2 — `A17` and `A175`
- **Method:** for each lot, the live material summary was read and inspected
  for the duplication signature — two surviving rows sharing one catalogue
  `item_id`, which is what multiplied delivered quantities

| Lot | BOQ rows returned | Rows sharing a catalogue item |
|---|---|---|
| A17 | 35 | **0** |
| A175 | 35 | **0** |

- **Actual:** no duplication in either lot. Genuine separate allocations are
  intact — 35 distinct rows each, not collapsed
- **Evidence:** `A09-dassenhoek-live.png`, `A99-findings.json`
- **Writes:** none. No delivery note was deleted, cancelled, reversed or
  altered

### 7. Bypass Orders — **PASS (and fully configured)**

This resolves the unknown carried through every previous report.

| Setting (live production) | Value |
|---|---|
| `enabled` | `true` |
| **`extraction_available`** | **`true`** — an Anthropic API key *is* configured in Render |
| `extraction_model` | `claude-opus-5-5` |
| **`private_storage_configured`** | **`true`** — Supabase private storage is configured |
| **`auto_post_enabled`** | **`false`** ✅ |
| `worker_enabled` | `true` |

- The page loads, the upload controls are present, and **no degraded-capability
  banner is shown — because production is not degraded.** Both integrations
  this environment lacks are present there
- **Automatic posting is off in production**, asserted directly
- **Evidence:** `A10-bypass-orders-live.png`, `A99-findings.json`

**The live extraction test was not run.** Uploading even a synthetic document
writes an `ai_import_document` row to production that somebody must then
review or reject. No explicitly authorised production test workspace was
designated, and I was asked not to create records on production. The
capability is confirmed configured; say the word and I will upload one clearly
marked synthetic document and verify it creates no accounting, stock or
supplier transaction.

**No API key was exposed.** `service-status` reports only whether each
integration is configured.

### 8. Unauthenticated checks — **PASS**

| Check | Result |
|---|---|
| Site loads | 200, genuine login page |
| Mobile 390×844 | renders, overflow ≤1px |
| Protected routes | leak nothing anonymously |
| Deployed bundle | **10/10 feature markers across 91 live bundles**, including text from the most recent commit |
| API auth | the four new routes answer 401, not 404 |

---

## Bugs found

| # | Bug | Severity | Status |
|---|---|---|---|
| 1 | HMH Group and Minerat missing from the company selector on production | **High** — blocks project creation with the real companies | Fixed, migration 0079, `fix/restore-hmh-minerat-companies`. Not merged |
| 2 | Form labels not associated with their inputs in the mechanic payment drawer and repair modal | Accessibility | Fixed, PR #3. Not merged |

No other defect was found. Everything checked behaved correctly.

---

## Evidence

At `C:\Users\junsm\Downloads\HMH-System\docs\testing\live-production-screenshots\`,
**gitignored** — this repository is public.

| File | Shows |
|---|---|
| `A01-companies-live.png` | Live Companies screen — three companies, the regression |
| `A02-projects-live.png` | Live Projects |
| `A03-company-selector-live.png` | The selector missing HMH and Minerat |
| `A04-vehicles-live.png` | Live Vehicles, 22 records |
| `A05-repair-history-live.png` | Live repair history (empty) |
| `A07-mechanic-payments-live.png` | Live Mechanic Payments tab |
| `A09-dassenhoek-live.png` | Live Projects showing DASSENHOEK |
| `A10-bypass-orders-live.png` | Live Bypass Orders, fully configured |
| `A99-findings.json` | Every machine-readable finding, including the Dassenhoek per-lot results |
| `P01`–`P05` | Unauthenticated checks from the earlier pass |

Reproduce:

```bash
cd hmh-frontend
PROD_EMAIL=... PROD_PASSWORD=... \
  npx playwright test --config=playwright.production.config.mjs live-authenticated-audit
```

The suite is read-only by construction: where a write would prove something,
it verifies the control is present and the form prefills, then closes it
without saving.

---

## What is working, what is unproven

**Confirmed working on live production:**

- **Dassenhoek BOQ quantities are no longer duplicated** — verified against
  real data in both lots
- Bypass Orders is deployed **and fully configured**: Anthropic key present,
  private storage present, automatic posting off
- Workshop → Mechanic Payments loads with correct totals and empty state
- The latest build is serving; protected routes and APIs require auth
- Existing project data intact; procurement letterheads unaffected

**Broken, fix awaiting review:**

- HMH Group and Minerat missing from the company selector

**Deployed but unexercised, because production has no data for them:**

- Repair editing, repair pagination, fuel history, and mechanic payment
  balances on real repairs

**Not run:**

- Live Anthropic extraction, pending your go-ahead to upload one synthetic
  document to production
