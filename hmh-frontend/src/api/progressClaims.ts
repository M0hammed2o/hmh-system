import client from "./client";

export type ProgressClaimStatus =
  | "DRAFT" | "GENERATED" | "UNDER_REVIEW" | "READY_FOR_PRICING" | "APPROVED" | "EXPORTED" | "CANCELLED";

export type ClaimSourceType = "STAGE_MILESTONE" | "WORK_DONE" | "JOB_CARD";

export interface ClaimLine {
  id: string;
  claim_id: string;
  source_type: ClaimSourceType;
  lot_id: string | null;
  stage_status_id: string | null;
  work_done_id: string | null;
  job_card_id: string | null;
  description: string;
  stage_name: string | null;
  lot_number: string | null;
  work_date: string | null;
  quantity: string | null;
  unit: string | null;
  progress_pct: number | null;
  is_included: boolean;
  is_system_generated: boolean;
  reviewer_notes: string | null;
  sort_order: number;
}

export interface ClaimEvidence {
  id: string;
  claim_id: string;
  line_id: string | null;
  attachment_id: string | null;
  evidence_type: string | null;
  caption: string | null;
  is_included: boolean;
  added_at: string;
}

export interface ProgressClaim {
  id: string;
  claim_number: string;
  project_id: string;
  site_id: string | null;
  claim_title: string;
  municipality_name: string;
  cert_number: string | null;
  period_start: string;
  period_end: string;
  reporting_cutoff_date: string;
  status: ProgressClaimStatus;
  notes: string | null;
  generation_summary: Record<string, unknown> | null;
  linked_invoice_id: string | null;
  generated_at: string | null;
  approved_at: string | null;
  exported_at: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  lines: ClaimLine[];
  evidence: ClaimEvidence[];
}

export interface ProgressClaimListItem {
  id: string;
  claim_number: string;
  project_id: string;
  site_id: string | null;
  claim_title: string;
  period_start: string;
  period_end: string;
  status: ProgressClaimStatus;
  line_count: number;
  included_line_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProgressClaimCreate {
  claim_title: string;
  municipality_name?: string;
  cert_number?: string | null;
  period_start: string;
  period_end: string;
  reporting_cutoff_date?: string | null;
  site_id?: string | null;
  notes?: string | null;
}

export interface GenerateClaimRequest {
  include_work_done?: boolean;
  include_job_cards?: boolean;
  include_milestones?: boolean;
  overwrite_existing?: boolean;
}

export interface ClaimLineUpdate {
  is_included?: boolean;
  reviewer_notes?: string | null;
  description?: string;
}

// List all progress claims for a project
export const listProgressClaims = (projectId: string, params?: { site_id?: string; status?: string }) =>
  client.get(`/api/v1/projects/${projectId}/progress-claims`, { params }).then((r) => r.data.data as ProgressClaimListItem[]);

// Get single claim with lines and evidence
export const getProgressClaim = (claimId: string) =>
  client.get(`/api/v1/progress-claims/${claimId}`).then((r) => r.data.data as ProgressClaim);

// Create a new claim
export const createProgressClaim = (projectId: string, body: ProgressClaimCreate) =>
  client.post(`/api/v1/projects/${projectId}/progress-claims`, body).then((r) => r.data.data as ProgressClaim);

// Update claim metadata
export const updateProgressClaim = (claimId: string, body: Partial<ProgressClaimCreate>) =>
  client.patch(`/api/v1/progress-claims/${claimId}`, body).then((r) => r.data.data as ProgressClaim);

// Delete claim
export const deleteProgressClaim = (claimId: string) =>
  client.delete(`/api/v1/progress-claims/${claimId}`).then((r) => r.data);

// Auto-generate lines from canonical sources
export const generateClaimLines = (claimId: string, body: GenerateClaimRequest = {}) =>
  client.post(`/api/v1/progress-claims/${claimId}/generate`, {
    include_work_done: true,
    include_job_cards: true,
    include_milestones: true,
    overwrite_existing: false,
    ...body,
  }).then((r) => r.data);

// Transition claim status
export const transitionClaimStatus = (claimId: string, newStatus: ProgressClaimStatus) =>
  client.post(`/api/v1/progress-claims/${claimId}/transition/${newStatus}`).then((r) => r.data.data as ProgressClaim);

// Update a single claim line (include/exclude, reviewer_notes)
export const updateClaimLine = (claimId: string, lineId: string, body: ClaimLineUpdate) =>
  client.patch(`/api/v1/progress-claims/${claimId}/lines/${lineId}`, body).then((r) => r.data);

// Delete a line
export const deleteClaimLine = (claimId: string, lineId: string) =>
  client.delete(`/api/v1/progress-claims/${claimId}/lines/${lineId}`).then((r) => r.data);

// Export PDF
export const exportClaimPdf = (claimId: string): Promise<Blob> =>
  client.get(`/api/v1/progress-claims/${claimId}/export/pdf`, { responseType: "blob" }).then((r) => r.data);
