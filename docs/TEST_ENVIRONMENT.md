# HMH TEST Environment Runbook

This environment uses the production source tree with completely separate
runtime services and data stores:

```
test.hmhgroup.co.za
  -> hmh-test-frontend (Render static service)
  -> hmh-test-backend (Render Python service)
  -> Supabase project ekipedffcywxlabchznq (TEST only)
```

The production frontend, backend and database are not used by this chain.
The TEST frontend shows a persistent `TEST ENVIRONMENT` badge. The TEST
backend has SMTP, IMAP, WhatsApp, OCR/AI calls and cron endpoints disabled.

## Deploy

1. In Render, create a Blueprint from `render.test.yaml`.
2. On `hmh-test-backend`, set these secret values in the Render dashboard:
   - `DATABASE_URL`: the TEST project's Supavisor **session-mode** URL on port
     5432. Render is IPv4-only; do not use the direct IPv6 database hostname.
   - `SECRET_KEY`: a new random 64+ character TEST-only value.
   - `SUPABASE_SERVICE_KEY`: the TEST project's secret/service key.
3. Deploy the backend and confirm `GET /health` reports `status=ok` and
   `env=test`, then confirm `GET /health/db` reports `db=connected` (the two
   are separate on purpose — `/health` is a pure liveness check with no DB
   call, so it can't be taken down by DB load; `/health/db` is the readiness
   check).
4. Deploy the frontend. Map `test.hmhgroup.co.za` to the TEST frontend in
   Render and at the DNS provider, then wait for managed TLS to become active.
5. Never add production email, WhatsApp, Google, Anthropic or webhook secrets
   to either TEST service.

## Recreate the TEST data

Run from `hmh-backend` with the TEST database URL in the process environment:

```powershell
$env:APP_ENV = "test"
$env:NODE_ENV = "test"
$env:HMH_TEST_SUPABASE_REF = "ekipedffcywxlabchznq"
$env:HMH_TEST_SEED_CONFIRM = "government_housing_test_v1"
$env:DATABASE_URL = "<TEST Supavisor session-mode URL>"
python scripts/seed_government_housing_test.py
```

The seeder terminates unless every guard passes. Once guarded, it truncates
only application tables in that dedicated TEST database, recreates the full
synthetic portfolio, validates financial and fuel integrity, enables RLS on
all public tables, revokes Data API table privileges from `anon` and
`authenticated`, and ensures the required storage buckets exist.

## TEST accounts

All seeded accounts use password `HMH-Test-2026!`. Primary presentation users:

| Role | Email |
|---|---|
| Executive / Director | `executive.test@ubuntu-housing.invalid` |
| Contract / Office Admin | `admin.test@ubuntu-housing.invalid` |
| Finance Manager | `finance.test@ubuntu-housing.invalid` |
| Procurement Lead | `procurement.test@ubuntu-housing.invalid` |
| Site Manager (KZN) | `site.kzn.test@ubuntu-housing.invalid` |
| Site Clerk (KZN) | `clerk.kzn.test@ubuntu-housing.invalid` |

Site users also have TEST PIN `2468`.

## Shutdown after the presentation

Safely suspend or delete only `hmh-test-frontend` and `hmh-test-backend` in
Render and remove the `test.hmhgroup.co.za` custom-domain mapping. The TEST
Supabase project can be paused to retain the populated environment, or deleted
if the seed script and migrations are retained. Never remove or edit the live
`hmh-backend-uhzu` service or `app.hmhgroup.co.za` mapping.

