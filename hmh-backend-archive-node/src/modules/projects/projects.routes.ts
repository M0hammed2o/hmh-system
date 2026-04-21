import { Router, Response, NextFunction } from 'express';
import { body } from 'express-validator';
import * as projectsService from './projects.service';
import { authenticate, authorize, OFFICE_AND_ABOVE, OFFICE_ADMIN_AND_ABOVE, ALL_ROLES } from '../../middleware/auth';
import { validate } from '../../middleware/validate';
import { AuthRequest, ProjectStatus } from '../../types';
import { AppError } from '../../middleware/errorHandler';

const router = Router();
router.use(authenticate);

const projectValidators = [
  body('name').trim().notEmpty().withMessage('Project name is required.'),
  body('code').trim().notEmpty().withMessage('Project code is required.'),
  body('status').optional().isIn(['PLANNED', 'ACTIVE', 'PAUSED', 'COMPLETED']),
  body('start_date').optional().isISO8601().toDate(),
  body('estimated_end_date').optional().isISO8601().toDate(),
];

router.get('/', authorize(...ALL_ROLES), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
    const page = parseInt(req.query.page as string ?? '1', 10);
    const limit = Math.min(parseInt(req.query.limit as string ?? '20', 10), 100);
    const result = await projectsService.listProjects(
      req.user.sub, req.user.role, page, limit,
      { status: req.query.status as ProjectStatus, search: req.query.search as string }
    );
    res.json({ success: true, data: result });
  } catch (err) { next(err); }
});

router.get('/:id', authorize(...ALL_ROLES), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const project = await projectsService.getProjectById(req.params.id);
    res.json({ success: true, data: project });
  } catch (err) { next(err); }
});

router.post('/', authorize(...OFFICE_ADMIN_AND_ABOVE), projectValidators, validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const project = await projectsService.createProject(req.body, req.user.sub);
      res.status(201).json({ success: true, data: project });
    } catch (err) { next(err); }
  }
);

router.patch('/:id', authorize(...OFFICE_ADMIN_AND_ABOVE), projectValidators.map(v => v.optional()), validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const project = await projectsService.updateProject(req.params.id, req.body, req.user.sub);
      res.json({ success: true, data: project });
    } catch (err) { next(err); }
  }
);

export default router;
