# TODO — pending features and open work items

Priority: **P0** = production blocker · **P1** = high · **P2** = medium · **P3** = low / nice-to-have

---

## P0 — Production Blockers (must resolve before live)

- [ ] **Set production env vars in Render**
  `WHATSAPP_APP_SECRET`, `CRON_SECRET`, `WHATSAPP_VERIFY_TOKEN` (change from default), `SECRET_KEY` (64+ chars).
  See `KNOWN_BUGS.md §Production Launch Blockers` and `PRODUCTION_DEPLOY_CHECKLIST.md §1`.

- [ ] **Configure persistent file storage**
  Set `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` in Render, OR mount a Render Persistent Disk at `UPLOAD_DIR`.
  Without this, all uploaded files (PO attachments, delivery photos, invoices) are lost on every deploy.

---

## P1 — High Priority

- [ ] **Automate Gmail inbox polling**
  Add a Render cron job: `POST /api/v1/gmail/fetch` every 10 min.
  OR add an in-process background polling task in `main.py` alongside `_queue_drain_loop`.
  Currently manual-only — supplier quotes and invoices are not auto-ingested.
  See `PRODUCTION_DEPLOY_CHECKLIST.md §7`.

- [ ] **Warehouse transfer integration tests**
  Add `tests/test_warehouse_transfer_flow.py` covering: submit, 3-vote execute, OWNER override, reject, stock-insufficient guard.
  See `KNOWN_BUGS.md`.

- [ ] **Payment due scan integration tests**
  Add `tests/test_payment_due_scan.py` covering: 7-day warning, overdue, 23h deduplication.
  See `KNOWN_BUGS.md`.

- [ ] **Add `confirm=true` requirement to admin demo-wipe endpoint**
  `app/api/v1/admin.py:32` — `POST /admin/clear-demo-data` currently wipes without confirmation.

---

## P2 — Medium Priority

- [ ] **Timeline feature — backend enhancement**
  `TimelinePage.tsx` exists and renders a timeline of stage updates, deliveries, usage, and alerts.
  A unified `/api/v1/projects/{id}/timeline` endpoint that aggregates these in chronological order would replace the current per-type client-side fetching. **Do not implement without explicit user sign-off** — this was identified in the discovery session as pending.

- [ ] **Automated payment due scan cron**
  Add a Render cron job: `POST /api/v1/internal/scan-payment-due` at 08:00 daily.
  Currently manual-only via the Notification Settings page button.

- [ ] **Automated daily summary cron**
  `render.yaml` only has the queue drain cron. Add a cron for `POST /api/v1/internal/send-daily-summary` at 18:00 daily.

- [ ] **Refactor duplicate `_phone_variants()`**
  Consolidate into `app/utils/phone.py` and import from `notification_service.py` and `whatsapp_webhook.py`.
  See `KNOWN_BUGS.md §L1`.

- [ ] **Payroll system**
  `HMH_Payroll_System_Proposal.md` exists in the repo root. Design and implementation pending.
  Separate discovery session required before any implementation.

---

## P3 — Low Priority / Nice-to-Have

- [ ] **Make company list DB-configurable**
  Currently "HMH Group" and "Minerat Construction & Civils" are hardcoded in the frontend dropdown.
  The `companies` table and `CompaniesPage` already exist — wire the project form to load from the companies API.

- [ ] **Add `SITE_MANAGER_VIEW` to test suite**
  `UserRole.SITE_MANAGER_VIEW` is defined but coverage of its read-only behaviour is thin.

- [ ] **WhatsApp ALERT_TEMPLATE_NAME validation on startup**
  Log a warning if `WHATSAPP_ENABLED=true` and `WHATSAPP_ALERT_TEMPLATE_NAME` is not set (messages outside the 24h window will fail silently). Already logged in `_log_startup_config()` — confirm Render dashboard shows this warning at next deploy.
