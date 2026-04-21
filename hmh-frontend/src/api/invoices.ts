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

export const invoicesApi = {
  list: async (projectId: string): Promise<Invoice[]> => {
    const res = await client.get<{ data: Invoice[] }>(`/projects/${projectId}/invoices/`);
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
