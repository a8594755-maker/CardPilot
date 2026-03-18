import { Router, type Request, type Response } from 'express';
import {
  EXACT_CONFIG,
  getExactSpotIds,
  getPreflopConfigs,
  getPreflopSpots,
  getPreflopRange,
  getGtoWizardSpots,
  getGtoWizardRange,
} from '../../services/gto/preflop-service.js';

export function createPreflopRouter(): Router {
  const router = Router();

  // List available preflop configs
  router.get('/preflop/configs', async (_req: Request, res: Response) => {
    try {
      res.json(getPreflopConfigs());
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // List all spots for a config
  router.get('/preflop/spots/:config', async (req: Request, res: Response) => {
    try {
      const config = req.params.config;

      // Try solutions first, then fall back to GTO Wizard
      const spots = getPreflopSpots(config);
      if (spots.length > 0) {
        return res.json({ config, spots });
      }

      // Fallback to GTO Wizard format
      if (config === 'gto-wizard') {
        const wizardSpots = getGtoWizardSpots();
        return res.json({
          config,
          spots: wizardSpots.map((s) => ({
            spot: s,
            heroPosition: s.split('_')[0],
            scenario: 'unknown',
            coverage: 'solver',
          })),
        });
      }

      res.status(404).json({ error: `Config not found: ${config}` });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // Get 169-hand grid for a specific spot
  router.get('/preflop/range/:config/:spot', async (req: Request, res: Response) => {
    try {
      const { config, spot } = req.params;

      // Try solutions first
      const solution = getPreflopRange(config, spot);
      if (solution) {
        return res.json(solution);
      }

      if (config === EXACT_CONFIG) {
        return res.status(404).json({
          error: `Exact chart spot not found: ${spot}`,
          coverage: 'exact',
          availableSpots: getExactSpotIds(),
        });
      }

      // Fallback to GTO Wizard
      if (config === 'gto-wizard') {
        const range = getGtoWizardRange(spot);
        if (range) {
          const grid: Record<string, Record<string, number>> = {};
          for (const entry of range) {
            grid[entry.hand] = entry.actions;
          }
          return res.json({
            spot,
            format: 'gto-wizard',
            coverage: 'solver',
            heroPosition: spot.split('_')[0],
            actions: [...new Set(range.flatMap((entry) => Object.keys(entry.actions)))],
            grid,
            summary: {
              totalCombos: range.length,
              rangeSize: range.filter((e) => (e.actions.fold ?? 0) < 0.99).length,
              actionFrequencies: {},
            },
            metadata: {
              iterations: 0,
              exploitability: 0,
              solveDate: '',
              solver: 'legacy-import',
            },
          });
        }
      }

      res.status(404).json({ error: `Spot not found: ${spot} in config ${config}` });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  return router;
}
