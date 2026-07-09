import client from "./client";
import { Supplier } from "./suppliers";
import { Company, CompanyCreate } from "./projects";

export type { Company, CompanyCreate };

export interface CompanyWithSuppliers extends Company {
  suppliers: Supplier[];
}

export interface CompanyUpdate {
  name?: string;
  registration_number?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  address?: string | null;
  notes?: string | null;
}

export const companiesApi = {
  list: async (): Promise<Company[]> => {
    const res = await client.get<{ data: Company[] }>("/companies/");
    return res.data.data;
  },

  get: async (id: string): Promise<CompanyWithSuppliers> => {
    const res = await client.get<{ data: CompanyWithSuppliers }>(`/companies/${id}`);
    return res.data.data;
  },

  create: async (body: CompanyCreate): Promise<Company> => {
    const res = await client.post<{ data: Company }>("/companies/", body);
    return res.data.data;
  },

  update: async (id: string, body: CompanyUpdate): Promise<Company> => {
    const res = await client.patch<{ data: Company }>(`/companies/${id}`, body);
    return res.data.data;
  },

  delete: async (id: string): Promise<void> => {
    await client.delete(`/companies/${id}`);
  },

  linkSupplier: async (companyId: string, supplierId: string): Promise<void> => {
    await client.post(`/companies/${companyId}/suppliers/${supplierId}`);
  },

  unlinkSupplier: async (companyId: string, supplierId: string): Promise<void> => {
    await client.delete(`/companies/${companyId}/suppliers/${supplierId}`);
  },

  getProjectSuppliers: async (projectId: string): Promise<Supplier[]> => {
    const res = await client.get<{ data: Supplier[] }>(`/companies/project/${projectId}/suppliers`);
    return res.data.data;
  },
};
