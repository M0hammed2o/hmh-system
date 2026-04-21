import { Router, Response, NextFunction } from 'express';
import * as alertsService from './alerts.service';
import { authenticate, authorize, OFFICE_AND_ABOVE, ALL_ROLES } from '../../middleware/auth';
import { AuthRequest, AlertStatus, AlertSeverity } from '../../types';
import { AppError } from '../../middleware/errorHandler';

const router = Router({ mergeParams: true });
router.use(authenticate);

router.get('/', authorize(...ALL_ROLES), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const page = parseInt(req.query.page as string ?? '1', 10);
    const limit = Math.min(parseInt(req.query.limit as string ?? '20', 10), 100);
    const result = await alertsService.listAlerts(
      req.params.projectId, page, limit,
      {
        status: req.query.status as AlertStatus,
        severity: req.query.severity as AlertSeverity,
        site_id: req.query.site_id as string,
      }
    );
    res.json({ success: true, data: result });
  } catch (err) { next(err); }
});

router.get('/counts', authorize(...ALL_ROLES), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const counts = await alertsService.getAlertCounts(req.params.projectId);
    res.json({ success: true, data: counts });
  } catch (err) { next(err); }
});

router.post('/:id/acknowledge', authorize(...ALL_ROLES), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
    const alert = await alertsService.acknowledgeAlert(req.params.id, req.user.sub);
    res.json({ success: true, data: alert });
  } catch (err) { next(err); }
});

router.post('/:id/resolve', authorize(...OFFICE_AND_ABOVE), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    if (!req.user) throw new AppError(401, 'Not authenticated.', 'UNAUTHORIZED');
    const alert = await alertsService.resolveAlert(req.params.id, req.user.sub);
    res.json({ success: true, data: alert });
  } catch (err) { next(err); }
});

export default router;
