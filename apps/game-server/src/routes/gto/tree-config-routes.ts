import { Router, type Request, type Response } from 'express';

// Import tree config data from cfr-solver
// We dynamically import to handle the case where the module isn't built yet
const CONFIG_DATA: Record<
  string,
  {
    label: string;
    stackLabel: string;
    iterations: number;
    buckets: number;
    config: {
      startingPot: number;
      effectiveStack: number;
      betSizes: { flop: number[]; turn: number[]; river: number[] };
      raiseCapPerStreet: number;
      numPlayers?: number;
    };
  }
> = {
  v1_50bb: {
    label: 'V1 50bb (2 sizes)',
    stackLabel: '50bb',
    iterations: 50000,
    buckets: 50,
    config: {
      startingPot: 5,
      effectiveStack: 47.5,
      betSizes: { flop: [0.33, 0.75], turn: [0.5, 1.0], river: [0.75, 1.5] },
      raiseCapPerStreet: 1,
    },
  },
  standard_50bb: {
    label: 'Standard 50bb (5 sizes)',
    stackLabel: '50bb',
    iterations: 200000,
    buckets: 100,
    config: {
      startingPot: 5,
      effectiveStack: 47.5,
      betSizes: {
        flop: [0.33, 0.5, 0.75, 1.0, 1.5],
        turn: [0.33, 0.5, 0.75, 1.0, 1.5],
        river: [0.33, 0.5, 0.75, 1.0, 1.5],
      },
      raiseCapPerStreet: 1,
    },
  },
  standard_100bb: {
    label: 'Standard 100bb (5 sizes)',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
    config: {
      startingPot: 5,
      effectiveStack: 97.5,
      betSizes: {
        flop: [0.33, 0.5, 0.75, 1.0, 1.5],
        turn: [0.33, 0.5, 0.75, 1.0, 1.5],
        river: [0.33, 0.5, 0.75, 1.0, 1.5],
      },
      raiseCapPerStreet: 1,
    },
  },
  hu_btn_bb_srp_100bb: {
    label: 'HU BTN vs BB SRP 100bb (3 sizes)',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
    config: {
      startingPot: 5,
      effectiveStack: 97.5,
      betSizes: { flop: [0.33, 0.75, 1.5], turn: [0.33, 0.75, 1.5], river: [0.33, 0.75, 1.5] },
      raiseCapPerStreet: 0,
    },
  },
  hu_btn_bb_3bp_100bb: {
    label: 'HU BTN vs BB 3BP 100bb (2 sizes)',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
    config: {
      startingPot: 17.5,
      effectiveStack: 91.25,
      betSizes: { flop: [0.33, 0.75], turn: [0.33, 0.75], river: [0.33, 0.75] },
      raiseCapPerStreet: 0,
    },
  },
  hu_btn_bb_srp_50bb: {
    label: 'HU BTN vs BB SRP 50bb (2 sizes)',
    stackLabel: '50bb',
    iterations: 200000,
    buckets: 100,
    config: {
      startingPot: 5,
      effectiveStack: 47.5,
      betSizes: { flop: [0.33, 0.75], turn: [0.33, 0.75], river: [0.33, 0.75] },
      raiseCapPerStreet: 0,
    },
  },
  hu_btn_bb_3bp_50bb: {
    label: 'HU BTN vs BB 3BP 50bb (2 sizes)',
    stackLabel: '50bb',
    iterations: 200000,
    buckets: 100,
    config: {
      startingPot: 17.5,
      effectiveStack: 41.25,
      betSizes: { flop: [0.33, 0.75], turn: [0.33, 0.75], river: [0.33, 0.75] },
      raiseCapPerStreet: 0,
    },
  },
  hu_co_bb_srp_100bb: {
    label: 'HU CO vs BB SRP 100bb (2 sizes)',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
    config: {
      startingPot: 5,
      effectiveStack: 97.5,
      betSizes: { flop: [0.33, 0.75], turn: [0.33, 0.75], river: [0.33, 0.75] },
      raiseCapPerStreet: 0,
    },
  },
  mw3_btn_sb_bb_srp_100bb: {
    label: '3-way BTN+SB+BB SRP 100bb',
    stackLabel: '100bb',
    iterations: 200000,
    buckets: 100,
    config: {
      startingPot: 7.5,
      effectiveStack: 97.5,
      betSizes: { flop: [0.5], turn: [0.5], river: [0.5] },
      raiseCapPerStreet: 0,
      numPlayers: 3,
    },
  },
};

export function createTreeConfigRouter(): Router {
  const router = Router();

  // List all preset tree configs
  router.get('/tree-configs', async (_req: Request, res: Response) => {
    try {
      res.json(
        Object.entries(CONFIG_DATA).map(([name, data]) => ({
          name,
          label: data.label,
          stackLabel: data.stackLabel,
          iterations: data.iterations,
          buckets: data.buckets,
          numPlayers: data.config.numPlayers ?? 2,
          startingPot: data.config.startingPot,
          effectiveStack: data.config.effectiveStack,
        })),
      );
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // Get specific config details
  router.get('/tree-configs/:name', async (req: Request, res: Response) => {
    try {
      const { name } = req.params;
      const data = CONFIG_DATA[name];
      if (!data) {
        return res.status(404).json({ error: `Config not found: ${name}` });
      }
      res.json({ name, ...data });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  return router;
}
