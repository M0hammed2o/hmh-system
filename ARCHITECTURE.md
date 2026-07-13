# ARCHITECTURE — HMH Construction OS

## System Overview

```
Browser (React SPA)
     │ HTTPS / Axios / JWT Bearer
     ▼
FastAPI (Render web service — hmh-backend.onrender.com)
     │
     ├── app/api/v1/          ← 50+ route modules
     ├── app/services/        ← Business logic (45 service files)
     ├── app/models/          ← SQLAlchemy ORM (40 models)
     │
     ├── PostgreSQL 15        ← Primary data store
     │
     ├── WhatsApp Cloud API   ← Outbound alerts + inbound webhook
     ├── Gmail SMTP/IMAP      ← Procurement emails
     ├── Claude API           ← AI OCR field extraction
     └── Google Vision        ← PDF/image OCR
```

---

## Authentication & Authorisation

**Flow:** `POST /api/v1/auth/login` → validates credentials → returns `access_token` (JWT, 8h) + `refresh_token` (JWT, 7d).
JWT payload contains `{"sub": "<user_id>", "role": "<UserRole>"}`.
All protected routes inject `CurrentUser` or `CurrentUserPayload` via `app/dependencies.py`.

**Role guards (FastAPI Depends):**
- `OWNER_ONLY` — role=OWNER
- `OFFICE_ADMIN_AND_ABOVE` — OWNER, OFFICE_ADMIN
- `OFFICE_AND_ABOVE` — OWNER, OFFICE_ADMIN, OFFICE_USER, PROCUREMENT_LEAD
- `WRITE_ROLES` — all above + SITE_MANAGER, SITE_STAFF
- `ALL_ROLES` — every role including READ_ONLY, SITE_MANAGER_VIEW
- `PROCUREMENT_LEAD_ONLY` — OWNER, PROCUREMENT_LEAD (final MR approval + override)

**Project isolation:** `check_project_access(db, user, project_id)` raises HTTP 403 for site-level roles (`SITE_MANAGER`, `SITE_STAFF`, `SITE_MANAGER_VIEW`) without a matching `UserProjectAccess` row. Must be called after every project-scoped resource fetch. Office roles bypass automatically.

---

## Procurement Pipeline

```
Material Request (MR)
   └── 3-vote approval (OFFICE_AND_ABOVE) OR OWNER override
         └── [approved] Email suppliers for quote (SMTP)
               └── Quote received → Upload + 3-vote approval
                     └── Purchase Order (PO) → Delivery → Invoice → Payment
                                                        └── Reconciliation
```

**Key models:** `MaterialRequest`, `PurchaseOrder`, `Delivery`, `Invoice`, `Payment`, `Quotation`, `MRQuote`, `MRQuoteVote`
**Vote tracking:** `STAFF_VOTES_REQUIRED = 3` (defined in `app/models/material_request.py`)
**Issuing company:** PO has `issuing_company` field (HMH_GROUP | MINERAT). Auto-filled from `project.client_name` on frontend.

---

## Workshop Pipeline

```
Workshop Repair Request (vehicle)
   └── 3-vote approval (OFFICE_AND_ABOVE) OR OWNER override
         └── Email suppliers for parts quote
               └── Quote upload + 3-vote approval
                     └── PO → Delivery Note → Invoice
```

**Key models:** `RepairJob` (linked to `Vehicle`), reuses `MRQuote`, `MRQuoteVote`, `MREmailLog`
**Parts issuance:** Parts can be issued directly from warehouse stock to a repair job.

---

## Warehouse Transfer (Project-to-Project)

```
Site clerk submits WarehouseTransferRequest (from_project → to_project, item, quantity, reason)
   └── WhatsApp alert to office
         └── 3 OFFICE_AND_ABOVE votes  OR  OWNER single override
               └── _execute_transfer(): writes paired TRANSFER_OUT + TRANSFER_IN in StockLedger
```

**`TRANSFER_VOTES_REQUIRED = 3`** — re-checks stock quantity at execution time (not just at request time).

---

## Stock / Warehouse Model

- `StockLedger`: append-only log of all stock movements. Movement types include RECEIVED, ISSUED, ADJUSTMENT, TRANSFER_OUT, TRANSFER_IN. Paired transfers share `reference_id`.
- `stock_balances`: PostgreSQL materialized view — SUM of all ledger entries per (project, item). Never written directly.
- `ItemCategory` + `Item`: shared catalog of materials/parts.
- Project warehouse vs. main warehouse: items assigned per-project scope.

---

## Notification System

```
Any service → alert_service.create_alert() → SystemAlert row
           → notification_service.enqueue_for_alert() → NotificationQueue rows (one per recipient)
           → _queue_drain_loop() (asyncio, 30s) OR Render cron → process_queue()
           → WhatsApp Cloud API send
```

**Recipients:** `AlertRecipient` rows with per-category subscription flags: `receives_critical_alerts`, `receives_procurement_alerts`, `receives_payment_alerts`, etc.
**Deduplication:** `SystemAlert` queried within 23h window before creating a new alert (prevents spam for recurring conditions like low stock or overdue payment).
**Mock mode:** `WHATSAPP_ENABLED=false` → all sends are `MOCK_SENT` (no real API calls, queue still processed).
**Immediate wake:** `_drain_event.set()` is called by `enqueue_direct()` to wake the background loop immediately.

---

## Gmail OCR Pipeline

```
POST /api/v1/gmail/fetch (IMAP poll, manual or cron)
   └── gmail_reader_service: fetch unread emails → save attachments
         └── document_ai_service: Claude/Vision OCR → extract fields
               └── procurement_matching_service: match to supplier/PO → auto-create invoice draft
```

**Key models:** `IncomingEmail`, `DocumentExtraction`
**OCR providers:** `OCR_PROVIDER=google_vision` (production) or `disabled` (fallback to Claude text only).

---

## Payment Due Alert System

```
Daily cron (POST /api/v1/internal/scan-payment-due)
   └── payment_due_service.scan_payment_due(db)
         └── query unpaid invoices with due_date set
               └── due within 7 days → PAYMENT_DUE alert
               └── past due_date    → OVERDUE_PAYMENT alert
               └── 23h deduplication via SystemAlert (same entity_id + alert_type)
```

`due_date` is auto-computed from `invoice_date + supplier.payment_due_days` when not manually set.

---

## Frontend Architecture

**SPA:** React 18, React Router v6, lazy-loaded pages, Radix UI primitives, Tailwind CSS.
**Auth:** `AuthContext` stores JWT in memory (not localStorage); `ProtectedRoute` redirects to `/login` if unauthenticated; `SiteRoute` redirects to `/site-login` for site portal.
**Service block:** `config/serviceBlock.ts` — `SERVICE_BLOCKED=true` renders a hard block screen instead of the app (used for maintenance or access control).
**API layer:** One file per backend domain in `src/api/`. All return typed responses. `client.ts` sets the base URL from `VITE_API_BASE_URL` env var and attaches the Bearer token.
**Site portal:** `SiteDashboardPage` at `/site` — restricted view for site-level users (lots, stock, vehicles, workshop tab).

---

## Background Tasks & Cron

| Task | Mechanism | Schedule |
|---|---|---|
| Notification queue drain (primary) | asyncio `_queue_drain_loop` in main.py | ~30s or immediate on enqueue |
| Notification queue drain (backup) | Render cron → `POST .../process-notifications` | Every 5 min |
| Daily WhatsApp summary | Render cron / manual UI trigger → `POST .../send-daily-summary` | 18:00 daily |
| Payment due scan | Render cron / manual UI trigger → `POST .../scan-payment-due` | Daily (08:00 recommended) |
| Gmail inbox poll | Manual via `POST /api/v1/gmail/fetch` | Not yet automated |
| Stage auto-seed | Startup event in main.py | Once on fresh DB |
| Alembic migrate | Startup event in main.py | Every deploy |

---

## Key Model Groups

| Group | Models |
|---|---|
| Project hierarchy | `Project`, `Site`, `Lot`, `LotType`, `StageMaster`, `ProjectStageStatus` |
| Access control | `User`, `UserProjectAccess`, `UserSiteAccess` |
| Procurement | `MaterialRequest`, `PurchaseOrder`, `Delivery`, `Invoice`, `Payment`, `Quotation`, `MRQuote`, `MRQuoteVote`, `MREmailLog`, `ProcurementReconciliation` |
| Stock | `Item`, `ItemCategory`, `StockLedger` (append-only) |
| Warehouse transfer | `WarehouseTransferRequest`, `WarehouseTransferVote` |
| BOQ | `BOQHeader`, `BOQSection`, `BOQItem` (with `planned_total` GENERATED ALWAYS col) |
| Notifications | `SystemAlert`, `AlertRecipient`, `NotificationQueue` |
| Fleet/Workshop | `Vehicle`, `FuelLog`, `RepairJob`, `JobCard` |
| Documents | `Attachment`, `IncomingEmail`, `DocumentExtraction` |
| Finance | `Company`, `Supplier`, `MunicipalityInvoice`, `Expense` |
| Audit | `AuditLog` |
