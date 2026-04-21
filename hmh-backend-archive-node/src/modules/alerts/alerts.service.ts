import { query, queryOne, pool } from '../../config/database';
import { AppError } from '../../middleware/errorHandler';
import { AlertType, AlertSeverity, AlertStatus, PaginatedResult } from '../../types';

interface SystemAlert {
  id: string;
  project_id: string | null;
  site_id: string | null;
  lot_id: string | null;
  reference_type: string | null;
  reference_id: string | null;
  alert_type: AlertType;
  severity: AlertSeverity;
  title: string;
  message: string;
  status: AlertStatus;
  notification_channel: string;
  sent_at: Date | null;
  read_at: Date | null;
  acknowledged_by: string | null;
  acknowledged_at: Date | null;
  created_at: Date;
  resolved_at: Date | null;
  resolved_by: string | null;
}

export async function createAlert(input: {
  project_id?: string;
  site_id?: string;
  lot_id?: string;
  alert_type: AlertType;
  severity?: AlertSeverity;
  title: string;
  message: string;
  reference_type?: string;
  reference_id?: string;
}): Promise<void> {
  await pool.query(
    `INSERT INTO system_alerts
       (project_id, site_id, lot_id, alert_type, severity, title, message, reference_type, reference_id)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
    [
      input.project_id ?? null,
      input.site_id ?? null,
      input.lot_id ?? null,
      input.alert_type,
      input.severity ?? 'MEDIUM',
      input.title,
      input.message,
      input.reference_type ?? null,
      input.reference_id ?? null,
    ]
  );
}

export async function listAlerts(
  projectId: string,
  page = 1,
  limit = 20,
  filters: { status?: AlertStatus; severity?: AlertSeverity; site_id?: string } = {}
): Promise<PaginatedResult<SystemAlert>> {
  const conditions = ['project_id = $1'];
  const params: unknown[] = [projectId];
  let i = 2;

  if (filters.status) { conditions.push(`status = $${i++}`); params.push(filters.status); }
  if (filters.severity) { conditions.push(`severity = $${i++}`); params.push(filters.severity); }
  if (filters.site_id) { conditions.push(`site_id = $${i++}`); params.push(filters.site_id); }

  const where = `WHERE ${conditions.join(' AND ')}`;
  const offset = (page - 1) * limit;

  const [countRow] = await query<{ count: string }>(`SELECT COUNT(*) as count FROM system_alerts ${where}`, params);
  const total = parseInt(countRow.count, 10);

  const items = await query<SystemAlert>(
    `SELECT * FROM system_alerts ${where} ORDER BY
       CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END,
       created_at DESC
     LIMIT $${i} OFFSET $${i + 1}`,
    [...params, limit, offset]
  );

  return { items, total, page, limit, totalPages: Math.ceil(total / limit) };
}

export async function acknowledgeAlert(id: string, userId: string): Promise<SystemAlert> {
  const alert = await queryOne<SystemAlert>(`SELECT * FROM system_alerts WHERE id = $1`, [id]);
  if (!alert) throw new AppError(404, 'Alert not found.', 'NOT_FOUND');
  if (alert.status !== 'OPEN') throw new AppError(422, 'Only OPEN alerts can be acknowledged.', 'INVALID_STATE');

  const [updated] = await query<SystemAlert>(
    `UPDATE system_alerts SET status = 'ACKNOWLEDGED', acknowledged_by = $1, acknowledged_at = NOW()
     WHERE id = $2 RETURNING *`,
    [userId, id]
  );
  return updated;
}

export async function resolveAlert(id: string, userId: string): Promise<SystemAlert> {
  const alert = await queryOne<SystemAlert>(`SELECT * FROM system_alerts WHERE id = $1`, [id]);
  if (!alert) throw new AppError(404, 'Alert not found.', 'NOT_FOUND');
  if (alert.status === 'RESOLVED') throw new AppError(422, 'Alert is already resolved.', 'INVALID_STATE');

  const [updated] = await query<SystemAlert>(
    `UPDATE system_alerts SET status = 'RESOLVED', resolved_by = $1, resolved_at = NOW()
     WHERE id = $2 RETURNING *`,
    [userId, id]
  );
  return updated;
}

export async function getAlertCounts(projectId: string): Promise<{
  open: number; acknowledged: number; critical: number; high: number;
}> {
  const rows = await query<{ status: string; severity: string; count: string }>(
    `SELECT status, severity, COUNT(*) as count FROM system_alerts
     WHERE project_id = $1 GROUP BY status, severity`,
    [projectId]
  );

  let open = 0, acknowledged = 0, critical = 0, high = 0;
  for (const row of rows) {
    const count = parseInt(row.count, 10);
    if (row.status === 'OPEN') open += count;
    if (row.status === 'ACKNOWLEDGED') acknowledged += count;
    if (row.severity === 'CRITICAL' && row.status !== 'RESOLVED') critical += count;
    if (row.severity === 'HIGH' && row.status !== 'RESOLVED') high += count;
  }

  return { open, acknowledged, critical, high };
}
