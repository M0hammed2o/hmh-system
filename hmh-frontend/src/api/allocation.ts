import client from "./client";

export interface LotAllocation {
  lot_id: string;
  item_id: string;
  item_name: string;
  item_unit: string | null;
  allocated_quantity: number;
  used_quantity: number;
  remaining_quantity: number;
  over_quantity: number;
  is_over: boolean;
}

export interface TransferToLotBody {
  item_id: string;
  quantity: number;
  site_id: string;
  notes?: string;
  overrun_reason?: string;
  boq_item_id?: string;
  unit_cost?: number;
}

export const allocationApi = {
  getLotAllocations: async (lotId: string): Promise<LotAllocation[]> => {
    const res = await client.get<{ data: LotAllocation[] }>(`/lots/${lotId}/allocations`);
    return res.data.data;
  },

  getLotAllocation: async (lotId: string, itemId: string): Promise<LotAllocation> => {
    const res = await client.get<{ data: LotAllocation }>(`/lots/${lotId}/allocations/${itemId}`);
    return res.data.data;
  },

  transferToLot: async (projectId: string, lotId: string, body: TransferToLotBody): Promise<{ id: string }> => {
    const res = await client.post<{ data: { id: string } }>(
      `/projects/${projectId}/lots/${lotId}/transfer`,
      body
    );
    return res.data.data;
  },
};
