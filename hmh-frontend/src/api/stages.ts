import client from "./client";

export type StageStatus =
  | "NOT_STARTED"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "AWAITING_INSPECTION"
  | "CERTIFIED";

export interface MilestonePhoto {
  id: string;
  url: string;
  file_name: string;
  mime_type: string;
  uploaded_at: string;
}

export interface StageMaster {
  id: string;
  name: string;
  sequence_order: number;
  description: string | null;
  created_at: string;
}

export interface ProjectStageStatus {
  id: string;
  project_id: string;
  site_id: string | null;
  lot_id: string | null;
  stage_id: string;
  status: StageStatus;
  started_at: string | null;
  completed_at: string | null;
  certified_at: string | null;
  inspection_required: boolean;
  certification_required: boolean;
  ready_for_labour_payment: boolean;
  notes: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
  // Enriched fields
  stage_name: string | null;
  sequence_order: number | null;
}

export interface StageStatusUpsert {
  stage_id: string;
  site_id?: string | null;
  lot_id?: string | null;
  status?: StageStatus;
  inspection_required?: boolean;
  certification_required?: boolean;
  ready_for_labour_payment?: boolean;
  notes?: string | null;
  delay_reason?: string | null;
}

export const stagesApi = {
  listMasters: async (): Promise<StageMaster[]> => {
    const res = await client.get<{ data: StageMaster[] }>("/stages/");
    return res.data.data;
  },

  listProjectStatuses: async (
    projectId: string,
    params?: { site_id?: string; lot_id?: string }
  ): Promise<ProjectStageStatus[]> => {
    const res = await client.get<{ data: ProjectStageStatus[] }>(
      `/projects/${projectId}/stage-statuses/`,
      { params }
    );
    return res.data.data;
  },

  upsert: async (
    projectId: string,
    body: StageStatusUpsert
  ): Promise<ProjectStageStatus> => {
    const res = await client.post<{ data: ProjectStageStatus }>(
      `/projects/${projectId}/stage-statuses/`,
      body
    );
    return res.data.data;
  },

  upsertWithEvidence: async (
    projectId: string,
    formData: FormData
  ): Promise<ProjectStageStatus> => {
    const res = await client.post<{ data: ProjectStageStatus }>(
      `/projects/${projectId}/stage-statuses/with-evidence`,
      formData,
      { headers: { "Content-Type": "multipart/form-data" } }
    );
    return res.data.data;
  },

  complete: async (projectId: string, statusId: string): Promise<ProjectStageStatus> => {
    const res = await client.post<{ data: ProjectStageStatus }>(
      `/projects/${projectId}/stage-statuses/${statusId}/complete`
    );
    return res.data.data;
  },

  listPhotos: async (projectId: string, statusId: string): Promise<MilestonePhoto[]> => {
    const res = await client.get<{ data: MilestonePhoto[] }>(
      `/projects/${projectId}/stage-statuses/${statusId}/photos`
    );
    return res.data.data;
  },

  uploadPhoto: async (projectId: string, statusId: string, file: File): Promise<MilestonePhoto> => {
    const fd = new FormData();
    fd.append("photo", file);
    const res = await client.post<{ data: MilestonePhoto }>(
      `/projects/${projectId}/stage-statuses/${statusId}/photos`,
      fd,
      { headers: { "Content-Type": "multipart/form-data" } }
    );
    return res.data.data;
  },

  deletePhoto: async (projectId: string, statusId: string, photoId: string): Promise<void> => {
    await client.delete(`/projects/${projectId}/stage-statuses/${statusId}/photos/${photoId}`);
  },
};
