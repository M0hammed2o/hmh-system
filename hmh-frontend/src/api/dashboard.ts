import client from "./client";

export interface DashboardStats {
  active_projects: number;
  total_projects: number;
  active_sites: number;
  total_lots: number;
  open_purchase_orders: number;
  pending_invoices: number;
  pending_payments: number;
  total_paid_amount: number;
  open_alerts: number;
  fuel_total_cost: number;
  fuel_total_litres: number;
}

export const dashboardApi = {
  getStats: async (projectId?: string): Promise<DashboardStats> => {
    const res = await client.get<{ data: DashboardStats }>("/dashboard/stats", {
      params: projectId ? { project_id: projectId } : {},
    });
    return res.data.data;
  },
};
