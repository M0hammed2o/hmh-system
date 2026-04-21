import client from "./client";

export type MovementType =
  | "OPENING_BALANCE" | "DELIVERY_RECEIVED" | "USAGE"
  | "ADJUSTMENT_ADD" | "ADJUSTMENT_SUBTRACT"
  | "RETURN_TO_STORE" | "TRANSFER_IN" | "TRANSFER_OUT";

export interface StockLedgerEntry {
  id: string;
  project_id: string;
  site_id: string;
  lot_id: string | null;
  item_id: string;
  boq_item_id: string | null;
  movement_type: MovementType;
  reference_type: string;
  reference_id: string | null;
  quantity_in: number;
  quantity_out: number;
  unit: string | null;
  unit_cost: number | null;
  movement_date: string;
  entered_by: string | null;
  notes: string | null;
  created_at: string;
}

export interface StockBalance {
  project_id: string;
  site_id: string;
  lot_id: string | null;
  item_id: string;
  balance: number;
  last_movement_date: string | null;
  item_name: string | null;
  item_unit: string | null;
}

export interface UsageLog {
  id: string;
  project_id: string;
  site_id: string;
  lot_id: string | null;
  stage_id: string | null;
  item_id: string;
  boq_item_id: string | null;
  quantity_used: number;
  used_by_person_name: string | null;
  used_by_team_name: string | null;
  recorded_by_user_id: string;
  usage_date: string;
  comments: string | null;
  created_at: string;
}

export interface UsageLogCreate {
  site_id: string;
  item_id: string;
  quantity_used: number;
  lot_id?: string | null;
  stage_id?: string | null;
  boq_item_id?: string | null;
  used_by_person_name?: string | null;
  used_by_team_name?: string | null;
  usage_date?: string | null;
  comments?: string | null;
}

export const stockApi = {
  getBalances: async (projectId: string, siteId?: string): Promise<StockBalance[]> => {
    const res = await client.get<{ data: StockBalance[] }>("/stock/balances", {
      params: { project_id: projectId, ...(siteId ? { site_id: siteId } : {}) },
    });
    return res.data.data;
  },

  getLedger: async (
    projectId: string,
    params?: { site_id?: string; item_id?: string; limit?: number }
  ): Promise<StockLedgerEntry[]> => {
    const res = await client.get<{ data: StockLedgerEntry[] }>("/stock/ledger", {
      params: { project_id: projectId, ...params },
    });
    return res.data.data;
  },

  recordUsage: async (projectId: string, body: UsageLogCreate): Promise<UsageLog> => {
    const res = await client.post<{ data: UsageLog }>("/stock/usage", body, {
      params: { project_id: projectId },
    });
    return res.data.data;
  },
};
