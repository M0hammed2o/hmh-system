import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { queryOne, pool } from '../../config/database';
import { env } from '../../config/env';
import { AppError } from '../../middleware/errorHandler';
import { logAudit } from '../../middleware/audit';
import { User, JwtPayload, AuthTokens } from '../../types';

const MAX_FAILED_ATTEMPTS = 5;
const LOCKOUT_MINUTES = 15;

function generateTokens(user: User): AuthTokens {
  const payload: JwtPayload = { sub: user.id, email: user.email, role: user.role };

  const accessToken = jwt.sign(payload, env.jwt.secret, {
    expiresIn: env.jwt.expiresIn,
  } as jwt.SignOptions);

  const refreshToken = jwt.sign(
    { sub: user.id },
    env.jwt.refreshSecret,
    { expiresIn: env.jwt.refreshExpiresIn } as jwt.SignOptions
  );

  return { accessToken, refreshToken, expiresIn: env.jwt.expiresIn };
}

export async function login(
  email: string,
  password: string,
  ip?: string,
  ua?: string
): Promise<{ tokens: AuthTokens; mustResetPassword: boolean }> {
  const user = await queryOne<User>(
    `SELECT * FROM users WHERE email = $1`,
    [email.toLowerCase().trim()]
  );

  if (!user) {
    throw new AppError(401, 'Invalid email or password.', 'INVALID_CREDENTIALS');
  }

  if (!user.is_active) {
    throw new AppError(403, 'Account is disabled. Contact your administrator.', 'ACCOUNT_DISABLED');
  }

  // Check lockout
  if (user.locked_until && new Date() < new Date(user.locked_until)) {
    throw new AppError(423, 'Account is temporarily locked. Try again later.', 'ACCOUNT_LOCKED');
  }

  const valid = await bcrypt.compare(password, user.password_hash);

  if (!valid) {
    const newAttempts = user.failed_login_attempts + 1;
    const lockedUntil =
      newAttempts >= MAX_FAILED_ATTEMPTS
        ? new Date(Date.now() + LOCKOUT_MINUTES * 60 * 1000)
        : null;

    await pool.query(
      `UPDATE users SET failed_login_attempts = $1, locked_until = $2, updated_at = NOW() WHERE id = $3`,
      [newAttempts, lockedUntil, user.id]
    );

    await logAudit(user.id, 'users', user.id, 'LOGIN_FAILED', null, { attempts: newAttempts }, ip, ua);
    throw new AppError(401, 'Invalid email or password.', 'INVALID_CREDENTIALS');
  }

  // Successful login — reset attempts and update last_login_at
  await pool.query(
    `UPDATE users SET failed_login_attempts = 0, locked_until = NULL, last_login_at = NOW(), updated_at = NOW() WHERE id = $1`,
    [user.id]
  );

  const tokens = generateTokens(user);
  await logAudit(user.id, 'users', user.id, 'LOGIN_SUCCESS', null, null, ip, ua);

  return { tokens, mustResetPassword: user.must_reset_password };
}

export async function refreshTokens(refreshToken: string): Promise<AuthTokens> {
  let decoded: { sub: string };
  try {
    decoded = jwt.verify(refreshToken, env.jwt.refreshSecret) as { sub: string };
  } catch {
    throw new AppError(401, 'Invalid or expired refresh token.', 'INVALID_TOKEN');
  }

  const user = await queryOne<User>(`SELECT * FROM users WHERE id = $1 AND is_active = TRUE`, [decoded.sub]);
  if (!user) {
    throw new AppError(401, 'User not found or inactive.', 'UNAUTHORIZED');
  }

  return generateTokens(user);
}

export async function changePassword(
  userId: string,
  currentPassword: string,
  newPassword: string
): Promise<void> {
  const user = await queryOne<User>(`SELECT * FROM users WHERE id = $1`, [userId]);
  if (!user) throw new AppError(404, 'User not found.', 'NOT_FOUND');

  const valid = await bcrypt.compare(currentPassword, user.password_hash);
  if (!valid) throw new AppError(401, 'Current password is incorrect.', 'INVALID_CREDENTIALS');

  if (newPassword.length < 8) {
    throw new AppError(422, 'New password must be at least 8 characters.', 'VALIDATION_ERROR');
  }

  const hash = await bcrypt.hash(newPassword, 12);
  await pool.query(
    `UPDATE users SET password_hash = $1, must_reset_password = FALSE, updated_at = NOW() WHERE id = $2`,
    [hash, userId]
  );

  await logAudit(userId, 'users', userId, 'PASSWORD_CHANGED', null, null);
}

export async function getMe(userId: string): Promise<Omit<User, 'password_hash'>> {
  const user = await queryOne<User>(
    `SELECT id, full_name, email, phone, role, is_active, must_reset_password, last_login_at, created_at, updated_at
     FROM users WHERE id = $1`,
    [userId]
  );
  if (!user) throw new AppError(404, 'User not found.', 'NOT_FOUND');
  return user as Omit<User, 'password_hash'>;
}
