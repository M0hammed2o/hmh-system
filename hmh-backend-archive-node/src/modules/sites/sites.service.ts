import { query, queryOne, pool } from '../../config/database';
import { AppError } from '../../middleware/errorHandler';
import { logAudit } from '../../middleware/audit';
import { Site } from '../../types';

export async function listSites(projectId: string, includeInactive = false): Promise<Site[]> {
  const where = includeInactive ? 'WHERE project_id = $1' : 'WHERE project_id = $1 AND is_active = TRUE';
  return query<Site>(`SELECT * FROM sites ${where} ORDER BY name`, [projectId]);
}

export async function getSiteById(id: string): Promise<Site> {
  const site = await queryOne<Site>(`SELECT * FROM sites WHERE id = $1`, [id]);
  if (!site) throw new AppError(404, 'Site not found.', 'NOT_FOUND');
  return site;
}

export async function createSite(
  input: { project_id: string; name: string; code?: string; site_type?: string; location_description?: string },
  createdBy: string
): Promise<Site> {
  const [site] = await query<Site>(
    `INSERT INTO sites (project_id, name, code, site_type, location_description)
     VALUES ($1, $2, $3, $4, $5) RETURNING *`,
    [input.project_id, input.name, input.code ?? null, input.site_type ?? 'construction_site', input.location_description ?? null]
  );
  await logAudit(createdBy, 'sites', site.id, 'CREATE', null, { name: site.name, project_id: input.project_id });
  return site;
}

export async function updateSite(
  id: string,
  input: Partial<{ name: string; code: string; site_type: string; location_description: string; is_active: boolean }>,
  updatedBy: string
): Promise<Site> {
  const existing = await getSiteById(id);
  const sets: string[] = [];
  const params: unknown[] = [];
  let i = 1;

  const fields = ['name', 'code', 'site_type', 'location_description', 'is_active'] as const;
  for (const f of fields) {
    if (input[f] !== undefined) { sets.push(`${f} = $${i++}`); params.push(input[f]); }
  }

  if (sets.length === 0) return existing;
  sets.push(`updated_at = NOW()`);
  params.push(id);

  const [updated] = await query<Site>(
    `UPDATE sites SET ${sets.join(', ')} WHERE id = $${i} RETURNING *`, params
  );
  await logAudit(updatedBy, 'sites', id, 'UPDATE', existing as unknown as Record<string, unknown>, input as Record<string, unknown>);
  return updated;
}
