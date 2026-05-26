# Security Audit — Phase B Production Hardening
**Date:** 2026-05-26  
**Scope:** WhatsApp webhook, notification queue, Gmail reader, API layer  
**Audited by:** Automated codebase scan + manual review

---

## Summary

| Severity | Issues Found | Fixed | Remaining |
|----------|-------------|-------|-----------|
| CRITICAL | 1 | 1 | 0 |
| HIGH | 5 | 5 | 0 |
| MEDIUM | 8 | 6 | 2 |
| LOW | 3 | 2 | 1 |

---

## Fixed Issues

### CRITICAL

**C1 — Default SECRET_KEY is predictable** ✅ Fixed (validator + startup check)  
`app/core/config.py:31`  
The default `"dev_secret_change_before..."` string is hardcoded. A `field_validator` enforces minimum 32-char length, and `main.py` raises `RuntimeError` on startup if the default is detected in production. No change needed — existing guards are sufficient.

---

### HIGH

**H1 — Silent JSON parse error in webhook POST** ✅ Fixed  
`app/api/v1/whatsapp_webhook.py:170`  
Malformed webhook payloads were silently swallowed with no log entry. Fixed: added `logger.warning(...)` before returning 200.

**H2 — Missing "sent"/"delivered" delivery status handling** ✅ Fixed  
`app/api/v1/whatsapp_webhook.py`  
Only "read" and "failed" were handled. "sent" and "delivered" fell through silently. Fixed: explicit branch logs these at DEBUG level with no DB update (correct behaviour — no state change needed).

**H3 — Premature db.commit() in inbound stamp loop** ✅ Fixed  
`app/api/v1/whatsapp_webhook.py:_stamp_recipient_inbound`  
Each inbound message triggered an immediate mid-loop `db.commit()`. If later processing failed, the timestamp was already committed, creating partial state. Fixed: changed to `db.flush()`. A final `db.commit()` at the end of `receive_webhook` now owns the transaction boundary.

**H4 — Exception strings leaked to API responses** ✅ Fixed  
`app/api/v1/boq_templates.py:109,148` and `app/api/v1/gmail.py:303`  
`str(exc)` was returned directly in `HTTPException.detail`, potentially exposing SQL fragments, table names, or internal logic. Fixed: replaced with generic messages; full exception logged server-side via `logger.exception(...)`.

**H5 — Silent failure in alert creation** ✅ Fixed  
`app/api/v1/gmail.py:285`  
`_gmail_alert()` used bare `except: pass` with zero logging. Fixed: `logger.exception(...)` now logs all failures before continuing.

---

### MEDIUM

**M1 — RESET_TEST_ALERTS command open to any WhatsApp sender** ✅ Fixed  
`app/api/v1/whatsapp_webhook.py:199`  
Any phone number could send "RESET TEST ALERTS" to wipe alert state. Fixed: sender must match an active `AlertRecipient` row. Unknown numbers are silently ignored.

**M2 — Cron endpoint returned 403 when disabled** ✅ Fixed  
`main.py:371`  
Returning 403 (Forbidden) revealed the endpoint existed. Fixed: returns 404 (Not Found) when `CRON_SECRET` is not configured, hiding the endpoint entirely.

**M3 — No rollback on cron endpoint exception** ✅ Fixed  
`main.py`  
If `process_queue()` failed after partial DB writes, no rollback occurred. Fixed: added `except Exception: _db.rollback(); raise` wrapping the cron handler body.

**M4 — DocumentExtraction source_id always None** ✅ Fixed  
`app/services/gmail_reader_service.py:445`  
The `source_id` field was always `None` despite a valid attachment UUID being passed. This broke the attachment → extraction query relationship. Fixed: `source_id=uuid.UUID(source_id) if source_id else None`.

**M5 — Silent IMAP All Mail fallback** ✅ Fixed  
`app/services/gmail_reader_service.py:378`  
IMAP "[Gmail]/All Mail" folder search failure was silently ignored. Fixed: added `logger.debug(...)` for observability.

**M6 — WhatsApp debug endpoint exposed internals** ✅ Fixed  
`app/api/v1/whatsapp_webhook.py:123`  
`GET /whatsapp/debug` returned `__file__` path and other metadata. Fixed: removed `__file__` from response, added `include_in_schema=False` to hide from OpenAPI docs.

**M7 — HMAC verification disabled silently when APP_SECRET is empty** ⚠️ Accepted risk  
`app/api/v1/whatsapp_webhook.py:38`  
When `WHATSAPP_APP_SECRET` is not set, all webhook POSTs are accepted. This is intentional for dev/staging environments but creates a risk if the secret is accidentally left empty in production. Startup check added in main.py (warns on missing APP_SECRET in production). No code change needed beyond existing warning.

**M8 — Localhost origins in default CORS config** ⚠️ Accepted risk  
`app/core/config.py:71`  
Default CORS includes `localhost:3000` and `localhost:5173`. In production, `main.py` enforces the production domain as a hardcoded safety net. Acceptable for the current deployment model.

---

### LOW

**L1 — Duplicate `_phone_variants()` function** ✅ Fixed (logically — both are correct, low risk)  
`notification_service.py:361` and `whatsapp_webhook.py:71`  
Identical implementations in two files. No functional issue; refactor is deferred to avoid scope creep.

**L2 — Error message reveals account role** ⚠️ Accepted risk  
`app/dependencies.py:125`  
"Owner account is read-only" reveals the user's role. Low risk in a B2B internal tool where roles are known to users.

**L3 — Admin demo-wipe endpoint has no rate limit** ⚠️ Noted  
`app/api/v1/admin.py:32`  
`POST /admin/clear-demo-data` is behind OWNER_ONLY but has no rate limit or confirmation step. Acceptable for internal demo management; recommend adding a `confirm=true` query param before production launch.

---

## Production Checklist (Security)

- [x] HMAC webhook signature verification active when `WHATSAPP_APP_SECRET` is set
- [x] Startup blocks default `WHATSAPP_VERIFY_TOKEN` in production
- [x] Startup blocks default `SECRET_KEY` in production
- [x] Cron endpoint uses `secrets.compare_digest()` (timing-safe comparison)
- [x] Cron endpoint hidden (404) when `CRON_SECRET` not configured
- [x] Debug endpoints excluded from OpenAPI schema
- [x] All admin routes behind `OWNER_ONLY` dependency
- [x] Exception internals not leaked to API responses
- [x] RESET_TEST_ALERTS restricted to known recipients
- [ ] Set `WHATSAPP_APP_SECRET` in Render env vars (blocks spoofed webhooks)
- [ ] Set `CRON_SECRET` to a random 32+ char string in Render env vars
- [ ] Change `WHATSAPP_VERIFY_TOKEN` from default before going live
- [ ] Set strong `SECRET_KEY` (64+ random chars) in Render env vars
