import client from "./client";

export type ProgrammeActivityStatus =
  | "NOT_STARTED" | "IN_PROGRESS" | "DELAYED" | "BLOCKED" | "COMPLETED" | "VERIFIED" | "CANCELLED";

export type ProgrammeActivityType =
  | "CONSTRUCTION" | "PROCUREMENT" | "INSPECTION" | "ADMIN" | "MILESTONE";

export interface ProgrammeActivity {
  id: string;
  activity_number: string;
  project_id: string;
  site_id: string | null;
  lot_id: string | null;
  stage_status_id: string | null;
  title: string;
  description: string | null;
  activity_type: ProgrammeActivityType;
  planned_start_date: string;
  planned_finish_date: string;
  actual_start_date: string | null;
  actual_finish_date: string | null;
  baseline_start_date: string | null;
  baseline_finish_date: string | null;
  duration_days: number | null;
  progress_pct: number;
  status: ProgrammeActivityStatus;
  predecessor_id: string | null;
  lag_days: number;
  is_critical_path: boolean;
  is_milestone: boolean;
  responsible_team: string | null;
  notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProgrammeActivityCreate {
  title: string;
  activity_type?: ProgrammeActivityType;
  site_id?: string | null;
  lot_id?: string | null;
  stage_status_id?: string | null;
  planned_start_date: string;
  planned_finish_date: string;
  predecessor_id?: string | null;
  lag_days?: number;
  is_critical_path?: boolean;
  is_milestone?: boolean;
  responsible_team?: string | null;
  description?: string | null;
  notes?: string | null;
}

export const listActivities = (projectId: string, params?: { site_id?: string; status?: string }) =>
  client.get(`/api/v1/projects/${projectId}/programme`, { params }).then((r) => r.data.data as ProgrammeActivity[]);

export const getActivity = (activityId: string) =>
  client.get(`/api/v1/programme/${activityId}`).then((r) => r.data.data as ProgrammeActivity);

export const createActivity = (projectId: string, body: ProgrammeActivityCreate) =>
  client.post(`/api/v1/projects/${projectId}/programme`, body).then((r) => r.data.data as ProgrammeActivity);

export const updateActivity = (activityId: string, body: Partial<ProgrammeActivityCreate> & { progress_pct?: number; status?: string; actual_start_date?: string; actual_finish_date?: string }) =>
  client.patch(`/api/v1/programme/${activityId}`, body).then((r) => r.data.data as ProgrammeActivity);

export const deleteActivity = (activityId: string) =>
  client.delete(`/api/v1/programme/${activityId}`).then((r) => r.data);

export const setBaseline = (activityId: string) =>
  client.post(`/api/v1/programme/${activityId}/baseline`, { confirm: true }).then((r) => r.data.data as ProgrammeActivity);
