import { query, queryOne, pool } from '../../config/database';
import { AppError } from '../../middleware/errorHandler';
import { logAudit } from '../../middleware/audit';
import { Project, ProjectStatus, PaginatedResult } from '../../types';

export async function listProjects(
  userId: string,
  userRole: string,
  page = 1,
  limit = 20,
  filters: { status?: ProjectStatus; search?: string } = {}
): Promise<PaginatedResult<Project>> {
  const conditions: string[] = [];
  const params: unknown[] = [];
  let i = 1;

  // Non-owners only see projects they have access to
  if (!['OWNER', 'OFFICE_ADMIN'].includes(userRole)) {
    conditions.push(`p.id IN (SELECT project_id FROM user_project_access WHERE user_id = $${i++})`);
    params.push(userId);
  }

  if (filters.status) { conditions.push(`p.status = $${i++}`); params.push(filters.status); }
  if (filters.search) {
    conditions.push(`(p.name ILIKE $${i} OR p.code ILIKE $${i})`);
    params.push(`%${filters.search}%`);
    i++;
  }

  const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
  const offset = (page - 1) * limit;

  const [countRow] = await query<{ count: string }>(
    `SELECT COUNT(*) as count FROM projects p ${where}`, params
  );
  const total = parseInt(countRow.count, 10);

  const items = await query<Project>(
    `SELECT p.* FROM projects p ${where} ORDER BY p.created_at DESC LIMIT $${i} OFFSET $${i + 1}`,
    [...params, limit, offset]
  );

  return { items, total, page, limit, totalPages: Math.ceil(total / limit) };
}

export async function getProjectById(id: string): Promise<Project> {
  const project = await queryOne<Project>(`SELECT * FROM projects WHERE id = $1`, [id]);
  if (!project) throw new AppError(404, 'Project not found.', 'NOT_FOUND');
  return project;
}

export async function createProject(
  input: Omit<Project, 'id' | 'created_at' | 'updated_at'>,
  createdBy: string
): Promise<Project> {
  const [project] = await query<Project>(
    `INSERT INTO projects (name, code, description, location, client_name, start_date, estimated_end_date, go_live_date, status, created_by)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
     RETURNING *`,
    [input.name, input.code, input.description, input.location, input.client_name,
     input.start_date, input.estimated_end_date, input.go_live_date, input.status ?? 'PLANNED', createdBy]
  );
  await logAudit(createdBy, 'projects', project.id, 'CREATE', null, { name: project.name, code: project.code });
  return project;
}

export async function updateProject(
  id: string,
  input: Partial<Omit<Project, 'id' | 'created_at' | 'updated_at'>>,
  updatedBy: string
): Promise<Project> {
  const existing = await getProjectById(id);
  const sets: string[] = [];
  const params: unknown[] = [];
  let i = 1;

  const fields = ['name', 'code', 'description', 'location', 'client_name', 'start_date',
    'estimated_end_date', 'go_live_date', 'status'] as const;

  for (const field of fields) {
    if (input[field] !== undefined) {
      sets.push(`${field} = $${i++}`);
      params.push(input[field]);
    }
  }

  if (sets.length === 0) return existing;
  sets.push(`updated_at = NOW()`);
  params.push(id);

  const [updated] = await query<Project>(
    `UPDATE projects SET ${sets.join(', ')} WHERE id = $${i} RETURNING *`, params
  );
  await logAudit(updatedBy, 'projects', id, 'UPDATE', existing as unknown as Record<string, unknown>, input as Record<string, unknown>);
  return updated;
}
