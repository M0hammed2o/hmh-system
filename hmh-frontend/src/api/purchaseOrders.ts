import client from "./client";

export type RecordStatus =
  | "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED"
  | "SENT" | "RECEIVED" | "MATCHED" | "PAID" | "CANCELLED";

export type VatMode = "INCLUSIVE" | "EXCLUSIVE";

export interface POItem {
  id: string;
  purchase_order_id: string;
  item_id: string | null;
  boq_item_id: string | null;
  lot_id: string | null;
  stage_id: string | null;
  description: string;
  quantity_ordered: number;
  unit: string | null;
  rate: number | null;
  vat_mode: VatMode;
  vat_rate: number;
  line_total: number | null;
  // Computed by backend (per-line VAT breakdown)
  unit_price_excl: number | null;
  unit_price_incl: number | null;
  line_vat_amount: number | null;
  line_excl_vat: number | null;
  created_at: string;
}

export interface PurchaseOrder {
  id: string;
  po_number: string;
  project_id: string;
  site_id: string | null;
  supplier_id: string;
  material_request_id: string | null;
  status: RecordStatus;
  po_date: string;
  expected_delivery_date: string | null;
  subtotal_amount: number;
  vat_amount: number;
  total_amount: number;
  created_by: string;
  approved_by: string | null;
  sent_at: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  order_items: POItem[];
}

export interface POItemCreate {
  description: string;
  quantity_ordered: number;
  unit?: string | null;
  rate?: number | null;
  vat_mode?: VatMode;
  vat_rate?: number;
  item_id?: string | null;
  boq_item_id?: string | null;
  lot_id?: string | null;
  stage_id?: string | null;
}

export interface PurchaseOrderCreate {
  supplier_id: string;
  site_id?: string | null;
  material_request_id?: string | null;
  expected_delivery_date?: string | null;
  notes?: string | null;
  items: POItemCreate[];
}

export interface PurchaseOrderUpdate {
  status?: RecordStatus;
  expected_delivery_date?: string | null;
  notes?: string | null;
  site_id?: string | null;
}

export const purchaseOrdersApi = {
  list: async (projectId: string): Promise<PurchaseOrder[]> => {
    const res = await client.get<{ data: PurchaseOrder[] }>(
      `/projects/${projectId}/purchase-orders/`
    );
    return res.data.data;
  },

  get: async (poId: string): Promise<PurchaseOrder> => {
    const res = await client.get<{ data: PurchaseOrder }>(`/purchase-orders/${poId}`);
    return res.data.data;
  },

  create: async (projectId: string, body: PurchaseOrderCreate): Promise<PurchaseOrder> => {
    const res = await client.post<{ data: PurchaseOrder }>(
      `/projects/${projectId}/purchase-orders/`,
      body
    );
    return res.data.data;
  },

  update: async (poId: string, body: PurchaseOrderUpdate): Promise<PurchaseOrder> => {
    const res = await client.patch<{ data: PurchaseOrder }>(`/purchase-orders/${poId}`, body);
    return res.data.data;
  },

  addItem: async (poId: string, body: POItemCreate): Promise<POItem> => {
    const res = await client.post<{ data: POItem }>(`/purchase-orders/${poId}/items`, body);
    return res.data.data;
  },
};
