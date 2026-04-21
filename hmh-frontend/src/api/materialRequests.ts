import client from "./client";

export type MRStatus = "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED";

export interface MRItem {
  id: string;
  material_request_id: string;
  item_id: string | null;
  boq_item_id: string | null;
  description: string;
  quantity_requested: number;
  unit: string | null;
  notes: string | null;
  created_at: string;
}

export interface MaterialRequest {
  id: string;
  request_number: string;
  project_id: string;
  site_id: string | null;
  lot_id: string | null;
  requested_by_user_id: string;
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
}

export interface MRItemCreate {
  description: string;
  quantity_requested: number;
  unit?: string | null;
  item_id?: string | null;
  boq_item_id?: string | null;
  notes?: string | null;
}

export interface MaterialRequestCreate {
  site_id?: string | null;
  lot_id?: string | null;
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
  list: async (projectId: string): Promise<MaterialRequest[]> => {
    const res = await client.get<{ data: MaterialRequest[] }>(
      `/projects/${projectId}/material-requests/`
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
};
