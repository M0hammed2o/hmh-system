import client from "./client";

export type MaterialStatus = "OK" | "LOW" | "OVER_BOQ" | "STOCK_ISSUE";

export interface MaterialSummaryItem {
  boq_item_id:        string;
  item_id:            string | null;   // null when not linked to the items catalog
  description:        string;
  unit:               string | null;
  boq_allocated_qty:  number;
  delivered_qty:      number;
  used_qty:           number;
  remaining_qty:      number;
  over_qty:           number;
  status:             MaterialStatus;
  from_site_template: boolean;         // true when derived from site-level BOQ, not lot-specific
  supplier_id:        string | null;   // preferred supplier from the BOQ item
  supplier_name:      string | null;   // supplier display name
  // BOQ section / milestone grouping
  section_name:       string | null;
  section_order:      number;
  // BOQ price columns
  planned_rate:       number | null;
  planned_total:      number | null;
  item_type:          string;          // MATERIAL | LABOUR | PLANT | SERVICE
}

export type ActivityType = "delivery" | "usage" | "alert" | "stage";

export interface ActivityItem {
  type:      ActivityType;
  title:     string;
  date:      string | null;
  status:    string | null;
  severity?: string | null;
}

export interface MaterialSummaryItemExtended extends MaterialSummaryItem {
  shortfall_qty?: number;   // Phase 3J: max(0, planned - dispatched)
}

export const siteDashboardApi = {
  getMaterialSummary: async (
    siteId: string,
    lotId:  string,
  ): Promise<MaterialSummaryItem[]> => {
    const res = await client.get<{ data: MaterialSummaryItem[] }>(
      `/site-dashboard/${siteId}/lots/${lotId}/material-summary`,
    );
    return res.data.data;
  },

  /**
   * Phase 3J: project-level material summary.
   * Works for both site lots and freestanding lots (site_id=NULL).
   * Uses Phase 3B warehouse model: delivered = TRANSFER_IN to lot.
   */
  getProjectLotMaterialSummary: async (
    projectId: string,
    lotId:     string,
  ): Promise<MaterialSummaryItemExtended[]> => {
    const res = await client.get<{ data: MaterialSummaryItemExtended[] }>(
      `/projects/${projectId}/lots/${lotId}/material-summary`,
    );
    return res.data.data;
  },

  getProjectWarehouseMaterialSummary: async (
    projectId: string,
  ): Promise<MaterialSummaryItem[]> => {
    const res = await client.get<{ data: MaterialSummaryItem[] }>(
      `/projects/${projectId}/warehouse/material-summary`,
    );
    return res.data.data;
  },

  getActivity: async (
    siteId: string,
    lotId:  string,
    limit = 20,
  ): Promise<ActivityItem[]> => {
    const res = await client.get<{ data: ActivityItem[] }>(
      `/site-dashboard/${siteId}/lots/${lotId}/activity`,
      { params: { limit } },
    );
    return res.data.data;
  },
};
