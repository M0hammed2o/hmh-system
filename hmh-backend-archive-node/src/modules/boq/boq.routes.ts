import { Router, Response, NextFunction } from 'express';
import { body } from 'express-validator';
import * as boqService from './boq.service';
import { authenticate, authorize, OFFICE_AND_ABOVE, OFFICE_ADMIN_AND_ABOVE, ALL_ROLES } from '../../middleware/auth';
import { validate } from '../../middleware/validate';
import { AuthRequest } from '../../types';
import { AppError } from '../../middleware/errorHandler';

const router = Router({ mergeParams: true }); // mounted under /api/projects/:projectId/boq
router.use(authenticate);

// GET /api/projects/:projectId/boq  — list all versions
router.get('/', authorize(...OFFICE_AND_ABOVE), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const headers = await boqService.listBoqHeaders(req.params.projectId);
    res.json({ success: true, data: headers });
  } catch (err) { next(err); }
});

// GET /api/projects/:projectId/boq/active
router.get('/active', authorize(...ALL_ROLES), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const boq = await boqService.getBoqWithSectionsAndItems(
      (await boqService.getActiveBoq(req.params.projectId)).id
    );
    res.json({ success: true, data: boq });
  } catch (err) { next(err); }
});

// GET /api/projects/:projectId/boq/variance
router.get('/variance', authorize(...OFFICE_AND_ABOVE), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const data = await boqService.getBoqVariance(req.params.projectId, req.query.header_id as string);
    res.json({ success: true, data });
  } catch (err) { next(err); }
});

// GET /api/projects/:projectId/boq/:id
router.get('/:id', authorize(...OFFICE_AND_ABOVE), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const boq = await boqService.getBoqWithSectionsAndItems(req.params.id);
    res.json({ success: true, data: boq });
  } catch (err) { next(err); }
});

// POST /api/projects/:projectId/boq
router.post('/',
  authorize(...OFFICE_ADMIN_AND_ABOVE),
  [body('version_name').trim().notEmpty().withMessage('version_name is required.')],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const header = await boqService.createBoqHeader(
        { ...req.body, project_id: req.params.projectId },
        req.user.sub
      );
      res.status(201).json({ success: true, data: header });
    } catch (err) { next(err); }
  }
);

// POST /api/projects/:projectId/boq/:id/activate
router.post('/:id/activate',
  authorize(...OFFICE_ADMIN_AND_ABOVE),
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const header = await boqService.activateBoqVersion(req.params.id, req.user.sub);
      res.json({ success: true, data: header });
    } catch (err) { next(err); }
  }
);

// POST /api/projects/:projectId/boq/:id/sections
router.post('/:id/sections',
  authorize(...OFFICE_ADMIN_AND_ABOVE),
  [body('section_name').trim().notEmpty().withMessage('section_name is required.')],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const section = await boqService.addBoqSection(req.params.id, req.body, req.user.sub);
      res.status(201).json({ success: true, data: section });
    } catch (err) { next(err); }
  }
);

// POST /api/projects/:projectId/boq/:id/items
router.post('/:id/items',
  authorize(...OFFICE_ADMIN_AND_ABOVE),
  [
    body('boq_section_id').isUUID().withMessage('boq_section_id is required.'),
    body('raw_description').trim().notEmpty().withMessage('raw_description is required.'),
  ],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const item = await boqService.addBoqItem(
        { ...req.body, project_id: req.params.projectId },
        req.user.sub
      );
      res.status(201).json({ success: true, data: item });
    } catch (err) { next(err); }
  }
);

// PATCH /api/projects/:projectId/boq/items/:itemId/normalize
router.patch('/items/:itemId/normalize',
  authorize(...OFFICE_ADMIN_AND_ABOVE),
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const item = await boqService.normalizeBoqItem(req.params.itemId, req.body, req.user.sub);
      res.json({ success: true, data: item });
    } catch (err) { next(err); }
  }
);

export default router;
