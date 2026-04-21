import { Router, Response, NextFunction } from 'express';
import { body, query as qv, param } from 'express-validator';
import * as usersService from './users.service';
import { authenticate, authorize, OWNER_ONLY, OFFICE_ADMIN_AND_ABOVE } from '../../middleware/auth';
import { validate } from '../../middleware/validate';
import { AuthRequest, UserRole } from '../../types';
import { AppError } from '../../middleware/errorHandler';

const router = Router();

// All routes require auth
router.use(authenticate);

// GET /api/users
router.get(
  '/',
  authorize(...OFFICE_ADMIN_AND_ABOVE),
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      const page = parseInt(req.query.page as string ?? '1', 10);
      const limit = Math.min(parseInt(req.query.limit as string ?? '20', 10), 100);
      const result = await usersService.listUsers(page, limit, {
        role: req.query.role as UserRole,
        is_active: req.query.is_active !== undefined ? req.query.is_active === 'true' : undefined,
        search: req.query.search as string,
      });
      res.json({ success: true, data: result });
    } catch (err) { next(err); }
  }
);

// GET /api/users/:id
router.get(
  '/:id',
  authorize(...OFFICE_ADMIN_AND_ABOVE),
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      const user = await usersService.getUserById(req.params.id);
      res.json({ success: true, data: user });
    } catch (err) { next(err); }
  }
);

// POST /api/users
router.post(
  '/',
  authorize(...OWNER_ONLY),
  [
    body('full_name').trim().notEmpty().withMessage('Full name is required.'),
    body('email').isEmail().normalizeEmail().withMessage('Valid email is required.'),
    body('phone').optional().trim(),
    body('role').isIn(['OWNER', 'OFFICE_ADMIN', 'OFFICE_USER', 'SITE_MANAGER', 'SITE_STAFF'])
      .withMessage('Invalid role.'),
  ],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const user = await usersService.createUser({ ...req.body, createdBy: req.user.sub });
      res.status(201).json({ success: true, data: user });
    } catch (err) { next(err); }
  }
);

// PATCH /api/users/:id
router.patch(
  '/:id',
  authorize(...OWNER_ONLY),
  [
    body('role').optional().isIn(['OWNER', 'OFFICE_ADMIN', 'OFFICE_USER', 'SITE_MANAGER', 'SITE_STAFF']),
    body('is_active').optional().isBoolean(),
  ],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const user = await usersService.updateUser(req.params.id, req.body, req.user.sub);
      res.json({ success: true, data: user });
    } catch (err) { next(err); }
  }
);

// POST /api/users/:id/unlock
router.post(
  '/:id/unlock',
  authorize(...OWNER_ONLY),
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const user = await usersService.unlockUser(req.params.id, req.user.sub);
      res.json({ success: true, data: user });
    } catch (err) { next(err); }
  }
);

// POST /api/users/:id/reset-password
router.post(
  '/:id/reset-password',
  authorize(...OWNER_ONLY),
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const result = await usersService.resetUserPassword(req.params.id, req.user.sub);
      res.json({ success: true, data: result });
    } catch (err) { next(err); }
  }
);

// POST /api/users/:id/project-access
router.post(
  '/:id/project-access',
  authorize(...OWNER_ONLY),
  [
    body('project_id').isUUID().withMessage('Valid project_id is required.'),
    body('can_view').optional().isBoolean(),
    body('can_edit').optional().isBoolean(),
    body('can_approve').optional().isBoolean(),
  ],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      await usersService.grantProjectAccess(req.params.id, req.body.project_id, req.body, req.user.sub);
      res.json({ success: true, data: null, message: 'Project access updated.' });
    } catch (err) { next(err); }
  }
);

// POST /api/users/:id/site-access
router.post(
  '/:id/site-access',
  authorize(...OWNER_ONLY),
  [
    body('site_id').isUUID().withMessage('Valid site_id is required.'),
  ],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      await usersService.grantSiteAccess(req.params.id, req.body.site_id, req.body, req.user.sub);
      res.json({ success: true, data: null, message: 'Site access updated.' });
    } catch (err) { next(err); }
  }
);

export default router;
