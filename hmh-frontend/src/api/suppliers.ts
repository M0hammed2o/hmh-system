import client from "./client";

export interface Supplier {
  id: string;
  name: string;
  code: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  contact_person: string | null;
  payment_terms: string | null;
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SupplierCreate {
  name: string;
  code?: string | null;
  email?: string | null;
  phone?: string | null;
  address?: string | null;
  contact_person?: string | null;
  payment_terms?: string | null;
  notes?: string | null;
}

export interface SupplierUpdate {
  name?: string;
  code?: string | null;
  email?: string | null;
  phone?: string | null;
  address?: string | null;
  contact_person?: string | null;
  payment_terms?: string | null;
  notes?: string | null;
  is_active?: boolean;
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
};
