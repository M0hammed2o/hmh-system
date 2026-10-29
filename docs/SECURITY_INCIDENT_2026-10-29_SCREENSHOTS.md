# Incident: screenshots of the live system pushed to a public repository

Date: 2026-10-29
Repository: `M0hammed2o/hmh-system` (public)
Status: contained; one residual item depends on GitHub

---

## What happened

While committing work on the Bypass Orders branch, a `git add -A` swept in a
directory of screenshots taken during an earlier live-system audit. They were
untracked at the time, not ignored, and the commit was pushed.

They were removed from the branch's history and the branch force-pushed. No
other branch, and `main` in particular, ever contained them.

## What was exposed

Six image files, in two commits on one feature branch.

| | |
|---|---|
| Files containing real operational data | **2** |
| Files containing only empty application chrome | **4** |
| Credentials, tokens or keys | **none** |
| Customer or employee personal data | **none** |

The two files showing real data were screenshots of the Vehicles screen.
Between them they showed the fleet list — registration numbers and vehicle
descriptions — and four repair cost entries with their amounts and dates.

The other four were Bypass Orders screens with no records loaded. The only
document visible in any of them is a synthetic test file created for that
audit.

## Exposure window

Approximately **100 seconds** between the push and the corrective
force-push.

At the time, the repository had **no forks, no watchers and no stars**. The
commits do not appear in the repository's public events feed, and the pull
request timeline records only the post-rewrite head.

## Residual accessibility

GitHub does not immediately garbage-collect objects that become unreachable
after a force-push. **The removed images remain retrievable through the API
by anyone who knows the object hash.** Those hashes are not published
anywhere we could find, so retrieval requires having recorded them during
the window above.

This is the one item that cannot be closed from inside the repository.

### Recommended remediation

1. **Ask GitHub Support to garbage-collect unreachable objects** for this
   repository, citing this incident. This is the documented route and the
   only one that removes the objects from GitHub's storage.
2. **Or** make the repository private, which ends anonymous access
   immediately. The objects survive but are reachable only to collaborators.

No credential was involved, so **no password, key or token needs rotating**.
Vehicle registration numbers are visible on the vehicles themselves; the
commercially meaningful part is the repair costs and fleet composition.

## What prevents a recurrence

1. **`.gitignore`** now excludes `live-production-screenshots/` at both the
   repository root and under `hmh-frontend/`. A sweep cannot pick them up
   again.
2. Screenshots that *are* committed come from the local demo stack, whose
   suppliers, project and document numbers are invented
   (`scripts/seed_mixed_batch_demo.py`). Nothing in them is real.
3. Browser suites that run against the live system live under
   `tests/production/` and are excluded from every local Playwright config,
   so they cannot run by accident.

## A second, related finding

The same audit surfaced that `playwright.config.mjs` started its server with
`npm run preview`, which serves `dist/` — normally a **production** build.
Local browser suites were therefore driving a bundle addressed to the live
backend while appearing entirely local, and did briefly send failed logins
for a non-existent account to it. No data was read or changed.

Two independent guards now prevent it:

- `vite.config.demo.mjs` pins the API base URL at build time and refuses to
  build against any non-local address. The local Playwright config builds
  through it rather than through `npm run build`.
- `tests/support/local-only.mjs` aborts any request leaving the machine, with
  a narrow allowlist for font CDNs and an absolute rule that anything
  API-shaped must be local. Local suites import `test` from there.
