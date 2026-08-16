import client from "./client";

export type MRStatus = "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED";
export type ProcurementCategory = "MATERIAL" | "FUEL";

export interface MRItem {
  id: string;
  material_request_id: string;
  item_id: string | null;
  boq_item_id: string | null;
  description: string;
  requested_quantity: number;
  quantity_requested: number;   // alias — backend serialises as requested_quantity
  unit: string | null;
  remarks: string | null;
  notes: string | null;
  created_at: string;
}

export interface MaterialRequest {
  id: string;
  request_number: string;
  project_id: string;
  site_id: string | null;
  lot_id: string | null;
  requested_by: string;
  requested_by_user_id: string;
  preferred_supplier_id: string | null;
  procurement_category: ProcurementCategory;
  priority: string;
  delivery_destination: string;
  status: MRStatus;
  requested_date: string;
  needed_by_date: string | null;
  notes: string | null;
  approved_by: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
  created_at: string;
  updated_at: string;
  items: MRItem[];
  email_log: MREmailLog | null;
}

export interface MRItemCreate {
  description: string;
  quantity_requested: number;
  unit?: string | null;
  item_id?: string | null;
  boq_item_id?: string | null;
  preferred_supplier_id?: string | null;
  notes?: string | null;
}

export interface MREmailLog {
  id: string;
  status: "SENT" | "MOCK_SENT" | "FAILED";
  sent_to_email: string;
  sent_at: string | null;
  error_message: string | null;
  created_at: string;
}

export interface MaterialRequestCreate {
  site_id?: string | null;
  lot_id?: string | null;
  preferred_supplier_id?: string | null;
  procurement_category?: ProcurementCategory;
  delivery_destination?: "SITE_STORE" | "MAIN_WAREHOUSE" | null;
  needed_by_date?: string | null;
  notes?: string | null;
  items: MRItemCreate[];
}

export interface MaterialRequestUpdate {
  status?: MRStatus;
  needed_by_date?: string | null;
  notes?: string | null;
  rejection_reason?: string | null;
}

export const materialRequestsApi = {
  list: async (
    projectId: string,
    params?: { site_id?: string; status?: MRStatus }
  ): Promise<MaterialRequest[]> => {
    const res = await client.get<{ data: MaterialRequest[] }>(
      `/projects/${projectId}/material-requests/`,
      { params }
    );
    return res.data.data;
  },

  get: async (mrId: string): Promise<MaterialRequest> => {
    const res = await client.get<{ data: MaterialRequest }>(`/material-requests/${mrId}`);
    return res.data.data;
  },

  create: async (projectId: string, body: MaterialRequestCreate): Promise<MaterialRequest> => {
    const res = await client.post<{ data: MaterialRequest }>(
      `/projects/${projectId}/material-requests/`,
      body
    );
    return res.data.data;
  },

  update: async (mrId: string, body: MaterialRequestUpdate): Promise<MaterialRequest> => {
    const res = await client.patch<{ data: MaterialRequest }>(`/material-requests/${mrId}`, body);
    return res.data.data;
  },

  submit: async (mrId: string): Promise<MaterialRequest> => {
    const res = await client.post<{ data: MaterialRequest }>(`/material-requests/${mrId}/submit`);
    return res.data.data;
  },

  sendEmail: async (mrId: string): Promise<{ status: string; sent_to_email: string; sent_at: string | null; error: string | null }> => {
    const res = await client.post<{ data: { status: string; sent_to_email: string; sent_at: string | null; error: string | null } }>(
      `/material-requests/${mrId}/send-email`,
    );
    return res.data.data;
  },

  getEmailLog: async (mrId: string): Promise<MREmailLog[]> => {
    const res = await client.get<{ data: MREmailLog[] }>(`/material-requests/${mrId}/email-log`);
    return res.data.data;
  },
};
