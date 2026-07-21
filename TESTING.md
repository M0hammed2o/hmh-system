# TESTING — HMH Construction OS

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
| `test_stage_tracking.py` | Stage milestone tracking, seed, progress and alert workflows |

### Notable Gaps (see KNOWN_BUGS.md)
- Warehouse transfer approval flow: **no tests** — `tests/test_warehouse_transfer_flow.py` needed
- Payment due scan: **no tests** — `tests/test_payment_due_scan.py` needed

---

## Frontend

**No frontend test suite exists** (no Vitest, Jest, or Playwright config found).
Type checking is the only automated frontend validation: `cd hmh-frontend && npx tsc --noEmit`.
All frontend behaviour is manually verified.

---

## Test Architecture Notes

- Tests connect to a live PostgreSQL database (not mocked). Default: `hmh-backend/pytest.ini` or `DATABASE_URL` env var.
- `conftest.py` in `tests/` provides shared fixtures (DB session, user factory, project factory).
- Tests are integration-level: they hit the actual service layer and database; no mocking of DB operations.
- WhatsApp sends are intercepted in test environments via `WHATSAPP_ENABLED=false` — sends are `MOCK_SENT`.
- Gmail/SMTP sends are intercepted via `SMTP_ENABLED=false` in test environments.
