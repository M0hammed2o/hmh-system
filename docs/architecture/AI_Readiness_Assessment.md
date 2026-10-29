# AI Readiness Assessment

**Date:** 2026-07-16  
**Author:** Architecture Audit — Level 4  
**Classification:** L0 — Documentation only.  
**Evidence basis:** Direct repository inspection of all AI integration files, model files, analytics service files, and route handlers.

---

## Assessment Framework

AI readiness is measured across five dimensions for each module:

| Dimension | Question |
|-----------|---------|
| **Data Quality** | Is the data structured, typed, and complete enough to train or prompt AI reliably? |
| **Data Volume** | Is there enough historical data (or will there be) for pattern detection? |
| **API Surface** | Are there clear endpoints where AI could enhance input, output, or processing? |
| **Human-in-Loop** | Is there a natural confirmation step where AI output becomes canonical? |
| **Current AI** | Is AI already used here today? |

**Score:** 0–10 per module (10 = immediately AI-ready with high business value)

---

## Section 1 — Current AI Integrations

### AI-CURR-01 — Document OCR and Field Extraction (Claude Haiku)

**Location:** `app/services/ai_ocr_service.py`  
**Model:** `claude-haiku-4-5-20251001`, max_tokens=1024  
**Trigger:** Manual — `POST /gmail/incoming/{id}/process`

**What it does:**
1. Receives raw text extracted from a document (via Google Cloud Vision or pytesseract)
2. Sends to Claude Haiku with a structured prompt requesting JSON extraction of 8 fields:
   - `supplier_name`, `invoice_number`, `invoice_date`, `po_number`, `vat_number`, `net_amount`, `vat_amount`, `gross_amount`
3. Returns per-field confidence scores (0.0–1.0) and overall confidence
4. Merges AI results with regex-extracted results: AI wins if field confidence ≥ 0.50

**Data stored:**
- `DocumentExtraction.raw_text` — raw OCR text
- `DocumentExtraction.extracted_json` — regex extraction result
- `DocumentExtraction.ai_extraction_json` — Claude Haiku result
- `DocumentExtraction.confidence_score` — overall confidence (0.0–1.0)
- `DocumentExtraction.manually_corrected_json` — human-confirmed values (canonical)

**Status:** Production-ready. The pipeline is functional and the data model correctly separates AI suggestion from human confirmation.

**Improvement opportunities:**
- Line item extraction is not implemented — only header fields
- `po_number` extracted from invoice is not used to auto-link the invoice to a PurchaseOrder record
- High-confidence extractions still require manual confirmation; could auto-confirm above 0.90

---

### AI-CURR-02 — Supplier Fuzzy Matching

**Location:** `app/services/document_ai_service.py`  
**Method:** `difflib.SequenceMatcher`, threshold=0.60

**What it does:** After OCR extracts a supplier name from a document, fuzzy-matches it against the `suppliers` table to auto-link the document to an existing supplier record.

**Assessment:** This is algorithmic matching, not AI. It works well for clean text but fails on abbreviated supplier names (e.g., "HMH" vs "HMH Construction Group"). Replacing or augmenting with embedding-based similarity (e.g., sentence-transformers or Claude embedding API) would substantially improve match rates.

---

### AI-CURR-03 — Document Classification

**Location:** `app/services/gmail_ocr_pipeline_service.py`

**What it does:** Classifies incoming email attachments as QUOTE, INVOICE, DELIVERY_NOTE, PO, FUEL_SLIP, or PAYMENT_PROOF using filename patterns first, then content keywords post-OCR.

**Assessment:** Rule-based classification. No AI model involved. Misclassifications require manual correction. The `DocumentExtraction.manually_corrected_json` field already captures corrections, which is the labelled data needed to train a classifier.

---

### AI-CURR-04 — Procurement Analytics

**Location:** `app/services/procurement_analytics_service.py`

**What it does:** Computes supplier performance scores from: on_time_delivery_rate, invoice_accuracy_rate, quote_win_rate, average_delivery_time. These are SQL aggregations, not AI inference.

**Assessment:** The `suppliers.performance_score` column exists but is never written. The analytics endpoint computes the score on every request without persisting it. This is the highest-value analytical output that AI could enhance: a learned supplier risk score that incorporates more signals than rule-based aggregates.

---

## Section 2 — Per-Module AI Readiness Score

### Procurement Pipeline (MR → Quote → PO → Delivery → Stock → Invoice → Payment)

**Score: 7/10**

| Dimension | Score | Evidence |
|-----------|-------|---------|
| Data Quality | 8/10 | MaterialRequestItem has description, quantity, unit, rate. PO line items have full pricing. Payment ledger is complete. |
| Data Volume | 6/10 | System is new; historical data grows with usage. PriceHistory endpoint provides item price trends. |
| API Surface | 8/10 | Every step has a distinct API endpoint. AI can assist at: MR auto-fill, quote comparison ranking, invoice field extraction, payment anomaly detection. |
| Human-in-Loop | 9/10 | Every stage has an explicit approval/confirmation action that can act as the human-confirms-AI-suggestion step. |
| Current AI | 5/10 | Invoice extraction is AI-powered. Everything else is manual. |

**High-value AI opportunities:**
- **MR auto-complete:** When a site staff member starts typing a material description, suggest items from historical MRs for the same stage/lot type
- **Quote ranking:** When multiple supplier quotes arrive, AI ranks them by price × delivery time × supplier score (rather than manual comparison)
- **Invoice matching:** AI suggests which delivery note and PO match an extracted invoice (currently a manual `PATCH /invoices/{id}/match`)
- **Price anomaly:** When a quote price is >20% above the price history for that item, flag automatically

---

### Workshop Module

**Score: 3/10**

| Dimension | Score | Evidence |
|-----------|-------|---------|
| Data Quality | 4/10 | Workshop entities have descriptions and amounts but minimal structured metadata |
| Data Volume | 3/10 | Workshop module is new; limited historical data |
| API Surface | 5/10 | Has MR, Quote, PO, Invoice endpoints |
| Human-in-Loop | 5/10 | Vote-based approvals could act as confirmation steps |
| Current AI | 0/10 | No AI integration in Workshop module |

**Blocker:** Workshop module has no `project_id` foreign key, so AI cannot relate Workshop spend to project context for cost forecasting.

---

### Document AI / Gmail Pipeline

**Score: 9/10**

| Dimension | Score | Evidence |
|-----------|-------|---------|
| Data Quality | 9/10 | `DocumentExtraction` stores raw_text, extracted_json, ai_extraction_json, manually_corrected_json, confidence_score — ideal training data structure |
| Data Volume | 7/10 | Every processed email adds labelled data. Manual corrections are stored separately from AI output. |
| API Surface | 9/10 | Processing pipeline is explicit and replaceable |
| Human-in-Loop | 10/10 | Every document goes through a human confirmation step before becoming canonical |
| Current AI | 8/10 | Claude Haiku extraction is live |

**High-value AI opportunities:**
- **Auto-classify corrections:** Use `manually_corrected_json` vs `ai_extraction_json` disagreements as training signal for future model fine-tuning
- **Zero-touch invoices:** When `confidence_score >= 0.92` AND supplier is known AND PO number matches, auto-confirm the invoice without human review — creating it as DRAFT for audit but not requiring a click
- **Anomaly detection:** Flag invoices where AI-extracted `gross_amount` differs from PO `total_price` by more than 5%

---

### Notifications / WhatsApp

**Score: 6/10**

| Dimension | Score | Evidence |
|-----------|-------|---------|
| Data Quality | 7/10 | `NotificationQueue` stores sent_at, delivered_at, read_at, acknowledged_at — full engagement lifecycle |
| Data Volume | 7/10 | Notification history accumulates continuously |
| API Surface | 6/10 | WhatsApp webhook parses APPROVE/REJECT/ACK/LIST/RESET intents |
| Human-in-Loop | 8/10 | WhatsApp responses already create structured intent objects |
| Current AI | 3/10 | Intent parsing is keyword-based, not AI-powered |

**High-value AI opportunities:**
- **Natural language approvals:** "Approve that MR" in WhatsApp should work even if the user doesn't type "APPROVE" exactly
- **Conversational queries:** "What's the status of the site delivery from yesterday?" answered from the database via AI agent
- **Escalation prediction:** Based on notification open rates and time-to-acknowledge patterns, predict which alerts are being ignored and escalate before the deadline

---

### Stage / Milestone Tracking

**Score: 5/10**

| Dimension | Score | Evidence |
|-----------|-------|---------|
| Data Quality | 8/10 | `ProjectStageStatus` has: status, progress_pct, planned_completion_date, completed_at, blocked_at, blocked_reason — rich structured data |
| Data Volume | 5/10 | Data grows with projects but each project has only ~15 stages |
| API Surface | 6/10 | Stage status updates are single-endpoint |
| Human-in-Loop | 7/10 | Stage updates require explicit site staff action |
| Current AI | 0/10 | No AI in milestone module |

**High-value AI opportunities:**
- **Delay prediction:** Given current progress_pct, planned_completion_date, and historical completion rates for similar stages, predict whether a stage will be late — before it is
- **Blocked reason classification:** Auto-categorise `blocked_reason` text into WEATHER, MATERIAL_DELAY, LABOUR, REGULATORY categories for reporting
- **Critical path analysis:** Given all stage completion dates and dependencies, identify which currently-blocked stages affect the project completion date most

---

### BOQ and Cost Management

**Score: 6/10**

| Dimension | Score | Evidence |
|-----------|-------|---------|
| Data Quality | 8/10 | BOQ items are fully typed with rate, quantity, section, type (LABOUR/MATERIAL/PLANT) |
| Data Volume | 5/10 | BOQ is populated per project; comparable projects are needed for benchmarking |
| API Surface | 7/10 | Budget vs actual comparison is available via cost-summary endpoint |
| Human-in-Loop | 8/10 | BOQ adjustments are explicitly approved |
| Current AI | 0/10 | No AI in BOQ |

**High-value AI opportunities:**
- **BOQ auto-generation from project description:** "Site A — 5-unit residential, 450m²" → suggested BOQ with quantities and rates from similar historical projects
- **Cost to completion forecast:** Given current spend rate and remaining BOQ, predict final project cost vs budget
- **Overrun early warning:** When procurement spend for a BOQ category reaches 70% of budget and the stage is only 40% complete, alert automatically

---

### Vehicles and Fuel

**Score: 5/10**

| Dimension | Score | Evidence |
|-----------|-------|---------|
| Data Quality | 7/10 | `FuelLog` has odometer_reading, litres, total_cost, vehicle_id, date |
| Data Volume | 7/10 | Fuel logs accumulate continuously with vehicle usage |
| API Surface | 6/10 | Fuel and vehicle cost endpoints exist |
| Human-in-Loop | 7/10 | Fuel logs are manually recorded |
| Current AI | 0/10 | No AI in vehicle module |

**High-value AI opportunities:**
- **Fuel anomaly detection:** When litres per km recorded deviates by >20% from the vehicle's 30-day average, trigger a FUEL_ANOMALY alert automatically
- **Maintenance prediction:** Based on odometer progression rate and last service date, predict when next service is due
- **Vehicle assignment optimisation:** Given active sites and vehicle locations, suggest which vehicle should be assigned to new site

---

### Analytics and Reporting

**Score: 7/10**

| Dimension | Score | Evidence |
|-----------|-------|---------|
| Data Quality | 9/10 | Procurement analytics endpoints return typed, aggregated data |
| Data Volume | 7/10 | Analytics are computed from full historical payment, delivery, and quote data |
| API Surface | 8/10 | 6 dedicated analytics endpoints exist |
| Human-in-Loop | 6/10 | Reports are read-only; no human action loop exists yet |
| Current AI | 2/10 | Supplier score is computed but not AI-derived |

**High-value AI opportunities:**
- **Natural language reports:** "Show me all suppliers who delivered late last month and how much we paid them" answered directly from database via AI agent
- **Spend anomaly detection:** Flag when a supplier's invoice amount is statistically unusual compared to their historical range
- **Weekly summary generation:** Automated generation of the weekly project summary narrative from database state (no human typing required)

---

## Section 3 — Data Assets Available for AI

The following structured datasets are already in the database and are suitable for AI model training or inference without any schema changes:

| Dataset | Table | Size grows with | AI application |
|---------|-------|----------------|----------------|
| Item price history | `purchase_order_items` | PO volume | Price trend prediction, anomaly detection |
| Supplier payment history | `payments` | Payment volume | Cash flow forecasting |
| Stage completion times | `project_stage_statuses` | Project count | Delay prediction |
| Fuel consumption per vehicle | `fuel_logs` | Vehicle usage | Anomaly detection |
| Notification engagement | `notification_queue` | User activity | Engagement optimisation |
| Document extraction accuracy | `document_extractions` | Email volume | OCR model fine-tuning |
| Approval cycle times | `mr_approvals`, `warehouse_transfer_votes` | Approval volume | Process bottleneck analysis |
| BOQ vs actual cost | `boq_items` + `cost_summary` | Project completion | Cost forecasting |
| Blocked stage reasons | `project_stage_statuses.blocked_reason` | Site activity | Delay categorisation |

---

## Section 4 — AI Readiness by Capability

| Capability | Readiness | Best Module to Start |
|-----------|-----------|---------------------|
| **Document extraction** | Production | Document AI (already live) |
| **Anomaly detection** | Ready | Invoice amounts, fuel consumption |
| **Natural language query** | 6 months away | Need data volume + API agent layer |
| **Predictive delay** | 12 months away | Need more completed project data |
| **Auto-scheduling** | 24 months away | Requires Timeline module first |
| **Conversational assistant** | 12 months away | WhatsApp intent parsing is the foundation |
| **BOQ generation** | 18 months away | Need project description schema |
| **Supplier risk scoring** | Ready | Procurement analytics data exists |

---

## Section 5 — Architecture Readiness for AI

| Requirement | Current State | Gap |
|-------------|--------------|-----|
| Structured event log | AuditEvent table with before/after JSON | No event bus; events not streamable |
| Labelled training data | DocumentExtraction manual corrections | Limited volume |
| Data API layer | Analytics endpoints exist | No embeddings API, no vector store |
| Human-in-loop UI | Confirmation steps exist in procurement | Not standardised across all modules |
| Model versioning | None | No infrastructure for model deployment |
| Feedback collection | Manual correction stored | Not used for retraining |

**Overall AI Readiness Score: 6/10**

The system has the right data model for AI (structured, typed, with explicit confidence and correction tracking) and one production AI integration (Claude Haiku OCR). The gap is the absence of an event streaming layer, a feedback loop for model improvement, and the data volume that comes with scale. The AI foundation is correct; the AI infrastructure is not yet built.

**Immediate next step:** Persist `suppliers.performance_score` from the existing analytics computation (half-day work, AUT-012 in Automation_Opportunities.md). This is the first AI-adjacent signal that should feed into future recommendation features.
