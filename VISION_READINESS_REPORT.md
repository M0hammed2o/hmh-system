# Vision / Document AI Readiness Report
**Date:** 2026-05-26  
**Component:** `app/services/document_ai_service.py`, `app/api/v1/vision.py`

---

## Current Status: PARTIAL — Ready for staging with local OCR

---

## What Exists

### OCR Providers

| Provider | Status | Notes |
|----------|--------|-------|
| `local` (pytesseract) | **PRODUCTION_READY** | Default. No external credentials needed. |
| `google_vision` | **PRODUCTION_READY** (if credentials set) | Calls real Vision API — not stubbed. |
| `disabled` | **PRODUCTION_READY** | Returns `OCR_NOT_AVAILABLE` status immediately. |

### API Endpoints

| Endpoint | Auth | Status |
|----------|------|--------|
| `POST /vision/extract` | OFFICE_AND_ABOVE | Interactive upload → preview only (no auto-save) |
| `POST /document-ai/extract` | OFFICE_AND_ABOVE | Server-side extraction → saves to `DocumentExtraction` table |
| `POST /document-ai/compare` | OFFICE_AND_ABOVE | PO vs invoice vs delivery note comparison |

### Document Types Processed

| Type | Fields Extracted |
|------|-----------------|
| INVOICE | invoice_number, supplier_name, supplier_email, po_number, date, due_date, total_amount, vat_amount, line_items |
| DELIVERY_NOTE | delivery_note_number, po_number, supplier_name, supplier_email, date |
| QUOTE | po_number, supplier_name, supplier_email, date, total_amount |

### File Formats Supported

PDF (text-extractable + scanned), JPEG, PNG, WebP, BMP, TIFF, GIF, plain text.

PDF text-extraction stack (tried in order): PyMuPDF → pdfplumber → pypdf → PyPDF2 → OCR fallback.

---

## Deployment Readiness by Provider

### Option A: Local OCR (pytesseract)
**Required env vars:** none beyond defaults  
**Required packages:** `pytesseract`, `Pillow` (both in `requirements.txt`)  
**System dependency:** Tesseract binary must be installed on the server  
**Render note:** Tesseract is NOT installed by default on Render. Requires a custom Docker image or build command: `apt-get install -y tesseract-ocr`  
**Readiness:** ⚠️ PARTIAL — works locally, needs Render build config

### Option B: Google Cloud Vision
**Required env vars:**
```
OCR_PROVIDER=google_vision
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```
Or inline JSON:
```
GOOGLE_APPLICATION_CREDENTIALS={"type":"service_account","project_id":"..."}
```
**Required packages:** `google-cloud-vision` (in requirements.txt)  
**Required APIs:** Google Cloud Vision API enabled in the project  
**Graceful degradation:** If credentials are missing/invalid, Vision returns empty text and the system falls back to local OCR automatically  
**Readiness:** ✅ READY — if credentials are provided and Vision API is enabled

### Option C: Disabled
**Required env vars:** `OCR_PROVIDER=disabled`  
**Effect:** All extractions return `{"status": "OCR_NOT_AVAILABLE"}` immediately  
**Readiness:** ✅ READY — use this if OCR is not needed at launch

---

## Pipeline Connection to Business Logic

```
Gmail attachment received
  └─> _trigger_extraction() in gmail_reader_service.py
        └─> extract_document_data() in document_ai_service.py
              └─> stores DocumentExtraction row (source_id = attachment UUID)
                    └─> auto-matches to PO if po_number found in extracted fields
                          └─> logs match (no auto-action — human confirmation required)

Manual upload via /vision/extract
  └─> Returns preview JSON to frontend (NOT saved to DB)
  └─> User reviews extracted fields in UI before confirming

Manual server-side via /document-ai/extract
  └─> Saves DocumentExtraction row
  └─> User can trigger /document-ai/compare to check PO/invoice alignment
        └─> Creates SystemAlert on mismatch
```

---

## What Was Partially Broken (Now Fixed)

- `source_id` was always `None` in `DocumentExtraction` rows created from Gmail attachments. Fixed in this phase: `source_id = uuid.UUID(source_id) if source_id else None`.

---

## Missing Pieces for Full Production

1. **Tesseract on Render** — Required for `local` OCR provider. Add to Render build command:
   ```
   apt-get install -y tesseract-ocr && pip install -r requirements.txt
   ```

2. **No automated Gmail→OCR pipeline scheduling** — Extraction only triggers during manual `/gmail/fetch` call. No background polling. See PRODUCTION_DEPLOY_CHECKLIST.md.

3. **OCR results are not auto-actioned** — The system extracts and suggests, but all matching/approval is manual. This is by design for the current phase.

4. **No retry mechanism for failed extractions** — If OCR fails, the `DocumentExtraction` row is set to `FAILED` with no retry. Manual re-trigger via `/document-ai/extract` is required.

---

## Estimated Work Remaining for Full OCR Production

| Task | Effort | Priority |
|------|--------|---------|
| Configure Tesseract on Render (build command) | 30 min | HIGH |
| Set up Google Cloud Vision service account | 1-2 hours | MEDIUM |
| Add background Gmail polling loop | 2-3 hours | MEDIUM |
| Add OCR retry for failed extractions | 1 hour | LOW |

**Deployment recommendation:** Launch with `OCR_PROVIDER=google_vision` if credentials are ready, otherwise `OCR_PROVIDER=disabled` and enable later. Do NOT rely on `local` OCR on Render without the Tesseract build step.
