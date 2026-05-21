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

export interface ProjectOperation {
  project_id:               string;
  project_name:             string;
  project_code:             string;
  site_count:               number;
  total_lots:               number;
  lots_completed:           number;
  lots_in_progress:         number;
  milestones_completed:     number;
  total_milestones:         number;
  progress_pct:             number;
  active_material_requests: number;
  open_alerts:              number;
  total_paid:               number;
}

export const dashboardApi = {
  getStats: async (projectId?: string): Promise<DashboardStats> => {
    const res = await client.get<{ data: DashboardStats }>("/dashboard/stats", {
      params: projectId ? { project_id: projectId } : {},
    });
    return res.data.data;
  },

  getProjectOperations: async (): Promise<ProjectOperation[]> => {
    const res = await client.get<{ data: ProjectOperation[] }>("/dashboard/operations");
    return res.data.data;
  },
};
