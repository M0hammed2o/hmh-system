/**
 * Vision API — extract structured data from uploaded documents.
 * Returns a preview for user review/confirmation.
 * DOES NOT auto-save any business records.
 */
import client from "./client";

export type VisionDocumentType = "delivery_note" | "invoice" | "payment_proof";

export interface VisionPreviewInvoice {
  invoice_number: string | null;
  supplier_name:  string | null;
  supplier_email: string | null;
  po_number:      string | null;
  date:           string | null;
  due_date:       string | null;
  total_amount:   number | null;
  vat_amount:     number | null;
  line_items: Array<{
    description: string | null;
    quantity:    number | null;
    unit_price:  number | null;
    line_total:  number | null;
    unit:        string | null;
  }>;
}

export interface SupplierSuggestion {
  id:    string;
  name:  string;
  email: string | null;
  score: number;
}

export interface VisionPreviewDeliveryNote {
  delivery_note_number: string | null;
  supplier_name:        string | null;
  date:                 string | null;
  po_number:            string | null;
  items: Array<{ description: string | null; quantity: number | null; unit: string | null }>;
}

export interface VisionPreviewPaymentProof {
  amount:    number | null;
  date:      string | null;
  reference: string | null;
  supplier:  string | null;
}

export interface VisionResult {
  status:          string;   // EXTRACTED | NEEDS_REVIEW | OCR_NOT_AVAILABLE | FAILED
  document_type:   string;
  file_name:       string | null;
  file_size_bytes: number;
  extraction_id:   string | null;
  preview:         VisionPreviewInvoice | VisionPreviewDeliveryNote | VisionPreviewPaymentProof | Record<string, unknown>;
  raw_fields:      Record<string, unknown>;
  items:           Array<Record<string, unknown>>;
  warnings:        string[];
  provider:        string;
  note:            string;
}

export const visionApi = {
  extract: async (file: File, documentType: VisionDocumentType): Promise<VisionResult> => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("document_type", documentType);
    const res = await client.post<{ data: VisionResult }>("/vision/extract", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data.data;
  },

  suggestSupplier: async (name: string): Promise<SupplierSuggestion[]> => {
    const res = await client.get<{ data: SupplierSuggestion[] }>("/suppliers/suggest", { params: { name } });
    return res.data.data;
  },
};
