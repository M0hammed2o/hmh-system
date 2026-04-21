import client from "./client";

export type LotStatus = "AVAILABLE" | "IN_PROGRESS" | "COMPLETED" | "ON_HOLD";

export interface Lot {
  id: string;
  project_id: string;
  site_id: string | null;
  lot_number: string;
  unit_type: string | null;
  block_number: string | null;
  status: LotStatus;
  created_at: string;
  updated_at: string;
}

export interface LotCreate {
  lot_number: string;
  site_id?: string | null;
  unit_type?: string | null;
  block_number?: string | null;
  status?: LotStatus;
}

export interface LotUpdate {
  site_id?: string | null;
  unit_type?: string | null;
  block_number?: string | null;
  status?: LotStatus;
}

export const lotsApi = {
  list: async (projectId: string): Promise<Lot[]> => {
    const res = await client.get<{ data: Lot[] }>(`/projects/${projectId}/lots/`);
    return res.data.data;
  },

  get: async (lotId: string): Promise<Lot> => {
    const res = await client.get<{ data: Lot }>(`/lots/${lotId}`);
    return res.data.data;
  },

  create: async (projectId: string, body: LotCreate): Promise<Lot> => {
    const res = await client.post<{ data: Lot }>(`/projects/${projectId}/lots/`, body);
    return res.data.data;
  },

  update: async (lotId: string, body: LotUpdate): Promise<Lot> => {
    const res = await client.patch<{ data: Lot }>(`/lots/${lotId}`, body);
    return res.data.data;
  },
};
