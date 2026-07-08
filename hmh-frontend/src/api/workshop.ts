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

export interface WorkshopMRApproval {
  id: string;
  mr_id: string;
  approved_by: string | null;
  approved_at: string;
  is_override: boolean;
  notes: string | null;
  voter: { id: string; full_name: string; email: string } | null;
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
  approvals: WorkshopMRApproval[];
  vote_count: number;
  // Resolved names (embedded by backend)
  site: { id: string; name: string; site_type: string } | null;
  vehicle: { id: string; registration: string; name: string } | null;
}

export interface WorkshopIssuance {
  id: string;
  item_id: string;
  vehicle_id: string;
  workshop_mr_id: string | null;
  quantity_issued: number;
  issued_by: string;
  issued_at: string;
  notes: string | null;
  created_at: string;
  item: { id: string; name: string; unit: string; part_number: string | null } | null;
  vehicle: { id: string; registration: string; name: string } | null;
}

export interface WorkshopIssuanceCreate {
  item_id: string;
  vehicle_id: string;
  workshop_mr_id?: string | null;
  quantity_issued: number;
  notes?: string | null;
}

export interface WorkshopSupplierLink {
  id: string;
  category_id: string;
  supplier_id: string;
  is_preferred: boolean;
  category: { id: string; name: string; description: string | null } | null;
  supplier: { id: string; name: string; email: string | null } | null;
}

export interface WorkshopCategoryCreate {
  name: string;
  description?: string | null;
}

export interface WorkshopItemCreate {
  category_id: string;
  name: string;
  part_number?: string | null;
  unit?: string;
  description?: string | null;
  reorder_level?: number | null;
}

export interface WorkshopItemUpdate {
  name?: string;
  part_number?: string | null;
  unit?: string;
  description?: string | null;
  reorder_level?: number | null;
  is_active?: boolean;
}

export interface WorkshopSupplierLinkCreate {
  category_id: string;
  supplier_id: string;
  is_preferred?: boolean;
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

  castVote: async (mrId: string, notes?: string): Promise<WorkshopMR> => {
    const res = await client.post<{ data: WorkshopMR }>(`/workshop/mrs/${mrId}/vote`, {
      notes: notes ?? null,
    });
    return res.data.data;
  },

  // ── Categories ────────────────────────────────────────────────────────────

  createCategory: async (body: WorkshopCategoryCreate): Promise<WorkshopCategory> => {
    const res = await client.post<{ data: WorkshopCategory }>("/workshop/categories/", body);
    return res.data.data;
  },

  updateCategory: async (categoryId: string, body: WorkshopCategoryCreate): Promise<WorkshopCategory> => {
    const res = await client.patch<{ data: WorkshopCategory }>(`/workshop/categories/${categoryId}`, body);
    return res.data.data;
  },

  // ── Items ─────────────────────────────────────────────────────────────────

  createItem: async (body: WorkshopItemCreate): Promise<WorkshopItem> => {
    const res = await client.post<{ data: WorkshopItem }>("/workshop/items/", body);
    return res.data.data;
  },

  updateItem: async (itemId: string, body: WorkshopItemUpdate): Promise<WorkshopItem> => {
    const res = await client.patch<{ data: WorkshopItem }>(`/workshop/items/${itemId}`, body);
    return res.data.data;
  },

  adjustStock: async (itemId: string, quantityDelta: number): Promise<{ quantity_on_hand: number }> => {
    const res = await client.post<{ data: { quantity_on_hand: number } }>(
      `/workshop/items/${itemId}/adjust-stock`,
      { quantity_delta: quantityDelta },
    );
    return res.data.data;
  },

  // ── Supplier links ────────────────────────────────────────────────────────

  listSupplierLinks: async (categoryId?: string): Promise<WorkshopSupplierLink[]> => {
    const params: Record<string, string> = {};
    if (categoryId) params.category_id = categoryId;
    const res = await client.get<{ data: WorkshopSupplierLink[] }>("/workshop/supplier-links/", { params });
    return res.data.data;
  },

  createSupplierLink: async (body: WorkshopSupplierLinkCreate): Promise<WorkshopSupplierLink> => {
    const res = await client.post<{ data: WorkshopSupplierLink }>("/workshop/supplier-links/", body);
    return res.data.data;
  },

  deleteSupplierLink: async (linkId: string): Promise<void> => {
    await client.delete(`/workshop/supplier-links/${linkId}`);
  },

  // ── Issuances ─────────────────────────────────────────────────────────────

  listIssuances: async (opts?: { vehicle_id?: string; item_id?: string }): Promise<WorkshopIssuance[]> => {
    const params: Record<string, string> = {};
    if (opts?.vehicle_id) params.vehicle_id = opts.vehicle_id;
    if (opts?.item_id)    params.item_id    = opts.item_id;
    const res = await client.get<{ data: WorkshopIssuance[] }>("/workshop/issuances/", { params });
    return res.data.data;
  },

  issueParts: async (body: WorkshopIssuanceCreate): Promise<WorkshopIssuance> => {
    const res = await client.post<{ data: WorkshopIssuance }>("/workshop/issuances/", body);
    return res.data.data;
  },
};
