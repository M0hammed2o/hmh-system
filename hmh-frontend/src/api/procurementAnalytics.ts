import client from "./client";

// ── Dashboard ──────────────────────────────────────────────────────────────

export interface ProcurementDashboard {
  total_spend: number;
  spend_this_month: number;
  open_pos: number;
  pending_deliveries: number;
  pending_invoices: number;
  pending_reconciliations: number;
  approved_payments: number;
  outstanding_payments: number;
}

export interface DashboardFilters {
  project_id?: string;
  supplier_id?: string;
  date_from?: string;
  date_to?: string;
}

// ── Supplier Scorecard ──────────────────────────────────────────────────────

export interface SupplierMetrics {
  delivery_reliability: number;
  reconciliation_match_rate: number;
  quote_acceptance_rate: number;
  delivery_speed_score: number;
  avg_delivery_days: number | null;
}

export interface SupplierStats {
  total_spend: number;
  total_pos: number;
  total_deliveries: number;
  total_invoices: number;
  total_quotes: number;
  total_reconciliations: number;
  open_issues: number;
}

export interface SupplierScore {
  supplier_id: string;
  supplier_name: string;
  supplier_code: string;
  score: number;
  metrics: SupplierMetrics;
  stats: SupplierStats;
}

// ── Spend Analysis ──────────────────────────────────────────────────────────

export interface SpendPerProject {
  project_id: string;
  project_name: string;
  spend: number;
}

export interface SupplierSpendRow {
  supplier_id: string;
  supplier_name: string;
  supplier_code: string;
  total_spend: number;
  po_count: number;
  spend_this_month: number;
  spend_this_year: number;
  spend_per_project: SpendPerProject[];
}

export interface SupplierSpendData {
  top_suppliers: SupplierSpendRow[];
}

// ── Project Analytics ───────────────────────────────────────────────────────

export interface ProjectAnalyticsRow {
  project_id: string;
  project_name: string;
  project_code: string;
  project_status: string;
  boq_budget: number;
  total_spend: number;
  budget_variance: number;
  budget_variance_pct: number;
  open_pos: number;
  outstanding_deliveries: number;
  outstanding_invoices: number;
}

// ── Price History ───────────────────────────────────────────────────────────

export interface PriceHistoryRow {
  description: string;
  item_id: string | null;
  unit: string | null;
  rate: number;
  quantity_ordered: number;
  line_total: number | null;
  po_date: string | null;
  po_number: string;
  supplier_id: string | null;
  supplier_name: string | null;
  project_id: string | null;
}

// ── Quotation Comparison ────────────────────────────────────────────────────

export interface QuoteRow {
  quotation_id: string;
  quote_number: string;
  supplier_id: string | null;
  supplier_name: string;
  quote_date: string | null;
  expiry_date: string | null;
  status: string;
  net_amount: number;
  vat_amount: number;
  gross_amount: number;
  vat_rate: number;
  is_lowest: boolean;
}

export interface QuotationComparison {
  material_request_id: string;
  mr_number: string;
  quotation_count: number;
  quotes: QuoteRow[];
  lowest_quote_id: string | null;
  lowest_amount: number | null;
}

export interface MRForComparison {
  material_request_id: string;
  mr_number: string;
  project_id: string | null;
  quote_count: number;
}

// ── Savings ─────────────────────────────────────────────────────────────────

export interface SavingsRow {
  project_id: string;
  project_name: string;
  project_code: string;
  boq_budget: number;
  actual_spend: number;
  variance: number;
  variance_pct: number;
  has_boq: boolean;
  status: "under_budget" | "over_budget";
}

// ── API client ───────────────────────────────────────────────────────────────

const BASE = "/procurement-analytics";

export const analyticsApi = {
  dashboard: async (filters?: DashboardFilters): Promise<ProcurementDashboard> => {
    const res = await client.get<{ data: ProcurementDashboard }>(`${BASE}/dashboard`, { params: filters });
    return res.data.data;
  },

  allSupplierScores: async (): Promise<SupplierScore[]> => {
    const res = await client.get<{ data: SupplierScore[] }>(`${BASE}/supplier-performance`);
    return res.data.data;
  },

  supplierScore: async (supplierId: string): Promise<SupplierScore> => {
    const res = await client.get<{ data: SupplierScore }>(`${BASE}/supplier-performance/${supplierId}`);
    return res.data.data;
  },

  supplierSpend: async (limit = 10): Promise<SupplierSpendData> => {
    const res = await client.get<{ data: SupplierSpendData }>(`${BASE}/supplier-spend`, { params: { limit } });
    return res.data.data;
  },

  projectAnalytics: async (projectId?: string): Promise<ProjectAnalyticsRow[]> => {
    const res = await client.get<{ data: ProjectAnalyticsRow[] }>(`${BASE}/project-analytics`, {
      params: projectId ? { project_id: projectId } : undefined,
    });
    return res.data.data;
  },

  priceHistory: async (params: {
    item_id?: string;
    search?: string;
    project_id?: string;
    supplier_id?: string;
    limit?: number;
  }): Promise<PriceHistoryRow[]> => {
    const res = await client.get<{ data: PriceHistoryRow[] }>(`${BASE}/price-history`, { params });
    return res.data.data;
  },

  mrsWithMultipleQuotes: async (projectId?: string): Promise<MRForComparison[]> => {
    const res = await client.get<{ data: MRForComparison[] }>(`${BASE}/quotation-comparison/mrs`, {
      params: projectId ? { project_id: projectId } : undefined,
    });
    return res.data.data;
  },

  quotationComparison: async (mrId: string): Promise<QuotationComparison> => {
    const res = await client.get<{ data: QuotationComparison }>(`${BASE}/quotation-comparison/${mrId}`);
    return res.data.data;
  },

  savingsReport: async (projectId?: string): Promise<SavingsRow[]> => {
    const res = await client.get<{ data: SavingsRow[] }>(`${BASE}/savings-report`, {
      params: projectId ? { project_id: projectId } : undefined,
    });
    return res.data.data;
  },

  // Export URLs (trigger browser download)
  reportUrl: (type: string, format: "excel" | "pdf") =>
    `/api/v1/procurement-analytics/reports/${type}/${format}`,
};
