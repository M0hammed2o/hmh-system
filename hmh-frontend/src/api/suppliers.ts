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
};
