import client from "./client";

export interface ExtractionFields {
  po_number:            string | null;
  delivery_note_number: string | null;
  supplier_name:        string | null;
  supplier_email:       string | null;
  date:                 string | null;
  total_amount:         number | null;
}

export interface ExtractedItem {
  description:         string;
  unit:                string | null;
  ocr_qty:             number | null;
  actual_received_qty: number;
  accepted_qty:        number;
  rejected_qty:        number;
  mismatch_reason:     string | null;
  expected_qty?:       number | null;
}

export interface DeliveryNoteUploadResult {
  id:               string;
  extraction_id:    string;
  status:           string;   // EXTRACTED | OCR_NOT_AVAILABLE | OCR_FAILED | NEEDS_REVIEW | FAILED
  extracted_fields: ExtractionFields;
  items:            ExtractedItem[];
  warnings:         string[];
}

export interface VerificationResult {
  id:     string;
  status: string;   // VERIFIED | MISMATCH
}

export const siteCaptureApi = {
  uploadDeliveryNote: async (formData: FormData): Promise<DeliveryNoteUploadResult> => {
    const res = await client.post<{ data: DeliveryNoteUploadResult }>(
      "/site-capture/delivery-note/upload",
      formData,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return res.data.data;
  },

  correctDeliveryNote: async (
    id: string,
    body: {
      supplier_name?:        string | null;
      delivery_note_number?: string | null;
      vehicle_reg?:          string | null;
      driver_name?:          string | null;
      notes?:                string | null;
      items?: ExtractedItem[];
    },
  ): Promise<void> => {
    await client.post(`/site-capture/delivery-note/${id}/correct`, body);
  },

  saveSignature: async (
    id: string,
    signatureData: string,
    signedByName?: string,
  ): Promise<void> => {
    await client.post(`/site-capture/delivery-note/${id}/signature`, {
      signature_data: signatureData,
      signed_by_name: signedByName ?? null,
    });
  },

  verify: async (id: string): Promise<VerificationResult> => {
    const res = await client.post<{ data: VerificationResult }>(
      `/site-capture/delivery-note/${id}/verify`,
    );
    return res.data.data;
  },
};
