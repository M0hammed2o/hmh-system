import client from "./client";

export type StageStatus =
  | "NOT_STARTED"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "AWAITING_INSPECTION"
  | "CERTIFIED";

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
};
