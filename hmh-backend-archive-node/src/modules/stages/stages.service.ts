import { query, queryOne, pool } from '../../config/database';
import { AppError } from '../../middleware/errorHandler';
import { logAudit } from '../../middleware/audit';
import { StageMaster, StageStatus } from '../../types';

interface ProjectStageStatus {
  id: string;
  project_id: string;
  site_id: string | null;
  lot_id: string | null;
  stage_id: string;
  stage_name?: string;
  sequence_order?: number;
  status: StageStatus;
  started_at: Date | null;
  completed_at: Date | null;
  certified_at: Date | null;
  inspection_required: boolean;
  certification_required: boolean;
  ready_for_labour_payment: boolean;
  notes: string | null;
  updated_by: string | null;
  created_at: Date;
  updated_at: Date;
}

export async function listStageMaster(): Promise<StageMaster[]> {
  return query<StageMaster>(`SELECT * FROM stage_master ORDER BY sequence_order`);
}

export async function getProjectStages(
  projectId: string,
  siteId?: string,
  lotId?: string
): Promise<ProjectStageStatus[]> {
  const conditions = ['pss.project_id = $1'];
  const params: unknown[] = [projectId];
  let i = 2;

  if (siteId) { conditions.push(`pss.site_id = $${i++}`); params.push(siteId); }
  if (lotId) { conditions.push(`pss.lot_id = $${i++}`); params.push(lotId); }

  return query<ProjectStageStatus>(
    `SELECT pss.*, sm.name as stage_name, sm.sequence_order
     FROM project_stage_status pss
     JOIN stage_master sm ON sm.id = pss.stage_id
     WHERE ${conditions.join(' AND ')}
     ORDER BY sm.sequence_order`,
    params
  );
}

export async function upsertProjectStageStatus(
  input: {
    project_id: string;
    site_id?: string | null;
    lot_id?: string | null;
    stage_id: string;
    status?: StageStatus;
    inspection_required?: boolean;
    certification_required?: boolean;
    ready_for_labour_payment?: boolean;
    notes?: string;
  },
  updatedBy: string
): Promise<ProjectStageStatus> {
  // Validate status transitions: can't go back to NOT_STARTED once started
  const existing = await queryOne<ProjectStageStatus>(
    `SELECT * FROM project_stage_status WHERE project_id = $1
     AND (site_id = $2 OR (site_id IS NULL AND $2::uuid IS NULL))
     AND (lot_id = $3 OR (lot_id IS NULL AND $3::uuid IS NULL))
     AND stage_id = $4`,
    [input.project_id, input.site_id ?? null, input.lot_id ?? null, input.stage_id]
  );

  const newStatus = input.status ?? existing?.status ?? 'NOT_STARTED';
  const now = new Date();

  let started_at = existing?.started_at ?? null;
  let completed_at = existing?.completed_at ?? null;
  let certified_at = existing?.certified_at ?? null;

  if (newStatus === 'IN_PROGRESS' && !started_at) started_at = now;
  if (newStatus === 'COMPLETED' && !completed_at) completed_at = now;
  if (newStatus === 'CERTIFIED' && !certified_at) certified_at = now;

  const [record] = await query<ProjectStageStatus>(
    `INSERT INTO project_stage_status
       (project_id, site_id, lot_id, stage_id, status, started_at, completed_at, certified_at,
        inspection_required, certification_required, ready_for_labour_payment, notes, updated_by)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
     ON CONFLICT (project_id, site_id, lot_id, stage_id) DO UPDATE SET
       status = EXCLUDED.status,
       started_at = COALESCE(project_stage_status.started_at, EXCLUDED.started_at),
       completed_at = COALESCE(project_stage_status.completed_at, EXCLUDED.completed_at),
       certified_at = COALESCE(project_stage_status.certified_at, EXCLUDED.certified_at),
       inspection_required = EXCLUDED.inspection_required,
       certification_required = EXCLUDED.certification_required,
       ready_for_labour_payment = EXCLUDED.ready_for_labour_payment,
       notes = EXCLUDED.notes,
       updated_by = EXCLUDED.updated_by,
       updated_at = NOW()
     RETURNING *`,
    [
      input.project_id, input.site_id ?? null, input.lot_id ?? null, input.stage_id,
      newStatus, started_at, completed_at, certified_at,
      input.inspection_required ?? existing?.inspection_required ?? false,
      input.certification_required ?? existing?.certification_required ?? false,
      input.ready_for_labour_payment ?? existing?.ready_for_labour_payment ?? false,
      input.notes ?? existing?.notes ?? null,
      updatedBy,
    ]
  );

  await logAudit(updatedBy, 'project_stage_status', record.id, 'UPSERT',
    existing as unknown as Record<string, unknown>, input as Record<string, unknown>);
  return record;
}

export async function initializeProjectStages(
  projectId: string,
  siteId: string | null,
  lotId: string | null,
  createdBy: string
): Promise<void> {
  const stages = await listStageMaster();
  for (const stage of stages) {
    await upsertProjectStageStatus(
      { project_id: projectId, site_id: siteId, lot_id: lotId, stage_id: stage.id },
      createdBy
    );
  }
}
