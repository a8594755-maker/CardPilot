// CFR Lookup API — standalone endpoints for querying solved CFR strategies.
// Used by the web frontend's CFR Lookup page for studying GTO strategies.

import type { Express, Request, Response } from "express";
import { resolve } from "node:path";
import { existsSync, readdirSync, readFileSync } from "node:fs";

// Config registry (mirrors cfr-solver tree-config.ts)
const CFR_CONFIGS = [
  // HU configs
  { name: 'pipeline_srp', label: 'HU BTN vs BB SRP 50bb (1 size)', positions: 'BTN vs BB', potType: 'SRP', stack: '50bb', players: 2, sizes: 1 },
  { name: 'pipeline_3bet', label: 'HU BTN vs BB 3BP 50bb (1 size)', positions: 'BTN vs BB', potType: '3BP', stack: '50bb', players: 2, sizes: 1 },
  { name: 'hu_btn_bb_srp_100bb', label: 'HU BTN vs BB SRP 100bb (3 sizes)', positions: 'BTN vs BB', potType: 'SRP', stack: '100bb', players: 2, sizes: 3 },
  { name: 'hu_btn_bb_3bp_100bb', label: 'HU BTN vs BB 3BP 100bb (2 sizes)', positions: 'BTN vs BB', potType: '3BP', stack: '100bb', players: 2, sizes: 2 },
  { name: 'hu_btn_bb_srp_50bb', label: 'HU BTN vs BB SRP 50bb (2 sizes)', positions: 'BTN vs BB', potType: 'SRP', stack: '50bb', players: 2, sizes: 2 },
  { name: 'hu_btn_bb_3bp_50bb', label: 'HU BTN vs BB 3BP 50bb (2 sizes)', positions: 'BTN vs BB', potType: '3BP', stack: '50bb', players: 2, sizes: 2 },
  { name: 'hu_co_bb_srp_100bb', label: 'HU CO vs BB SRP 100bb (2 sizes)', positions: 'CO vs BB', potType: 'SRP', stack: '100bb', players: 2, sizes: 2 },
  { name: 'hu_co_bb_3bp_100bb', label: 'HU CO vs BB 3BP 100bb (1 size)', positions: 'CO vs BB', potType: '3BP', stack: '100bb', players: 2, sizes: 1 },
  { name: 'hu_utg_bb_srp_100bb', label: 'HU UTG vs BB SRP 100bb (1 size)', positions: 'UTG vs BB', potType: 'SRP', stack: '100bb', players: 2, sizes: 1 },
  // Multi-way configs
  { name: 'mw3_btn_sb_bb_srp_100bb', label: '3-way BTN+SB+BB SRP 100bb', positions: 'BTN+SB+BB', potType: 'SRP', stack: '100bb', players: 3, sizes: 1 },
  { name: 'mw3_btn_sb_bb_srp_50bb', label: '3-way BTN+SB+BB SRP 50bb', positions: 'BTN+SB+BB', potType: 'SRP', stack: '50bb', players: 3, sizes: 1 },
  { name: 'mw3_co_btn_bb_srp_100bb', label: '3-way CO+BTN+BB SRP 100bb', positions: 'CO+BTN+BB', potType: 'SRP', stack: '100bb', players: 3, sizes: 1 },
  { name: 'mw3_co_btn_bb_srp_50bb', label: '3-way CO+BTN+BB SRP 50bb', positions: 'CO+BTN+BB', potType: 'SRP', stack: '50bb', players: 3, sizes: 1 },
];

// Output dir mapping
const OUTPUT_DIRS: Record<string, string> = {
  pipeline_srp: 'pipeline_hu_srp_50bb',
  pipeline_3bet: 'pipeline_hu_3bet_50bb',
  hu_btn_bb_srp_100bb: 'hu_btn_bb_srp_100bb',
  hu_btn_bb_3bp_100bb: 'hu_btn_bb_3bp_100bb',
  hu_btn_bb_srp_50bb: 'hu_btn_bb_srp_50bb',
  hu_btn_bb_3bp_50bb: 'hu_btn_bb_3bp_50bb',
  hu_co_bb_srp_100bb: 'hu_co_bb_srp_100bb',
  hu_co_bb_3bp_100bb: 'hu_co_bb_3bp_100bb',
  hu_utg_bb_srp_100bb: 'hu_utg_bb_srp_100bb',
  mw3_btn_sb_bb_srp_100bb: 'mw3_btn_sb_bb_srp_100bb',
  mw3_btn_sb_bb_srp_50bb: 'mw3_btn_sb_bb_srp_50bb',
  mw3_co_btn_bb_srp_100bb: 'mw3_co_btn_bb_srp_100bb',
  mw3_co_btn_bb_srp_50bb: 'mw3_co_btn_bb_srp_50bb',
};

function findDataDir(): string {
  // Try common locations
  const candidates = [
    resolve(process.cwd(), 'data/cfr'),
    resolve(process.cwd(), '../../data/cfr'),
    resolve(process.cwd(), '../../../data/cfr'),
  ];
  for (const dir of candidates) {
    if (existsSync(dir)) return dir;
  }
  return resolve(process.cwd(), 'data/cfr');
}

export function setupCfrLookupRoutes(app: Express): void {
  const dataDir = findDataDir();

  // GET /api/cfr/configs — list all available configs with solve status
  app.get("/api/cfr/configs", (_req: Request, res: Response) => {
    const configs = CFR_CONFIGS.map(cfg => {
      const outputDir = resolve(dataDir, OUTPUT_DIRS[cfg.name] ?? cfg.name);
      let solvedFlops = 0;
      let totalFlops = 1755;

      if (existsSync(outputDir)) {
        try {
          const files = readdirSync(outputDir);
          solvedFlops = files.filter(f => f.endsWith('.meta.json')).length;
        } catch { /* ignore */ }
      }

      return {
        ...cfg,
        solvedFlops,
        totalFlops,
        progress: Math.round((solvedFlops / totalFlops) * 100),
        available: solvedFlops > 0,
      };
    });

    res.json({ ok: true, configs, dataDir });
  });

  // GET /api/cfr/flops?config=hu_btn_bb_srp_100bb — list solved flops for a config
  app.get("/api/cfr/flops", (req: Request, res: Response) => {
    const configName = req.query.config as string;
    if (!configName) {
      return res.status(400).json({ ok: false, error: 'Missing config parameter' });
    }

    const outputDir = resolve(dataDir, OUTPUT_DIRS[configName] ?? configName);
    if (!existsSync(outputDir)) {
      return res.json({ ok: true, flops: [] });
    }

    try {
      const files = readdirSync(outputDir).filter(f => f.endsWith('.meta.json')).sort();
      const flops = files.map(f => {
        try {
          const meta = JSON.parse(readFileSync(resolve(outputDir, f), 'utf-8'));
          return {
            boardId: meta.boardId,
            flopCards: meta.flopCards,
            flopLabel: meta.flopCards?.map(cardIndexToLabel).join(' ') ?? `Board ${meta.boardId}`,
            infoSets: meta.infoSets,
            iterations: meta.iterations,
          };
        } catch {
          return null;
        }
      }).filter(Boolean);

      return res.json({ ok: true, flops, total: flops.length });
    } catch (e) {
      return res.status(500).json({ ok: false, error: (e as Error).message });
    }
  });

  // GET /api/cfr/lookup?config=X&boardId=N&player=0&history=xb&bucket=42
  // Returns the raw CFR strategy for a specific info set
  app.get("/api/cfr/lookup", (req: Request, res: Response) => {
    const configName = req.query.config as string;
    const boardId = parseInt(req.query.boardId as string, 10);
    const player = parseInt(req.query.player as string, 10);
    const history = (req.query.history as string) ?? '';
    const bucket = parseInt(req.query.bucket as string, 10);
    const street = (req.query.street as string) ?? 'FLOP';

    if (!configName || isNaN(boardId) || isNaN(player) || isNaN(bucket)) {
      return res.status(400).json({ ok: false, error: 'Missing required parameters: config, boardId, player, bucket' });
    }

    const outputDir = resolve(dataDir, OUTPUT_DIRS[configName] ?? configName);
    const jsonlPath = resolve(outputDir, `flop_${String(boardId).padStart(3, '0')}.jsonl`);

    if (!existsSync(jsonlPath)) {
      return res.status(404).json({ ok: false, error: `No JSONL data for board ${boardId} in config ${configName}` });
    }

    try {
      // Build the info-set key
      const streetChar = street === 'FLOP' ? 'F' : street === 'TURN' ? 'T' : 'R';
      const keyPrefix = `${streetChar}|${boardId}|${player}|${history}|`;

      // Read the JSONL and find matching entry
      const content = readFileSync(jsonlPath, 'utf-8');
      const lines = content.split('\n');

      // Try exact bucket match first
      const exactKey = `${keyPrefix}${bucket}`;
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const entry = JSON.parse(line);
          if (entry.key === exactKey) {
            return res.json({
              ok: true,
              key: entry.key,
              probs: entry.probs,
              actions: entry.actions,
              source: 'exact',
            });
          }
        } catch { /* skip parse errors */ }
      }

      // Try nearby buckets (±5)
      for (let delta = 1; delta <= 5; delta++) {
        for (const b of [bucket + delta, bucket - delta]) {
          if (b < 0 || b >= 100) continue;
          const nearKey = `${keyPrefix}${b}`;
          for (const line of lines) {
            if (!line.trim()) continue;
            try {
              const entry = JSON.parse(line);
              if (entry.key === nearKey) {
                return res.json({
                  ok: true,
                  key: entry.key,
                  probs: entry.probs,
                  actions: entry.actions,
                  source: 'nearby',
                  requestedBucket: bucket,
                  matchedBucket: b,
                });
              }
            } catch { /* skip */ }
          }
        }
      }

      return res.json({ ok: false, error: 'No matching info set found', key: exactKey });
    } catch (e) {
      return res.status(500).json({ ok: false, error: (e as Error).message });
    }
  });

  // GET /api/cfr/board-strategy?config=X&boardId=N&street=FLOP&history=x
  // Returns all strategies for a board position (all buckets)
  app.get("/api/cfr/board-strategy", (req: Request, res: Response) => {
    const configName = req.query.config as string;
    const boardId = parseInt(req.query.boardId as string, 10);
    const player = parseInt(req.query.player as string, 10);
    const history = (req.query.history as string) ?? '';
    const street = (req.query.street as string) ?? 'FLOP';

    if (!configName || isNaN(boardId) || isNaN(player)) {
      return res.status(400).json({ ok: false, error: 'Missing required parameters' });
    }

    const outputDir = resolve(dataDir, OUTPUT_DIRS[configName] ?? configName);
    const jsonlPath = resolve(outputDir, `flop_${String(boardId).padStart(3, '0')}.jsonl`);

    if (!existsSync(jsonlPath)) {
      return res.status(404).json({ ok: false, error: `No data for board ${boardId}` });
    }

    try {
      const streetChar = street === 'FLOP' ? 'F' : street === 'TURN' ? 'T' : 'R';
      const keyPrefix = `${streetChar}|${boardId}|${player}|${history}|`;

      const content = readFileSync(jsonlPath, 'utf-8');
      const lines = content.split('\n');
      const strategies: Array<{ bucket: number; probs: number[]; actions?: string[] }> = [];

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const entry = JSON.parse(line);
          if (typeof entry.key === 'string' && entry.key.startsWith(keyPrefix)) {
            const bucketStr = entry.key.slice(keyPrefix.length);
            const bucket = parseInt(bucketStr, 10);
            if (!isNaN(bucket)) {
              strategies.push({ bucket, probs: entry.probs, actions: entry.actions });
            }
          }
        } catch { /* skip */ }
      }

      strategies.sort((a, b) => a.bucket - b.bucket);

      return res.json({
        ok: true,
        config: configName,
        boardId,
        player,
        street,
        history,
        strategies,
        count: strategies.length,
      });
    } catch (e) {
      return res.status(500).json({ ok: false, error: (e as Error).message });
    }
  });
}

// Card index to human-readable label (e.g., 48 → "As")
function cardIndexToLabel(index: number): string {
  const ranks = '23456789TJQKA';
  const suits = 'cdhs';
  const rank = Math.floor(index / 4);
  const suit = index % 4;
  return `${ranks[rank]}${suits[suit]}`;
}
