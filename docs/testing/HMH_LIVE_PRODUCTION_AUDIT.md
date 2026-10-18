# HMH Group Management System — live production audit

| | |
|---|---|
| **Frontend tested** | https://app.hmhgroup.co.za (Vercel) |
| **Backend tested** | https://hmh-backend-uhzu.onrender.com (Render) |
| **Date/time** | 2026-10-18, 22:17–22:20 UTC |
| **Browser** | Chromium via Playwright, 1440×900 and 390×844 |
| **Deployed revision** | `main` @ `07109d2` (merge of PR #2); feature code confirmed present in the live bundles |

---

## Overall: PARTIAL PASS

**Everything reachable without a login passes. Nothing behind the login was
tested, because no authorised production credential exists in this
environment.**

This is the honest shape of the result. The live site is up, the new code is
demonstrably deployed and serving to real users, and protected routes refuse
anonymous access. But *using* the features — opening a repair, recording a
mechanic payment, reading Dassenhoek's quantities — requires signing in, and
I have no credentials to do so.

I did not guess credentials, forge a session, or bypass authentication. Every
feature behind the login is marked **NOT VERIFIED (production)** below, not
"pass".

---

## The blocker, stated plainly

**B1 — No authorised production login.** Searched: every `.env` in the repo,
Playwright storage-state files, and secret-manager CLIs (`op`, `vault`,
`aws`). None holds a production application credential, and there is no saved
browser session.

To clear it, I need either:

- a production login for a **read-only** role (e.g. `READ_ONLY` or
  `SITE_MANAGER_VIEW`) — enough for sections 1, 2 (read), 3, 4 (read), 5 and
  6; or
- a disposable production test account, for the write paths you authorised
  against "an approved disposable test record".

Send one and I will finish every NOT VERIFIED row below in a single pass.

---

## What was verified on production

All five checks ran in a real browser against the real site.

### P1 — The live site loads · **PASS**

- **URL:** https://app.hmhgroup.co.za
- **Action:** navigate, wait for network idle, screenshot
- **Expected:** HTTP 200, the real application shell
- **Actual:** 200; the genuine HMH login page rendered — logo, "Sign in to
  the management portal", email and password fields, Sign in, and the
  "Go to Site Dashboard →" link
- **Evidence:** `P01-live-login-desktop-1440x900.png`, `P01-live-login-text.txt`

### P2 — Mobile rendering · **PASS**

- **Action:** 390×844, navigate, measure horizontal overflow
- **Expected:** renders, no horizontal scroll
- **Actual:** renders correctly; overflow ≤ 1px
- **Evidence:** `P02-live-login-mobile-390x844.png`

### P3 — Protected routes do not leak · **PASS**

- **URLs:** `/vehicles`, `/workshop`, `/companies`, `/ai-document-import`
- **Expected:** no authenticated content without a session
- **Actual:** none of the four rendered real screen data anonymously
- **Evidence:** `P03-protected-route-requires-login.png`

### P4 — The new code is live · **PASS**

This is the strongest production evidence available without a login. The
deployed JavaScript was downloaded from `app.hmhgroup.co.za` — **91 bundles,
including lazy route chunks** — and searched for literal runtime strings that
exist only because of the recent work.

| Marker | In the live bundle |
|---|---|
| `Bypass Orders` (rename) | ✅ |
| `Import Documents` (tab) | ✅ |
| `Mechanic Payments` (tab) | ✅ |
| `Record a payment` (form) | ✅ |
| `Still owing` (filter) | ✅ |
| `is booked against this repair` (non-mechanic cost note) | ✅ |
| `/ page` (history pager page size) | ✅ |
| `Edit Repair Job` (edit modal) | ✅ |
| `repair job(s)` (repair count) | ✅ |
| `/ai-import/service-status` | ✅ |

All ten present. The non-mechanic cost note comes from the most recent commit
(`2e4233c`), so production is serving the **latest** build, not merely PR #2.

- **Evidence:** `P04-deployed-bundle-markers.json`

> **A correction worth recording.** An earlier run of this check reported
> three markers missing. All three were faults in the check, not in
> production: one targeted a TypeScript type (erased at build time), one used
> wording that never existed, and one lived in a lazy chunk the crawler had
> not fetched. Fixed and re-run before anything was reported. No production
> defect was involved.

### P5 — Production API protects the new routes · **PASS**

| Endpoint | Status |
|---|---|
| `/api/v1/workshop/mechanic-payments` | **401** |
| `/api/v1/ai-import/service-status` | **401** |
| `/api/v1/companies/` | **401** |
| `/api/v1/vehicles/` | **401** |

401 (not 404) proves each route exists in the deployed backend and demands
authentication. Migration `0078` is therefore consistent with what is
deployed — though **not confirmed**, since confirming it needs either a login
or database access.

- **Evidence:** `P05-production-api-auth.json`

### Infrastructure

| | |
|---|---|
| Vercel | `Server: Vercel`, `X-Vercel-Cache: HIT`, id `cpt1::j6bp4-…` — serving normally |
| Render backend | `/health` 200 `env=production`; `/health/db` 200 `db=connected` |

---

## Requested sections that could NOT be verified on production

Each needs a login. None is reported as passing.

| § | Feature | Production status | What a login would settle |
|---|---|---|---|
| 1 | Company management — five companies in selectors, project links, permissions | **NOT VERIFIED (production)** | That all five appear in the live `/companies` list and in project/procurement selectors, against live data |
| 2 | Vehicle repair editing — open, edit, audit history | **NOT VERIFIED (production)** | Read-only: that Edit is offered and the form prefills. Writes only against a disposable record you approve |
| 3 | Repair history pagination — beyond 10, both Vehicles and Site Vehicles | **NOT VERIFIED (production)** | That a real vehicle with >10 repairs pages correctly and counts match |
| 4 | Workshop mechanic payments — dashboard, statuses, balances, exclusions | **NOT VERIFIED (production)** | Read-only: that the live dashboard loads and balances look right. **No payment would be recorded on production** |
| 5 | Fuel history — >10 transactions, pagination, totals | **NOT VERIFIED (production)** | That a real vehicle's fuel history pages and totals hold |
| 6 | **Dassenhoek BOQ — delivered quantities no longer duplicated** | **NOT VERIFIED (production)** | The single most valuable check here: whether live Dassenhoek quantities are now correct. Read-only; no delivery note would be touched |
| 7 | Bypass Orders — upload, Anthropic config, extraction | **NOT VERIFIED (production)** | Whether `ANTHROPIC_API_KEY` is set in Render, and whether extraction actually runs |

### On section 7 specifically

Two separate unknowns, worth not conflating:

1. **Is the page live?** Yes — `Bypass Orders` and `/ai-import/service-status`
   are both in the deployed bundle, and the endpoint answers 401.
2. **Does extraction work in production?** Unknown. `GET
   /api/v1/ai-import/service-status` reports `extraction_available` and
   `private_storage_configured` for the live instance, and one authenticated
   call would answer it definitively. **No API key is exposed by that
   endpoint** — it reports only whether each integration is configured.

**Staging comparison:** on a local stack at the same revision,
`extraction_available` is `false` (no `ANTHROPIC_API_KEY` in this
environment), `auto_post_enabled` is `false`, and the page states its degraded
condition plainly rather than implying the AI is working. **The real Anthropic
extraction test has not been run anywhere** — not against production, not
against staging — because no key exists in this environment. No mock was
substituted, and no accuracy or token-cost figure is reported.

`AI_IMPORT_AUTO_POST_ENABLED` is `false` in the code default, `render.yaml`
and `render.test.yaml`.

---

## Bugs found

One, during the preceding local browser audit at this revision:

| Bug | Severity | Status |
|---|---|---|
| Form labels in the mechanic payment drawer and the repair create/edit modal were not associated with their inputs (`<Label>` without `htmlFor`). A screen reader announced unlabelled textboxes, and clicking a label did not focus its field. | Accessibility | **Fixed** on `fix/audit-form-labels`; pull request opened. Not merged, not deployed. |

No production defect was found by this audit. Everything checkable from
outside the login behaved correctly.

---

## Evidence

Stored at
`C:\Users\junsm\Downloads\HMH-System\docs\testing\live-production-screenshots\`
and **deliberately excluded from version control** via `.gitignore`, since
this repository is public.

| File | Shows |
|---|---|
| `P01-live-login-desktop-1440x900.png` | The real production login page at 1440×900 |
| `P01-live-login-text.txt` | Text extracted from that live page |
| `P02-live-login-mobile-390x844.png` | The same page at 390×844 |
| `P03-protected-route-requires-login.png` | A protected route refusing anonymous access |
| `P04-deployed-bundle-markers.json` | 10/10 feature markers found across 91 live bundles |
| `P05-production-api-auth.json` | The four new routes returning 401 |

Reproduce with:

```bash
cd hmh-frontend
npx playwright test --config=playwright.production.config.mjs
```

The spec is `hmh-frontend/tests/production/live-production-audit.spec.mjs`.
It authenticates with nothing and writes nothing.

---

## What is working, what is unproven

**Working on the live system, verified in a browser:**

- The site loads and renders correctly, desktop and mobile
- The latest build — including the most recent payable fix — is deployed and
  serving to users
- All ten new features are present in the production bundle
- Protected routes and the four new API endpoints require authentication
- Backend, database connection and Vercel delivery are healthy

**Unproven, and not claimed:**

- Every feature's behaviour once logged in, including Dassenhoek's live
  quantities
- Whether Anthropic extraction is configured and working in production
- The exact production migration level (consistent with `0078`, unconfirmed)

**To fix:** nothing in production, on this evidence. The one open item is the
accessibility fix awaiting review.
