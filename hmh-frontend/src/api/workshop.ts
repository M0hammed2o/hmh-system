import client from "./client";

export type MRPriority = "LOW" | "NORMAL" | "HIGH" | "URGENT";
export type WorkshopMRStatus = "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED";

export interface WorkshopCategory {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkshopItem {
  id: string;
  category_id: string;
  name: string;
  part_number: string | null;
  unit: string;
  description: string | null;
  reorder_level: number | null;
  is_active: boolean;
  quantity_on_hand: number;
  created_at: string;
  updated_at: string;
}

export interface WorkshopMRLineBrief {
  id: string;
  workshop_mr_id: string;
  item_id: string;
  quantity_requested: number;
  quantity_approved: number | null;
  preferred_supplier_id: string | null;
  remarks: string | null;
  item: { id: string; name: string; unit: string; part_number: string | null } | null;
}

export interface WorkshopMR {
  id: string;
  mr_number: string;
  site_id: string;
  vehicle_id: string;
  reason: string;
  status: WorkshopMRStatus;
  priority: MRPriority;
  needed_by_date: string | null;
  requested_by: string;
  approved_by: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  lines: WorkshopMRLineBrief[];
}

export interface WorkshopMRLineCreate {
  item_id: string;
  quantity_requested: number;
  preferred_supplier_id?: string;
  remarks?: string;
}

export interface WorkshopMRCreate {
  site_id: string;
  vehicle_id: string;
  reason: string;
  priority?: MRPriority;
  needed_by_date?: string | null;
  notes?: string | null;
  lines: WorkshopMRLineCreate[];
}

export const workshopApi = {
  listCategories: async (): Promise<WorkshopCategory[]> => {
    const res = await client.get<{ data: WorkshopCategory[] }>("/workshop/categories/");
    return res.data.data;
  },

  listItems: async (categoryId?: string): Promise<WorkshopItem[]> => {
    const params: Record<string, string> = { active_only: "true" };
    if (categoryId) params.category_id = categoryId;
    const res = await client.get<{ data: WorkshopItem[] }>("/workshop/items/", { params });
    return res.data.data;
  },

  listMRs: async (opts?: {
    site_id?: string;
    vehicle_id?: string;
    status?: WorkshopMRStatus;
  }): Promise<WorkshopMR[]> => {
    const params: Record<string, string> = {};
    if (opts?.site_id)    params.site_id    = opts.site_id;
    if (opts?.vehicle_id) params.vehicle_id = opts.vehicle_id;
    if (opts?.status)     params.status     = opts.status;
    const res = await client.get<{ data: WorkshopMR[] }>("/workshop/mrs/", { params });
    return res.data.data;
  },

  getMR: async (mrId: string): Promise<WorkshopMR> => {
    const res = await client.get<{ data: WorkshopMR }>(`/workshop/mrs/${mrId}`);
    return res.data.data;
  },

  createMR: async (body: WorkshopMRCreate): Promise<WorkshopMR> => {
    const res = await client.post<{ data: WorkshopMR }>("/workshop/mrs/", body);
    return res.data.data;
  },

  submitMR: async (mrId: string): Promise<WorkshopMR> => {
    const res = await client.post<{ data: WorkshopMR }>(`/workshop/mrs/${mrId}/submit`);
    return res.data.data;
  },

  approveMR: async (mrId: string): Promise<WorkshopMR> => {
    const res = await client.post<{ data: WorkshopMR }>(`/workshop/mrs/${mrId}/approve`);
    return res.data.data;
  },

  rejectMR: async (mrId: string, reason?: string): Promise<WorkshopMR> => {
    const res = await client.post<{ data: WorkshopMR }>(`/workshop/mrs/${mrId}/reject`, {
      reason: reason ?? null,
    });
    return res.data.data;
  },
};
