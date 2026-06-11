import client from "./client";

export type WorkDoneStatus =
  | "DRAFT" | "SUBMITTED" | "SITE_APPROVED" | "OFFICE_APPROVED" | "PAID" | "REJECTED";

export interface WorkDone {
  id: string;
  work_done_number: string;
  project_id: string;
  site_id: string;
  lot_id: string | null;
  stage_status_id: string | null;
  supplier_id: string;
  job_card_id: string | null;
  work_description: string;
  quantity: number;
  unit: string | null;
  rate: number;
  amount: number;
  month: string;   // ISO date, always 1st of month
  comments: string | null;
  status: WorkDoneStatus;
  submitted_by: string | null;
  submitted_at: string | null;
  site_approved_by: string | null;
  site_approved_at: string | null;
  office_approved_by: string | null;
  office_approved_at: string | null;
  paid_by: string | null;
  paid_at: string | null;
  rejection_reason: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkDoneCreate {
  site_id: string;
  supplier_id: string;
  work_description: string;
  quantity: number;
  unit?: string | null;
  rate: number;
  month: string;   // ISO date
  lot_id?: string | null;
  stage_status_id?: string | null;
  job_card_id?: string | null;
  comments?: string | null;
}

export interface WorkDoneUpdate {
  work_description?: string;
  quantity?: number;
  unit?: string | null;
  rate?: number;
  month?: string;
  comments?: string | null;
  lot_id?: string | null;
  stage_status_id?: string | null;
  job_card_id?: string | null;
}

export interface WorkDoneSummary {
  project_id: string;
  month: string | null;
  total_records: number;
  total_amount: number;
  paid_amount: number;
  pending_amount: number;
  by_supplier: Array<{
    supplier_id: string;
    supplier_name: string;
    count: number;
    total_amount: number;
    paid_amount: number;
    statuses: Record<string, number>;
  }>;
}

export const workDoneApi = {
  list: (projectId: string, params?: {
    status?: WorkDoneStatus;
    site_id?: string;
    lot_id?: string;
    supplier_id?: string;
    month?: string;
  }) =>
    client.get<{ data: WorkDone[] }>(`/projects/${projectId}/work-done/`, { params })
      .then(r => r.data.data),

  create: (projectId: string, body: WorkDoneCreate) =>
    client.post<{ data: WorkDone }>(`/projects/${projectId}/work-done/`, body)
      .then(r => r.data.data),

  get: (id: string) =>
    client.get<{ data: WorkDone }>(`/work-done/${id}`)
      .then(r => r.data.data),

  update: (id: string, body: WorkDoneUpdate) =>
    client.patch<{ data: WorkDone }>(`/work-done/${id}`, body)
      .then(r => r.data.data),

  submit: (id: string) =>
    client.post<{ data: WorkDone }>(`/work-done/${id}/submit`)
      .then(r => r.data.data),

  siteApprove: (id: string) =>
    client.post<{ data: WorkDone }>(`/work-done/${id}/site-approve`)
      .then(r => r.data.data),

  officeApprove: (id: string) =>
    client.post<{ data: WorkDone }>(`/work-done/${id}/office-approve`)
      .then(r => r.data.data),

  markPaid: (id: string) =>
    client.post<{ data: WorkDone }>(`/work-done/${id}/mark-paid`)
      .then(r => r.data.data),

  reject: (id: string, reason: string) =>
    client.post<{ data: WorkDone }>(`/work-done/${id}/reject`, { reason })
      .then(r => r.data.data),

  summary: (projectId: string) =>
    client.get<{ data: Record<string, unknown> }>(`/projects/${projectId}/work-done/summary`)
      .then(r => r.data.data),

  monthlySummary: (projectId: string, params?: {
    month?: string;
    site_id?: string;
    supplier_id?: string;
  }) =>
    client.get<{ data: WorkDoneSummary }>(`/projects/${projectId}/work-done/monthly-summary`, { params })
      .then(r => r.data.data),
};
