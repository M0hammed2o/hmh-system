# AI Document Import & Reconciliation Engine — Implementation Plan

Status: Phase 0 complete (repository audit + plan). Implementation follows in this document's order.
Date: 2026-10-12.

---

## 1. Repository audit — what actually exists

Verified by inspection of the working tree at `C:\Users\junsm\Downloads\HMH-System`.

### 1.1 Stack

| Concern | Actual implementation |
|---|---|
| Backend framework | FastAPI 0.115.6, `main.py` mounts ~55 routers from `app/api/v1/` |
| ORM / DB | SQLAlchemy 2.0 (`Mapped[]` declarative), PostgreSQL 15, Alembic (head = `0075`) |
| Architecture | Thin routers -> `app/services/*_service.py` (module-level functions, not classes) -> `app/models/*` |
| Response envelope | `app.schemas.common.ApiSuccess[T]` / `ApiError` |
| Frontend | React 18 + TypeScript + Vite + Tailwind, lazy routes in `src/routes/AppRouter.tsx`, nav in `src/components/layout/AppSidebar.tsx` + `AppTopbar.tsx`, API wrappers in `src/api/*.ts` |
| Tests | pytest against a **real PostgreSQL** at `TEST_DATABASE_URL` (never `DATABASE_URL`); fixtures in `tests/conftest.py` (`db`, `client`, `make_user`, `make_project`, `make_supplier`, `make_item`, `login`, `auth`) |
| Deployment | Render (`render.yaml`); `alembic upgrade head && uvicorn main:app` as start command |

### 1.2 Authentication / authorisation / isolation

- JWT bearer (`app/dependencies.py`), `CurrentUser`, `CurrentUserPayload`, `DbSession`.
- Role aliases: `OWNER_ONLY`, `OFFICE_ADMIN_AND_ABOVE`, `OFFICE_AND_ABOVE`, `WRITE_ROLES`, `ALL_ROLES`, `PROCUREMENT_LEAD_ONLY`.
- Roles: `OWNER, OFFICE_ADMIN, OFFICE_USER, PROCUREMENT_LEAD, SITE_MANAGER, SITE_MANAGER_VIEW, SITE_STAFF, READ_ONLY`.
- **Project isolation**: `dependencies.check_project_access(db, user, project_id)` — office roles bypass; site roles require a `UserProjectAccess` row. This is the tenant/project isolation primitive and must be called on every project-scoped read and write in the new module.
- There is **no separate tenant table scoping users**; `companies` exists as an *issuing company* concept on POs. Project-level access is the real isolation boundary. Recorded as a finding; not re-invented here.

### 1.3 Existing domain services to reuse (critical — do not duplicate)

| Domain | Service | Entry point to use |
|---|---|---|
| Material requests | `app/services/mr_service.py` | `create_request(db, project_id, MaterialRequestCreate, requested_by_id)`, `submit_request`, `approve_request`, `convert_to_po` |
| Purchase orders | `app/services/po_service.py` | `create_po(db, project_id, PurchaseOrderCreate, created_by_id)`, `approve_po` |
| Delivery note (no stock) | `app/services/delivery_service.py` | `create_delivery(db, project_id, data, current_user_id)` — creates `Delivery` + `DeliveryItem`, **writes no stock ledger** |
| Goods receipt (stock) | `app/services/delivery_service.py` | `receive_stock(db, delivery_id, destination, actor_id, lot_id, overrun_reason, items_received)` — writes `StockLedger` rows, already **idempotent** (guards on an existing ledger row with `reference_type='delivery'`), routes `MAIN_WAREHOUSE`/`SITE_STORE` to the project warehouse and `LOT` to lot stock, updates `PurchaseOrderItem.quantity_received`, raises `DELIVERY_DISCREPANCY` alert on partials |
| Supplier liability | `app/services/invoice_service.py` | `create_invoice(db, project_id, InvoiceCreate, captured_by_id)` — enforces unique `(supplier_id, invoice_number)` via `ConflictError` |
| Payment / invoice status | `app/services/payment_service.py` | `create_payment`, `_recalculate_invoice_status` — invoice `PAID`/`PARTIALLY_PAID` is **derived from Payment rows**; never set directly |
| Suppliers / catalogue | `supplier_service.py`, `item_service.py` | `create_supplier`, `list_suppliers`, `list_items`, `create_item` |
| Matching (existing) | `procurement_matching_service.py` | `match_invoice_to_po`, `match_delivery_note_to_po`, `build_proof_pack`, `fuzzy_match_supplier` (in `document_ai_service`) |
| Reconciliation records | `procurement_reconciliation_service.py` + `ProcurementReconciliation` model | variance JSONB, statuses |
| Attachments | `attachment_service.py` | `save_attachment(db, UploadFile, entity_type, entity_id, attachment_type, uploaded_by_id, ...)` |
| Storage | `app/core/storage.py` | `save_upload(content, relative_path, private=True)`, `create_signed_url(path, expires_in)` — Supabase private bucket, local disk fallback |
| Upload validation | `app/core/upload_validation.py` | `validate_upload(file, DOCUMENT_MIMES, max_mb)` — MIME allowlist + extension blocklist + size cap |
| Audit | `audit_service.write_event(db, action, entity_type, actor_id, entity_id, before_value, after_value, notes, commit=False)` |
| Alerts / notifications | `app/models/alert.SystemAlert`, `notification_service.enqueue_direct` |

### 1.4 Existing AI / OCR capability

| Component | What it does | Gap |
|---|---|---|
| `document_ai_service.py` (1463 lines) | Google Cloud Vision OCR or local pypdf text extraction + **regex** field parsing for INVOICE / DELIVERY_NOTE / QUOTE / PURCHASE_ORDER / fuel slip / payment proof. Also `compare_po_invoice_delivery`, `fuzzy_match_supplier`. | No classification; no vision-model understanding; regex-fragile on handwriting and unfamiliar templates |
| `ai_ocr_service.py` (309 lines) | Claude Haiku over **OCR text only**, invoice header (8 fields) + line items with per-field confidence | Invoice-only; text-only (no image/PDF vision); no versioned schema; no injection hardening; no arithmetic validation |
| `DocumentExtraction` model | Stores `raw_text`, `extracted_json`, `ai_extraction_json`, `manually_corrected_json`, status, review_status | No batch, no page provenance, no checksum, no model/schema version columns, no job/retry columns, no posting ledger |
| `vision.py` API | `POST /vision/extract` — synchronous upload -> OCR -> preview. Explicitly does not save business records. | Synchronous (violates Phase 11); single document; no persistence of the upload |
| `gmail_ocr_pipeline_service.py` | IMAP -> attachment -> OCR -> invoice draft | Email-sourced only |

### 1.5 Background processing

There is **no generic job queue**. The established pattern (to be mirrored, not replaced) is:
- a DB table (`notification_queue`) with `status`, `attempt_count`, `last_attempt_at`, `next_attempt_at`, `error_message`;
- an in-process asyncio drain loop started by `@app.on_event("startup")` in `main.py` (`_queue_drain_loop`, 30s or event-woken);
- an external Render cron safety net calling an internal endpoint guarded by `X-Cron-Secret`.

### 1.6 Confirmed genuine gaps

1. No multi-document batch inbox or upload UI.
2. No document **classification** step at all.
3. No **vision-based** (image/PDF-native) extraction — current AI sees OCR text only.
4. No versioned, typed extraction schema; no per-field provenance (page, confidence, corrected-by).
5. No prompt-injection hardening on untrusted document content.
6. No independent arithmetic validation of extracted totals.
7. No out-of-order document reconciliation graph (MR -> PO -> GRN -> Invoice -> Payment) with explanations.
8. No duplicate-file detection (no checksum stored anywhere).
9. No generic job queue / retry / idempotent posting ledger.
10. No legacy-import authorisation concept — a historical paper MR/PO cannot currently be represented as "document-backed, not digitally approved".
11. No AI cost/usage tracking.

---

## 2. Design

### 2.1 Principle

The new module is an **ingestion and decision layer only**. Every business mutation is executed by calling an existing domain service. No new ledger, no new supplier balance, no new stock table, no new PO/MR numbering.

### 2.2 New tables (Alembic `0076`, additive only)

| Table | Purpose |
|---|---|
| `ai_import_batches` | one upload session: uploader, project hint, counts, status |
| `ai_import_documents` | one file: `sha256` checksum, stored_path, mime, pages, status (state machine), classified type + confidence, project/supplier resolution, `is_legacy`, failure reason |
| `ai_import_extractions` | versioned extraction attempt: `schema_version`, `provider`, `model`, `prompt_version`, `fields` JSONB (per-field `{value, page, confidence, source, validated, corrected_by}`), `line_items` JSONB, `arithmetic_checks` JSONB, `token_usage`, `cost_usd` |
| `ai_import_matches` | proposed/confirmed link: document -> (`material_request`/`purchase_order`/`delivery`/`invoice`/`payment`/`supplier`/`project`/`item`), `score`, `method`, `explanation`, `status` (PROPOSED/CONFIRMED/REJECTED/AMBIGUOUS) |
| `ai_import_postings` | what was actually posted: document -> entity_type/entity_id, `idempotency_key` (UNIQUE), posted_by, posted_at, reversal fields |
| `ai_import_jobs` | queue row: document_id, job_type, status, attempt_count, next_attempt_at, locked_at/locked_by, last_error |
| `ai_import_corrections` | field-level user correction audit: document, field_path, before, after, actor, at |

### 2.3 Document state machine

`UPLOADED -> QUEUED -> PROCESSING -> EXTRACTED -> CLASSIFIED -> MATCHING -> AWAITING_REVIEW | AWAITING_AUTHORISATION | READY_TO_POST -> POSTED | PARTIALLY_POSTED`
plus terminal/branch states `FAILED`, `REJECTED`, `DUPLICATE`.

### 2.4 Processing policy (Phase 9)

A deterministic rules engine (`ai_import_policy_service`) returns `AUTO_ELIGIBLE | NEEDS_REVIEW | BLOCKED` with a reason list. AI confidence is an *input*, never sufficient on its own: a posting requires the deterministic preconditions (unambiguous supplier + project, arithmetic valid, no duplicate, receipt evidence for stock, authorisation present for financial posting) regardless of model confidence.

### 2.5 Security

- Untrusted document text is wrapped in explicit delimiters with a standing instruction that content inside is data; a post-parse guard rejects any extraction whose values look like instructions to the system.
- Files stored private (`storage.save_upload(..., private=True)`); access only through a signed-URL endpoint that re-checks project access.
- Supplier bank details are extracted **for comparison display only** and are never written to `suppliers`.
- `check_project_access` on every project-scoped operation; cross-project references inside a document are a `BLOCKED` condition.

### 2.6 Background processing

Mirror the notification-queue pattern: `ai_import_jobs` table + `ai_import_worker.drain_once(db)` + in-process asyncio loop in `main.py` + internal cron endpoint. Row-level locking via `SELECT ... FOR UPDATE SKIP LOCKED` prevents duplicate concurrent execution. Posting idempotency is enforced by the `UNIQUE` idempotency key in `ai_import_postings` **and** by the existing guards in `delivery_service.receive_stock` and `invoice_service.create_invoice`.

---

## 3. Requirement -> code mapping

| Assignment phase | Implementation |
|---|---|
| 1 Universal inbox | `app/api/v1/ai_import.py` (upload/batch/list/detail/retry), `hmh-frontend/src/pages/AIDocumentImportPage.tsx`, `src/api/aiImport.ts`, nav + route |
| 2 Classification & extraction | `app/services/ai_import_extraction_service.py` (provider-agnostic; Claude vision primary, OCR+text fallback, regex fallback), `app/schemas/ai_import.py` typed schemas v1 |
| 3 Matching | `app/services/ai_import_matching_service.py` (reuses `procurement_matching_service` helpers + `fuzzy_match_supplier`) |
| 4 MR import | `ai_import_posting_service.post_material_request` -> `mr_service.create_request` |
| 5 PO import | `ai_import_posting_service.post_purchase_order` -> `po_service.create_po` |
| 6 Goods receipt | `ai_import_posting_service.post_goods_receipt` -> `delivery_service.create_delivery` + `receive_stock` |
| 7 Invoices / AP | `ai_import_posting_service.post_supplier_invoice` -> `invoice_service.create_invoice`; payment status stays derived from `payment_service` |
| 8 Dashboard | `GET /ai-import/dashboard` + frontend dashboard tab |
| 9 Policy | `app/services/ai_import_policy_service.py` |
| 10 Security & audit | `storage` private + signed URL, `audit_service.write_event`, `ai_import_corrections`, injection guard |
| 11 Reliability | `ai_import_jobs` + `app/services/ai_import_worker.py` + `main.py` loop + `/internal/process-ai-import` |
| 12 Tests | `tests/test_ai_import_*.py` against the real services with the existing `db`/`client` fixtures |
| 13 Integration | all postings route through existing services; no schema changes to existing tables |
| 14 Delivery doc | `docs/AI_DOCUMENT_IMPORT_COMPLETION.md` |
