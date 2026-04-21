import { Router, Response, NextFunction } from 'express';
import { body } from 'express-validator';
import * as stagesService from './stages.service';
import { authenticate, authorize, OFFICE_AND_ABOVE, ALL_ROLES } from '../../middleware/auth';
import { validate } from '../../middleware/validate';
import { AuthRequest } from '../../types';
import { AppError } from '../../middleware/errorHandler';

const router = Router({ mergeParams: true });
router.use(authenticate);

// GET /api/stages  — stage_master list
router.get('/master', authorize(...ALL_ROLES), async (_req, res: Response, next: NextFunction) => {
  try {
    const stages = await stagesService.listStageMaster();
    res.json({ success: true, data: stages });
  } catch (err) { next(err); }
});

// GET /api/projects/:projectId/stages
router.get('/', authorize(...ALL_ROLES), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const stages = await stagesService.getProjectStages(
      req.params.projectId,
      req.query.site_id as string,
      req.query.lot_id as string
    );
    res.json({ success: true, data: stages });
  } catch (err) { next(err); }
});

// POST /api/projects/:projectId/stages/initialize
router.post('/initialize',
  authorize(...OFFICE_AND_ABOVE),
  [
    body('site_id').optional().isUUID(),
    body('lot_id').optional().isUUID(),
  ],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      await stagesService.initializeProjectStages(
        req.params.projectId,
        req.body.site_id ?? null,
        req.body.lot_id ?? null,
        req.user.sub
      );
      res.json({ success: true, data: null, message: 'Project stages initialized.' });
    } catch (err) { next(err); }
  }
);

// PUT /api/projects/:projectId/stages
router.put('/',
  authorize(...ALL_ROLES),
  [
    body('stage_id').isUUID().withMessage('stage_id is required.'),
    body('status').optional().isIn(['NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'AWAITING_INSPECTION', 'CERTIFIED']),
  ],
  validate,
  async (req: AuthRequest, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
      const record = await stagesService.upsertProjectStageStatus(
        { ...req.body, project_id: req.params.projectId },
        req.user.sub
      );
      res.json({ success: true, data: record });
    } catch (err) { next(err); }
  }
);

export default router;
