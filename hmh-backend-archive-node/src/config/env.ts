import dotenv from 'dotenv';
import path from 'path';

dotenv.config({ path: path.resolve(process.cwd(), '.env') });

function required(key: string): string {
  const value = process.env[key];
  if (!value) throw new Error(`Missing required environment variable: ${key}`);
  return value;
}

function optional(key: string, fallback: string): string {
  return process.env[key] ?? fallback;
}

export const env = {
  NODE_ENV: optional('NODE_ENV', 'development'),
  PORT: parseInt(optional('PORT', '5000'), 10),

  db: {
    host: optional('DB_HOST', 'localhost'),
    port: parseInt(optional('DB_PORT', '5432'), 10),
    name: optional('DB_NAME', 'hmh_system'),
    user: optional('DB_USER', 'postgres'),
    password: optional('DB_PASSWORD', ''),
  },

  jwt: {
    secret: optional('JWT_SECRET', 'dev_secret_change_in_production_min_32'),
    expiresIn: optional('JWT_EXPIRES_IN', '8h'),
    refreshSecret: optional('JWT_REFRESH_SECRET', 'dev_refresh_secret_change_in_prod'),
    refreshExpiresIn: optional('JWT_REFRESH_EXPIRES_IN', '7d'),
  },

  upload: {
    dir: optional('UPLOAD_DIR', './uploads'),
    maxFileSizeMB: parseInt(optional('MAX_FILE_SIZE_MB', '5'), 10),
  },

  rateLimit: {
    windowMs: parseInt(optional('RATE_LIMIT_WINDOW_MS', '900000'), 10),
    max: parseInt(optional('RATE_LIMIT_MAX', '100'), 10),
  },

  logLevel: optional('LOG_LEVEL', 'info'),
};
