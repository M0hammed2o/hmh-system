import client from "./client";

export type JobCardStatus =
  | "DRAFT" | "SUBMITTED" | "SITE_APPROVED" | "OFFICE_APPROVED"
  | "OWNER_APPROVED" | "PAYMENT_APPROVED" | "PAID" | "REJECTED";

export type JobCardWorkType = "DAILY_LABOUR" | "CONTRACT" | "SUBCONTRACTOR" | "OVERTIME";

export interface JobCard {
  id: string;
  job_card_number: string;
  project_id: string;
  site_id: string;
  lot_id: string | null;
  work_description: string;
  work_type: JobCardWorkType;
  worker_name: string | null;
  team_name: string | null;
  quantity: number;
  unit: string | null;
  rate: number;
  total_amount: number;
  owner_approval_required: boolean;
  status: JobCardStatus;
  submitted_by: string | null;
  submitted_at: string | null;
  site_approved_by: string | null;
  site_approved_at: string | null;
  office_approved_by: string | null;
  office_approved_at: string | null;
  owner_approved_by: string | null;
  owner_approved_at: string | null;
  payment_approved_by: string | null;
  payment_approved_at: string | null;
  rejection_reason: string | null;
  work_date: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobCardCreate {
  site_id: string;
  lot_id?: string;
  work_description: string;
  work_type?: JobCardWorkType;
  worker_name?: string;
  team_name?: string;
  quantity?: number;
  unit?: string;
  rate: number;
  work_date?: string;
  notes?: string;
}

export const jobCardsApi = {
  list: async (projectId: string, status?: JobCardStatus, lotId?: string): Promise<JobCard[]> => {
    const params: Record<string, string> = {};
    if (status) params.status = status;
    if (lotId) params.lot_id = lotId;
    const res = await client.get<{ data: JobCard[] }>(`/projects/${projectId}/job-cards/`, { params });
    return res.data.data;
  },

  create: async (projectId: string, body: JobCardCreate): Promise<JobCard> => {
    const res = await client.post<{ data: JobCard }>(`/projects/${projectId}/job-cards/`, body);
    return res.data.data;
  },

  get: async (id: string): Promise<JobCard> => {
    const res = await client.get<{ data: JobCard }>(`/job-cards/${id}`);
    return res.data.data;
  },

  submit: async (id: string): Promise<JobCard> => {
    const res = await client.post<{ data: JobCard }>(`/job-cards/${id}/submit`);
    return res.data.data;
  },

  siteApprove: async (id: string): Promise<JobCard> => {
    const res = await client.post<{ data: JobCard }>(`/job-cards/${id}/site-approve`);
    return res.data.data;
  },

  officeApprove: async (id: string): Promise<JobCard> => {
    const res = await client.post<{ data: JobCard }>(`/job-cards/${id}/office-approve`);
    return res.data.data;
  },

  ownerApprove: async (id: string): Promise<JobCard> => {
    const res = await client.post<{ data: JobCard }>(`/job-cards/${id}/owner-approve`);
    return res.data.data;
  },

  approvePayment: async (id: string): Promise<JobCard> => {
    const res = await client.post<{ data: JobCard }>(`/job-cards/${id}/approve-payment`);
    return res.data.data;
  },

  markPaid: async (id: string): Promise<JobCard> => {
    const res = await client.post<{ data: JobCard }>(`/job-cards/${id}/mark-paid`);
    return res.data.data;
  },

  reject: async (id: string, reason: string): Promise<JobCard> => {
    const res = await client.post<{ data: JobCard }>(`/job-cards/${id}/reject`, { reason });
    return res.data.data;
  },

  summary: async (projectId: string): Promise<{ by_status: Record<string, { count: number; total: number }>; pending_payment_count: number; pending_payment_amount: number }> => {
    const res = await client.get<{ data: { by_status: Record<string, { count: number; total: number }>; pending_payment_count: number; pending_payment_amount: number } }>(`/projects/${projectId}/job-cards/summary`);
    return res.data.data;
  },
};
