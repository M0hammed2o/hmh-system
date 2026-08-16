# TESTING — HMH Construction OS

Fuel Management gap-closure coverage, its requirement matrix, dedicated PostgreSQL setup and Playwright commands are documented in [docs/fuel-management-gap-closure.md](docs/fuel-management-gap-closure.md).

**2026-08-03 — Attachment/evidence storage privacy:** `hmh-backend/tests/test_attachments.py` covers signed-URL generation and expiry, permission/project-isolation on `GET /attachments/{id}/download` for local/private/legacy-public stored paths, fail-closed `save_upload(private=True)` behaviour outside development/test, and private-object cleanup — all via mocked `httpx` calls, no real Supabase network access. `hmh-backend/tests/test_fuel_management.py::test_production_storage_validation` covers the new `Settings.validate_production_storage` startup check.

**2026-08-04 — Site-clerk Fuel balance, PWA mobile layout, dual-access routing:** `hmh-frontend/tests/pwa-login.spec.mjs` gained: 6 mobile-viewport tests (360×640, 390×844, 412×915) for `/site/fuel-request` and `/site`, asserting no horizontal document overflow and that key controls' bounding boxes stay within the viewport; 2 tests for the new "Estimated fuel remaining" balance section (populated and empty-storage states); 5 tests for dual-access Site Dashboard entry points (login-page link, topbar link + `/site` reachability for OWNER, absence of the link and 403-equivalent redirect for a non-dual-access role, and the expired-session/re-login path that previously would have looped through `SiteLoginPage`'s "Site portal access only" screen). 19/19 passing. Playwright's `webServer` serves the built `dist/` (via `npm run preview`), not live source — `npm run build` must be re-run before `npm run test:pwa`/`test:notifications` after any frontend source change, or tests silently run against a stale build.

**2026-08-03 — Attachment project-isolation audit:** every `AttachmentEntity` value was checked against `_entity_project_id()`'s resolution table. Found and fixed a genuine gap — `PROGRESS_CLAIM`, `PROGRAMME_ACTIVITY`, `WEEKLY_PLAN` fell through to unrestricted access — covered by the parametrized `test_previously_unresolved_entity_types_now_enforce_project_isolation` (list/upload/delete, 3 entity types × cross-project denial). Separately, `test_stage_status_attachment_requires_project_access` was failing for an unrelated reason (its "outsider" fixture used a company-wide office role, not a project-scoped site role) — corrected in the test, no production code change for that item. See `KNOWN_BUGS.md` for the full writeup. `test_attachments.py`: 48/48 passing.

## Backend Test Suite

**Location:** `hmh-backend/tests/`
**Framework:** pytest 8.3.4 + pytest-asyncio 0.25.0
**Config:** `hmh-backend/pytest.ini`

### Running Tests
```bash
cd hmh-backend
# Activate venv first
.venv\Scripts\activate

# Full suite
pytest tests/ -v

# Single file
pytest tests/test_procurement_flow.py -v

# Pattern
pytest tests/ -k "warehouse" -v

# Stop on first failure
pytest tests/ -x -v
```

### Test File Inventory (50+ files, Verified from tests/ directory listing)
<!-- Note: Tests require a live PostgreSQL DB on port 55432 (Docker). Docker Desktop was not running during the 2026-07-12 session. Evidence below is from prior sessions only — do NOT label as current-session PASS without running with Docker active. -->

| File | Coverage Area |
|---|---|
| `test_procurement_flow.py` | End-to-end MR → PO → Delivery → Invoice → Payment |
| `test_e2e_procurement_pipeline.py` | Full 41-test pipeline e2e suite (Phase 3M) |
| `test_procurement_scenarios.py` | Edge cases: partial delivery, split PO, etc. |
| `test_procurement_analytics.py` | Analytics aggregation |
| `test_procurement_matching.py` | Document → PO matching logic |
| `test_procurement_reconciliation.py` | Reconciliation calculations |
| `test_boq_system.py` | BOQ create, update, aggregation |
| `test_boq_aggregation.py` | BOQ quantity rollup |
| `test_boq_generated_column.py` | `planned_total` GENERATED ALWAYS column |
| `test_boq_validation.py` | BOQ constraint validation |
| `test_boq_sync.py` | BOQ sync with delivery data |
| `test_boq_catalog_autocreate.py` | Auto-creating catalog items on BOQ entry |
| `test_boq_section_delete.py` | Section cascade delete |
| `test_boq_template_apply.py` | Template application to project |
| `test_delivery_boq_update.py` | Delivery triggers BOQ quantity update |
| `test_delivery_documents.py` | Delivery attachment handling |
| `test_partial_delivery.py` | Partial delivery quantity tracking |
| `test_unified_delivery.py` | Unified delivery flow |
| `test_invoice_auto_create_fixes.py` | Auto-invoice creation edge cases |
| `test_invoice_parsing_and_delivery.py` | OCR-parsed invoice + delivery matching |
| `test_invoice_proof_pack.py` | Proof pack generation |
| `test_payments.py` | Payment recording and balance update |
| `test_po_received_qty.py` | PO received quantity tracking |
| `test_mr_pipeline_close.py` | MR close-out flow |
| `test_mr_email.py` | MR email send |
| `test_stock_issue_to_lot.py` | Stock issued to lot/site |
| `test_project_warehouse_add_adjust.py` | Warehouse add/adjust operations |
| `test_warehouse_project_scope.py` | Warehouse project isolation |
| `test_site_dashboard.py` | Site dashboard data |
| `test_stage_tracking.py` | Stage progress recording |
| `test_lot_types.py` | Lot type management |
| `test_lot_type_propagation.py` | Lot type inherited properties |
| `test_user_project_enforcement.py` | Role-based project isolation |
| `test_api_security.py` | Auth, role guards, injection attempts |
| `test_attachment_system.py` | File attachment CRUD |
| `test_attachments.py` | Additional attachment tests |
| `test_document_ai_service.py` | Claude/Vision OCR field extraction |
| `test_gmail_email_service.py` | Gmail SMTP send |
| `test_gmail_ocr_pipeline.py` | Full Gmail OCR pipeline |
| `test_gmail_processing.py` | Email processing logic |
| `test_gmail_quotation_classification.py` | Quote vs invoice classification |
| `test_gmail_reader_service.py` | IMAP reader |
| `test_document_matching_upgrade.py` | Improved document→PO matching |
| `test_ai_ocr.py` | AI OCR integration |
| `test_supplier_documents.py` | Supplier document history |
| `test_dashboard.py` | Dashboard data aggregation |
| `test_jobcard_approval.py` | Job card approval workflow |
| `test_work_done.py` | Subcontractor work-done recording |
| `test_municipality_invoice.py` | Municipality invoice management |
| `test_expense_records.py` | Expense recording |
| `test_site_capture_delivery_note.py` | Site capture delivery note |
| `test_boq_adjustment.py` | BOQ adjustment entries |
| `test_audit_fixes.py` | Audit log integrity |
| `test_whatsapp.py` | WhatsApp notification send/receive |
| `test_progress_claims.py` | Municipality progress claims: generation, transitions, PDF, no-pricing, propagation (38 tests — Phase 6) |
| `test_fuel_management.py` | Fuel lifecycle, permissions, delivery, stock, issues, reconciliation, exports and BOQ separation (14 tests) |
| `test_stage_tracking.py` | Stage milestone tracking, seed, progress and alert workflows |

### Notable Gaps (see KNOWN_BUGS.md)
- Warehouse transfer approval flow: **no tests** — `tests/test_warehouse_transfer_flow.py` needed
- Payment due scan: **no tests** — `tests/test_payment_due_scan.py` needed

---

## Frontend

Playwright browser coverage is configured in `hmh-frontend`:

```bash
npm run test:pwa
```

`hmh-frontend/tests/pwa-login.spec.mjs` covers direct/refreshed login routes, role routing, retained destinations, manifest metadata and offline service-worker navigation. Type check with `cd hmh-frontend && node_modules/.bin/tsc --noEmit`; build with `npm run build`.

---

## Test Architecture Notes

- Tests connect to a live PostgreSQL database (not mocked). `TEST_DATABASE_URL` must point to a dedicated non-production database; `tests/conftest.py` refuses the main local database.
- `conftest.py` in `tests/` provides shared fixtures (DB session, user factory, project factory).
- Tests are integration-level: they hit the actual service layer and database; no mocking of DB operations.
- WhatsApp sends are intercepted in test environments via `WHATSAPP_ENABLED=false` — sends are `MOCK_SENT`.
- Gmail/SMTP sends are intercepted via `SMTP_ENABLED=false` in test environments.

## 2026-08-02 verification

- Migration 0069: upgrade, downgrade to 0068 and re-upgrade all passed in isolated PostgreSQL.
- Fuel: 14/14 passed.
- Fuel + progress/programme/weekly: 51/51 passed.
- Frontend TypeScript: zero errors.
- Vite production build: passed (1,770 modules).
- Playwright PWA/login: 4/4 passed.
- Full backend suite: 873 collected; timed out at 900 seconds at 86% with legacy failures. See `KNOWN_BUGS.md`; do not label the full suite green.
- Live deployment audit: app-subdomain login routes returned 200, but apex/www returned 404; the currently deployed worker/icon URLs returned HTML. A new deployment plus domain mapping is still required.
