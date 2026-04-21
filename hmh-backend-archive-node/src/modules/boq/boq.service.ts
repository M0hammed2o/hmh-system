import { query, queryOne, pool, withTransaction } from '../../config/database';
import { AppError } from '../../middleware/errorHandler';
import { logAudit } from '../../middleware/audit';
import { PoolClient } from 'pg';

interface BoqHeader {
  id: string;
  project_id: string;
  version_name: string;
  source_file_name: string | null;
  source_type: string;
  status: string;
  is_active_version: boolean;
  uploaded_by: string | null;
  uploaded_at: Date;
  notes: string | null;
}

interface BoqSection {
  id: string;
  boq_header_id: string;
  stage_id: string | null;
  section_name: string;
  sequence_order: number;
  notes: string | null;
}

interface BoqItem {
  id: string;
  boq_section_id: string;
  project_id: string;
  site_id: string | null;
  lot_id: string | null;
  stage_id: string | null;
  item_id: string | null;
  supplier_id: string | null;
  raw_description: string;
  normalized_description: string | null;
  specification: string | null;
  item_type: string;
  unit: string | null;
  planned_quantity: number | null;
  planned_rate: number | null;
  planned_total: number | null;
  planned_total_override: number | null;
  sort_order: number;
  is_active: boolean;
  notes: string | null;
}

export async function listBoqHeaders(projectId: string): Promise<BoqHeader[]> {
  return query<BoqHeader>(
    `SELECT * FROM boq_headers WHERE project_id = $1 ORDER BY uploaded_at DESC`,
    [projectId]
  );
}

export async function getBoqHeader(id: string): Promise<BoqHeader> {
  const h = await queryOne<BoqHeader>(`SELECT * FROM boq_headers WHERE id = $1`, [id]);
  if (!h) throw new AppError(404, 'BOQ not found.', 'NOT_FOUND');
  return h;
}

export async function getActiveBoq(projectId: string): Promise<BoqHeader> {
  const h = await queryOne<BoqHeader>(
    `SELECT * FROM boq_headers WHERE project_id = $1 AND is_active_version = TRUE`,
    [projectId]
  );
  if (!h) throw new AppError(404, 'No active BOQ version for this project.', 'NOT_FOUND');
  return h;
}

export async function createBoqHeader(
  input: { project_id: string; version_name: string; source_file_name?: string; source_type?: string; notes?: string },
  uploadedBy: string
): Promise<BoqHeader> {
  const [h] = await query<BoqHeader>(
    `INSERT INTO boq_headers (project_id, version_name, source_file_name, source_type, notes, uploaded_by)
     VALUES ($1, $2, $3, $4, $5, $6) RETURNING *`,
    [input.project_id, input.version_name, input.source_file_name ?? null,
     input.source_type ?? 'manual', input.notes ?? null, uploadedBy]
  );
  await logAudit(uploadedBy, 'boq_headers', h.id, 'CREATE', null, { version_name: h.version_name });
  return h;
}

export async function activateBoqVersion(headerId: string, activatedBy: string): Promise<BoqHeader> {
  return withTransaction(async (client: PoolClient) => {
    // Get current header and its project
    const h = await client.query<BoqHeader>(`SELECT * FROM boq_headers WHERE id = $1`, [headerId]);
    if (!h.rows[0]) throw new AppError(404, 'BOQ not found.', 'NOT_FOUND');
    const header = h.rows[0];

    if (header.status !== 'UNDER_REVIEW' && header.status !== 'DRAFT') {
      throw new AppError(422, 'Only DRAFT or UNDER_REVIEW BOQs can be activated.', 'INVALID_STATE');
    }

    // Deactivate any existing active version
    await client.query(
      `UPDATE boq_headers SET is_active_version = FALSE, status = 'SUPERSEDED', uploaded_at = uploaded_at
       WHERE project_id = $1 AND is_active_version = TRUE AND id != $2`,
      [header.project_id, headerId]
    );

    // Activate this one
    const result = await client.query<BoqHeader>(
      `UPDATE boq_headers SET is_active_version = TRUE, status = 'ACTIVE' WHERE id = $1 RETURNING *`,
      [headerId]
    );

    await logAudit(activatedBy, 'boq_headers', headerId, 'ACTIVATE', null, null);
    return result.rows[0];
  });
}

export async function getBoqWithSectionsAndItems(headerId: string): Promise<{
  header: BoqHeader;
  sections: (BoqSection & { items: BoqItem[] })[];
}> {
  const header = await getBoqHeader(headerId);

  const sections = await query<BoqSection>(
    `SELECT * FROM boq_sections WHERE boq_header_id = $1 ORDER BY sequence_order`,
    [headerId]
  );

  const result: (BoqSection & { items: BoqItem[] })[] = [];
  for (const section of sections) {
    const items = await query<BoqItem>(
      `SELECT * FROM boq_items WHERE boq_section_id = $1 AND is_active = TRUE ORDER BY sort_order`,
      [section.id]
    );
    result.push({ ...section, items });
  }

  return { header, sections: result };
}

export async function addBoqSection(
  headerId: string,
  input: { section_name: string; stage_id?: string; sequence_order?: number; notes?: string },
  createdBy: string
): Promise<BoqSection> {
  const [s] = await query<BoqSection>(
    `INSERT INTO boq_sections (boq_header_id, section_name, stage_id, sequence_order, notes)
     VALUES ($1, $2, $3, $4, $5) RETURNING *`,
    [headerId, input.section_name, input.stage_id ?? null, input.sequence_order ?? 0, input.notes ?? null]
  );
  await logAudit(createdBy, 'boq_sections', s.id, 'CREATE', null, { section_name: s.section_name });
  return s;
}

export async function addBoqItem(
  input: {
    boq_section_id: string;
    project_id: string;
    raw_description: string;
    normalized_description?: string;
    unit?: string;
    planned_quantity?: number;
    planned_rate?: number;
    planned_total_override?: number;
    item_type?: string;
    site_id?: string;
    lot_id?: string;
    stage_id?: string;
    item_id?: string;
    supplier_id?: string;
    specification?: string;
    sort_order?: number;
    notes?: string;
  },
  createdBy: string
): Promise<BoqItem> {
  const [item] = await query<BoqItem>(
    `INSERT INTO boq_items
       (boq_section_id, project_id, site_id, lot_id, stage_id, item_id, supplier_id,
        raw_description, normalized_description, specification, item_type, unit,
        planned_quantity, planned_rate, planned_total_override, sort_order, notes)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
     RETURNING *`,
    [
      input.boq_section_id, input.project_id,
      input.site_id ?? null, input.lot_id ?? null, input.stage_id ?? null,
      input.item_id ?? null, input.supplier_id ?? null,
      input.raw_description, input.normalized_description ?? null,
      input.specification ?? null, input.item_type ?? 'MATERIAL',
      input.unit ?? null, input.planned_quantity ?? null, input.planned_rate ?? null,
      input.planned_total_override ?? null, input.sort_order ?? 0, input.notes ?? null,
    ]
  );
  await logAudit(createdBy, 'boq_items', item.id, 'CREATE', null, { raw_description: item.raw_description });
  return item;
}

export async function normalizeBoqItem(
  itemId: string,
  input: { normalized_description?: string; item_id?: string; unit?: string },
  updatedBy: string
): Promise<BoqItem> {
  const [item] = await query<BoqItem>(
    `UPDATE boq_items
     SET normalized_description = COALESCE($1, normalized_description),
         item_id = COALESCE($2, item_id),
         unit = COALESCE($3, unit),
         updated_at = NOW()
     WHERE id = $4 RETURNING *`,
    [input.normalized_description ?? null, input.item_id ?? null, input.unit ?? null, itemId]
  );
  if (!item) throw new AppError(404, 'BOQ item not found.', 'NOT_FOUND');
  await logAudit(updatedBy, 'boq_items', itemId, 'NORMALIZE', null, input as Record<string, unknown>);
  return item;
}

// BOQ variance report: planned vs actual usage
export async function getBoqVariance(projectId: string, headerId?: string): Promise<{
  boq_item_id: string;
  raw_description: string;
  normalized_description: string | null;
  unit: string | null;
  planned_quantity: number | null;
  total_delivered: number;
  total_used: number;
  variance_pct: number | null;
}[]> {
  const activeBoq = headerId
    ? await getBoqHeader(headerId)
    : await getActiveBoq(projectId);

  return query(
    `SELECT
       bi.id as boq_item_id,
       bi.raw_description,
       bi.normalized_description,
       bi.unit,
       bi.planned_quantity,
       COALESCE(SUM(di.quantity_received), 0) as total_delivered,
       COALESCE(SUM(ul.quantity_used), 0) as total_used,
       CASE
         WHEN bi.planned_quantity IS NOT NULL AND bi.planned_quantity > 0
         THEN ROUND(((COALESCE(SUM(ul.quantity_used), 0) / bi.planned_quantity) - 1) * 100, 2)
         ELSE NULL
       END as variance_pct
     FROM boq_items bi
     JOIN boq_sections bs ON bs.id = bi.boq_section_id
     LEFT JOIN delivery_items di ON di.boq_item_id = bi.id
     LEFT JOIN usage_logs ul ON ul.boq_item_id = bi.id
     WHERE bs.boq_header_id = $1 AND bi.project_id = $2 AND bi.is_active = TRUE
     GROUP BY bi.id, bi.raw_description, bi.normalized_description, bi.unit, bi.planned_quantity
     ORDER BY variance_pct DESC NULLS LAST`,
    [activeBoq.id, projectId]
  );
}
