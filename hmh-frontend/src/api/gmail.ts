import client from "./client";

export type DetectedType =
  | "INVOICE"
  | "DELIVERY_NOTE"
  | "PURCHASE_ORDER"
  | "PAYMENT_PROOF"
  | "FUEL_SLIP"
  | "QUOTE"
  | "OTHER";

export type ProcessedStatus = "UNPROCESSED" | "PROCESSED" | "IGNORED";

export interface IncomingEmailAttachment {
  id: string;
  filename: string;
  file_path: string;
  content_type: string | null;
  detected_type: DetectedType;
  created_at: string;
  file_exists: boolean;    // false = file missing from server disk (needs refetch)
}

export interface IncomingEmail {
  id: string;
  from_email: string;
  subject: string | null;
  received_at: string | null;
  has_attachments: boolean;
  processed_status: ProcessedStatus;
  matched_po_number: string | null;
  body_snippet?: string;
  attachments?: IncomingEmailAttachment[];
}

export interface GmailListResponse {
  total: number;
  items: IncomingEmail[];
}

export interface FetchResult {
  fetched: number;
  saved: number;
  skipped: number;
  mock: boolean;
  error?: string;
}

export type MatchStatus = "MATCHED" | "MISMATCH" | "NOT_FOUND" | "NO_REFERENCE";

export interface MRMatch {
  status:          MatchStatus;
  mr_number:       string | null;
  mr_id:           string | null;
  mr_status:       string | null;
  mismatch_detail: string | null;
}

export interface ProcessedAttachment {
  attachment_id:     string;
  filename:          string;
  detected_type:     DetectedType;
  extraction_status: string;
  fields: {
    po_number:            string | null;
    invoice_number:       string | null;
    delivery_note_number: string | null;
    supplier_name:        string | null;
    supplier_email:       string | null;
    date:                 string | null;
    total_amount:         number | null;
  };
  items: Array<{
    description: string;
    unit:        string | null;
    quantity:    number | null;
    unit_price:  number | null;
    line_total:  number | null;
  }>;
  mr_match: MRMatch;
  warnings: string[];
}

export interface ProcessEmailResult {
  email_id:         string;
  processed_status: string;
  results:          ProcessedAttachment[];
}

// ── Phase F: OCR reconciliation suggestion types ──────────────────────────────

export type ReviewStatus = "PENDING_REVIEW" | "INVOICE_CREATED" | "DELIVERY_LINKED" | "DISMISSED";

export interface ReconciliationSuggestion {
  attachment_id:        string | null;
  filename:             string;
  document_type:        string;
  extraction_status:    string;
  invoice_number:       string | null;
  delivery_note_number: string | null;
  po_number_from_doc:   string | null;
  supplier_name:        string | null;
  supplier_email:       string | null;
  total_amount:         number | null;
  date:                 string | null;
  matched_po:           string | null;
  matched_po_id:        string | null;
  match_confidence:     number;           // 0.0 – 1.0
  issues:               string[];
  requires_review:      true;             // always true — human approval required
  extraction_warnings:  string[];
  review_status:        ReviewStatus;
}

export interface SuggestResult {
  email_id:    string;
  from_email:  string;
  subject:     string | null;
  suggestions: ReconciliationSuggestion[];
}

export interface CreateInvoiceFromGmailBody {
  project_id:        string;
  invoice_number?:   string | null;
  supplier_id?:      string | null;
  purchase_order_id?: string | null;
  total_amount?:     number;
  notes?:            string | null;
}

export interface CreateInvoiceFromGmailResult {
  invoice_id: string;
  match:      Record<string, unknown>;
}

export const gmailApi = {
  fetch: async (limit = 20): Promise<FetchResult> => {
    const r = await client.post(`/gmail/fetch?limit=${limit}`);
    return r.data.data;
  },

  listIncoming: async (params?: {
    status?: ProcessedStatus;
    limit?: number;
    offset?: number;
  }): Promise<GmailListResponse> => {
    const r = await client.get("/gmail/incoming", { params });
    return r.data.data;
  },

  getIncoming: async (id: string): Promise<IncomingEmail> => {
    const r = await client.get(`/gmail/incoming/${id}`);
    return r.data.data;
  },

  getAttachment: async (id: string): Promise<IncomingEmailAttachment> => {
    const r = await client.get(`/gmail/attachments/${id}`);
    return r.data.data;
  },

  processEmail: async (emailId: string): Promise<ProcessEmailResult> => {
    const r = await client.post<{ data: ProcessEmailResult }>(`/gmail/incoming/${emailId}/process`);
    return r.data.data;
  },

  /** Re-fetch a missing attachment from Gmail IMAP and save it to the server disk. */
  refetchAttachment: async (attId: string): Promise<{ att_id: string; saved_path: string; exists: boolean; size: number }> => {
    const r = await client.post<{ data: { att_id: string; saved_path: string; exists: boolean; size: number } }>(
      `/gmail/attachments/${attId}/refetch`
    );
    return r.data.data;
  },

  /** Run OCR → PO matching pipeline for all attachments on an email.
   *  Returns reconciliation suggestions for human review.
   *  NEVER creates records — requires_review is always true on each suggestion. */
  suggestReconciliation: async (emailId: string): Promise<SuggestResult> => {
    const r = await client.post<{ data: SuggestResult }>(`/gmail/incoming/${emailId}/suggest`);
    return r.data.data;
  },

  /** Create an Invoice record from a Gmail attachment (human-triggered only). */
  createInvoiceFromGmail: async (
    attId: string,
    body: CreateInvoiceFromGmailBody,
  ): Promise<CreateInvoiceFromGmailResult> => {
    const r = await client.post<{ data: CreateInvoiceFromGmailResult }>(
      `/invoices/from-gmail/${attId}`,
      body,
    );
    return r.data.data;
  },

  /** Update the review_status of the DocumentExtraction linked to an attachment. */
  updateReviewStatus: async (attId: string, status: ReviewStatus): Promise<{ att_id: string; review_status: ReviewStatus }> => {
    const r = await client.patch<{ data: { att_id: string; review_status: ReviewStatus } }>(
      `/gmail/attachments/${attId}/review-status`,
      { status },
    );
    return r.data.data;
  },

  /** Link a Gmail attachment to an existing Delivery as its delivery note image. */
  linkDeliveryFromGmail: async (attId: string, deliveryId: string): Promise<{ delivery_id: string; match: Record<string, unknown> }> => {
    const r = await client.post<{ data: { delivery_id: string; match: Record<string, unknown> } }>(
      `/delivery-notes/from-gmail/${attId}`,
      { delivery_id: deliveryId },
    );
    return r.data.data;
  },

  /** Returns whether SMTP and IMAP are configured on the server. */
  getEmailConfig: async (): Promise<{ smtp_enabled: boolean; imap_enabled: boolean }> => {
    const r = await client.get<{ data: { smtp_enabled: boolean; imap_enabled: boolean } }>("/gmail/email-config");
    return r.data.data;
  },

  /**
   * Send a free-form email with optional file attachments (PDF/JPEG/PNG/GIF/XLS/XLSX/CSV).
   * Uses multipart/form-data so files can be included.
   */
  composeSend: async (
    toEmail: string,
    subject: string,
    bodyHtml: string,
    files: File[] = [],
  ): Promise<{ status: string; attachment_count: number }> => {
    const form = new FormData();
    form.append("to_email", toEmail);
    form.append("subject", subject);
    form.append("body_html", bodyHtml);
    for (const f of files) form.append("attachments", f);
    const r = await client.post<{ data: { status: string; attachment_count: number } }>(
      "/gmail/compose-send",
      form,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return r.data.data;
  },

  /**
   * Fetch an attachment file as a Blob (includes auth headers automatically).
   * inline=true  → browser can render PDF/image inline
   * inline=false → triggers download
   */
  getAttachmentBlob: async (attId: string, inline = false): Promise<{ blob: Blob; filename: string }> => {
    const r = await client.get(`/gmail/attachments/${attId}/download`, {
      params:       { inline },
      responseType: "blob",
    });
    // Extract filename from Content-Disposition if present
    const cd       = r.headers["content-disposition"] ?? "";
    const match    = cd.match(/filename="?([^";]+)"?/i);
    const filename = match?.[1] ?? "attachment";
    return { blob: r.data as Blob, filename };
  },
};

export interface ProofPackSummary {
  invoice_id: string;
  invoice_number: string | null;
  invoice_date: string | null;
  total_amount: number;
  status: string | null;
  supplier_name: string | null;
  po_number: string | null;
  match_status: string;
  is_matched: boolean;
}

export interface ProofPackListResponse {
  total: number;
  items: ProofPackSummary[];
}

export const proofPacksApi = {
  list: async (limit = 50, offset = 0): Promise<ProofPackListResponse> => {
    const r = await client.get("/proof-packs/", { params: { limit, offset } });
    return r.data.data;
  },

  get: async (invoiceId: string): Promise<Record<string, unknown>> => {
    const r = await client.get(`/proof-packs/${invoiceId}`);
    return r.data.data;
  },
};
