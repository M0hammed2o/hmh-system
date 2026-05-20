/**
 * Site Warehouse API client.
 *
 * Wraps:
 *   GET  /api/v1/sites/{siteId}/warehouse          — current on-hand stock
 *   POST /api/v1/sites/{siteId}/warehouse/transfer  — transfer to lot
 *   GET  /api/v1/sites/{siteId}/warehouse/history   — movement history
 */
import client from "./client";

export interface WarehouseStockItem {
  item_id:       string;
  item_name:     string;
  unit:          string | null;
  on_hand:       number;
  total_in:      number;
  total_out:     number;
  last_movement: string | null;
}

export interface WarehouseMovement {
  id:             string;
  movement_type:  string;
  item_name:      string;
  quantity_in:    number;
  quantity_out:   number;
  unit:           string | null;
  movement_date:  string | null;
  notes:          string | null;
  reference_type: string | null;
  entered_by:     string | null;
}

export interface TransferResult {
  transfer_ref: string;
  item_id:      string;
  item_name:    string;
  quantity:     number;
  unit:         string | null;
  lot_number:   string;
  new_balance:  number;
}

export const warehouseApi = {
  /** Current on-hand stock in the site warehouse (lot_id IS NULL). */
  getStock: async (siteId: string): Promise<WarehouseStockItem[]> => {
    const res = await client.get<{ data: WarehouseStockItem[] }>(
      `/sites/${siteId}/warehouse/`
    );
    return res.data.data ?? [];
  },

  /** Transfer items from the site warehouse to a specific lot. */
  transferToLot: async (
    siteId:   string,
    itemId:   string,
    lotId:    string,
    quantity: number,
    notes?:   string,
  ): Promise<TransferResult> => {
    const res = await client.post<{ data: TransferResult }>(
      `/sites/${siteId}/warehouse/transfer`,
      { item_id: itemId, lot_id: lotId, quantity, notes: notes || null }
    );
    return res.data.data;
  },

  /** Recent movements through this site warehouse. */
  getHistory: async (siteId: string, limit = 50): Promise<WarehouseMovement[]> => {
    const res = await client.get<{ data: WarehouseMovement[] }>(
      `/sites/${siteId}/warehouse/history`,
      { params: { limit } }
    );
    return res.data.data ?? [];
  },
};
