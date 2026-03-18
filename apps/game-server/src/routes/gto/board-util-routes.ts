import { Router, type Request, type Response } from 'express';
import { getFlops, findNearestFlop, getConfigs } from '../../services/gto/strategy-service.js';

export function createBoardUtilRouter(): Router {
  const router = Router();

  router.get('/flops', async (req: Request, res: Response) => {
    try {
      const configs = getConfigs();
      const configName = (req.query.config as string) || configs[0]?.name;
      if (!configName) return res.status(404).json({ error: 'No solved configs found' });
      const flops = getFlops(configName);
      res.json({ config: configName, count: flops.length, flops });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  router.get('/flops/nearest', async (req: Request, res: Response) => {
    try {
      const cards = req.query.cards as string;
      const config = req.query.config as string | undefined;
      if (!cards) return res.status(400).json({ error: 'Missing cards parameter' });
      const cardList = cards.split(',').map((c) => c.trim());
      if (cardList.length !== 3)
        return res.status(400).json({ error: 'Must provide exactly 3 flop cards' });
      const nearest = findNearestFlop(cardList, config);
      if (!nearest) return res.status(404).json({ error: 'No solved flops found' });
      res.json(nearest);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  router.get('/configs', async (_req: Request, res: Response) => {
    try {
      res.json({ configs: getConfigs() });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  return router;
}
