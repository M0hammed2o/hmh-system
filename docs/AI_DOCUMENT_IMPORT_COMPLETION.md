# AI Document Import & Reconciliation Engine — Completion Report

Date: 2026-10-13
Branch: `main` (uncommitted working tree)
Migration head: `0076`

---

## 1. What this is

A new module inside the existing HMH system. Staff upload scanned or
photographed procurement paperwork — material requests, purchase orders,
delivery notes, supplier invoices — in any mix and any order. The system reads
each document, works out what it is and which existing records it relates to,
checks it against deterministic rules, and asks a person to confirm before
anything is posted.

**It is an ingestion and decision layer only.** It owns no balances. Every
business mutation is executed by calling the domain service that already owned
that behaviour, so existing business rules, alerts, audit events and BOQ
interactions apply unchanged:

| Posting | Service called |
|---|---|
| Material request | `mr_service.create_request` |
| Purchase order | `po_service.create_po` |
| Goods receipt + stock | `delivery_service.create_delivery` |
| Supplier liability | `invoice_service.create_invoice` |

No parallel supplier ledger, stock table, procurement record or project costing
system was created.

---

## 2. Completed vs not completed

### Completed and tested

| Capability | Evidence |
|---|---|
| Batch upload of mixed document types, any order, no manual classification | `test_batch_upload_accepts_a_mixed_batch_and_detects_a_duplicate_file` |
| Drag-and-drop, multi-file, mobile camera capture, PDF + image | `AIDocumentImportPage.tsx` upload panel |
| Duplicate file detection by SHA-256, under any filename | same test; duplicate marked `DUPLICATE`, never queued |
| Document classification into 8 categories | `test_document_runs_through_the_full_pipeline` |
| Vision-based extraction (PDF/image read directly), OCR-text fallback, regex fallback | `ai_import_extraction_service.analyse_document` strategy chain |
| Per-field provenance: value, page, confidence, source, corrected-by | `ExtractedField`; `test_typed_pdf_material_request_is_classified_and_normalised` |
| Unreadable values stay unresolved — never invented | `test_handwritten_request_keeps_unreadable_values_unresolved` |
| Arithmetic recomputed independently of the model | 6 tests in `test_ai_import_extraction.py` |
| Prompt-injection detection on document content | `test_instruction_text_in_a_document_is_flagged_not_obeyed` |
| Supplier / project / site resolution, exact + fuzzy, with ambiguity refusal | 9 tests in `test_ai_import_matching.py` |
| MR → PO → GRN → Invoice chain matching, out of order | `test_an_invoice_uploaded_before_its_po_links_once_the_po_exists` |
| Unit conversion, with incomparable units reported not assumed | `test_incompatible_units_return_none_rather_than_a_wrong_number` |
| Three-way match (PO vs receipt vs invoice) with price/quantity/total variance | `test_price_difference_against_the_po_is_detected` and 5 others |
| Partial deliveries, partial invoices | `test_partial_delivery_is_reported_as_partial_not_as_an_error` |
| Multi-page documents, with per-page field provenance | `test_multi_page_invoice_keeps_page_provenance_and_totals_correctly` |
| Several invoices against one purchase order | `test_two_invoices_against_one_po_both_match_and_both_post` |
| One invoice covering several purchase orders (not silently attached to one) | `test_one_invoice_covering_two_pos_is_not_silently_attached_to_one` |
| Purchase order uploaded before its material request | `test_a_po_uploaded_before_its_mr_links_once_the_mr_exists` |
| Historical receipt added on top of an existing stocktake balance | `test_historical_receipt_adds_to_existing_stock_rather_than_replacing_it` |
| Human-readable matching explanations | `test_matching_explanations_are_human_readable` |
| Material request import (DRAFT, no stock movement) | 4 tests |
| Purchase order import (DRAFT, never auto-approved) | 2 tests |
| Goods receipt updating real stock through the real service | 7 tests |
| Stock cannot be moved by an invoice | `test_an_invoice_can_never_post_a_goods_receipt` |
| Double stock posting prevented | `test_the_same_delivery_note_posted_twice_increases_stock_once` |
| Supplier liability via `invoice_service`, never marked paid from a document | 5 tests |
| Duplicate invoice number refused | `test_duplicate_invoice_number_is_refused_by_the_domain_service` |
| AUTO_ELIGIBLE / NEEDS_REVIEW / BLOCKED policy engine | 10 tests |
| BLOCKED is absolute — no role, no override | `test_blocked_document_cannot_be_posted_even_with_override` |
| Legacy-import authorisation distinct from digital approval | `test_legacy_import_is_labelled_rather_than_shown_as_approved` |
| Field corrections with full before/after audit | `test_correcting_a_field_is_audited_and_re_evaluated` |
| Reconciliation dashboard with filters | `test_dashboard_counts_and_queues` |
| Side-by-side original vs extracted view | `AIDocumentImportDetail.tsx` |
| Project isolation on read, list, download and post | 5 API tests |
| Private storage + short-lived signed URLs only | `get_document_file` endpoint |
| Document access logging | `test_viewing_a_document_file_is_logged` |
| Background job queue, retry with backoff, permanent failure | 5 tests |
| Crash recovery (stale job reclaim) | `test_a_job_abandoned_by_a_dead_worker_is_reclaimed` |
| Duplicate concurrent job prevented | `test_a_second_live_job_for_the_same_document_is_refused` |
| Extraction never runs inside an HTTP request | `test_upload_queues_rather_than_extracting_inline` |
| Idempotent posting (crash-safe two-phase claim) | 4 tests |
| AI cost and token tracking | `test_dashboard_counts_and_queues` |
| Configurable retention with dry-run | 3 tests |

### Not completed — and why

| Item | Status | Reason |
|---|---|---|
| **Live AI provider verification** | **Not done** | No `ANTHROPIC_API_KEY` in this environment. Every test stubs the provider at `_call_model`. The request shape follows the current Anthropic Python SDK (base64 `document`/`image` blocks + `output_config.format` JSON schema), but **the prompt has never been run against the live model, and extraction accuracy on real HMH scans is unmeasured.** See §9. |
| **Supplier credit notes posting** | Deliberately not implemented | The system has no credit-note record and no supplier-balance adjustment entity. Rather than invent a parallel ledger, credit notes are classified, extracted, matched to their invoice and stored as evidence; posting is refused with an explanation. Applying the credit is a manual step at settlement. |
| **Payment proof posting** | Deliberately not implemented | Invoice payment status is derived from `Payment` rows by `payment_service._recalculate_invoice_status`. A document is not a settlement record. Proofs are stored as evidence; the payment is captured on the payments screen. |
| **Direct-to-lot goods receipt** | Deliberately not implemented | `delivery_service.create_delivery` routes all receipts to the project warehouse; the manual UI has no direct-to-lot receipt either. Posting is refused with a pointer to the existing issue-to-lot workflow, so the import path does not gain a route the rest of the system lacks. |
| **Malware scanning** | Not available | No scanner exists in this stack. Uploads are protected by MIME allowlist, executable-extension blocklist, size cap, private storage and never being executed or served inline from a public path. A real scanner should be added before accepting documents from outside the organisation. |
| **Automatic posting** | Implemented but **off** | `AI_IMPORT_AUTO_POST_ENABLED=false`. An AUTO_ELIGIBLE document stops at READY_TO_POST and waits for a person. Turning it on is a business decision, not a technical one. |

---

## 3. Database migrations

`alembic/versions/0076_ai_document_import.py` — `0075 -> 0076`.

Seven new tables, six new enum types. **Strictly additive**: no existing table,
column, constraint, index or row is modified or removed.

| Table | Purpose |
|---|---|
| `ai_import_batches` | one upload session |
| `ai_import_documents` | one file + lifecycle state + resolved context |
| `ai_import_extractions` | append-only versioned extraction attempts |
| `ai_import_matches` | links to existing records, with explanation and evidence |
| `ai_import_postings` | what was posted; **UNIQUE `idempotency_key`** |
| `ai_import_jobs` | work queue; **partial UNIQUE index** on one live job per document |
| `ai_import_corrections` | field-level human corrections |

Verified against a clean PostgreSQL 15 database: `upgrade head` reaches `0076`,
`downgrade 0075` removes all 7 tables and all 6 enum types, `upgrade head`
re-applies cleanly.

---

## 4. New API endpoints

All under `/api/v1/ai-import`.

| Method | Path | Roles |
|---|---|---|
| POST | `/batches` | office + site manager |
| GET | `/batches` | + view-only |
| GET | `/batches/{id}` | + view-only |
| POST | `/batches/{id}/documents` | office + site manager |
| GET | `/documents` | + view-only |
| GET | `/documents/{id}` | + view-only |
| GET | `/documents/{id}/file` | + view-only (signed URL, logged) |
| PATCH | `/documents/{id}/context` | office + site manager |
| PATCH | `/documents/{id}/corrections` | office + site manager |
| POST | `/documents/{id}/matches` | office + site manager |
| POST | `/documents/{id}/matches/decide` | office + site manager |
| POST | `/documents/{id}/review` | office + site manager |
| POST | `/documents/{id}/retry` | office + site manager |
| POST | `/documents/{id}/authorise` | office admin + |
| POST | `/documents/{id}/reject` | office admin + |
| POST | `/documents/{id}/post` | office admin + |
| GET | `/dashboard` | + view-only |
| GET | `/health` | office admin + |
| POST | `/process` | office admin + |
| GET | `/postings/incomplete` | office admin + |
| POST | `/postings/{id}/resolve` | office admin + |
| POST | `/retention/purge` | owner only |

Plus two cron endpoints (`X-Cron-Secret`, hidden from the schema):
`POST /api/v1/internal/process-ai-import` drains the queue, and
`POST /api/v1/internal/ai-import-retention` applies the retention policy —
defaulting to a dry run so a schedule can be proven before it deletes.

---

## 5. New UI

| Path | File |
|---|---|
| `/ai-document-import` | `src/pages/AIDocumentImportPage.tsx` |
| — | `src/components/aiImport/AIDocumentImportDetail.tsx` |
| — | `src/components/aiImport/AIImportBadges.tsx` |
| — | `src/components/aiImport/ManualLinkPanel.tsx` |
| — | `src/api/aiImport.ts` |

Three tabs: **Upload** (drag-drop / file picker / camera, project hint,
historical-paperwork flag), **Documents** (filter by project, site, supplier,
type, status, uploader, date range; each row says in plain words what is holding
it up), **Reconciliation** (pipeline counts, operational queues, AI spend).

The detail drawer shows the original document beside what was read, with a
coloured confidence marker and page number on every field, inline correction,
the arithmetic check, line items with their catalogue matches, every match with
its explanation, related uploads, the correction history, and the post / reject
/ re-read actions. Nav entries added to the sidebar and the mobile topbar under
Procurement.

---

## 6. Environment variables

New (all optional, with working defaults):

| Variable | Default | Meaning |
|---|---|---|
| `AI_IMPORT_ENABLED` | `true` | Master switch |
| `AI_IMPORT_MODEL` | `claude-opus-5-5` | Extraction model |
| `AI_IMPORT_TIMEOUT_SECONDS` | `120` | Per-request timeout |
| `AI_IMPORT_MAX_UPLOAD_MB` | `20` | Per-file size cap. Not higher: base64 inflates by 4/3 and the provider caps a request at 32 MB |
| `AI_IMPORT_MAX_FILES_PER_BATCH` | `50` | Batch cap |
| `AI_IMPORT_WORKER_ENABLED` | `true` | In-process drain loop |
| `AI_IMPORT_WORKER_INTERVAL_SECONDS` | `20` | Drain interval |
| `AI_IMPORT_WORKER_BATCH_SIZE` | `3` | Documents per pass |
| `AI_IMPORT_JOB_STALE_MINUTES` | `15` | Crash-recovery threshold |
| `AI_IMPORT_JOB_MAX_ATTEMPTS` | `3` | Retry budget |
| `AI_IMPORT_RETRY_BACKOFF_SECONDS` | `60` | Backoff base (doubles, capped at 1h) |
| `AI_IMPORT_AUTO_POST_ENABLED` | `false` | Auto-post AUTO_ELIGIBLE documents |
| `AI_IMPORT_MIN_AUTO_CONFIDENCE` | `0.85` | Confidence floor (necessary, not sufficient) |
| `AI_IMPORT_RETENTION_DAYS` | `2555` | ~7 years |
| `AI_IMPORT_MAX_OUTPUT_TOKENS` | `16000` | Output budget; thinking shares it on current models |
| `AI_IMPORT_SCAN_ENABLED` | `false` | Turn on malware scanning |
| `AI_IMPORT_SCAN_URL` | `""` | Scanner endpoint that accepts the bytes |
| `AI_IMPORT_SCAN_TIMEOUT_SECONDS` | `30` | Scanner timeout |
| `AI_IMPORT_SCAN_FAIL_OPEN` | `false` | Accept uploads when the scanner is unreachable. Off, because an unreachable scanner is not evidence a file is clean |

Existing variables reused: `ANTHROPIC_API_KEY` (required for AI extraction),
`SUPABASE_*` (private storage), `EVIDENCE_SIGNED_URL_EXPIRY_SECONDS`,
`MAX_UPLOAD_SIZE_MB`, `CRON_SECRET`, `OCR_PROVIDER`, `GOOGLE_*`.

**No API key is hardcoded anywhere.** With no `ANTHROPIC_API_KEY` the module
still ingests, stores, tracks and deterministically parses documents — every
one lands in human review.

---

## 7. Operating cost

Cost is **measured, not estimated**: each extraction records its input and
output tokens and computes a USD cost from the model's published rate, stored
on `ai_import_extractions.cost_usd` and totalled on the dashboard.

At `claude-opus-5-5` rates ($4 / $20 per million tokens), a single-page
document observed in the test harness uses ~1,200 input and ~300 output
tokens, which is about **$0.011 per document**. Real scans will use more input
tokens than the stub; a multi-page PDF scales roughly with page count. Setting
`AI_IMPORT_MODEL=claude-haiku-5-5` ($0.10 / $0.50) reduces this by roughly 40×
at some cost in reading accuracy on poor scans — that trade-off should be
measured on real documents before being chosen.

---

## 8. Security controls

- Existing JWT authentication; role checks on every endpoint.
- `check_project_access` on every project-scoped read and write. A document
  with no resolved project is visible only to its uploader and office roles.
- A manual match that would cross a project boundary is rejected.
- A cross-project reference inside a document is a BLOCKED condition.
- Files stored with `private=True`, which inherits the existing hardening:
  with Supabase configured the bytes go to the private bucket and
  `stored_path` is an internal `supabase://` reference that is not fetchable;
  **without** Supabase, `storage.save_upload` raises rather than writing
  evidence to local disk outside development/test. The `/uploads` static mount
  is skipped whenever `APP_ENV` is not a dev-like value. So in production a
  supplier document cannot exist anywhere a URL could reach it directly.
- The only route to the file is `GET /ai-import/documents/{id}/file`, which
  re-runs the project access check, logs the access with the file checksum,
  and returns a signed URL expiring after
  `EVIDENCE_SIGNED_URL_EXPIRY_SECONDS` (default 300s).
- Upload validation: MIME allowlist, executable-extension blocklist, size cap.
- Uploaded content is treated as untrusted data: delimited in the prompt, the
  system prompt states content cannot issue instructions, unknown field names
  are discarded, and extracted values are scanned for instruction-like text.
  A hit is BLOCKED — it cannot be posted by any role.
- **Supplier bank details are extracted for display only and are never written
  to the `suppliers` table.**
- Audit trail: upload (with checksum), access, every correction (before/after),
  context assignment, match decisions, legacy authorisation, rejection, every
  posting, and every override post.
- BLOCKED cannot be overridden by any role or flag.

---

## 8b. Independent verification

An independent verifier reviewed the module adversarially and **returned
FAIL**, finding nine defects — two proven by executed tests, not merely by
reading. All nine are fixed, and each now has a regression test in
`tests/test_ai_import_safety.py` that was confirmed to fail against the
original code.

| # | Defect | Severity | Fix |
|---|---|---|---|
| 1 | `_abandon` released the idempotency claim on **any** exception. Because every domain service commits internally before returning, a failure in the post-commit window freed the claim and a retry created a **second stock movement** (proven: 2 ledger rows, 200 bags for one 100-bag note). | Critical | The claim is released only for `_PRE_WRITE_ERRORS` — the exception types the services raise from their validation guards before writing. Any other failure leaves the claim standing, blocking retries and surfacing in `incomplete_postings()`. |
| 2 | After a reversal, `_claim` minted a fresh random key, so two concurrent posts could both insert — the UNIQUE index was bypassed. | High | The key is now derived solely from (document, entity_type) and never varied. A claim is freed only by deleting its row, so the key is reusable without ever being duplicated. |
| 3 | `add_manual_match` validated neither `target_type` nor project access. A site manager could POST `target_type: "project"` and **relocate a document into a project they had no access to** (proven). | Critical | `target_type` is whitelisted to the four linkable record types; project/site/supplier are rejected (they belong to `PATCH /context`, which has its own check). The endpoint calls `check_project_access` on the target's project, and a document with no project cannot be linked at all. |
| 4 | `GET /dashboard` applied only caller-supplied filters. Omitting `project_id` returned **company-wide counts and the total ZAR awaiting authorisation** to any viewer, including READ_ONLY (proven). | High | `dashboard()` takes the viewer and scopes to `visible_project_ids`, the same helper `_visible_documents` uses, so the two cannot drift apart. |
| 5 | `_record_failure` committed without rolling back, persisting a half-processed document — in particular one whose proposed matches `rematch_document` had already deleted. | High | The attempt is always rolled back first, returning the document to its state when the job was claimed. |
| 6 | The `CROSS_TENANT_REFERENCE` policy rule was dead code — nothing ever set `cross_project`. The same was true of `supplier_conflict`: both were built as low-scored candidates, which `_choose` discards before anything is persisted. | Medium | `find_reference_conflicts` detects both and `rematch_document` persists them as REJECTED matches carrying the evidence; the policy reads them without filtering on status. Both rules now fire and block. |
| 7 | `_auto_post` posted under the uploader's identity with no role check, so with auto-post enabled a site manager could become the recorded author of a liability. | Medium (latent) | The uploader must hold a role in `AUTO_POST_ROLES`, mirroring `OFFICE_ADMIN_AND_ABOVE` on the manual endpoint; otherwise the document goes to review. |
| 8 | `legacy_authorisation_note` was documented as required, sent by the frontend, and never read. A legacy document could be posted with `confirm_override` alone and no note recorded. | Medium | Posting an unauthorised legacy document requires the note, which is recorded through `authorise_legacy` and appears in the audit trail and on the created record. |
| 9 | Minor: `locked_by` was cleared before being interpolated into the reclaim message (every message read "Worker unknown"); the `FAILED` job state was unreachable; `list_batches` over-fetched then post-filtered, returning short pages; `lines_sum_to_subtotal` summed the document's **stated** line totals rather than recomputed ones. | Low | All four fixed; the subtotal check now sums our own computed figures with a tolerance that scales per line. |

The verifier also **confirmed** these properties hold, with evidence: stock
safety (only delivery notes and GRNs move stock; an invoice is refused),
BLOCKED being absolute through `/post` even for an OWNER with
`confirm_override`, no hardcoded secrets, no SQL injection, supplier bank
details never written to `suppliers`, migration `0076` being additive and
reversible, and extraction never inventing a missing value.

A by-product of the review: `tests/conftest.py` bound its session without
`join_transaction_mode="create_savepoint"`, so a `db.rollback()` in
application code discarded work that `db.commit()` had already committed —
unlike production. That hid defect 5 and made correct code look broken. The
fixture now matches production semantics, which benefits the whole suite.

---

## 8c. Phase 2 — real-world validation and hardening (2026-10-13)

A second work session re-verified the engine, validated the provider
integration as far as is possible offline, completed the operator interface
and hardened storage. A second independent review returned **FAIL with nine
further defects**; all are fixed and regression-tested.

### Defects found by the second review

| # | Defect | Severity | Fix |
|---|---|---|---|
| 1 | `rematch_document` cleared only PROPOSED/AMBIGUOUS matches. Exact-reference hits are written CONFIRMED with `decided_by` NULL, so they survived every recomputation. Correcting a misread invoice number left `DUPLICATE_INVOICE_NUMBER` in place **permanently** (BLOCKED, unoverridable); correcting a purchase order reference left two confirmed orders, and `best_match` could return the superseded one — booking the goods receipt against the wrong order and corrupting its outstanding quantities. | **High** | The cleanup rule is now ownership, not status: everything with `decided_by IS NULL` is recomputed. Human decisions still survive. |
| 2 | An interrupted posting (claim taken, process died) blocked every retry by design, but had **no resolution path**. The document was permanently stuck and `reversed_at` was dead schema — nothing ever wrote it. | **High** | A resolution workflow: `GET /ai-import/postings/incomplete` lists them with what to check, and `POST /ai-import/postings/{id}/resolve` either **links** the record that was created or **discards** the claim so the document can be posted properly. Both require a note and are audited. |
| 3 | Claim release trusted the *exception type* as a proxy for "nothing was written". `delivery_service.create_delivery` re-queried with a raising helper **after** committing the stock ledger, so a `NotFoundError` there would have released the claim and let a retry double the stock. | **Medium-High** | Two changes. `create_delivery` no longer raises after committing. More importantly, releasing a claim now requires **evidence**: the row count is sampled before the domain call and re-checked after a failure, and the release is refused if a record appeared — regardless of what was raised. Proven load-bearing by disabling the guard and observing the stock double. |
| 4 | `POST /matches/decide` had no access check. Accepting a proposed `project` match moved the document into that project, bypassing the check `PATCH /context` enforces, and returned that project's related-document metadata. | **Medium** | Accepting a `project` or `site` match now runs `check_project_access` on the target. Rejecting is still unrestricted — it moves nothing. |
| 5 | `related_documents` applied its project filter only when the document had a project, so an unclassified upload listed every project's files for that supplier. | **Medium** | With no project resolved, the comparison is confined to the uploader's own unclassified documents. |
| 6 | No rule warned that importing historical paperwork which moves stock may double-count goods already in an opening balance, and the ledger movement is dated today rather than the original delivery date. | **Medium** | A `LEGACY_STOCK_DOUBLE_COUNT_RISK` review reason states both plainly. (The movement date itself is `delivery_service` behaviour shared with manual deliveries and was not changed — see Known limitations.) |
| 7 | `reject_document` lacked the terminal-state guard every other mutating path has. | **Medium** | Re-rejecting is refused. Verified separately that the duplicate-file anchor cannot be cleared for a **posted** document, because a posted document can never be rejected. |
| 8 | `document.site_id` was passed straight to `invoice_service` and `po_service`, neither of which checks the site belongs to the project. A site stranded by a later project change would be written onto another project's invoice. | **Low-Medium** | `_safe_site_id` drops a site that does not belong to the posting project, and logs it. |
| 9 | A genuine concurrent post reported "a previous attempt did not finish", sending the operator to hunt for a phantom problem. | **Low** | A claim younger than five minutes reads as a post in flight; an older one points at the incomplete-postings list. |

### Defects found while building the end-to-end workflow

| Defect | Fix |
|---|---|
| An imported historical purchase order receives a freshly generated `po_number`, so later delivery notes and invoices quoting the **paper** number matched nothing and fell to manual linking. | The posting records `source_document_number`, and `match_purchase_order` resolves a paper reference through it. This is the link between a scanned order and the record it created. |
| The PO comparison was computed for every matched document but only **invoices** read it, so a delivery note containing goods that were never ordered passed with no comment at all. | `_receipt_rules` now reads the same comparison and raises `ITEM_NOT_ORDERED`, `QUANTITY_DISCREPANCY` and `UNIT_NOT_COMPARABLE`. |

### Provider integration defects found offline

| Defect | Fix |
|---|---|
| `AI_IMPORT_MAX_UPLOAD_MB` was 25. Base64 inflates a file by 4/3 and the provider caps a request at 32 MB, so a 25 MB upload encoded to ~33 MB — accepted at upload, then failing at the provider every time. | Cap lowered to 20 MB, and `_extract_vision` refuses anything over the encoded limit locally with a clear message. A test asserts the cap can never exceed the API limit again. |
| `stop_reason == "max_tokens"` was not checked, so a truncated response was parsed as JSON, failed, and was reported as a generic extraction failure. Thinking shares the output budget on current models, making this reachable on long documents. | Reported as what it is, naming the budget. `AI_IMPORT_MAX_OUTPUT_TOKENS` makes it adjustable. |
| No PDF page-count guard; the provider caps at 600 pages (100 on 200k-context models). | Checked locally before sending. An unreadable page count does not block the document. |
| `requirements.txt` pinned `anthropic>=0.40.0`, but the code calls `messages.create(output_config=...)`, which older releases reject. A fresh install could resolve to an SDK that raises `TypeError` on every extraction. | Pinned to `>=0.109.1`, the version verified against this code, with a test asserting the installed SDK accepts every parameter sent. |

---

## 9. Tests executed and their actual results

All runs below are from session 2 (2026-10-13), against a real PostgreSQL
16.9 cluster. Docker Desktop could not be started (no rights to start
`com.docker.service`), so a private throwaway cluster was initialised from
the native PostgreSQL install on port 55433; the machine's existing clusters
and services were untouched. The session-1 baseline of 181 tests reproduced
exactly on it, which also confirms the suite depends on no leftover state.

### AI Document Import suite

```
cd hmh-backend
TEST_DATABASE_URL=postgresql://hmh:hmhdev@127.0.0.1:55433/hmh_test APP_ENV=test   python -m pytest tests/test_ai_import_*.py -q
```

**Result: 259 passed, 0 failed.**

| File | Tests | Covers |
|---|---|---|
| `test_ai_import_extraction.py` | 32 | normalisation, SA number/date formats, arithmetic verification, injection detection, provider failure, no-provider degradation, keyword classifier, cost |
| `test_ai_import_matching.py` | 35 | supplier/project/site resolution, ambiguity, PO matching, duplicates, unit conversion, catalogue matching, three-way comparison |
| `test_ai_import_pipeline.py` | 52 | full pipeline, policy outcomes, corrections, worker retry/backoff/reclaim, out-of-order linking, duplicate detection, dashboard, API access control, retention |
| `test_ai_import_posting.py` | 28 | MR/PO/GRN/invoice via the real domain services, stock ledger assertions, idempotency, crash safety, refusals, audit, attachment |
| `test_ai_import_provider_contract.py` | 25 | SDK surface, content-block shapes, request size and page limits, output schema, truncation and refusal handling, credentials |
| `test_ai_import_safety.py` | 19 | the nine round-1 defects |
| `test_ai_import_safety_round2.py` | 22 | the nine round-2 defects |
| `test_ai_import_scenarios.py` | 15 | multi-page with page provenance, several invoices per order, consolidated invoice, PO before MR, historical stock, cron auth, company filtering |
| `test_ai_import_storage_security.py` | 24 | content verification, malware scanning, storage path scoping, signed URLs, retention |
| `test_ai_import_workflow_e2e.py` | 7 | the four-document transaction end to end, run twice for idempotency, missing and conflicting documents |

### Full backend suite

```
TEST_DATABASE_URL=... APP_ENV=test python -m pytest tests/ -q
```

**Result: 1296 passed, 3 failed in 24m 47s.**

The three failures are **pre-existing and unrelated**, verified twice by
stashing all of this work (including the `delivery_service.py` change) and
re-running them — they fail identically on a clean tree:

- `test_document_ai_service.py::TestDeliveryItemOptionalUnit::test_multiple_items_mixed_units`
- `test_gmail_processing.py::TestMRMatching::test_no_mr_reference_returns_no_reference`
- `test_whatsapp.py::TestCronEndpoint::test_correct_secret_processes_queue`

They are recorded in `KNOWN_BUGS.md`.

### Migration

Clean database → `alembic upgrade head` (reaches `0076`, 7 tables) →
`downgrade 0075` (0 tables, 0 enum types) → `upgrade head` (7 tables again).
Both unique guards present: `uq_ai_import_postings_idempotency_key` and the
partial `uq_ai_import_jobs_active`.

### Frontend

- `npx tsc --noEmit -p tsconfig.app.json` — **0 errors in the new files**
  (the repository has 119 pre-existing errors in unrelated files, unchanged)
- `npx vite build` — **succeeded**
- `npx playwright test` — **32 passed**

### Offline provider validation

`scripts/generate_ai_import_samples.py` produced four real PDFs, which were
then run through the actual (unstubbed) local path: `pypdf` text extraction,
page counting and the fallback keyword classifier correctly identified all
four document types.

### What these tests still do NOT prove

- **No test calls a real AI provider.** `_call_model` is stubbed everywhere.
  The request contract is now verified in detail — the installed SDK accepts
  every parameter sent, the blocks are the documented shapes, the request
  cannot exceed the size or page limits, the schema is closed and matches the
  allowed field set, truncation and refusal are reported as themselves. None
  of that establishes that the model reads real documents correctly.
- No real HMH supplier document has been processed.
- No live Supabase bucket was contacted; storage is stubbed.
- Concurrency is verified through the database guards (`FOR UPDATE SKIP
  LOCKED`, the two unique indexes) and, in the second review, two real
  concurrent psycopg2 connections racing on `_claim` and on the job queue.
  Sustained multi-process load has not been run.

## 10. Manual testing instructions

Prerequisites: a database at `0076`, and `ANTHROPIC_API_KEY` set.

1. **Smoke the provider.** Set the key, start the backend, and confirm the
   startup log shows `ai_import_worker=started`.
2. **Upload one clean typed invoice.** Navigate to **AI Document Import →
   Upload**, drop a PDF, submit. The document should appear QUEUED, then move
   to AWAITING_REVIEW or READY_TO_POST within ~30 seconds.
3. **Open it.** Check the original renders beside the extracted fields, that
   the supplier and total were read correctly, and that the confidence markers
   are sensible. *This is the step that validates the live model — if the
   fields are wrong or empty, the prompt needs tuning before go-live.*
4. **Check the arithmetic panel** against the printed totals.
5. **Correct a field** and confirm the correction appears in the history and
   the arithmetic recomputes.
6. **Upload the same file again under a different name.** It must come back
   as DUPLICATE and must not be read again.
7. **Out of order:** upload an invoice quoting a PO number that does not exist,
   confirm it reports "no purchase order"; create that PO; press *Read again*
   and confirm it now links.
8. **Delivery note:** upload one, assign the site, post it, then check the
   project warehouse stock increased by the delivered quantity and the PO's
   received quantity went up. Post it again — it must be refused.
9. **Blocked path:** upload an invoice whose totals do not add up. Confirm it
   is BLOCKED and that pressing post is refused even as OWNER.
10. **Historical batch:** tick "these are historical documents", upload, and
    confirm the document asks for authorisation. Try to post it without
    authorising — it must be refused for want of an authorisation note. Then
    authorise it with a note saying where the signed original is kept, post,
    and confirm the created record's notes say LEGACY IMPORT and name who
    authorised the import.
11. **Permissions:** sign in as a SITE_MANAGER with access to one project only
    and confirm another project's documents are neither listed nor openable,
    and that the Reconciliation tab with no project filter shows only their
    own project's figures.
12. **Cross-project reference:** upload an invoice quoting a purchase order
    number that belongs to a different project. It must be BLOCKED with
    "belongs to a different project", and posting must be refused even as
    OWNER with override. Correct the reference and confirm the block clears.

---

## 11. Deployment

1. Deploy the backend. `render.yaml` already runs `alembic upgrade head` in the
   start command, so `0076` applies on release.
2. Set `ANTHROPIC_API_KEY` in the environment. Without it the module runs in
   degraded mode (deterministic parser only, everything to review).
3. Optionally tune `AI_IMPORT_MODEL`. Leave `AI_IMPORT_AUTO_POST_ENABLED=false`
   until extraction accuracy has been measured on real documents.
4. Confirm `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` are set so documents go to
   private object storage rather than ephemeral local disk.
5. Optionally add a cron safety net alongside the existing one:

```yaml
  - name: ai-import-queue-drain
    schedule: "*/5 * * * *"
    command: >
      curl -s -f -X POST
      https://hmh-backend-uhzu.onrender.com/api/v1/internal/process-ai-import
      -H "X-Cron-Secret: $CRON_SECRET"
    envVars:
      - key: CRON_SECRET
        sync: false

  # Retention. Defaults to a DRY RUN — it reports what it would remove and
  # removes nothing. Leave it that way for a month, read the logs, then add
  # ?apply=true once the window is agreed.
  - name: ai-import-retention
    schedule: "30 2 * * 0"
    command: >
      curl -s -f -X POST
      https://hmh-backend-uhzu.onrender.com/api/v1/internal/ai-import-retention
      -H "X-Cron-Secret: $CRON_SECRET"
    envVars:
      - key: CRON_SECRET
        sync: false
```

6. Deploy the frontend. The nav entry appears automatically.
7. After release, check `GET /api/v1/ai-import/health` as an office admin:
   queue depth, worker state, and any postings left unverified by a crash.
8. Make one administrator responsible for `GET /ai-import/postings/incomplete`.
   It should normally be empty; an entry means a posting was interrupted and
   somebody must check the destination module before it can be resolved.

---

## 12. Rollback

The module is additive and self-contained.

- **Disable without deploying:** set `AI_IMPORT_ENABLED=false`. Uploads are
  refused and the worker stops. Nothing already posted is affected — those are
  ordinary material requests, purchase orders, deliveries and invoices owned by
  their own modules.
- **Roll back the code:** redeploy the previous build. The `0076` tables simply
  go unused; no existing code reads them.
- **Roll back the schema:** `alembic downgrade 0075` drops the 7 tables and 6
  enum types. **This destroys the import audit trail** (which documents were
  uploaded, by whom, what was corrected). The business records created from
  them survive untouched, as do their attachments and `audit_events` rows.
  Prefer disabling over downgrading.
- **Reverse a posted record:** use the owning module. The engine never deletes
  or edits a posted record; `ai_import_postings.reversed_at` records a
  reversal for traceability.

---

## 13. Known limitations

1. Live AI extraction accuracy is unverified (§2, §9).
2. Credit notes and payment proofs are evidence only (§2).
3. Direct-to-lot receipt is refused by design (§2).
4. No malware *scanner*; content verification does run (see item 11).
5. Text-mode extraction truncates at 60,000 characters and says so in the
   document's warnings.
6. OCR and regex fallback strategies require the file to be on local disk; with
   Supabase storage the file is downloaded for vision extraction, and if vision
   is unavailable the document goes to manual capture rather than silently
   degrading.
7. The keyword classifier used when no AI provider is configured recognises
   clear headings only and returns UNKNOWN rather than guessing.
8. A posting interrupted mid-flight leaves a claim with no entity id. It can
   never cause a duplicate — retries are refused — and it is now resolvable:
   `GET /ai-import/postings/incomplete` lists them with what to check, and
   `POST /ai-import/postings/{id}/resolve` either links the record that was
   created or discards the claim. Both require a note and are audited.
9. The project is the isolation boundary; there is no separate tenant concept
   in this system (noted in the Phase 0 audit).
10. **Stock movements from imported deliveries are dated today**, not the
    original delivery date. `delivery_service` sets `movement_date = now` for
    every delivery, manual or imported; changing it would alter behaviour
    shared with the manual screens and existing reports, so it was left
    alone. A `LEGACY_STOCK_DOUBLE_COUNT_RISK` review reason warns about this
    and about goods possibly already sitting in an opening balance. If HMH
    needs historical movements dated correctly, that is a deliberate change
    to `delivery_service` with its own regression pass.
11. **Malware scanning is an integration point, not an implementation.**
    Content-type verification against the file's own magic bytes runs
    unconditionally and rejects renamed executables, archives and scripts.
    An actual virus scanner has to be procured and pointed at via
    `AI_IMPORT_SCAN_URL`.
12. **Supabase storage paths are exercised with the storage layer stubbed.**
    No live bucket was contacted in either session — there are no
    credentials here. Runbook §6 is the procedure for validating them.
13. `tests/conftest.py` was changed to bind its session with
    `join_transaction_mode="create_savepoint"`. This makes the harness match
    production (a commit survives a later rollback) and the full suite passes
    with it, but it does change the transactional behaviour every existing
    test runs under — worth knowing if an unrelated test starts behaving
    differently.

---

## 14. Outstanding work

| Priority | Item |
|---|---|
| **Blocker** | Run `docs/AI_DOCUMENT_IMPORT_LIVE_VALIDATION.md` with a real `ANTHROPIC_API_KEY`. Until section 4 passes, extraction accuracy is unknown and the engine must not be called validated. |
| **Blocker** | Measure accuracy on ~20 real historical documents from one supplier (runbook §5) before any pilot. `AI_IMPORT_AUTO_POST_ENABLED` stays `false` until then. |
| **High** | Validate the Supabase paths against a live private bucket (runbook §6). No credentials were available, so signed access and deletion are tested with the storage layer stubbed. |
| **High** | Procure a malware scanner and point `AI_IMPORT_SCAN_URL` at it. Content verification runs today; an actual scanner does not exist. |
| Medium | Decide `AI_IMPORT_MODEL` on measured accuracy, not price. |
| Medium | Schedule the retention purge in `render.yaml`. Leave it in dry-run for a month and read what it reports first. |
| Medium | Build a credit-note record so supplier credits can be applied properly. Still deliberately undesigned. |
| Medium | Decide whether imported historical stock movements should carry the original delivery date (Known limitations, item 10). That is a change to `delivery_service` shared with the manual screens. |
| Low | A two-process soak test of the worker, and of `_claim` under real parallel HTTP load. The database-level guards are verified; sustained concurrency is not. |
| Low | Throughput: a 200-document historical batch has never been run. |

---

## 15. Pilot

`docs/AI_DOCUMENT_IMPORT_PILOT.md` is the step-by-step plan for putting this
in front of HMH staff: clear the two blockers, measure accuracy on closed
historical paperwork, rehearse with one administrator, then one supplier and
two staff running as a shadow process for two weeks in TEST.

Do not start the pilot before the accuracy figure exists. Staff should not be
the ones who discover the error rate.
