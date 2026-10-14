import client from "./client";

/**
 * Bypass Orders (AI Document Import & Reconciliation Engine).
 *
 * "Bypass Orders" is the user-facing name. The API paths, services and
 * tables keep the ai_import name deliberately — renaming them would be a
 * migration and an API break for no user benefit.
 *
 * Upload scanned procurement paperwork, let the backend read and reconcile it,
 * review what it found, and post the authorised result through the existing
 * procurement, inventory and finance services.
 */

// ── Types ─────────────────────────────────────────────────────────────────────

export type DocumentType =
  | "MATERIAL_REQUEST"
  | "PURCHASE_ORDER"
  | "SUPPLIER_INVOICE"
  | "DELIVERY_NOTE"
  | "GOODS_RECEIVED_NOTE"
  | "SUPPLIER_CREDIT_NOTE"
  | "PAYMENT_PROOF"
  | "UNKNOWN";

export type DocumentStatus =
  | "UPLOADED"
  | "QUEUED"
  | "PROCESSING"
  | "EXTRACTED"
  | "CLASSIFIED"
  | "MATCHING"
  | "AWAITING_REVIEW"
  | "AWAITING_AUTHORISATION"
  | "READY_TO_POST"
  | "POSTED"
  | "PARTIALLY_POSTED"
  | "FAILED"
  | "REJECTED"
  | "DUPLICATE";

export type ProcessingOutcome = "AUTO_ELIGIBLE" | "NEEDS_REVIEW" | "BLOCKED";

export type MatchStatus = "PROPOSED" | "CONFIRMED" | "REJECTED" | "AMBIGUOUS";

export const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  MATERIAL_REQUEST:     "Material Request",
  PURCHASE_ORDER:       "Purchase Order",
  SUPPLIER_INVOICE:     "Supplier Invoice",
  DELIVERY_NOTE:        "Delivery Note",
  GOODS_RECEIVED_NOTE:  "Goods Received Note",
  SUPPLIER_CREDIT_NOTE: "Credit Note",
  PAYMENT_PROOF:        "Proof of Payment",
  UNKNOWN:              "Not identified",
};

export const STATUS_LABELS: Record<DocumentStatus, string> = {
  UPLOADED:               "Uploaded",
  QUEUED:                 "Queued",
  PROCESSING:             "Reading…",
  EXTRACTED:              "Read",
  CLASSIFIED:             "Identified",
  MATCHING:               "Matching",
  AWAITING_REVIEW:        "Needs review",
  AWAITING_AUTHORISATION: "Needs authorisation",
  READY_TO_POST:          "Ready to post",
  POSTED:                 "Posted",
  PARTIALLY_POSTED:       "Partly posted",
  FAILED:                 "Failed",
  REJECTED:               "Rejected",
  DUPLICATE:              "Duplicate",
};

/** Statuses the backend is still working on — the UI polls while any are present. */
export const IN_FLIGHT_STATUSES: DocumentStatus[] = [
  "UPLOADED", "QUEUED", "PROCESSING", "EXTRACTED", "CLASSIFIED", "MATCHING",
];

export interface OutcomeReason {
  code: string;
  message: string;
  severity: "BLOCKED" | "NEEDS_REVIEW";
  field: string | null;
}

export interface ExtractedFieldValue {
  value: unknown;
  page: number | null;
  confidence: number;
  source: "vision" | "text" | "regex" | "manual";
  validated: boolean;
  corrected: boolean;
  corrected_by: string | null;
}

export interface ExtractedLineItem {
  description: string | null;
  stock_code: string | null;
  quantity: number | null;
  unit: string | null;
  unit_price: number | null;
  discount: number | null;
  vat_rate: number | null;
  line_total: number | null;
  page: number | null;
  confidence: number;
}

export interface ArithmeticCheck {
  name: string;
  expected: number | null;
  actual: number | null;
  difference: number | null;
  tolerance: number;
  passed: boolean;
  message: string | null;
}

export interface Extraction {
  id: string;
  schema_version: string;
  prompt_version: string;
  provider: string;
  model: string | null;
  extraction_mode: string;
  fields: Record<string, ExtractedFieldValue>;
  line_items: ExtractedLineItem[];
  arithmetic_checks: ArithmeticCheck[];
  warnings: string[];
  overall_confidence: number;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  created_at: string | null;
}

export interface DocumentMatch {
  id: string;
  target_type: string;
  target_id: string | null;
  target_label: string | null;
  status: MatchStatus;
  method: string;
  score: number | null;
  explanation: string | null;
  evidence: Record<string, unknown>;
  decided_by: string | null;
}

export interface Posting {
  id: string;
  entity_type: string;
  entity_id: string | null;
  entity_label: string | null;
  posted_at: string | null;
  reversed_at: string | null;
  complete: boolean;
}

export interface Correction {
  field_path: string;
  before_value: string | null;
  after_value: string | null;
  reason: string | null;
  corrected_by: string;
  created_at: string | null;
}

export interface LineItemMatch {
  index: number;
  description: string | null;
  stock_code: string | null;
  quantity: number | null;
  unit: string | null;
  item_id: string | null;
  item_name: string | null;
  item_unit: string | null;
  converted_quantity: number | null;
  unit_convertible: boolean;
  score: number;
  ambiguous: boolean;
  explanation: string;
}

export interface RelatedDocument {
  id: string;
  file_name: string;
  document_type: DocumentType;
  status: DocumentStatus;
  created_at: string | null;
  shared_links: string[];
}

export interface ImportDocument {
  id: string;
  batch_id: string;
  batch_reference: string | null;
  file_name: string;
  mime_type: string;
  file_size_bytes: number;
  checksum_sha256: string;
  page_count: number | null;
  status: DocumentStatus;
  processing_outcome: ProcessingOutcome | null;
  outcome_reasons: OutcomeReason[];
  document_type: DocumentType;
  classification_confidence: number;
  document_type_confirmed: boolean;
  project_id: string | null;
  site_id: string | null;
  supplier_id: string | null;
  is_legacy: boolean;
  duplicate_of_id: string | null;
  failure_reason: string | null;
  retry_count: number;
  reviewed_by: string | null;
  reviewed_at: string | null;
  authorised_by: string | null;
  authorised_at: string | null;
  rejection_reason: string | null;
  uploaded_by: string;
  created_at: string | null;
  can_post: boolean;
}

export interface ImportDocumentDetail extends ImportDocument {
  extraction: Extraction | null;
  matches: DocumentMatch[];
  postings: Posting[];
  corrections: Correction[];
  job_status: string | null;
  job: {
    status: string;
    attempt_count: number;
    max_attempts: number;
    next_attempt_at: string | null;
    last_error: string | null;
  } | null;
  related_documents: RelatedDocument[];
  line_item_matches: LineItemMatch[];
}

export interface ImportBatch {
  id: string;
  reference: string;
  project_id: string | null;
  site_id: string | null;
  is_legacy: boolean;
  status: "OPEN" | "PROCESSING" | "COMPLETE" | "CANCELLED";
  notes: string | null;
  uploaded_by: string;
  created_at: string | null;
  document_count: number;
  documents?: ImportDocument[];
}

export interface ImportDashboard {
  totals: {
    uploaded: number;
    classified: number;
    processed: number;
    awaiting_review: number;
    awaiting_authorisation: number;
    ready_to_post: number;
    posted: number;
    duplicates: number;
    failed: number;
    rejected: number;
    in_progress: number;
    failed_jobs: number;
    posted_transactions: number;
    incomplete_postings: number;
  };
  queues: Record<string, number>;
  amounts_awaiting_authorisation: number;
  by_status: Record<string, number>;
  by_document_type: Record<string, number>;
  reason_counts: Record<string, number>;
  ai_usage: {
    cost_usd: number;
    input_tokens: number;
    output_tokens: number;
    provider_configured: boolean;
    model: string;
  };
}

export interface DocumentFilters {
  /** Resolved through the document's project — documents carry no company of their own. */
  company_id?: string;
  project_id?: string;
  site_id?: string;
  supplier_id?: string;
  document_type?: DocumentType;
  status?: DocumentStatus;
  uploaded_by?: string;
  /** Only documents carrying this policy reason, e.g. NO_PURCHASE_ORDER. */
  reason_code?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  limit?: number;
}

export interface UploadResult {
  batch: ImportBatch;
  accepted: ImportDocument[];
  rejected: { file_name: string; reason: string }[];
}

// ── API ───────────────────────────────────────────────────────────────────────

export interface ServiceStatus {
  enabled: boolean;
  extraction_available: boolean;
  extraction_model: string;
  private_storage_configured: boolean;
  auto_post_enabled: boolean;
  worker_enabled: boolean;
}

export const aiImportApi = {
  createBatch: async (body: {
    project_id?: string | null;
    site_id?: string | null;
    is_legacy?: boolean;
    notes?: string | null;
  }): Promise<ImportBatch> => {
    const res = await client.post<{ data: ImportBatch }>("/ai-import/batches", body);
    return res.data.data;
  },

  listBatches: async (limit = 25): Promise<ImportBatch[]> => {
    const res = await client.get<{ data: ImportBatch[] }>("/ai-import/batches", {
      params: { limit },
    });
    return res.data.data;
  },

  getBatch: async (id: string): Promise<ImportBatch> => {
    const res = await client.get<{ data: ImportBatch }>(`/ai-import/batches/${id}`);
    return res.data.data;
  },

  /** Upload one or more files into a batch. Processing happens in the background. */
  upload: async (
    batchId: string,
    files: File[],
    opts?: { isLegacy?: boolean; onProgress?: (percent: number) => void },
  ): Promise<UploadResult> => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    if (opts?.isLegacy !== undefined) form.append("is_legacy", String(opts.isLegacy));

    const res = await client.post<{ data: UploadResult }>(
      `/ai-import/batches/${batchId}/documents`,
      form,
      {
        onUploadProgress: (event) => {
          if (opts?.onProgress && event.total) {
            opts.onProgress(Math.round((event.loaded / event.total) * 100));
          }
        },
      },
    );
    return res.data.data;
  },

  listDocuments: async (
    filters: DocumentFilters = {},
  ): Promise<{ items: ImportDocument[]; total: number; page: number; total_pages: number }> => {
    const res = await client.get<{
      data: { items: ImportDocument[]; total: number; page: number; total_pages: number };
    }>("/ai-import/documents", { params: filters });
    return res.data.data;
  },

  getDocument: async (id: string): Promise<ImportDocumentDetail> => {
    const res = await client.get<{ data: ImportDocumentDetail }>(`/ai-import/documents/${id}`);
    return res.data.data;
  },

  /** Short-lived signed URL for the original file. Private storage — never a public path. */
  getFileUrl: async (
    id: string,
  ): Promise<{ url: string; expires_in_seconds: number; mime_type: string; file_name: string }> => {
    const res = await client.get<{
      data: { url: string; expires_in_seconds: number; mime_type: string; file_name: string };
    }>(`/ai-import/documents/${id}/file`);
    return res.data.data;
  },

  assignContext: async (
    id: string,
    body: {
      project_id?: string | null;
      site_id?: string | null;
      supplier_id?: string | null;
      document_type?: DocumentType;
      is_legacy?: boolean;
    },
  ): Promise<ImportDocumentDetail> => {
    const res = await client.patch<{ data: ImportDocumentDetail }>(
      `/ai-import/documents/${id}/context`, body,
    );
    return res.data.data;
  },

  correct: async (
    id: string,
    corrections: { field_path: string; value: unknown; reason?: string }[],
  ): Promise<ImportDocumentDetail> => {
    const res = await client.patch<{ data: ImportDocumentDetail }>(
      `/ai-import/documents/${id}/corrections`, { corrections },
    );
    return res.data.data;
  },

  decideMatch: async (
    id: string, matchId: string, accept: boolean, reason?: string,
  ): Promise<ImportDocumentDetail> => {
    const res = await client.post<{ data: ImportDocumentDetail }>(
      `/ai-import/documents/${id}/matches/decide`,
      { match_id: matchId, accept, reason },
    );
    return res.data.data;
  },

  addMatch: async (
    id: string, targetType: string, targetId: string, reason?: string,
  ): Promise<ImportDocumentDetail> => {
    const res = await client.post<{ data: ImportDocumentDetail }>(
      `/ai-import/documents/${id}/matches`,
      { target_type: targetType, target_id: targetId, reason },
    );
    return res.data.data;
  },

  markReviewed: async (id: string): Promise<ImportDocumentDetail> => {
    const res = await client.post<{ data: ImportDocumentDetail }>(
      `/ai-import/documents/${id}/review`,
    );
    return res.data.data;
  },

  authoriseLegacy: async (id: string, note: string): Promise<ImportDocumentDetail> => {
    const res = await client.post<{ data: ImportDocumentDetail }>(
      `/ai-import/documents/${id}/authorise`, { reason: note },
    );
    return res.data.data;
  },

  reject: async (id: string, reason: string): Promise<ImportDocument> => {
    const res = await client.post<{ data: ImportDocument }>(
      `/ai-import/documents/${id}/reject`, { reason },
    );
    return res.data.data;
  },

  retry: async (id: string): Promise<ImportDocument> => {
    const res = await client.post<{ data: ImportDocument }>(`/ai-import/documents/${id}/retry`);
    return res.data.data;
  },

  post: async (
    id: string,
    body: { destination?: string; confirm_override?: boolean; legacy_authorisation_note?: string } = {},
  ): Promise<{
    document: ImportDocumentDetail;
    posting: { entity_type: string; entity_id: string | null; entity_label: string | null };
    related_documents_reevaluated: number;
  }> => {
    const res = await client.post<{
      data: {
        document: ImportDocumentDetail;
        posting: { entity_type: string; entity_id: string | null; entity_label: string | null };
        related_documents_reevaluated: number;
      };
      message: string;
    }>(`/ai-import/documents/${id}/post`, body);
    return res.data.data;
  },

  /**
   * What the service can actually do right now.
   *
   * Bypass Orders degrades rather than fails when its external integrations
   * are missing, so the page has to say which of them are configured — an
   * empty extraction otherwise reads as a bad scan.
   */
  serviceStatus: async (): Promise<ServiceStatus> => {
    const res = await client.get<{ data: ServiceStatus }>("/ai-import/service-status");
    return res.data.data;
  },

  dashboard: async (filters: DocumentFilters = {}): Promise<ImportDashboard> => {
    const res = await client.get<{ data: ImportDashboard }>("/ai-import/dashboard", {
      params: filters,
    });
    return res.data.data;
  },

  /** Drain the queue on demand — useful when the background worker is off. */
  processNow: async (limit = 5): Promise<{ processed: number; failed: number }> => {
    const res = await client.post<{ data: { processed: number; failed: number } }>(
      "/ai-import/process", null, { params: { limit } },
    );
    return res.data.data;
  },
};

// ── Display helpers ───────────────────────────────────────────────────────────

export const confidenceBand = (confidence: number): "high" | "medium" | "low" =>
  confidence >= 0.8 ? "high" : confidence >= 0.5 ? "medium" : "low";

export const fieldLabel = (name: string): string =>
  name.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
