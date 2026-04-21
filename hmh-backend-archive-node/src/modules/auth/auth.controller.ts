import { Request, Response, NextFunction } from 'express';
import { body } from 'express-validator';
import * as authService from './auth.service';
import { validate } from '../../middleware/validate';
import { authenticate } from '../../middleware/auth';
import { AuthRequest } from '../../types';
import { AppError } from '../../middleware/errorHandler';

export const loginValidators = [
  body('email').isEmail().normalizeEmail().withMessage('Valid email is required.'),
  body('password').notEmpty().withMessage('Password is required.'),
];

export const changePasswordValidators = [
  body('currentPassword').notEmpty().withMessage('Current password is required.'),
  body('newPassword')
    .isLength({ min: 8 })
    .withMessage('New password must be at least 8 characters.')
    .matches(/[A-Z]/).withMessage('New password must contain at least one uppercase letter.')
    .matches(/[0-9]/).withMessage('New password must contain at least one number.'),
];

export async function loginHandler(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const { email, password } = req.body as { email: string; password: string };
    const ip = req.ip ?? undefined;
    const ua = req.headers['user-agent'];
    const result = await authService.login(email, password, ip, ua);
    res.json({
      success: true,
      data: {
        ...result.tokens,
        mustResetPassword: result.mustResetPassword,
      },
    });
  } catch (err) {
    next(err);
  }
}

export async function refreshHandler(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const { refreshToken } = req.body as { refreshToken: string };
    if (!refreshToken) {
      res.status(400).json({ success: false, message: 'refreshToken is required.' });
      return;
    }
    const tokens = await authService.refreshTokens(refreshToken);
    res.json({ success: true, data: tokens });
  } catch (err) {
    next(err);
  }
}

export async function changePasswordHandler(req: AuthRequest, res: Response, next: NextFunction): Promise<void> {
  try {
    if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
    const { currentPassword, newPassword } = req.body as { currentPassword: string; newPassword: string };
    await authService.changePassword(req.user.sub, currentPassword, newPassword);
    res.json({ success: true, data: null, message: 'Password changed successfully.' });
  } catch (err) {
    next(err);
  }
}

export async function getMeHandler(req: AuthRequest, res: Response, next: NextFunction): Promise<void> {
  try {
    if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
    const user = await authService.getMe(req.user.sub);
    res.json({ success: true, data: user });
  } catch (err) {
    next(err);
  }
}

export { validate, authenticate };
