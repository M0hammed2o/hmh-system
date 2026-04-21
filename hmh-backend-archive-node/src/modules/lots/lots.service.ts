import { query, queryOne } from '../../config/database';
import { AppError } from '../../middleware/errorHandler';
import { logAudit } from '../../middleware/audit';
import { Lot } from '../../types';

export async function listLots(projectId: string, siteId?: string): Promise<Lot[]> {
  if (siteId) {
    return query<Lot>(
      `SELECT * FROM lots WHERE project_id = $1 AND site_id = $2 ORDER BY lot_number`,
      [projectId, siteId]
    );
  }
  return query<Lot>(`SELECT * FROM lots WHERE project_id = $1 ORDER BY lot_number`, [projectId]);
}

export async function getLotById(id: string): Promise<Lot> {
  const lot = await queryOne<Lot>(`SELECT * FROM lots WHERE id = $1`, [id]);
  if (!lot) throw new AppError(404, 'Lot not found.', 'NOT_FOUND');
  return lot;
}

export async function createLot(
  input: { project_id: string; site_id?: string; lot_number: string; unit_type?: string; block_number?: string },
  createdBy: string
): Promise<Lot> {
  const [lot] = await query<Lot>(
    `INSERT INTO lots (project_id, site_id, lot_number, unit_type, block_number)
     VALUES ($1, $2, $3, $4, $5) RETURNING *`,
    [input.project_id, input.site_id ?? null, input.lot_number, input.unit_type ?? null, input.block_number ?? null]
  );
  await logAudit(createdBy, 'lots', lot.id, 'CREATE', null, { lot_number: lot.lot_number });
  return lot;
}

export async function updateLot(
  id: string,
  input: Partial<{ site_id: string; unit_type: string; block_number: string; status: string }>,
  updatedBy: string
): Promise<Lot> {
  const existing = await getLotById(id);
  const sets: string[] = [];
  const params: unknown[] = [];
  let i = 1;

  const fields = ['site_id', 'unit_type', 'block_number', 'status'] as const;
  for (const f of fields) {
    if (input[f] !== undefined) { sets.push(`${f} = $${i++}`); params.push(input[f]); }
  }

  if (sets.length === 0) return existing;
  sets.push(`updated_at = NOW()`);
  params.push(id);

  const [updated] = await query<Lot>(
    `UPDATE lots SET ${sets.join(', ')} WHERE id = $${i} RETURNING *`, params
  );
  await logAudit(updatedBy, 'lots', id, 'UPDATE', existing as unknown as Record<string, unknown>, input as Record<string, unknown>);
  return updated;
}
