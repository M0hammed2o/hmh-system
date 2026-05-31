/**
 * Warehouse API client — three warehouse levels:
 *
 * Global Main Warehouse (company-wide, no project filter):
 *   GET  /warehouse/main/         — on-hand stock across ALL projects
 *   GET  /warehouse/main/history  — movement history across ALL projects
 *
 * Project Warehouse (per-project, site_id IS NULL):
 *   GET  /projects/{projectId}/warehouse/          — on-hand stock
 *   POST /projects/{projectId}/warehouse/transfer  — dispatch to site
 *   POST /projects/{projectId}/warehouse/return    — receive back from site
 *   GET  /projects/{projectId}/warehouse/history   — movement history
 *
 * Site Warehouse (per-site, lot_id IS NULL):
 *   GET  /sites/{siteId}/warehouse/          — on-hand stock
 *   POST /sites/{siteId}/warehouse/transfer  — transfer to lot
 *   GET  /sites/{siteId}/warehouse/history   — movement history
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
  lot_number?:  string;   // lot transfer only
  site_name?:   string;   // site transfer only
  new_balance:  number;
}

export interface ReturnResult {
  transfer_ref:     string;
  item_id:          string;
  item_name:        string;
  quantity:         number;
  unit:             string | null;
  site_name:        string;
  new_main_balance: number;
}

export interface GlobalWarehouseStockItem {
  project_id:    string | null;  // null = global stock (no project assigned)
  project_name:  string;
  project_code:  string;
  item_id:       string;
  item_name:     string;
  unit:          string | null;
  on_hand:       number;
  total_in:      number;
  total_out:     number;
  last_movement: string | null;
}

export interface GlobalWarehouseSite {
  id:           string;
  name:         string;
  project_id:   string;
  project_name: string;
  project_code: string;
}

export interface GlobalWarehouseMovement extends WarehouseMovement {
  project_id:   string;
  project_name: string;
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

  // ── Main Warehouse ────────────────────────────────────────────────────────

  /** Current on-hand stock in the Main (project-level) Warehouse. */
  getMainStock: async (projectId: string): Promise<WarehouseStockItem[]> => {
    const res = await client.get<{ data: WarehouseStockItem[] }>(
      `/projects/${projectId}/warehouse/`
    );
    return res.data.data ?? [];
  },

  /** Dispatch stock from Main Warehouse to a Site Warehouse. */
  transferToSite: async (
    projectId: string,
    itemId:    string,
    siteId:    string,
    quantity:  number,
    notes?:    string,
  ): Promise<TransferResult> => {
    const res = await client.post<{ data: TransferResult }>(
      `/projects/${projectId}/warehouse/transfer`,
      { item_id: itemId, site_id: siteId, quantity, notes: notes || null }
    );
    return res.data.data;
  },

  /** Receive stock returned from a Site Warehouse back to Main Warehouse. */
  returnFromSite: async (
    projectId: string,
    itemId:    string,
    siteId:    string,
    quantity:  number,
    notes?:    string,
  ): Promise<ReturnResult> => {
    const res = await client.post<{ data: ReturnResult }>(
      `/projects/${projectId}/warehouse/return`,
      { item_id: itemId, site_id: siteId, quantity, notes: notes || null }
    );
    return res.data.data;
  },

  /** Aggregated MATERIAL BOQ vs on-hand stock for the Project Warehouse dashboard. */
  getProjectWarehouseBOQSummary: async (projectId: string): Promise<Array<{
    item_id: string | null;
    description: string;
    unit: string | null;
    total_boq_qty: number;
    on_hand_qty: number;
    shortfall_qty: number;
    lots_count: number;
  }>> => {
    const res = await client.get(`/projects/${projectId}/warehouse/boq-summary`);
    return res.data.data ?? [];
  },

  /** Recent movements through the Main Warehouse. */
  getMainHistory: async (projectId: string, limit = 100): Promise<WarehouseMovement[]> => {
    const res = await client.get<{ data: WarehouseMovement[] }>(
      `/projects/${projectId}/warehouse/history`,
      { params: { limit } }
    );
    return res.data.data ?? [];
  },

  // ── Global Main Warehouse (company-wide, no project filter) ──────────────

  /** On-hand stock across ALL project warehouses (site_id IS NULL, lot_id IS NULL). */
  getGlobalStock: async (): Promise<GlobalWarehouseStockItem[]> => {
    const res = await client.get<{ data: GlobalWarehouseStockItem[] }>("/warehouse/main/");
    return res.data.data ?? [];
  },

  /** Recent movements across ALL main warehouses. */
  getGlobalHistory: async (limit = 100): Promise<GlobalWarehouseMovement[]> => {
    const res = await client.get<{ data: GlobalWarehouseMovement[] }>(
      "/warehouse/main/history",
      { params: { limit } }
    );
    return res.data.data ?? [];
  },

  /** Receive stock from supplier into the global main warehouse (no project required). */
  receiveStock: async (body: {
    item_id: string;
    quantity: number;
    unit?: string;
    unit_cost?: number;
    supplier_ref?: string;
    movement_date?: string;
    notes?: string;
  }): Promise<{ id: string; item_name: string; quantity_in: number }> => {
    const res = await client.post<{ data: { id: string; item_name: string; quantity_in: number } }>(
      "/warehouse/main/receive",
      body
    );
    return res.data.data;
  },

  /** Create a stock adjustment in the global main warehouse. */
  adjustStock: async (body: {
    item_id: string;
    adjustment_type: string;
    quantity: number;
    movement_date?: string;
    notes?: string;
  }): Promise<{ id: string; item_name: string; adjustment_type: string; quantity: number }> => {
    const res = await client.post<{ data: { id: string; item_name: string; adjustment_type: string; quantity: number } }>(
      "/warehouse/main/adjust",
      body
    );
    return res.data.data;
  },

  /** All active sites across all projects (for global warehouse transfer modal). */
  listAllSites: async (): Promise<GlobalWarehouseSite[]> => {
    const res = await client.get<{ data: GlobalWarehouseSite[] }>("/warehouse/main/sites");
    return res.data.data ?? [];
  },

  /** Transfer global stock (project_id=null) to a specific site. */
  transferGlobalToSite: async (
    itemId:   string,
    siteId:   string,
    quantity: number,
    notes?:   string,
  ): Promise<TransferResult> => {
    const res = await client.post<{ data: TransferResult }>(
      "/warehouse/main/transfer-to-site",
      { item_id: itemId, site_id: siteId, quantity, notes: notes || null }
    );
    return res.data.data;
  },
};
