import { Router, Response, NextFunction } from 'express';
import { body } from 'express-validator';
import * as sitesService from './sites.service';
import { authenticate, authorize, OFFICE_AND_ABOVE, OFFICE_ADMIN_AND_ABOVE, ALL_ROLES } from '../../middleware/auth';
import { validate } from '../../middleware/validate';
import { AuthRequest } from '../../types';
import { AppError } from '../../middleware/errorHandler';

const router = Router({ mergeParams: true }); // mounted under /api/projects/:projectId/sites
router.use(authenticate);

router.get('/', authorize(...ALL_ROLES), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const sites = await sitesService.listSites(req.params.projectId, req.query.include_inactive === 'true');
    res.json({ success: true, data: sites });
  } catch (err) { next(err); }
});

router.get('/:id', authorize(...ALL_ROLES), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const site = await sitesService.getSiteById(req.params.id);
    res.json({ success: true, data: site });
  } catch (err) { next(err); }
});

router.post('/',
  authorize(...OFFICE_ADMIN_AND_ABOVE),
  [body('name').trim().notEmpty().withMessage('Site name is required.')],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const site = await sitesService.createSite({ ...req.body, project_id: req.params.projectId }, req.user.sub);
      res.status(201).json({ success: true, data: site });
    } catch (err) { next(err); }
  }
);

router.patch('/:id', authorize(...OFFICE_ADMIN_AND_ABOVE), validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const site = await sitesService.updateSite(req.params.id, req.body, req.user.sub);
      res.json({ success: true, data: site });
    } catch (err) { next(err); }
  }
);

export default router;
