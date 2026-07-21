import client from "./client";

export type WeeklyPlanStatus =
  | "DRAFT" | "SUBMITTED" | "APPROVED" | "IN_PROGRESS" | "COMPLETED" | "REVIEWED" | "CANCELLED";

export interface WeeklyPlanItem {
  id: string;
  plan_id: string;
  programme_activity_id: string | null;
  stage_status_id: string | null;
  lot_id: string | null;
  description: string;
  planned_progress_pct: number;
  actual_progress_pct: number | null;
  carry_forward: boolean;
  completion_notes: string | null;
  completed_at: string | null;
  sort_order: number;
}

export interface WeeklyPlan {
  id: string;
  plan_number: string;
  project_id: string;
  site_id: string | null;
  week_start_date: string;
  week_end_date: string;
  status: WeeklyPlanStatus;
  notes: string | null;
  submitted_by: string | null;
  approved_by: string | null;
  submitted_at: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
  items: WeeklyPlanItem[];
}

export interface WeeklyPlanCreate {
  week_start_date: string;
  site_id?: string | null;
  notes?: string | null;
  items?: Array<{
    description: string;
    planned_progress_pct?: number;
    programme_activity_id?: string | null;
    stage_status_id?: string | null;
    lot_id?: string | null;
  }>;
}

export const listWeeklyPlans = (projectId: string, params?: { site_id?: string; status?: string }) =>
  client.get(`/api/v1/projects/${projectId}/weekly-plans`, { params }).then((r) => r.data.data as WeeklyPlan[]);

export const getWeeklyPlan = (planId: string) =>
  client.get(`/api/v1/weekly-plans/${planId}`).then((r) => r.data.data as WeeklyPlan);

export const createWeeklyPlan = (projectId: string, body: WeeklyPlanCreate) =>
  client.post(`/api/v1/projects/${projectId}/weekly-plans`, body).then((r) => r.data.data as WeeklyPlan);

export const submitWeeklyPlan = (planId: string) =>
  client.post(`/api/v1/weekly-plans/${planId}/submit`).then((r) => r.data.data as WeeklyPlan);

export const approveWeeklyPlan = (planId: string) =>
  client.post(`/api/v1/weekly-plans/${planId}/approve`).then((r) => r.data.data as WeeklyPlan);

export const rejectWeeklyPlan = (planId: string, reason?: string) =>
  client.post(`/api/v1/weekly-plans/${planId}/reject`, null, { params: reason ? { reason } : undefined }).then((r) => r.data.data as WeeklyPlan);

export const markItemDone = (planId: string, itemId: string, actual_progress_pct: number, completion_notes?: string) =>
  client.post(`/api/v1/weekly-plans/${planId}/items/${itemId}/done`, { actual_progress_pct, completion_notes }).then((r) => r.data);

export const addPlanItem = (planId: string, item: { description: string; planned_progress_pct?: number; programme_activity_id?: string | null }) =>
  client.post(`/api/v1/weekly-plans/${planId}/items`, item).then((r) => r.data);

export const deletePlanItem = (planId: string, itemId: string) =>
  client.delete(`/api/v1/weekly-plans/${planId}/items/${itemId}`).then((r) => r.data);
