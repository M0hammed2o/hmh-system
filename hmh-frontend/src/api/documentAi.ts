/**
 * Document AI API client — Phase 6A AI OCR extraction.
 *
 * Per-field confidence thresholds (mirrored from ai_ocr_service.py):
 *   ≥ 0.80 → high    (green)
 *   ≥ 0.50 → medium  (amber)
 *   <  0.50 → low     (red)
 */

import client from "./client";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AIFieldResult {
  value: string | number | null;
  confidence: number;  // 0.0 – 1.0
}

export interface AILineItem {
  description: string;
  quantity:    number | null;
  unit_rate:   number | null;
  total:       number | null;
  confidence:  number;
}

export interface AIExtractionHeader {
  supplier_name:  AIFieldResult;
  invoice_number: AIFieldResult;
  invoice_date:   AIFieldResult;
  po_number:      AIFieldResult;
  vat_number:     AIFieldResult;
  net_amount:     AIFieldResult;
  vat_amount:     AIFieldResult;
  gross_amount:   AIFieldResult;
}

export type AIExtractionStatus =
  | "AI_EXTRACTED"
  | "NEEDS_REVIEW"
  | "FAILED";

export interface AIExtractionResult {
  extraction_id:        string;
  attachment_id:        string;
  status:               AIExtractionStatus;
  model:                string;
  overall_confidence:   number;
  low_confidence_fields: string[];
  header:               AIExtractionHeader;
  line_items:           AILineItem[];
  warnings:             string[];
}

// ── Confidence helpers ────────────────────────────────────────────────────────

export const HIGH_CONF  = 0.80;
export const MED_CONF   = 0.50;

export type ConfidenceTier = "high" | "medium" | "low";

export function confidenceTier(c: number): ConfidenceTier {
  if (c >= HIGH_CONF) return "high";
  if (c >= MED_CONF)  return "medium";
  return "low";
}

export const CONF_COLOR: Record<ConfidenceTier, string> = {
  high:   "text-green-700 bg-green-50 border-green-300",
  medium: "text-amber-700 bg-amber-50 border-amber-300",
  low:    "text-red-700 bg-red-50 border-red-300",
};

export const CONF_BADGE: Record<ConfidenceTier, string> = {
  high:   "bg-green-100 text-green-800 border-green-300",
  medium: "bg-amber-100 text-amber-800 border-amber-300",
  low:    "bg-red-100 text-red-800 border-red-300",
};

export const CONF_LABEL: Record<ConfidenceTier, string> = {
  high:   "High confidence",
  medium: "Review recommended",
  low:    "Low confidence — verify",
};

export const HEADER_FIELD_LABELS: Record<keyof AIExtractionHeader, string> = {
  supplier_name:  "Supplier",
  invoice_number: "Invoice Number",
  invoice_date:   "Invoice Date",
  po_number:      "PO Number",
  vat_number:     "VAT Number",
  net_amount:     "Net Amount",
  vat_amount:     "VAT Amount",
  gross_amount:   "Gross Amount",
};

// ── API calls ─────────────────────────────────────────────────────────────────

export const documentAiApi = {
  /**
   * Trigger Claude AI extraction for a Gmail attachment.
   * Returns per-field confidence scores for the 8 invoice header fields.
   * NEVER creates an invoice automatically — human approval required.
   */
  async runAIExtraction(attachmentId: string): Promise<AIExtractionResult> {
    const r = await client.post<{ data: AIExtractionResult }>(
      `/document-ai/ai-extract/${attachmentId}`
    );
    return r.data.data;
  },

  /**
   * Retrieve a previously computed AI extraction result without re-running Claude.
   * Returns 404 if extraction has not been run yet.
   */
  async getAIExtraction(attachmentId: string): Promise<AIExtractionResult> {
    const r = await client.get<{ data: AIExtractionResult }>(
      `/document-ai/ai-extract/${attachmentId}`
    );
    return r.data.data;
  },
};
