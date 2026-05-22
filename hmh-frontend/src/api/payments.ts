import client from "./client";

export type PaymentType   = "SUPPLIER" | "LABOUR" | "OTHER";
export type PaymentStatus = "PENDING" | "APPROVED" | "PAID" | "FAILED" | "CANCELLED";

/** Common payment methods — free text in DB but displayed as suggestions. */
export const PAYMENT_METHODS = ["EFT", "CASH", "CHEQUE", "BANK_TRANSFER", "CREDIT_CARD", "OTHER"] as const;

export interface Payment {
  id: string;
  invoice_id: string | null;
  supplier_id: string | null;
  project_id: string;
  payment_type: PaymentType;
  payment_reference: string | null;
  payment_date: string | null;
  amount_paid: number;
  status: PaymentStatus;
  approved_by: string | null;
  captured_by: string | null;
  notes: string | null;
  // Phase 3L
  payment_method: string | null;
  lot_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaymentCreate {
  payment_type: PaymentType;
  amount_paid: number;
  invoice_id?: string | null;
  supplier_id?: string | null;
  payment_reference?: string | null;
  payment_date?: string | null;
  notes?: string | null;
  // Phase 3L
  payment_method?: string | null;
  lot_id?: string | null;
}

export interface PaymentUpdate {
  status?: PaymentStatus;
  payment_reference?: string | null;
  payment_date?: string | null;
  notes?: string | null;
  payment_method?: string | null;
}

export interface InvoiceReconciliation {
  invoice_id:     string;
  invoice_number: string;
  invoice_date:   string | null;
  due_date:       string | null;
  total_amount:   number;
  total_paid:     number;
  outstanding:    number;
  is_overpaid:    boolean;
  status:         string;
  payments: Array<{
    id:                string;
    amount_paid:       number;
    payment_date:      string | null;
    payment_method:    string | null;
    payment_reference: string | null;
    payment_type:      string;
    status:            string;
    notes:             string | null;
    captured_by_name:  string | null;
    created_at:        string;
  }>;
}

export interface PaymentReport {
  project_id:    string;
  total_paid:    number;
  payment_count: number;
  by_supplier: Array<{ supplier_id: string; supplier_name: string | null; total: number; count: number }>;
  by_month:    Array<{ month: string; total: number; count: number }>;
}

export interface PaymentActivityEntry {
  type:        "status" | "document";
  timestamp:   string;
  actor:       string | null;
  description: string;
  url?:        string;
  is_image?:   boolean;
}

export const paymentsApi = {
  list: async (projectId: string): Promise<Payment[]> => {
    const res = await client.get<{ data: Payment[] }>(`/projects/${projectId}/payments/`);
    return res.data.data;
  },

  get: async (paymentId: string): Promise<Payment> => {
    const res = await client.get<{ data: Payment }>(`/payments/${paymentId}`);
    return res.data.data;
  },

  create: async (projectId: string, body: PaymentCreate): Promise<Payment> => {
    const res = await client.post<{ data: Payment }>(`/projects/${projectId}/payments/`, body);
    return res.data.data;
  },

  update: async (paymentId: string, body: PaymentUpdate): Promise<Payment> => {
    const res = await client.patch<{ data: Payment }>(`/payments/${paymentId}`, body);
    return res.data.data;
  },

  // Phase 3L additions
  getActivity: async (paymentId: string): Promise<PaymentActivityEntry[]> => {
    const res = await client.get<{ data: PaymentActivityEntry[] }>(`/payments/${paymentId}/activity`);
    return res.data.data;
  },

  getInvoiceReconciliation: async (invoiceId: string): Promise<InvoiceReconciliation> => {
    const res = await client.get<{ data: InvoiceReconciliation }>(`/invoices/${invoiceId}/reconciliation`);
    return res.data.data;
  },

  getReport: async (
    projectId: string,
    params?: { from_date?: string; to_date?: string; supplier_id?: string }
  ): Promise<PaymentReport> => {
    const res = await client.get<{ data: PaymentReport }>(
      `/projects/${projectId}/payments/report`,
      { params }
    );
    return res.data.data;
  },
};
