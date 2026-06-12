import client from "./client";

export interface MuniInvoiceItem {
  id?:          string;
  sort_order:   number;
  line_number:  string | null;
  description:  string;
  quantity:     number | null;
  unit_price:   number | null;
  total:        number | null;
  disc_pct:     number | null;
  comments:     string | null;
}

export interface MuniInvoice {
  id:             string;
  invoice_number: string;
  cert_number:    string | null;
  project_id:     string;
  invoice_date:   string;
  due_date:       string | null;
  client_name:    string;
  client_vat_no:  string | null;
  client_address: string | null;
  company_email:  string | null;
  project_description: string | null;
  contract_reference:  string | null;
  subtotal:        number;
  previously_paid: number | null;
  vat_rate:        number;
  vat_amount:      number;
  total_due:       number;
  notes:          string | null;
  bank_name:      string | null;
  account_number: string | null;
  branch_name:    string | null;
  branch_code:    string | null;
  status:         string;
  created_at:     string | null;
  items:          MuniInvoiceItem[];
}

export type MuniInvoiceCreate = Omit<MuniInvoice, "id" | "project_id" | "subtotal" | "vat_amount" | "total_due" | "created_at">;

export const muniInvoiceApi = {
  list: async (projectId: string, status?: string): Promise<MuniInvoice[]> => {
    const params: Record<string, string> = {};
    if (status) params.status = status;
    const res = await client.get<{ data: MuniInvoice[] }>(
      `/projects/${projectId}/municipality-invoices/`, { params }
    );
    return res.data.data;
  },

  get: async (id: string): Promise<MuniInvoice> => {
    const res = await client.get<{ data: MuniInvoice }>(`/municipality-invoices/${id}`);
    return res.data.data;
  },

  create: async (projectId: string, body: Partial<MuniInvoiceCreate>): Promise<MuniInvoice> => {
    const res = await client.post<{ data: MuniInvoice }>(
      `/projects/${projectId}/municipality-invoices/`, body
    );
    return res.data.data;
  },

  update: async (id: string, body: Partial<MuniInvoice>): Promise<MuniInvoice> => {
    const res = await client.patch<{ data: MuniInvoice }>(`/municipality-invoices/${id}`, body);
    return res.data.data;
  },

  delete: async (id: string): Promise<void> => {
    await client.delete(`/municipality-invoices/${id}`);
  },

  exportExcel: (id: string): string =>
    `/municipality-invoices/${id}/export/excel`,
};
