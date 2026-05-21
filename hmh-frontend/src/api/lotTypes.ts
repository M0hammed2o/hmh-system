import client from "./client";

export interface LotType {
  id:                     string;
  project_id:             string;
  name:                   string;
  code:                   string | null;
  description:            string | null;
  default_template_id:    string | null;
  default_template_name:  string | null;
  lot_count:              number;
  created_at:             string;
  updated_at:             string;
}

export interface LotTypeLotSummary {
  id:            string;
  lot_number:    string;
  unit_type:     string | null;
  site_id:       string | null;
  status:        string;
  boq_customized: boolean;
}

export interface LotTypeWithLots extends LotType {
  lots: LotTypeLotSummary[];
}

export interface LotTypeCreate {
  name:                string;
  code?:               string | null;
  description?:        string | null;
  default_template_id?: string | null;
}

export interface LotTypeUpdate {
  name?:               string;
  code?:               string | null;
  description?:        string | null;
  default_template_id?: string | null;
}

export interface AssignResult {
  lot_type_id:   string;
  lot_type_name: string;
  assigned:      number;
  reassigned:    number;
  already_set:   number;
  total:         number;
}

export interface RemoveResult {
  lot_type_id:   string;
  lot_type_name: string;
  removed:       number;
  not_in_type:   number;
}

// Phase 3D.3 — Propagation
export type PropagateMode = "SAFE" | "FORCE";

export interface PropagatePreviewLot {
  lot_id:        string;
  lot_number:    string;
  unit_type:     string | null;
  site_id:       string | null;
  is_customized: boolean;
  action:        "propagate" | "skip";
  skip_reason:   string | null;
}

export interface PropagatePreview {
  lot_type_id:       string;
  lot_type_name:     string;
  template_name:     string | null;
  mode:              string;
  total_linked_lots: number;
  lots_to_propagate: number;
  lots_skipped:      number;
  skipped_reason:    string | null;
  items_per_lot:     number;
  stages_per_lot:    number;
  lots:              PropagatePreviewLot[];
}

export interface PropagateResult {
  lot_type_id:        string;
  lot_type_name:      string;
  mode:               string;
  propagated:         number;
  skipped:            number;
  milestones_created: number;
  items_replaced:     number;
  message:            string;
}

export const lotTypesApi = {
  list: async (projectId: string): Promise<LotType[]> => {
    const res = await client.get<{ data: LotType[] }>(
      `/projects/${projectId}/lot-types/`
    );
    return res.data.data;
  },

  create: async (projectId: string, body: LotTypeCreate): Promise<LotType> => {
    const res = await client.post<{ data: LotType }>(
      `/projects/${projectId}/lot-types/`,
      body
    );
    return res.data.data;
  },

  get: async (lotTypeId: string): Promise<LotTypeWithLots> => {
    const res = await client.get<{ data: LotTypeWithLots }>(
      `/lot-types/${lotTypeId}`
    );
    return res.data.data;
  },

  update: async (lotTypeId: string, body: LotTypeUpdate): Promise<LotType> => {
    const res = await client.patch<{ data: LotType }>(
      `/lot-types/${lotTypeId}`,
      body
    );
    return res.data.data;
  },

  delete: async (lotTypeId: string): Promise<void> => {
    await client.delete(`/lot-types/${lotTypeId}`);
  },

  assignLots: async (lotTypeId: string, lotIds: string[]): Promise<AssignResult> => {
    const res = await client.post<{ data: AssignResult }>(
      `/lot-types/${lotTypeId}/assign-lots`,
      { lot_ids: lotIds }
    );
    return res.data.data;
  },

  removeLots: async (lotTypeId: string, lotIds: string[]): Promise<RemoveResult> => {
    const res = await client.post<{ data: RemoveResult }>(
      `/lot-types/${lotTypeId}/remove-lots`,
      { lot_ids: lotIds }
    );
    return res.data.data;
  },

  // Phase 3D.3 — Propagation
  previewPropagate: async (
    lotTypeId: string,
    mode: PropagateMode = "SAFE",
    lotIds?: string[],
  ): Promise<PropagatePreview> => {
    const res = await client.post<{ data: PropagatePreview }>(
      `/lot-types/${lotTypeId}/preview-propagate`,
      { mode, lot_ids: lotIds ?? null, generate_milestones: true }
    );
    return res.data.data;
  },

  propagate: async (
    lotTypeId: string,
    mode: PropagateMode,
    lotIds?: string[],
    generateMilestones = true,
  ): Promise<PropagateResult> => {
    const res = await client.post<{ data: PropagateResult }>(
      `/lot-types/${lotTypeId}/propagate`,
      { mode, lot_ids: lotIds ?? null, generate_milestones: generateMilestones }
    );
    return res.data.data;
  },
};
