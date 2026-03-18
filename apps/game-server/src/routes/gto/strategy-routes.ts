import { Router, type Request, type Response } from 'express';
import {
  loadFlopStrategies,
  queryStrategy,
  getConfigs,
  buildSolverGrid,
} from '../../services/gto/strategy-service.js';

export function createStrategyRouter(): Router {
  const router = Router();

  // Query strategy for a specific node
  router.get('/strategy/query', async (req: Request, res: Response) => {
    try {
      const config = req.query.config as string;
      const flop = req.query.flop as string;
      const key = req.query.key as string;
      if (!config || !flop || !key) {
        return res.status(400).json({ error: 'Missing required params: config, flop, key' });
      }
      const probs = queryStrategy(config, flop, key);
      if (!probs) {
        return res.status(404).json({ error: 'Strategy not found for key' });
      }
      res.json({ key, probs });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // Get all strategies for a solved flop
  router.get('/strategy/tree/:config/:flop', async (req: Request, res: Response) => {
    try {
      const { config, flop } = req.params;
      const player = req.query.player as string | undefined;
      const history = req.query.history as string | undefined;
      const strategies = loadFlopStrategies(config, flop);
      if (strategies.size === 0) {
        return res.status(404).json({ error: 'No strategies found' });
      }
      const entries: Array<{ key: string; probs: number[] }> = [];
      for (const [key, probs] of strategies) {
        const parts = key.split('|');
        if (player !== undefined && parts[2] !== player) continue;
        if (history !== undefined && !parts[3]?.startsWith(history)) continue;
        entries.push({ key, probs });
      }
      res.json({
        config,
        flop,
        totalStrategies: strategies.size,
        filtered: entries.length,
        strategies: entries,
      });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // Get solver results as strategy grid (for strategy browser)
  router.get('/strategy/grid/:config/:flop', async (req: Request, res: Response) => {
    try {
      const { config, flop } = req.params;
      const player = (req.query.player as string) || '0';
      const history = (req.query.history as string) || '';
      const result = buildSolverGrid(config, flop, parseInt(player), history);
      if (!result) {
        return res.status(404).json({ error: 'No solved data found' });
      }
      res.json(result);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // Get all solved configs
  router.get('/strategy/configs', async (_req: Request, res: Response) => {
    try {
      res.json({ configs: getConfigs() });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  return router;
}
