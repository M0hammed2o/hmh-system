import bcrypt from 'bcryptjs';
import { query, queryOne, pool } from '../../config/database';
import { AppError } from '../../middleware/errorHandler';
import { logAudit } from '../../middleware/audit';
import { User, UserRole, PaginatedResult } from '../../types';

type SafeUser = Omit<User, 'password_hash'>;

const SAFE_FIELDS = `
  id, full_name, email, phone, role, is_active, must_reset_password,
  last_login_at, failed_login_attempts, locked_until, created_by, created_at, updated_at
`;

export async function listUsers(
  page = 1,
  limit = 20,
  filters: { role?: UserRole; is_active?: boolean; search?: string } = {}
): Promise<PaginatedResult<SafeUser>> {
  const conditions: string[] = [];
  const params: unknown[] = [];
  let i = 1;

  if (filters.role) { conditions.push(`role = $${i++}`); params.push(filters.role); }
  if (filters.is_active !== undefined) { conditions.push(`is_active = $${i++}`); params.push(filters.is_active); }
  if (filters.search) {
    conditions.push(`(full_name ILIKE $${i} OR email ILIKE $${i})`);
    params.push(`%${filters.search}%`);
    i++;
  }

  const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
  const offset = (page - 1) * limit;

  const [countRow] = await query<{ count: string }>(
    `SELECT COUNT(*) as count FROM users ${where}`,
    params
  );
  const total = parseInt(countRow.count, 10);

  const items = await query<SafeUser>(
    `SELECT ${SAFE_FIELDS} FROM users ${where} ORDER BY created_at DESC LIMIT $${i} OFFSET $${i + 1}`,
    [...params, limit, offset]
  );

  return { items, total, page, limit, totalPages: Math.ceil(total / limit) };
}

export async function getUserById(id: string): Promise<SafeUser> {
  const user = await queryOne<SafeUser>(
    `SELECT ${SAFE_FIELDS} FROM users WHERE id = $1`,
    [id]
  );
  if (!user) throw new AppError(404, 'User not found.', 'NOT_FOUND');
  return user;
}

export interface CreateUserInput {
  full_name: string;
  email: string;
  phone?: string;
  role: UserRole;
  createdBy: string;
}

export async function createUser(input: CreateUserInput): Promise<SafeUser> {
  // Generate a temporary password — user must reset on first login
  const tempPassword = generateTempPassword();
  const passwordHash = await bcrypt.hash(tempPassword, 12);

  const [user] = await query<SafeUser>(
    `INSERT INTO users (full_name, email, phone, password_hash, role, must_reset_password, created_by)
     VALUES ($1, $2, $3, $4, $5, TRUE, $6)
     RETURNING ${SAFE_FIELDS}`,
    [input.full_name, input.email.toLowerCase().trim(), input.phone ?? null, passwordHash, input.role, input.createdBy]
  );

  await logAudit(input.createdBy, 'users', user.id, 'CREATE', null, {
    email: user.email,
    role: user.role,
  });

  // In production, email the tempPassword to the user here.
  // For now, return it in the response (shown only once).
  (user as SafeUser & { tempPassword?: string }).tempPassword = tempPassword;

  return user;
}

export interface UpdateUserInput {
  full_name?: string;
  phone?: string;
  role?: UserRole;
  is_active?: boolean;
}

export async function updateUser(
  id: string,
  input: UpdateUserInput,
  updatedBy: string
): Promise<SafeUser> {
  const existing = await getUserById(id);

  const sets: string[] = [];
  const params: unknown[] = [];
  let i = 1;

  if (input.full_name !== undefined) { sets.push(`full_name = $${i++}`); params.push(input.full_name); }
  if (input.phone !== undefined) { sets.push(`phone = $${i++}`); params.push(input.phone); }
  if (input.role !== undefined) { sets.push(`role = $${i++}`); params.push(input.role); }
  if (input.is_active !== undefined) { sets.push(`is_active = $${i++}`); params.push(input.is_active); }

  if (sets.length === 0) return existing;

  sets.push(`updated_at = NOW()`);
  params.push(id);

  const [updated] = await query<SafeUser>(
    `UPDATE users SET ${sets.join(', ')} WHERE id = $${i} RETURNING ${SAFE_FIELDS}`,
    params
  );

  await logAudit(updatedBy, 'users', id, 'UPDATE', existing as unknown as Record<string, unknown>, input as Record<string, unknown>);
  return updated;
}

export async function unlockUser(id: string, unlockedBy: string): Promise<SafeUser> {
  const [user] = await query<SafeUser>(
    `UPDATE users SET locked_until = NULL, failed_login_attempts = 0, updated_at = NOW()
     WHERE id = $1 RETURNING ${SAFE_FIELDS}`,
    [id]
  );
  if (!user) throw new AppError(404, 'User not found.', 'NOT_FOUND');
  await logAudit(unlockedBy, 'users', id, 'UNLOCK', null, null);
  return user;
}

export async function resetUserPassword(id: string, resetBy: string): Promise<{ tempPassword: string }> {
  const tempPassword = generateTempPassword();
  const passwordHash = await bcrypt.hash(tempPassword, 12);

  await pool.query(
    `UPDATE users SET password_hash = $1, must_reset_password = TRUE, updated_at = NOW() WHERE id = $2`,
    [passwordHash, id]
  );

  await logAudit(resetBy, 'users', id, 'PASSWORD_RESET', null, null);
  return { tempPassword };
}

// Access control management
export async function grantProjectAccess(
  userId: string,
  projectId: string,
  permissions: { can_view?: boolean; can_edit?: boolean; can_approve?: boolean },
  grantedBy: string
): Promise<void> {
  await pool.query(
    `INSERT INTO user_project_access (user_id, project_id, can_view, can_edit, can_approve)
     VALUES ($1, $2, $3, $4, $5)
     ON CONFLICT (user_id, project_id) DO UPDATE SET
       can_view = EXCLUDED.can_view,
       can_edit = EXCLUDED.can_edit,
       can_approve = EXCLUDED.can_approve`,
    [userId, projectId, permissions.can_view ?? true, permissions.can_edit ?? false, permissions.can_approve ?? false]
  );
  await logAudit(grantedBy, 'user_project_access', userId, 'GRANT_ACCESS', null, { projectId, permissions });
}

export async function grantSiteAccess(
  userId: string,
  siteId: string,
  permissions: {
    can_receive_delivery?: boolean;
    can_record_usage?: boolean;
    can_request_stock?: boolean;
    can_update_stage?: boolean;
  },
  grantedBy: string
): Promise<void> {
  await pool.query(
    `INSERT INTO user_site_access (user_id, site_id, can_receive_delivery, can_record_usage, can_request_stock, can_update_stage)
     VALUES ($1, $2, $3, $4, $5, $6)
     ON CONFLICT (user_id, site_id) DO UPDATE SET
       can_receive_delivery = EXCLUDED.can_receive_delivery,
       can_record_usage = EXCLUDED.can_record_usage,
       can_request_stock = EXCLUDED.can_request_stock,
       can_update_stage = EXCLUDED.can_update_stage`,
    [
      userId, siteId,
      permissions.can_receive_delivery ?? false,
      permissions.can_record_usage ?? false,
      permissions.can_request_stock ?? false,
      permissions.can_update_stage ?? false,
    ]
  );
  await logAudit(grantedBy, 'user_site_access', userId, 'GRANT_SITE_ACCESS', null, { siteId, permissions });
}

function generateTempPassword(): string {
  const chars = 'ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#';
  let pwd = '';
  for (let i = 0; i < 10; i++) {
    pwd += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return pwd;
}
