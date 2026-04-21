import { Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import { env } from '../config/env';
import { AppError } from './errorHandler';
import { AuthRequest, JwtPayload, UserRole } from '../types';

export function authenticate(req: AuthRequest, _res: Response, next: NextFunction): void {
  const authHeader = req.headers.authorization;
  if (!authHeader?.startsWith('Bearer ')) {
    return next(new AppError(401, 'No token provided.', 'UNAUTHORIZED'));
  }

  const token = authHeader.slice(7);
  try {
    const payload = jwt.verify(token, env.jwt.secret) as JwtPayload;
    req.user = payload;
    next();
  } catch {
    next(new AppError(401, 'Invalid or expired token.', 'UNAUTHORIZED'));
  }
}

export function authorize(...roles: UserRole[]) {
  return (req: AuthRequest, _res: Response, next: NextFunction): void => {
    if (!req.user) {
      return next(new AppError(401, 'Not authenticated.', 'UNAUTHORIZED'));
    }
    if (!roles.includes(req.user.role)) {
      return next(new AppError(403, 'You do not have permission to perform this action.', 'FORBIDDEN'));
    }
    next();
  };
}

// Convenience role sets
export const OWNER_ONLY = ['OWNER'] as UserRole[];
export const OFFICE_AND_ABOVE = ['OWNER', 'OFFICE_ADMIN', 'OFFICE_USER'] as UserRole[];
export const OFFICE_ADMIN_AND_ABOVE = ['OWNER', 'OFFICE_ADMIN'] as UserRole[];
export const ALL_ROLES = ['OWNER', 'OFFICE_ADMIN', 'OFFICE_USER', 'SITE_MANAGER', 'SITE_STAFF'] as UserRole[];
