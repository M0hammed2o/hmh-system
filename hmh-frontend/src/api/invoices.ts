import client from "./client";
import type { RecordStatus } from "./purchaseOrders";

export interface Invoice {
  id: string;
  invoice_number: string;
  supplier_id: string;
  project_id: string;
  site_id: string | null;
  purchase_order_id: string | null;
  invoice_date: string | null;
  due_date: string | null;
  subtotal_amount: number | null;
  vat_amount: number | null;
  total_amount: number;
  status: RecordStatus;
  captured_by: string | null;
  captured_at: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface InvoiceCreate {
  invoice_number: string;
  supplier_id: string;
  total_amount: number;
  site_id?: string | null;
  purchase_order_id?: string | null;
  invoice_date?: string | null;
  due_date?: string | null;
  subtotal_amount?: number | null;
  vat_amount?: number | null;
  notes?: string | null;
}

export interface InvoiceUpdate {
  status?: RecordStatus;
  due_date?: string | null;
  total_amount?: number;
  subtotal_amount?: number | null;
  vat_amount?: number | null;
  notes?: string | null;
}

export interface EnrichedInvoice {
  invoice_id:         string;
  invoice_number:     string;
  supplier_id:        string | null;
  supplier_name:      string | null;
  purchase_order_id:  string | null;
  po_number:          string | null;
  invoice_date:       string | null;
  due_date:           string | null;
  total_amount:       number;
  paid_amount:        number;
  outstanding_amount: number;
  status:             string;
  match_status:       string;
  is_overdue:         boolean;
  notes:              string | null;
  captured_at:        string | null;
}

export const invoicesApi = {
  list: async (projectId: string): Promise<Invoice[]> => {
    const res = await client.get<{ data: Invoice[] }>(`/projects/${projectId}/invoices/`);
    return res.data.data;
  },

  listEnriched: async (projectId: string): Promise<EnrichedInvoice[]> => {
    const res = await client.get<{ data: EnrichedInvoice[] }>(
      `/projects/${projectId}/invoices/enriched`
    );
    return res.data.data;
  },

  get: async (invoiceId: string): Promise<Invoice> => {
    const res = await client.get<{ data: Invoice }>(`/invoices/${invoiceId}`);
    return res.data.data;
  },

  create: async (projectId: string, body: InvoiceCreate): Promise<Invoice> => {
    const res = await client.post<{ data: Invoice }>(`/projects/${projectId}/invoices/`, body);
    return res.data.data;
  },

  update: async (invoiceId: string, body: InvoiceUpdate): Promise<Invoice> => {
    const res = await client.patch<{ data: Invoice }>(`/invoices/${invoiceId}`, body);
    return res.data.data;
  },
};
