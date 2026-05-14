import client from "./client";

export interface DailySummary {
  date_today: string;
  spend_today: number;
  spend_week: number;
  spend_month: number;
  deliveries_today: number;
  active_lots: number;
  delayed_lots: number;
  completed_lots: number;
  open_alerts: number;
  material_overrun_alerts: number;
  unmatched_invoices: number;
  vehicle_spend_today: number;
  vehicle_spend_month: number;
  burn_rate_daily_avg: number;
}

export const summaryApi = {
  daily: async (projectId?: string): Promise<DailySummary> => {
    const params = projectId ? { project_id: projectId } : {};
    const res = await client.get<{ data: DailySummary }>("/summary/daily", { params });
    return res.data.data;
  },
};
