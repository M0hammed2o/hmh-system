import client from "./client";

export type PricingMethod = "EX_VAT" | "INCL_VAT";

export interface Supplier {
  id: string;
  name: string;
  code: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  contact_person: string | null;
  whatsapp_number: string | null;
  vat_number: string | null;
  payment_terms: string | null;
  notes: string | null;
  is_active: boolean;
  vat_registered: boolean;
  pricing_method: PricingMethod;
  default_vat_rate: number;
  created_at: string;
  updated_at: string;
}

export interface SupplierOutstanding {
  supplier_id: string;
  supplier_name: string;
  po_total: number;
  invoice_total: number;
  paid_total: number;
  outstanding: number;
  overdue_amount: number;
}

export interface SupplierCreate {
  name: string;
  code?: string | null;
  email: string;
  phone?: string | null;
  address?: string | null;
  contact_person?: string | null;
  whatsapp_number?: string | null;
  vat_number?: string | null;
  payment_terms?: string | null;
  notes?: string | null;
  vat_registered?: boolean;
  pricing_method?: PricingMethod;
  default_vat_rate?: number;
}

export interface SupplierUpdate {
  name?: string;
  code?: string | null;
  email?: string | null;
  phone?: string | null;
  address?: string | null;
  contact_person?: string | null;
  whatsapp_number?: string | null;
  vat_number?: string | null;
  payment_terms?: string | null;
  notes?: string | null;
  is_active?: boolean;
  vat_registered?: boolean;
  pricing_method?: PricingMethod;
  default_vat_rate?: number;
}

export interface PODeliverySummary {
  delivery_id: string;
  delivery_number: string;
  delivery_date: string | null;
  status: string | null;
}

export interface POInvoiceSummary {
  invoice_id: string;
  invoice_number: string;
  total_amount: number;
  total_paid: number;
  balance_due: number;
  status: string;
  due_date: string | null;
  invoice_date: string | null;
}

export interface POQuotationSummary {
  quotation_id: string;
  quote_number: string;
  status: string;
  gross_amount: number;
  vat_rate_used: number;
  expiry_date: string | null;
}

export interface POChain {
  po_id: string;
  po_number: string;
  po_date: string | null;
  status: string;
  total_amount: number;
  subtotal_amount: number;
  vat_amount: number;
  project_id: string;
  quotation: POQuotationSummary | null;
  source_mr: { mr_id: string } | null;
  deliveries: PODeliverySummary[];
  invoices: POInvoiceSummary[];
  chain_status: {
    has_mr: boolean;
    has_quotation: boolean;
    quotation_status: string | null;
    po_status: string;
    has_delivery: boolean;
    delivery_status: string | null;
    has_invoice: boolean;
    invoice_status: string | null;
    total_invoiced: number;
    total_paid: number;
    is_fully_paid: boolean;
  };
}

export interface StandaloneQuotation {
  quotation_id: string;
  quote_number: string;
  status: string;
  quote_date: string | null;
  expiry_date: string | null;
  net_amount: number;
  vat_amount: number;
  gross_amount: number;
  vat_rate_used: number;
  notes: string | null;
  created_at: string;
}

export interface SupplierProcurementHistory {
  supplier_id: string;
  supplier_name: string;
  purchase_orders: POChain[];
  standalone_quotations: StandaloneQuotation[];
  po_count: number;
  quotation_count: number;
}

export const suppliersApi = {
  list: async (includeInactive = false): Promise<Supplier[]> => {
    const res = await client.get<{ data: Supplier[] }>("/suppliers/", {
      params: includeInactive ? { include_inactive: true } : {},
    });
    return res.data.data;
  },

  get: async (id: string): Promise<Supplier> => {
    const res = await client.get<{ data: Supplier }>(`/suppliers/${id}`);
    return res.data.data;
  },

  create: async (body: SupplierCreate): Promise<Supplier> => {
    const res = await client.post<{ data: Supplier }>("/suppliers/", body);
    return res.data.data;
  },

  update: async (id: string, body: SupplierUpdate): Promise<Supplier> => {
    const res = await client.patch<{ data: Supplier }>(`/suppliers/${id}`, body);
    return res.data.data;
  },

  outstanding: async (id: string): Promise<SupplierOutstanding> => {
    const res = await client.get<{ data: SupplierOutstanding }>(`/suppliers/${id}/outstanding`);
    return res.data.data;
  },

  delete: async (id: string): Promise<void> => {
    await client.delete(`/suppliers/${id}`);
  },

  procurementHistory: async (id: string): Promise<SupplierProcurementHistory> => {
    const res = await client.get<{ data: SupplierProcurementHistory }>(`/suppliers/${id}/procurement-history`);
    return res.data.data;
  },
};
