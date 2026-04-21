import client from "./client";

export type PaymentType = "SUPPLIER" | "LABOUR" | "OTHER";
export type PaymentStatus = "PENDING" | "APPROVED" | "PAID" | "FAILED" | "CANCELLED";

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
}

export interface PaymentUpdate {
  status?: PaymentStatus;
  payment_reference?: string | null;
  payment_date?: string | null;
  notes?: string | null;
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
};
