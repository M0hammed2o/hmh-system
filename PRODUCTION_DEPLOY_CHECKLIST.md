# Production Deployment Checklist
**Project:** HMH Construction OS  
**Date:** 2026-05-26  
**Platform:** Render (backend + frontend) + PostgreSQL (external)

---

## 1. Environment Variables (Render Dashboard)

### Required — App Core
| Variable | Value | Notes |
|----------|-------|-------|
| `APP_ENV` | `production` | Enables startup security checks |
| `SECRET_KEY` | 64+ random chars | Generate: `openssl rand -hex 32` |
| `DATABASE_URL` | `postgresql://user:pass@host/db` | Postgres connection string |

### Required — WhatsApp Cloud API
| Variable | Value | Notes |
|----------|-------|-------|
| `WHATSAPP_ENABLED` | `true` | Enables WhatsApp sending |
| `WHATSAPP_PHONE_NUMBER_ID` | From Meta dashboard | |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | From Meta dashboard | |
| `WHATSAPP_ACCESS_TOKEN` | Permanent system user token | NOT the temporary token |
| `WHATSAPP_APP_SECRET` | App Secret from Meta App settings | Used for HMAC webhook verification |
| `WHATSAPP_VERIFY_TOKEN` | Any random string (not "hmh_verify_token") | Used during webhook setup only |
| `WHATSAPP_ALERT_TEMPLATE_NAME` | Your approved Meta template name | e.g., `hmh_alert_notification` |
| `WHATSAPP_ALERT_TEMPLATE_LANGUAGE` | `en_US` | Or your template's language code |
| `CRON_SECRET` | 32+ random chars | Secures the /internal/process-notifications endpoint |

### Required — SMTP / Gmail Outbound
| Variable | Value | Notes |
|----------|-------|-------|
| `SMTP_ENABLED` | `true` | |
| `SMTP_USERNAME` | Gmail address | e.g., `procurementhmhgroup@gmail.com` |
| `SMTP_PASSWORD` | Gmail App Password (16 chars) | Enable 2FA, then create App Password |
| `SMTP_FROM_NAME` | `HMH Procurement` | Displayed sender name |
| `PROCUREMENT_EMAIL_CC` | Comma-separated CCs | Optional |

### Required — IMAP / Gmail Inbox Reader
| Variable | Value | Notes |
|----------|-------|-------|
| `IMAP_ENABLED` | `true` | Enables inbound email fetch |
| `IMAP_USERNAME` | Same as SMTP_USERNAME | Defaults to SMTP_USERNAME if empty |
| `IMAP_PASSWORD` | Same as SMTP_PASSWORD | Defaults to SMTP_PASSWORD if empty |

### Optional — OCR / Document AI
| Variable | Value | Notes |
|----------|-------|-------|
| `OCR_PROVIDER` | `google_vision` or `disabled` | See VISION_READINESS_REPORT.md |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path or inline JSON of service account | Required if OCR_PROVIDER=google_vision |

### Optional — Supabase Storage (persistent uploads)
| Variable | Value | Notes |
|----------|-------|-------|
| `SUPABASE_URL` | `https://xyz.supabase.co` | If using Supabase for file storage |
| `SUPABASE_SERVICE_KEY` | service_role key | Never use the anon key |

### Optional — Tuning
| Variable | Default | Notes |
|----------|---------|-------|
| `CORS_ORIGINS` | `https://app.hmhgroup.co.za` | Override with your frontend domain |
| `LOW_STOCK_THRESHOLD` | `5.0` | Items below this trigger LOW_STOCK alert |
| `BOQ_VARIANCE_ALERT_PCT` | `10.0` | % variance that triggers BOQ_VARIANCE alert |
| `PENDING_MR_DAYS` | `5` | MR pending longer triggers REQUEST_PENDING_TOO_LONG |
| `PAYMENT_DUE_DAYS` | `3` | Days before due date to fire PAYMENT_DUE alert |

---

## 2. Database Migration Order

Run in this exact sequence after deploying the backend:

```bash
cd hmh-backend
alembic upgrade head
```

All migrations (0001–0027) are idempotent — safe to re-run on any DB state.

If alembic is not in PATH on Render, use the one-shot migration route or run manually via psql.

**Migration summary:**
- 0001–0015: Core schema (projects, sites, lots, BOQ, invoices, etc.)
- 0016–0020: Lot types, attachments, partial payments
- 0021: supplier_confirmed_status enum value
- 0022: Notification enhancements (new queue columns, recipient flags)
- 0023: payment_due alert type
- 0024: Performance indexes
- 0025: Data consistency constraints (unique indexes)
- 0026: Milestone planned_completion_date
- 0027: Attachment enhancements (caption, uploaded_role)

---

## 3. Meta / WhatsApp Webhook Setup

1. In Meta App Dashboard → WhatsApp → Configuration → Webhooks:
   - **Callback URL:** `https://hmh-backend.onrender.com/api/v1/whatsapp/webhook`
   - **Verify Token:** same value as your `WHATSAPP_VERIFY_TOKEN` env var
   - **Subscribe to:** `messages` field

2. Verify the webhook completes — Meta will call `GET /api/v1/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...`

3. After verification, all incoming messages and delivery statuses will hit `POST /api/v1/whatsapp/webhook` with HMAC signature in `X-Hub-Signature-256` header.

---

## 4. Render Cron Job

Defined in `render.yaml`:
```yaml
cronJobs:
  - name: notification-queue-drain
    schedule: "*/5 * * * *"
    command: >
      curl -s -f -X POST
      https://hmh-backend.onrender.com/api/v1/internal/process-notifications
      -H "X-Cron-Secret: $CRON_SECRET"
    envVars:
      - key: CRON_SECRET
        sync: false
```

**Note:** This is a backup. The primary queue drain runs in-process every 5 minutes via `_queue_drain_loop()` in `main.py`. Both mechanisms are independent and safe to run concurrently (database-level `SKIP LOCKED` prevents duplicate sends).

---

## 5. Startup Order

1. Deploy PostgreSQL (Render Postgres or external)
2. Deploy `hmh-backend` Render web service
   - Render runs `pip install -r requirements.txt` → then `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - On startup, app validates all required env vars and refuses to start if critical ones are missing/default
3. Run `alembic upgrade head` (via Render shell or migration service)
4. Deploy `hmh-frontend` Render static service
5. Enable Render cron job after verifying backend health

---

## 6. Health Checks

| Endpoint | Expected | Notes |
|----------|----------|-------|
| `GET /api/health` | `{"status": "ok"}` | Render uses this for health monitoring |
| `GET /api/v1/ops/readiness` | `{"db": true, ...}` | Detailed component readiness |
| `GET /api/v1/whatsapp/debug` | `{"loaded": true}` | WhatsApp router loaded |

---

## 7. Gmail Automated Polling

**Current state:** Email fetch is MANUAL via `POST /api/v1/gmail/fetch`.

**For production:** Add a Render cron job to poll Gmail every 5–10 minutes:
```yaml
- name: gmail-inbox-poll
  schedule: "*/10 * * * *"
  command: >
    curl -s -X POST
    https://hmh-backend.onrender.com/api/v1/gmail/fetch
    -H "Authorization: Bearer $GMAIL_CRON_TOKEN"
```
Alternatively, add a background polling task in `main.py` similar to `_queue_drain_loop`.

---

## 8. Rollback Procedure

1. In Render dashboard → backend service → Deploys tab → select previous successful deploy → click "Rollback"
2. If a migration caused issues: connect to DB, run `alembic downgrade -1` to undo the last migration
3. If critical data was corrupted: restore from Render Postgres daily backup (Render retains 7 days)

---

## 9. Monitoring Checklist

After first deployment, verify:
- [ ] `GET /api/health` returns 200
- [ ] `GET /api/v1/ops/readiness` shows `db: true`
- [ ] WhatsApp webhook verification completes in Meta dashboard
- [ ] Test WhatsApp message sent from a recipient phone → appears in webhook logs
- [ ] Notification queue processes within 5 minutes (check Render logs for `queue_drain`)
- [ ] SMTP: send a test PO email to verify outbound email works
- [ ] IMAP: call `POST /api/v1/gmail/fetch?limit=5` → check response for `fetched > 0` or `mock: false`
- [ ] Upload test: create a project, upload an attachment, verify it saves without error

---

## 10. Known Limitations at Launch

| Item | Impact | Mitigation |
|------|--------|-----------|
| No automated Gmail polling | Procurement emails not auto-ingested | Manual fetch or add cron job (see §7) |
| Local OCR (pytesseract) not available on Render | OCR unavailable unless Tesseract installed | Use `OCR_PROVIDER=google_vision` or `disabled` |
| Render filesystem is ephemeral | Uploaded files lost on redeploy | Enable Supabase Storage or mount Render Persistent Disk |
| No OAuth for Gmail | Uses app password | Acceptable for single-org deployment; monitor for Google account security alerts |
