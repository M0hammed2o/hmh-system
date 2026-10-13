# AI Document Import — Live Validation Runbook

Everything in the engine that can be checked without calling the provider has
been checked. **The live model has still never been called.** This document is
the exact procedure for closing that gap.

Until section 4 passes, the engine must not be described as validated, and
`AI_IMPORT_AUTO_POST_ENABLED` must stay `false`.

---

## 1. What leaves your network, and what does not

Before anyone uploads a real supplier document, be clear about where it goes.

| Data | Where it goes |
|---|---|
| The document file itself (PDF/image bytes) | Sent to the Anthropic API as a base64 block on every vision extraction |
| OCR text, when vision is unavailable | Sent to the Anthropic API |
| Supplier names, VAT numbers, bank details, prices, project names appearing in the document | Sent, because they are part of the document |
| The document file at rest | Your Supabase private bucket, never a public URL |
| Your database contents (suppliers, projects, prices, balances) | **Never sent.** The prompt contains only the document and fixed instructions. Matching against your records happens locally, after extraction. |

The engine never sends your supplier list, your price history or your
balances to the provider. It sends one document at a time and gets fields back.

Anthropic's data handling for API traffic is governed by your commercial terms
with them. If HMH needs zero-retention or a specific data-residency
arrangement, settle that with Anthropic **before** section 5, not after.

---

## 2. Pre-flight (no API key needed)

These run offline and must pass before spending anything.

```bash
cd hmh-backend

# The request contract: SDK surface, block shapes, size and page limits,
# schema validity, truncation and refusal handling, no hardcoded key.
TEST_DATABASE_URL=<your test db> APP_ENV=test \
  python -m pytest tests/test_ai_import_provider_contract.py -q
```

Expected: **25 passed**. If `test_installed_sdk_accepts_every_parameter_the_code_sends`
fails, the installed `anthropic` package is too old — reinstall from
`requirements.txt` (floor is `0.109.1`).

---

## 3. Generate the sample set (no API key needed)

Never run the first live test on a real supplier invoice. Generate a
fictional one:

```bash
cd hmh-backend
python scripts/generate_ai_import_samples.py sample_documents
```

This writes four PDFs describing one coherent transaction — material request,
purchase order, delivery note, supplier invoice — for a **fictional** supplier
("Umhlanga Building Supplies CC") and a fictional project (`SAMPLE-RP2`).
Nothing in the set is HMH data, so it is safe to send to the provider, attach
to a support ticket, or share with a vendor.

The script prints the expected extraction values. Keep that output: it is the
answer key for section 4.

---

## 4. The controlled live test

**Cost: roughly $0.02–0.10 for the whole section** at `claude-opus-5-5` rates.

1. Set `ANTHROPIC_API_KEY` in the backend environment. Do not commit it.
   Confirm `AI_IMPORT_AUTO_POST_ENABLED=false`.
2. Start the backend. The startup log must show
   `ai_import_worker=started ... auto_post=False`.
3. Open **AI Document Import → Upload**. Leave the project blank. Upload
   `04_supplier_invoice_INV-SAMPLE-50231.pdf` on its own.
4. Watch the Documents tab. Within ~30 seconds the status should move
   `QUEUED → PROCESSING → AWAITING_REVIEW` (it will need review: the sample
   project and supplier do not exist in your database).
5. Open the document. **This is the step that validates the model.** Check
   the extracted values against the answer key:

   | Field | Expected |
   |---|---|
   | document type | Supplier Invoice |
   | document_number | `INV-SAMPLE-50231` |
   | supplier_name | Umhlanga Building Supplies CC |
   | supplier_vat_number | `4350198762` |
   | purchase_order_reference | `PO-SAMPLE-2291` |
   | issue_date | `2026-03-20` |
   | due_date | `2026-04-19` |
   | subtotal_amount | `18951.25` |
   | vat_amount | `2842.69` |
   | total_amount | `21793.94` |
   | line items | 3, with quantities 120 / 8 / 15 |

6. Check the **arithmetic panel** shows all checks passing. If the model
   misread a figure, a check will fail — which is the system working.
7. Check **AI usage** on the Reconciliation tab shows non-zero tokens and a
   cost of roughly $0.01–0.03 for that one document.

### Acceptance

| Outcome | Verdict |
|---|---|
| All header fields correct, 3 line items, arithmetic passes | **Pass.** Proceed to section 5. |
| Header correct, a line item quantity or price wrong | **Marginal.** Usable with review, but tune the prompt before widening the pilot. |
| Supplier or total wrong, or fields empty | **Fail.** Do not pilot. Tune `_SYSTEM_PROMPT` / `_OUTPUT_SCHEMA` in `app/services/ai_import_extraction_service.py` and repeat. Bump `EXTRACTION_SCHEMA_VERSION` / `PROMPT_VERSION` if the field set changes. |
| `AWAITING_REVIEW` with "the model reached its output limit" | Raise `AI_IMPORT_MAX_OUTPUT_TOKENS` and retry. |
| Document `FAILED` with a storage error | Storage, not AI. See section 6. |

### Then repeat with the harder cases

8. Upload the remaining three sample PDFs **in reverse order** (invoice,
   delivery note, purchase order, material request). Confirm each is
   classified correctly and that the later uploads link to the earlier ones.
9. Photograph one of the printed PDFs on a phone, at an angle, in poor light.
   Upload the photo. This is the realistic site case. Expect lower confidence
   — the test is whether it degrades honestly (low confidence, fields marked
   "hard to read") rather than inventing values.
10. Print the invoice, strike out the total by hand, write a different total,
    photograph and upload. The arithmetic check must catch the inconsistency.

---

## 5. Moving to real HMH documents safely

Only after section 4 passes.

1. **Use the TEST environment first.** `docs/TEST_ENVIRONMENT.md` describes a
   fully separate stack with its own Supabase project. Note that TEST has AI
   calls disabled by default — enable `ANTHROPIC_API_KEY` there specifically
   for this exercise, and nowhere else.
2. **Start with closed, historical transactions**, not live ones. A 2024
   invoice that is already paid and reconciled can be imported, checked
   against what the books already say, and rejected afterwards with no
   consequence.
3. **Pick one supplier to begin with**, ideally one whose invoice template is
   typical of your set. Ten documents from one supplier tells you more than
   one document from ten suppliers.
4. **Do not post anything on the first pass.** Upload, review the extraction
   against the paper, and reject. You are measuring reading accuracy, not
   exercising the posting path.
5. **Record the error rate.** For each document note: was the supplier right,
   the invoice number right, the total right, the line count right. Twenty
   documents gives a usable figure. Below ~95% on supplier and total, the
   prompt needs work before anyone relies on it.
6. **Only then** post one document and verify in the destination module that
   the invoice, delivery or order looks exactly as a hand-captured one would.

### If a document must not leave the network at all

Some supplier agreements prohibit sending documents to third parties. For
those:

- Set `AI_IMPORT_ENABLED=false` for the period, or simply do not upload them.
  The rest of the system is unaffected.
- The engine still works without an AI provider: it stores, hashes,
  deduplicates, runs the deterministic parser and routes everything to human
  review. Accuracy is much lower, but nothing leaves the network.
- There is currently **no** per-document "do not send" flag. If HMH needs one,
  it is a small addition to `upload_document` and the policy engine — raise it
  as a requirement rather than relying on process.

---

## 6. Storage validation (separate from AI)

The AI path and the storage path fail differently; validate them separately.

1. Confirm `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are set. Without them,
   `storage.save_upload(private=True)` **refuses** to write outside
   development, so uploads will fail cleanly rather than landing on an
   ephemeral disk.
2. Upload a sample PDF. In the Supabase dashboard confirm the object appears
   in the **private** bucket (`SUPABASE_PRIVATE_BUCKET`), not the public one.
3. In the document drawer, confirm the original renders. The URL in the
   network tab must be a signed URL with an expiry, not a bare bucket path.
4. Copy that signed URL, wait past `EVIDENCE_SIGNED_URL_EXPIRY_SECONDS`
   (default 300s), and open it in a private window. It must now fail.
5. Confirm that opening the document wrote an `ACCESS` row in `audit_events`
   for `ai_import_document_file`.
6. Run the retention purge in dry-run mode and confirm it reports what it
   would remove without removing it:
   `POST /api/v1/ai-import/retention/purge` (owner only, `apply=false`).

---

## 7. What this runbook does not cover

- **Throughput.** No load testing has been done. A 200-document historical
  batch has never been run.
- **Provider outage behaviour in production.** The retry/backoff path is
  unit-tested against a stubbed failure, not against a real outage.
- **Cost at scale.** The per-document figure comes from the test harness and
  one sample document, not from a representative mix of real scans.
- **Multi-page real scans.** The multi-page handling is tested with a
  synthetic three-page fixture, not a real 40-page statement.
