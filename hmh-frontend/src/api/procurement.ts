import client from "./client";

export type MRStatus =
  | "DRAFT" | "SUBMITTED" | "PENDING_APPROVAL" | "APPROVED" | "REJECTED"
  | "CONVERTED_TO_PO" | "ORDERED" | "PARTIALLY_RECEIVED" | "RECEIVED"
  | "INVOICED" | "CLOSED" | "CANCELLED";   // INVOICED added Phase 3I

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
export type DeliveryDestination = "MAIN_WAREHOUSE" | "SITE_STORE" | "LOT";
export type POStatus = MRStatus;

export interface MRItem {
  id: string;
  material_request_id: string;
  item_id: string | null;
  boq_item_id: string | null;
  description: string;
  requested_quantity: number;
  approved_quantity: number | null;
  over_boq_quantity: number | null;
  unit: string | null;
  remarks: string | null;
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
}

export interface MRItemCreate {
  item_id?: string;
  boq_item_id?: string;
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

  approveMR: async (mrId: string, overBoqReason?: string): Promise<MaterialRequest> => {
    const res = await client.post<{ data: MaterialRequest }>(
      `/material-requests/${mrId}/approve`,
      { over_boq_reason: overBoqReason ?? null }
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
};
