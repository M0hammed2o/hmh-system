import { Response, NextFunction } from 'express';
import { pool } from '../config/database';
import { AuthRequest } from '../types';
import { logger } from '../config/logger';

export async function logAudit(
  userId: string | null,
  entityType: string,
  entityId: string | null,
  action: string,
  oldValues: Record<string, unknown> | null,
  newValues: Record<string, unknown> | null,
  ipAddress?: string,
  userAgent?: string
): Promise<void> {
  try {
    await pool.query(
      `INSERT INTO audit_logs
         (user_id, entity_type, entity_id, action, old_values_json, new_values_json, ip_address, user_agent)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
      [
        userId,
        entityType,
        entityId,
        action,
        oldValues ? JSON.stringify(oldValues) : null,
        newValues ? JSON.stringify(newValues) : null,
        ipAddress ?? null,
        userAgent ?? null,
      ]
    );
  } catch (err) {
    logger.error('Failed to write audit log', { error: (err as Error).message });
  }
}

export function auditMiddleware(entityType: string, action: string) {
  return async (req: AuthRequest, _res: Response, next: NextFunction): Promise<void> => {
    const userId = req.user?.sub ?? null;
    const ip = req.ip ?? req.socket.remoteAddress ?? undefined;
    const ua = req.headers['user-agent'];
    await logAudit(userId, entityType, null, action, null, null, ip, ua);
    next();
  };
}
