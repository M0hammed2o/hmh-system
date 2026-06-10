import client from "./client";

export type QuotationStatus = "DRAFT" | "SENT" | "RECEIVED" | "APPROVED" | "REJECTED" | "EXPIRED";

export interface Quotation {
  id: string;
  quote_number: string;
  supplier_id: string | null;
  project_id: string | null;
  material_request_id: string | null;
  status: QuotationStatus;
  quote_date: string | null;
  expiry_date: string | null;
  net_amount: number;
  vat_amount: number;
  gross_amount: number;
  vat_rate_used: number;
  notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface QuotationCreate {
  quote_number: string;
  supplier_id?: string | null;
  project_id?: string | null;
  material_request_id?: string | null;
  status?: QuotationStatus;
  quote_date?: string | null;
  expiry_date?: string | null;
  net_amount?: number;
  vat_amount?: number;
  gross_amount?: number;
  vat_rate_used?: number;
  notes?: string | null;
}

export interface QuotationUpdate {
  status?: QuotationStatus;
  quote_date?: string | null;
  expiry_date?: string | null;
  net_amount?: number;
  vat_amount?: number;
  gross_amount?: number;
  vat_rate_used?: number;
  notes?: string | null;
  project_id?: string | null;
}

export const QUOTATION_STATUS_LABELS: Record<QuotationStatus, string> = {
  DRAFT:    "Draft",
  SENT:     "Sent",
  RECEIVED: "Received",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  EXPIRED:  "Expired",
};

export const quotationsApi = {
  listBySupplier: async (supplierId: string): Promise<Quotation[]> => {
    const res = await client.get<{ data: Quotation[] }>("/quotations/", {
      params: { supplier_id: supplierId },
    });
    return res.data.data;
  },

  get: async (quotationId: string): Promise<Quotation> => {
    const res = await client.get<{ data: Quotation }>(`/quotations/${quotationId}`);
    return res.data.data;
  },

  create: async (data: QuotationCreate): Promise<Quotation> => {
    const res = await client.post<{ data: Quotation }>("/quotations/", data);
    return res.data.data;
  },

  update: async (quotationId: string, data: QuotationUpdate): Promise<Quotation> => {
    const res = await client.patch<{ data: Quotation }>(`/quotations/${quotationId}`, data);
    return res.data.data;
  },

  delete: async (quotationId: string): Promise<void> => {
    await client.delete(`/quotations/${quotationId}`);
  },
};
