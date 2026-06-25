import client from "./client";

export type MRStatus =
  | "DRAFT" | "SUBMITTED" | "PENDING_APPROVAL" | "STAFF_APPROVED" | "APPROVED" | "REJECTED"
  | "CONVERTED_TO_PO" | "ORDERED" | "PARTIALLY_RECEIVED" | "RECEIVED"
  | "INVOICED" | "CLOSED" | "CANCELLED";

export interface MRApprovalVote {
  id: string;
  mr_id: string;
  approved_by: string | null;
  approved_by_name: string | null;
  approved_at: string;
  is_override: boolean;
  notes: string | null;
}

export interface QuoteVote {
  id: string;
  quote_id: string;
  voted_by: string | null;
  voted_by_name: string | null;
  voted_at: string;
  is_override: boolean;
  notes: string | null;
}

export interface ProcurementActivityEntry {
  type:          "status" | "document";
  timestamp:     string;
  actor:         string | null;
  description:   string;
  url?:          string;
  attachment_id?: string;
  is_image?:     boolean;
}

export type MRPriority = "URGENT" | "HIGH" | "NORMAL" | "LOW";
export type DeliveryDestination = "MAIN_WAREHOUSE" | "SITE_STORE" | "LOT" | "PICKUP";
export type POStatus = MRStatus;

export interface MRItem {
  id: string;
  material_request_id: string;
  item_id: string | null;
  boq_item_id: string | null;
  preferred_supplier_id: string | null;
  description: string;
  requested_quantity: number;
  approved_quantity: number | null;
  over_boq_quantity: number | null;
  unit: string | null;
  remarks: string | null;
}

export interface MREmailLog {
  id: string;
  status: string;
  sent_to_email: string;
  email_subject: string | null;
  sent_at: string | null;
  error_message: string | null;
}

export interface MaterialRequest {
  id: string;
  request_number: string;
  project_id: string;
  site_id: string;
  lot_id: string | null;
  requested_by: string;
  priority: MRPriority;
  delivery_destination: DeliveryDestination;
  status: MRStatus;
  preferred_supplier_id: string | null;
  over_boq: boolean;
  over_boq_reason: string | null;
  approved_by: string | null;
  approved_at: string | null;
  needed_by_date: string | null;
  rejection_reason: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  items: MRItem[];
  email_log?: MREmailLog | null;
}

export interface MRItemCreate {
  item_id?: string;
  boq_item_id?: string;
  preferred_supplier_id?: string | null;
  description: string;
  requested_quantity: number;
  unit?: string;
  remarks?: string;
}

export interface BOQSearchResult {
  id: string;
  description: string;
  unit: string | null;
  planned_quantity: number | null;
  preferred_supplier_id: string | null;
  supplier_name: string | null;
  lot_id: string | null;
  site_id: string | null;
  item_id: string | null;
}

export interface MRCreate {
  site_id?: string | null;
  lot_id?: string;
  priority?: MRPriority;
  delivery_destination?: DeliveryDestination;
  needed_by_date?: string;
  notes?: string;
  preferred_supplier_id?: string | null;
  items: MRItemCreate[];
}

export interface MRQuote {
  id: string;
  material_request_id: string;
  supplier_id: string;
  description: string;
  quoted_quantity: number;
  unit: string | null;
  unit_price: number;
  total_price: number | null;
  delivery_date: string | null;
  notes: string | null;
  is_selected: boolean;
  // Phase 4A pipeline fields
  source?: "MANUAL" | "EMAIL";
  status?: "PENDING" | "APPROVED" | "REJECTED";
  boq_unit_price?: number | null;
  boq_variance_pct?: number | null;
  rejection_reason?: string | null;
  rejected_at?: string | null;
  approved_at?: string | null;
  created_at?: string | null;
}

// ── Pipeline types (Phase 4A) ────────────────────────────────────────────────

export type PipelineStepStatus = "COMPLETE" | "CURRENT" | "WAITING" | "BLOCKED";

export interface POEntry {
  id: string;
  po_number: string;
  status: string;
  total: number;
  sent: boolean;
  supplier_name: string | null;
  invoice: { id: string; invoice_number: string; total_amount: number; status: string; matches_po: boolean } | null;
  delivery: { id: string; delivery_note_number: string; status: string; received_at: string | null } | null;
}

export interface PipelineStep {
  step: number;
  key: string;
  label: string;
  status: PipelineStepStatus;
  // step 1
  submitted_at?: string | null;
  item_count?: number;
  // step 2
  approved_at?: string | null;
  over_boq?: boolean;
  // step 3
  email_sent?: boolean;
  email_logs?: Array<{ sent_to: string; sent_at: string | null; status: string }>;
  sent_to?: string | null;
  sent_at?: string | null;
  email_status?: string | null;
  supplier_name?: string | null;
  supplier_email?: string | null;
  missing_email?: boolean;
  // step 4
  quotes?: MRQuote[];
  pending_count?: number;
  approved_count?: number;
  // step 5 — pos covers all POs for multi-supplier MRs; po is latest for compat
  po?: POEntry | null;
  pos?: POEntry[];
  // step 6 — invoice is latest for compat; per-PO invoices are in pos[*].invoice
  invoice?: { id: string; invoice_number: string; total_amount: number; status: string; matches_po: boolean } | null;
  // step 7 — delivery is latest for compat; per-PO deliveries are in pos[*].delivery
  delivery?: { id: string; delivery_note_number: string; status: string; received_at: string | null } | null;
}

export interface PipelineSupplier {
  id: string | null;
  name: string | null;
  email: string | null;
  has_email: boolean;
}

export interface MRPipeline {
  mr_id: string;
  mr_number: string;
  mr_status: string;
  pipeline_complete: boolean;
  priority: MRPriority;
  project_id: string | null;
  lot_id: string | null;
  notes: string | null;
  over_boq: boolean;
  items: Array<{ id: string; description: string; requested_quantity: number; unit: string | null; over_boq_quantity: number | null; preferred_supplier_id: string | null }>;
  current_step: number;
  steps: PipelineStep[];
  supplier: PipelineSupplier;
}

export interface POItem {
  id: string;
  description: string;
  quantity_ordered: number;
  quantity_received: number;
  unit: string | null;
  rate: number | null;
  line_total: number | null;
  lot_id: string | null;
}

export interface PurchaseOrder {
  id: string;
  po_number: string;
  project_id: string;
  site_id: string | null;
  lot_id: string | null;
  supplier_id: string;
  material_request_id: string | null;
  status: POStatus;
  delivery_destination: DeliveryDestination | null;
  po_date: string;
  expected_delivery_date: string | null;
  subtotal_amount: number;
  vat_amount: number;
  total_amount: number;
  sent_at: string | null;
  notes: string | null;
  created_at: string;
  order_items: POItem[];
}

export const procurementApi = {
  // Material Requests
  listMRs: async (projectId: string, status?: string): Promise<MaterialRequest[]> => {
    const params: Record<string, string> = {};
    if (status) params.status = status;
    const res = await client.get<{ data: MaterialRequest[] }>(
      `/projects/${projectId}/material-requests/`, { params }
    );
    return res.data.data;
  },

  getMR: async (mrId: string): Promise<MaterialRequest> => {
    const res = await client.get<{ data: MaterialRequest }>(`/material-requests/${mrId}`);
    return res.data.data;
  },

  createMR: async (projectId: string, body: MRCreate): Promise<MaterialRequest> => {
    const res = await client.post<{ data: MaterialRequest }>(
      `/projects/${projectId}/material-requests/`, body
    );
    return res.data.data;
  },

  createWarehouseMR: async (body: MRCreate): Promise<MaterialRequest> => {
    const res = await client.post<{ data: MaterialRequest }>(`/material-requests/`, body);
    return res.data.data;
  },

  submitMR: async (mrId: string): Promise<MaterialRequest> => {
    const res = await client.post<{ data: MaterialRequest }>(`/material-requests/${mrId}/submit`);
    return res.data.data;
  },

  approveMR: async (mrId: string, overBoqReason?: string, issuingCompany?: string): Promise<MaterialRequest> => {
    const res = await client.post<{ data: MaterialRequest }>(
      `/material-requests/${mrId}/approve`,
      { over_boq_reason: overBoqReason ?? null, issuing_company: issuingCompany ?? "HMH_GROUP" }
    );
    return res.data.data;
  },

  listMRApprovals: async (mrId: string): Promise<MRApprovalVote[]> => {
    const res = await client.get<{ data: MRApprovalVote[] }>(`/material-requests/${mrId}/approvals`);
    return res.data.data;
  },

  voteMR: async (mrId: string, notes?: string): Promise<MaterialRequest> => {
    const res = await client.post<{ data: MaterialRequest }>(
      `/material-requests/${mrId}/vote`,
      { notes: notes ?? null }
    );
    return res.data.data;
  },

  procurementApproveMR: async (mrId: string, overBoqReason?: string, issuingCompany?: string): Promise<MaterialRequest> => {
    const res = await client.post<{ data: MaterialRequest }>(
      `/material-requests/${mrId}/procurement-approve`,
      { over_boq_reason: overBoqReason ?? null, issuing_company: issuingCompany ?? "HMH_GROUP" }
    );
    return res.data.data;
  },

  rejectMR: async (mrId: string, reason: string): Promise<MaterialRequest> => {
    const res = await client.post<{ data: MaterialRequest }>(
      `/material-requests/${mrId}/reject`, { reason }
    );
    return res.data.data;
  },

  convertToPO: async (
    mrId: string,
    supplierId: string,
    items: Array<{ description: string; quantity: number; unit?: string; rate: number; item_id?: string }>,
    expectedDeliveryDate?: string,
    notes?: string,
  ): Promise<{ po_id: string; po_number: string }> => {
    const res = await client.post<{ data: { po_id: string; po_number: string } }>(
      `/material-requests/${mrId}/convert-to-po`,
      { supplier_id: supplierId, items, expected_delivery_date: expectedDeliveryDate, notes }
    );
    return res.data.data;
  },

  // Quotes
  listQuotes: async (mrId: string): Promise<MRQuote[]> => {
    const res = await client.get<{ data: MRQuote[] }>(`/material-requests/${mrId}/quotes`);
    return res.data.data;
  },

  addQuote: async (mrId: string, body: {
    supplier_id: string; description: string; quoted_quantity: number;
    unit_price: number; unit?: string; delivery_date?: string; notes?: string;
  }): Promise<MRQuote> => {
    const res = await client.post<{ data: MRQuote }>(`/material-requests/${mrId}/quotes`, body);
    return res.data.data;
  },

  selectQuote: async (mrId: string, quoteId: string): Promise<MRQuote> => {
    const res = await client.post<{ data: MRQuote }>(`/material-requests/${mrId}/quotes/${quoteId}/select`);
    return res.data.data;
  },

  // Purchase Orders
  listPOs: async (projectId: string): Promise<PurchaseOrder[]> => {
    const res = await client.get<{ data: PurchaseOrder[] }>(`/projects/${projectId}/purchase-orders/`);
    return res.data.data;
  },

  getPO: async (poId: string): Promise<PurchaseOrder> => {
    const res = await client.get<{ data: PurchaseOrder }>(`/purchase-orders/${poId}`);
    return res.data.data;
  },

  approvePO: async (poId: string): Promise<PurchaseOrder> => {
    const res = await client.post<{ data: PurchaseOrder }>(`/purchase-orders/${poId}/approve`);
    return res.data.data;
  },

  sendEmail: async (poId: string): Promise<{ po_number: string; sent_to: string; status: string; is_mock: boolean }> => {
    const res = await client.post<{ data: { po_number: string; sent_to: string; status: string; is_mock: boolean } }>(
      `/purchase-orders/${poId}/send-email`
    );
    return res.data.data;
  },

  getEmailLog: async (poId: string): Promise<Array<{ id: string; sent_to: string; subject: string; status: string; sent_at: string | null }>> => {
    const res = await client.get<{ data: Array<{ id: string; sent_to: string; subject: string; status: string; sent_at: string | null }> }>(
      `/purchase-orders/${poId}/email-log`
    );
    return res.data.data;
  },

  getOutstanding: async (poId: string): Promise<{
    po_number: string; status: string; is_fully_received: boolean;
    items: Array<{ description: string; quantity_ordered: number; quantity_received: number; quantity_outstanding: number }>;
  }> => {
    const res = await client.get<{ data: unknown }>(`/purchase-orders/${poId}/outstanding`);
    return res.data.data as ReturnType<typeof procurementApi.getOutstanding> extends Promise<infer T> ? T : never;
  },

  markSent: async (poId: string): Promise<PurchaseOrder> => {
    const res = await client.post<{ data: PurchaseOrder }>(`/purchase-orders/${poId}/mark-sent`);
    return res.data.data;
  },

  // ── Activity timelines ──────────────────────────────────────────────────

  searchBOQItems: async (projectId: string, q: string): Promise<BOQSearchResult[]> => {
    const res = await client.get<{ data: BOQSearchResult[] }>(
      `/projects/${projectId}/boq/items/search`,
      { params: { q } },
    );
    return res.data.data ?? [];
  },

  getMRActivity: async (mrId: string): Promise<ProcurementActivityEntry[]> => {
    const res = await client.get<{ data: ProcurementActivityEntry[] }>(
      `/material-requests/${mrId}/activity`
    );
    return res.data.data;
  },

  getPOActivity: async (poId: string): Promise<ProcurementActivityEntry[]> => {
    const res = await client.get<{ data: ProcurementActivityEntry[] }>(
      `/purchase-orders/${poId}/activity`
    );
    return res.data.data;
  },

  // ── Pipeline (Phase 4A) ────────────────────────────────────────────────────

  getPipeline: async (mrId: string): Promise<MRPipeline> => {
    const res = await client.get<{ data: MRPipeline }>(`/procurement/mrs/${mrId}/pipeline`);
    return res.data.data;
  },

  approveQuote: async (mrId: string, quoteId: string, notes?: string): Promise<{ quote_id: string; status: string }> => {
    const res = await client.post<{ data: { quote_id: string; status: string } }>(
      `/procurement/mrs/${mrId}/quotes/${quoteId}/approve`,
      { notes: notes ?? null },
    );
    return res.data.data;
  },

  voteQuote: async (mrId: string, quoteId: string, notes?: string): Promise<{ quote_id: string; vote_count: number; status: string }> => {
    const res = await client.post<{ data: { quote_id: string; vote_count: number; status: string } }>(
      `/procurement/mrs/${mrId}/quotes/${quoteId}/vote`,
      { notes: notes ?? null },
    );
    return res.data.data;
  },

  listQuoteVotes: async (mrId: string): Promise<QuoteVote[]> => {
    const res = await client.get<{ data: QuoteVote[] }>(`/procurement/mrs/${mrId}/quote-votes`);
    return res.data.data;
  },

  finalizePOs: async (mrId: string): Promise<{
    pos: Array<{ po_id: string; po_number: string; supplier_name: string | null; total_amount: number; email: { status: string; sent_to: string | null } }>;
    count: number;
  }> => {
    const res = await client.post<{ data: { pos: Array<{ po_id: string; po_number: string; supplier_name: string | null; total_amount: number; email: { status: string; sent_to: string | null } }>; count: number } }>(
      `/procurement/mrs/${mrId}/finalize-pos`,
    );
    return res.data.data;
  },

  rejectQuote: async (mrId: string, quoteId: string, reason: string, tryAnotherSupplierId?: string): Promise<{ quote_id: string; status: string }> => {
    const res = await client.post<{ data: { quote_id: string; status: string } }>(
      `/procurement/mrs/${mrId}/quotes/${quoteId}/reject`,
      { reason, try_another_supplier_id: tryAnotherSupplierId ?? null },
    );
    return res.data.data;
  },

  deleteQuote: async (mrId: string, quoteId: string): Promise<void> => {
    await client.delete(`/procurement/mrs/${mrId}/quotes/${quoteId}`);
  },

  deleteMR: async (mrId: string): Promise<void> => {
    await client.delete(`/material-requests/${mrId}`);
  },
};
