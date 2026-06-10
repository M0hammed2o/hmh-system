import client from "./client";

export type ReconciliationStatus =
  | "PENDING"
  | "MATCHED"
  | "VARIANCE_DETECTED"
  | "APPROVED"
  | "REJECTED";

export const RECON_STATUS_LABELS: Record<ReconciliationStatus, string> = {
  PENDING:           "Pending",
  MATCHED:           "Matched",
  VARIANCE_DETECTED: "Variance Detected",
  APPROVED:          "Approved",
  REJECTED:          "Rejected",
};

export interface VarianceField {
  name: string;
  a_label: string;
  a_value: number;
  b_label: string;
  b_value: number;
  diff: number;
  diff_pct: number;
  has_variance: boolean;
}

export interface VarianceComparison {
  label: string;
  fields: VarianceField[];
}

export interface VarianceData {
  comparisons: VarianceComparison[];
  has_variance: boolean;
  total_variances: number;
  threshold_rands: number;
}

export interface POSummary {
  po_id: string;
  po_number: string;
  po_date: string | null;
  status: string;
  subtotal_amount: number;
  vat_amount: number;
  total_amount: number;
  supplier_id: string;
  supplier_name: string | null;
  project_id: string;
}

export interface InvoiceSummary {
  invoice_id: string;
  invoice_number: string;
  invoice_date: string | null;
  due_date: string | null;
  subtotal_amount: number;
  vat_amount: number;
  total_amount: number;
  status: string;
  vat_rate_used: number | null;
}

export interface DeliverySummary {
  delivery_id: string;
  delivery_number: string | null;
  delivery_date: string | null;
  status: string;
  items_count: number;
}

export interface QuotationSummary {
  quotation_id: string;
  quote_number: string;
  quote_date: string | null;
  status: string;
  net_amount: number;
  vat_amount: number;
  gross_amount: number;
  vat_rate_used: number;
}

export interface MRSummary {
  mr_id: string;
  mr_number: string;
  status: string;
}

export interface Reconciliation {
  id: string;
  reconciliation_number: string;
  status: ReconciliationStatus;
  purchase_order_id: string | null;
  invoice_id: string | null;
  delivery_id: string | null;
  quotation_id: string | null;
  material_request_id: string | null;
  variance_data: VarianceData | null;
  notes: string | null;
  reviewed_by: string | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  // resolved summaries
  po: POSummary | null;
  invoice: InvoiceSummary | null;
  delivery: DeliverySummary | null;
  quotation: QuotationSummary | null;
  material_request: MRSummary | null;
}

export interface ReconciliationDashboard {
  pending: number;
  matched: number;
  variance_detected: number;
  approved: number;
  rejected: number;
  awaiting_review: number;
  total: number;
}

export interface ReconciliationCreate {
  purchase_order_id: string;
  invoice_id?: string | null;
  delivery_id?: string | null;
  quotation_id?: string | null;
  material_request_id?: string | null;
  notes?: string | null;
}

export interface ReconciliationUpdate {
  status?: ReconciliationStatus;
  notes?: string | null;
  invoice_id?: string | null;
  delivery_id?: string | null;
  quotation_id?: string | null;
}

export const reconciliationApi = {
  dashboard: async (): Promise<ReconciliationDashboard> => {
    const res = await client.get<{ data: ReconciliationDashboard }>("/reconciliations/dashboard");
    return res.data.data;
  },

  list: async (params?: {
    status?: ReconciliationStatus;
    supplier_id?: string;
    project_id?: string;
    limit?: number;
    offset?: number;
  }): Promise<Reconciliation[]> => {
    const res = await client.get<{ data: Reconciliation[] }>("/reconciliations/", { params });
    return res.data.data;
  },

  get: async (id: string): Promise<Reconciliation> => {
    const res = await client.get<{ data: Reconciliation }>(`/reconciliations/${id}`);
    return res.data.data;
  },

  create: async (body: ReconciliationCreate): Promise<Reconciliation> => {
    const res = await client.post<{ data: Reconciliation }>("/reconciliations/", body);
    return res.data.data;
  },

  update: async (id: string, body: ReconciliationUpdate): Promise<Reconciliation> => {
    const res = await client.patch<{ data: Reconciliation }>(`/reconciliations/${id}`, body);
    return res.data.data;
  },

  recompute: async (id: string): Promise<Reconciliation> => {
    const res = await client.post<{ data: Reconciliation }>(`/reconciliations/${id}/recompute`);
    return res.data.data;
  },

  delete: async (id: string): Promise<void> => {
    await client.delete(`/reconciliations/${id}`);
  },
};
