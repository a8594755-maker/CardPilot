import { Router } from 'express';
import { createSolverRouter } from './solver-routes.js';
import { createStrategyRouter } from './strategy-routes.js';
import { createDatabaseRouter } from './database-routes.js';
import { createGtoPlusRouter } from './gtoplus-routes.js';
import { createPreflopRouter } from './preflop-routes.js';
import { createTreeConfigRouter } from './tree-config-routes.js';
import { createBoardUtilRouter } from './board-util-routes.js';
import { createRangeVsRangeRouter } from './range-vs-range-routes.js';
import { createCoachingRouter } from './coaching-routes.js';
import { createRealtimeSolveRouter } from './realtime-solve-routes.js';

export function createGtoRouter(): Router {
  const router = Router();

  router.use(createSolverRouter());
  router.use(createStrategyRouter());
  router.use(createDatabaseRouter());
  router.use(createGtoPlusRouter());
  router.use(createPreflopRouter());
  router.use(createTreeConfigRouter());
  router.use(createBoardUtilRouter());
  router.use(createRangeVsRangeRouter());
  router.use('/coaching', createCoachingRouter());
  router.use('/realtime-solve', createRealtimeSolveRouter());

  return router;
}
