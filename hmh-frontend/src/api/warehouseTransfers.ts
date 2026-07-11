import client from "./client";

export interface TransferVote {
  id: string;
  voted_by: string;
  voted_by_name: string | null;
  voted_at: string;
  is_override: boolean;
  notes: string | null;
}

export interface WarehouseTransferRequest {
  id: string;
  from_project_id: string;
  from_project_name: string | null;
  to_project_id: string;
  to_project_name: string | null;
  item_id: string;
  item_name: string | null;
  quantity: number;
  unit: string | null;
  reason: string;
  notes: string | null;
  status: "PENDING" | "EXECUTED" | "REJECTED";
  requested_by: string;
  requested_by_name: string | null;
  requested_at: string;
  executed_at: string | null;
  rejection_reason: string | null;
  vote_count: number;
  votes_required: number;
  votes: TransferVote[];
  created_at: string;
}

export interface TransferRequestCreate {
  to_project_id: string;
  item_id: string;
  quantity: number;
  reason: string;
  notes?: string;
}

export const warehouseTransfersApi = {
  submitRequest: async (projectId: string, data: TransferRequestCreate): Promise<WarehouseTransferRequest> => {
    const res = await client.post(`/projects/${projectId}/warehouse-transfers/`, data);
    return res.data.data;
  },

  listForProject: async (projectId: string, status?: string): Promise<WarehouseTransferRequest[]> => {
    const params = status ? { status } : {};
    const res = await client.get(`/projects/${projectId}/warehouse-transfers/`, { params });
    return res.data.data;
  },

  listAllPending: async (): Promise<WarehouseTransferRequest[]> => {
    const res = await client.get("/warehouse-transfers/pending");
    return res.data.data;
  },

  castVote: async (transferId: string, notes?: string): Promise<WarehouseTransferRequest> => {
    const res = await client.post(`/warehouse-transfers/${transferId}/vote`, { notes });
    return res.data.data;
  },

  overrideApprove: async (transferId: string, notes?: string): Promise<WarehouseTransferRequest> => {
    const res = await client.post(`/warehouse-transfers/${transferId}/override`, { notes });
    return res.data.data;
  },

  reject: async (transferId: string, reason: string): Promise<WarehouseTransferRequest> => {
    const res = await client.post(`/warehouse-transfers/${transferId}/reject`, { reason });
    return res.data.data;
  },
};
