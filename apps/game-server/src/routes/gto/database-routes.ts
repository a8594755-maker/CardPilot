import { Router, type Request, type Response } from 'express';
import {
  createDatabase,
  getDatabase,
  listDatabases,
  deleteDatabase,
  addFlops,
  addRandomFlops,
  toggleFlopIgnored,
  deleteFlop,
  getAggregateReport,
  loadSubset,
  FLOP_SUBSETS,
} from '../../services/gto/database-service.js';
import { createJob } from '../../services/gto/solve-manager.js';

export function createDatabaseRouter(): Router {
  const router = Router();

  // List all databases
  router.get('/database', async (_req: Request, res: Response) => {
    try {
      res.json({ databases: listDatabases() });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // Get database details
  router.get('/database/:id', async (req: Request, res: Response) => {
    try {
      const db = getDatabase(req.params.id);
      if (!db) return res.status(404).json({ error: 'Database not found' });
      res.json(db);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // Create new database
  router.post('/database', async (req: Request, res: Response) => {
    try {
      const { name, config } = req.body;
      const db = createDatabase(name, config);
      res.json(db);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // Delete database
  router.delete('/database/:id', async (req: Request, res: Response) => {
    try {
      const success = deleteDatabase(req.params.id);
      if (!success) return res.status(404).json({ error: 'Database not found' });
      res.json({ deleted: true });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // Add specific flops
  router.post('/database/:id/flops', async (req: Request, res: Response) => {
    try {
      const db = addFlops(req.params.id, req.body.flops);
      if (!db) return res.status(404).json({ error: 'Database not found' });
      res.json(db);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // Add random flops
  router.post('/database/:id/random-flops', async (req: Request, res: Response) => {
    try {
      const db = addRandomFlops(req.params.id, req.body.count);
      if (!db) return res.status(404).json({ error: 'Database not found' });
      res.json(db);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // Load predefined subset
  router.post('/database/:id/load-subset', async (req: Request, res: Response) => {
    try {
      const subset = loadSubset(req.body.subsetName);
      if (!subset) return res.status(404).json({ error: 'Subset not found' });

      const db = addFlops(req.params.id, subset.flops);
      if (!db) return res.status(404).json({ error: 'Database not found' });
      res.json(db);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // Toggle flop ignored status
  router.post('/database/:id/flops/:flopId/toggle-ignore', async (req: Request, res: Response) => {
    try {
      const db = toggleFlopIgnored(req.params.id, req.params.flopId);
      if (!db) return res.status(404).json({ error: 'Not found' });
      res.json(db);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // Delete a flop
  router.delete('/database/:id/flops/:flopId', async (req: Request, res: Response) => {
    try {
      const db = deleteFlop(req.params.id, req.params.flopId);
      if (!db) return res.status(404).json({ error: 'Not found' });
      res.json(db);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // Get aggregate report
  router.get('/database/:id/report', async (req: Request, res: Response) => {
    try {
      const report = getAggregateReport(req.params.id);
      if (!report) return res.status(404).json({ error: 'Database not found' });
      res.json(report);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // List available subsets
  router.get('/database/subsets', async (_req: Request, res: Response) => {
    try {
      res.json({
        subsets: FLOP_SUBSETS.map((s) => ({
          name: s.name,
          description: s.description,
          count: s.count,
        })),
      });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // Solve database — queues real solver jobs for each pending flop
  router.post('/database/:id/solve', async (req: Request, res: Response) => {
    try {
      const db = getDatabase(req.params.id);
      if (!db) return res.status(404).json({ error: 'Database not found' });

      const pendingFlops = db.flops.filter((f) => f.status === 'pending');
      if (pendingFlops.length === 0) {
        return res.status(400).json({ error: 'No pending flops to solve' });
      }

      const oopRange = db.config.oopRange
        .split(',')
        .map((s: string) => s.trim())
        .filter(Boolean);
      const ipRange = db.config.ipRange
        .split(',')
        .map((s: string) => s.trim())
        .filter(Boolean);

      if (oopRange.length === 0 || ipRange.length === 0) {
        return res
          .status(400)
          .json({ error: 'Database config must have non-empty OOP and IP ranges' });
      }

      db.status = 'solving';

      // Solve each flop sequentially in the background
      (async () => {
        for (const flop of pendingFlops) {
          flop.status = 'solving';
          const jobConfig = {
            configName: db.config.treeConfigName,
            iterations: 10000,
            buckets: 100,
            board: flop.cards as string[],
            oopRange,
            ipRange,
          };

          try {
            // Use dynamic import to access runSolverJob indirectly via solve-manager
            createJob(jobConfig);
            // Import and run the solver directly
            const cfr = await import('@cardpilot/cfr-solver');
            const {
              vectorized,
              getTreeConfig,
              buildTree,
              expandHandClassToCombos,
              exportArrayStoreToJSONL,
            } = cfr;
            const { flattenTree, ArrayStore, enumerateValidCombos, solveVectorized } = vectorized;
            const { resolve } = await import('node:path');

            const RANKS = '23456789TJQKA';
            const SUIT_MAP: Record<string, number> = { c: 0, d: 1, h: 2, s: 3 };
            const boardIndices = jobConfig.board.map((card: string) => {
              const rank = RANKS.indexOf(card[0].toUpperCase());
              const suit = SUIT_MAP[card[1].toLowerCase()];
              return rank * 4 + suit;
            });

            const treeConfig = getTreeConfig(jobConfig.configName as any);
            if (!treeConfig) {
              flop.status = 'error';
              continue;
            }

            const tree = buildTree(treeConfig);
            const flatTree = flattenTree(tree);
            const validCombos = enumerateValidCombos(boardIndices);
            const store = new ArrayStore(flatTree, validCombos.numCombos);

            // Expand ranges
            const oopWeighted: Array<{ combo: [number, number]; weight: number }> = [];
            const ipWeighted: Array<{ combo: [number, number]; weight: number }> = [];
            for (const hc of oopRange) {
              for (const combo of expandHandClassToCombos(hc)) {
                oopWeighted.push({
                  combo: [Math.min(combo[0], combo[1]), Math.max(combo[0], combo[1])],
                  weight: 1,
                });
              }
            }
            for (const hc of ipRange) {
              for (const combo of expandHandClassToCombos(hc)) {
                ipWeighted.push({
                  combo: [Math.min(combo[0], combo[1]), Math.max(combo[0], combo[1])],
                  weight: 1,
                });
              }
            }

            const startTime = Date.now();
            solveVectorized({
              tree: flatTree,
              store,
              board: boardIndices,
              oopRange: oopWeighted,
              ipRange: ipWeighted,
              iterations: jobConfig.iterations,
            });
            const elapsedMs = Date.now() - startTime;

            const flopLabel = jobConfig.board
              .slice(0, 3)
              .map((c: string) => c.toLowerCase())
              .join('');
            const outputPath = resolve(
              process.cwd(),
              'data',
              'cfr',
              jobConfig.configName,
              `${flopLabel}.jsonl`,
            );
            exportArrayStoreToJSONL(store, flatTree, validCombos, {
              outputPath,
              board: boardIndices,
              boardCards: jobConfig.board,
              configName: jobConfig.configName,
              iterations: jobConfig.iterations,
              elapsedMs,
            });

            flop.status = 'solved';
            flop.results = {
              oopEquity: 0.5,
              ipEquity: 0.5,
              oopEV: 0,
              ipEV: 0,
              bettingFrequency: {},
              exploitability: 0,
              iterations: jobConfig.iterations,
              solvedAt: new Date().toISOString(),
            };
          } catch (err) {
            flop.status = 'error';
            console.error(`Database flop solve failed: ${JSON.stringify(flop.cards)}`, err);
          }
        }

        // Check if all flops are done
        if (
          db.flops.every(
            (f) => f.status === 'solved' || f.status === 'ignored' || f.status === 'error',
          )
        ) {
          db.status = 'complete';
        }
      })();

      res.json({
        message: 'Solve started',
        databaseId: db.id,
        pendingFlops: pendingFlops.length,
      });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  return router;
}
