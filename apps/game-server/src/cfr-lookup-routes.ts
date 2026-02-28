// CFR Lookup API — standalone endpoints for querying solved CFR strategies.
// Used by the web frontend's CFR Lookup page for studying GTO strategies.

import type { Express, Request, Response } from "express";
import { resolve } from "node:path";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { getHandMap, classifyFlop, flopDistance, cardToIndex } from "./services/hand-map-service.js";

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
  pipeline_srp: 'v1_hu_srp_50bb',
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

// Card index to human-readable label (e.g., 48 → "As")
function cardIndexToLabel(index: number): string {
  const ranks = '23456789TJQKA';
  const suits = 'cdhs';
  return `${ranks[Math.floor(index / 4)]}${suits[index % 4]}`;
}

// ── In-memory meta cache (Phase 1A) ─────────────────────────────────────────

interface FlopMetaCached {
  boardId: number;
  flopCards: number[];
  flopLabel: string;
  infoSets: number;
  iterations: number;
  bucketCount: number;
  texture: string;
  pairing: string;
  highCard: string;
  connectivity: string;
}

// configName → pre-computed flop list
const metaCache = new Map<string, FlopMetaCached[]>();

function loadAllMeta(dataDir: string): void {
  for (const cfg of CFR_CONFIGS) {
    const outputDir = resolve(dataDir, OUTPUT_DIRS[cfg.name] ?? cfg.name);
    if (!existsSync(outputDir)) continue;

    try {
      const files = readdirSync(outputDir).filter(f => f.endsWith('.meta.json')).sort();
      const flops: FlopMetaCached[] = [];

      for (const f of files) {
        try {
          const raw = readFileSync(resolve(outputDir, f), 'utf-8');
          const meta = JSON.parse(raw);
          const classification = classifyFlop(meta.flopCards);
          flops.push({
            boardId: meta.boardId,
            flopCards: meta.flopCards,
            flopLabel: meta.flopCards?.map(cardIndexToLabel).join(' ') ?? `Board ${meta.boardId}`,
            infoSets: meta.infoSets,
            iterations: meta.iterations,
            bucketCount: meta.bucketCount || 50,
            ...classification,
          });
        } catch { /* skip corrupt meta */ }
      }

      if (flops.length > 0) metaCache.set(cfg.name, flops);
    } catch { /* skip inaccessible dir */ }
  }

  console.log(`[CFR] Meta cache loaded: ${[...metaCache.entries()].map(([k, v]) => `${k}(${v.length})`).join(', ') || 'no data'}`);
}

// ── JSONL board data LRU cache (Phase 1B) ────────────────────────────────────

interface BoardEntry { key: string; probs: number[]; actions?: string[] }

const BOARD_CACHE_MAX = 20;
const boardDataCache = new Map<string, { meta: Record<string, unknown>; entries: BoardEntry[]; index: Map<string, BoardEntry> }>();

async function loadBoardData(dataDir: string, configName: string, boardId: number) {
  const cacheKey = `${configName}:${boardId}`;
  const cached = boardDataCache.get(cacheKey);
  if (cached) return cached;

  const outputDir = resolve(dataDir, OUTPUT_DIRS[configName] ?? configName);
  const pad = String(boardId).padStart(3, '0');
  const metaPath = resolve(outputDir, `flop_${pad}.meta.json`);
  const jsonlPath = resolve(outputDir, `flop_${pad}.jsonl`);

  if (!existsSync(metaPath) || !existsSync(jsonlPath)) return null;

  const [metaText, jsonlText] = await Promise.all([
    readFile(metaPath, 'utf-8'),
    readFile(jsonlPath, 'utf-8'),
  ]);

  const meta = JSON.parse(metaText);
  const entries: BoardEntry[] = [];
  const index = new Map<string, BoardEntry>();

  for (const line of jsonlText.split('\n')) {
    if (!line.trim()) continue;
    try {
      const entry: BoardEntry = JSON.parse(line);
      entries.push(entry);
      index.set(entry.key, entry);
    } catch { /* skip malformed line */ }
  }

  const result = { meta, entries, index };

  // LRU eviction
  if (boardDataCache.size >= BOARD_CACHE_MAX) {
    const oldest = boardDataCache.keys().next().value;
    if (oldest) boardDataCache.delete(oldest);
  }
  boardDataCache.set(cacheKey, result);

  return result;
}

// ── Route setup ──────────────────────────────────────────────────────────────

export function setupCfrLookupRoutes(app: Express): void {
  const dataDir = findDataDir();

  // Load all meta files into memory at startup (Phase 1A)
  loadAllMeta(dataDir);

  // GET /api/cfr/configs — list all available configs with solve status
  app.get("/api/cfr/configs", (_req: Request, res: Response) => {
    const configs = CFR_CONFIGS.map(cfg => {
      const solvedFlops = metaCache.get(cfg.name)?.length ?? 0;
      const totalFlops = 1755;
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

  // GET /api/cfr/flops?config=X — list solved flops with classification
  app.get("/api/cfr/flops", (req: Request, res: Response) => {
    const configName = req.query.config as string;
    if (!configName) {
      return res.status(400).json({ ok: false, error: 'Missing config parameter' });
    }

    const flops = metaCache.get(configName) ?? [];
    return res.json({ ok: true, flops, total: flops.length });
  });

  // GET /api/cfr/board-data?config=X&boardId=N — full JSONL + meta for client-side indexing
  app.get("/api/cfr/board-data", async (req: Request, res: Response) => {
    const configName = req.query.config as string;
    const boardId = parseInt(req.query.boardId as string, 10);

    if (!configName || isNaN(boardId)) {
      return res.status(400).json({ ok: false, error: 'Missing config or boardId' });
    }

    try {
      const data = await loadBoardData(dataDir, configName, boardId);
      if (!data) {
        return res.status(404).json({ ok: false, error: `No data for board ${boardId}` });
      }
      return res.json({ ok: true, meta: data.meta, entries: data.entries });
    } catch (e) {
      return res.status(500).json({ ok: false, error: (e as Error).message });
    }
  });

  // GET /api/cfr/hand-map?config=X&boardId=N — hand class → bucket mapping
  app.get("/api/cfr/hand-map", async (req: Request, res: Response) => {
    const configName = req.query.config as string;
    const boardId = parseInt(req.query.boardId as string, 10);

    if (!configName || isNaN(boardId)) {
      return res.status(400).json({ ok: false, error: 'Missing config or boardId' });
    }

    // Use meta cache first, fall back to disk
    const cachedFlops = metaCache.get(configName);
    const cachedMeta = cachedFlops?.find(f => f.boardId === boardId);

    if (cachedMeta) {
      try {
        const handMap = getHandMap(configName, cachedMeta.flopCards, cachedMeta.bucketCount);
        return res.json({ ok: true, ...handMap });
      } catch (e) {
        return res.status(500).json({ ok: false, error: (e as Error).message });
      }
    }

    // Fallback: read meta from disk
    const outputDir = resolve(dataDir, OUTPUT_DIRS[configName] ?? configName);
    const metaPath = resolve(outputDir, `flop_${String(boardId).padStart(3, '0')}.meta.json`);

    if (!existsSync(metaPath)) {
      return res.status(404).json({ ok: false, error: `No meta for board ${boardId}` });
    }

    try {
      const metaText = await readFile(metaPath, 'utf-8');
      const meta = JSON.parse(metaText);
      const handMap = getHandMap(configName, meta.flopCards, meta.bucketCount || 50);
      return res.json({ ok: true, ...handMap });
    } catch (e) {
      return res.status(500).json({ ok: false, error: (e as Error).message });
    }
  });

  // GET /api/cfr/nearest-flop?config=X&cards=As,Kh,7d — find nearest solved flop
  app.get("/api/cfr/nearest-flop", (req: Request, res: Response) => {
    const configName = req.query.config as string;
    const cardsParam = req.query.cards as string;

    if (!configName || !cardsParam) {
      return res.status(400).json({ ok: false, error: 'Missing config or cards parameter' });
    }

    const queryCards = cardsParam.split(',').map(c => cardToIndex(c.trim()));
    if (queryCards.some(c => c < 0) || queryCards.length < 3) {
      return res.status(400).json({ ok: false, error: 'Invalid card format. Use e.g. As,Kh,7d' });
    }

    const flops = metaCache.get(configName);
    if (!flops || flops.length === 0) {
      return res.status(404).json({ ok: false, error: 'No data for config' });
    }

    let bestBoardId = -1;
    let bestDist = Infinity;
    let bestCards: number[] = [];

    for (const flop of flops) {
      const dist = flopDistance(queryCards.slice(0, 3), flop.flopCards);
      if (dist < bestDist) {
        bestDist = dist;
        bestBoardId = flop.boardId;
        bestCards = flop.flopCards;
      }
    }

    if (bestBoardId < 0) {
      return res.status(404).json({ ok: false, error: 'No boards found' });
    }

    return res.json({
      ok: true,
      boardId: bestBoardId,
      flopCards: bestCards,
      flopLabel: bestCards.map(cardIndexToLabel).join(' '),
      distance: bestDist,
    });
  });

  // GET /api/cfr/lookup?config=X&boardId=N&player=0&history=xb&bucket=42
  app.get("/api/cfr/lookup", async (req: Request, res: Response) => {
    const configName = req.query.config as string;
    const boardId = parseInt(req.query.boardId as string, 10);
    const player = parseInt(req.query.player as string, 10);
    const history = (req.query.history as string) ?? '';
    const bucket = parseInt(req.query.bucket as string, 10);
    const street = (req.query.street as string) ?? 'FLOP';

    if (!configName || isNaN(boardId) || isNaN(player) || isNaN(bucket)) {
      return res.status(400).json({ ok: false, error: 'Missing required parameters: config, boardId, player, bucket' });
    }

    try {
      const data = await loadBoardData(dataDir, configName, boardId);
      if (!data) {
        return res.status(404).json({ ok: false, error: `No JSONL data for board ${boardId} in config ${configName}` });
      }

      const streetChar = street === 'FLOP' ? 'F' : street === 'TURN' ? 'T' : 'R';
      const keyPrefix = `${streetChar}|${boardId}|${player}|${history}|`;

      // O(1) HashMap lookup (was O(n) linear scan)
      const exactKey = `${keyPrefix}${bucket}`;
      const exact = data.index.get(exactKey);
      if (exact) {
        return res.json({ ok: true, key: exact.key, probs: exact.probs, actions: exact.actions, source: 'exact' });
      }

      // Nearby bucket search (still fast — at most 10 lookups)
      const bucketCount = (data.meta as { bucketCount?: number }).bucketCount || 50;
      for (let delta = 1; delta <= 5; delta++) {
        for (const b of [bucket + delta, bucket - delta]) {
          if (b < 0 || b >= bucketCount) continue;
          const nearKey = `${keyPrefix}${b}`;
          const near = data.index.get(nearKey);
          if (near) {
            return res.json({ ok: true, key: near.key, probs: near.probs, actions: near.actions, source: 'nearby', requestedBucket: bucket, matchedBucket: b });
          }
        }
      }

      return res.json({ ok: false, error: 'No matching info set found', key: exactKey });
    } catch (e) {
      return res.status(500).json({ ok: false, error: (e as Error).message });
    }
  });

  // GET /api/cfr/board-strategy?config=X&boardId=N&street=FLOP&history=x
  app.get("/api/cfr/board-strategy", async (req: Request, res: Response) => {
    const configName = req.query.config as string;
    const boardId = parseInt(req.query.boardId as string, 10);
    const player = parseInt(req.query.player as string, 10);
    const history = (req.query.history as string) ?? '';
    const street = (req.query.street as string) ?? 'FLOP';

    if (!configName || isNaN(boardId) || isNaN(player)) {
      return res.status(400).json({ ok: false, error: 'Missing required parameters' });
    }

    try {
      const data = await loadBoardData(dataDir, configName, boardId);
      if (!data) {
        return res.status(404).json({ ok: false, error: `No data for board ${boardId}` });
      }

      const streetChar = street === 'FLOP' ? 'F' : street === 'TURN' ? 'T' : 'R';
      const keyPrefix = `${streetChar}|${boardId}|${player}|${history}|`;
      const strategies: Array<{ bucket: number; probs: number[]; actions?: string[] }> = [];

      // Scan only the index keys with matching prefix
      for (const [key, entry] of data.index) {
        if (!key.startsWith(keyPrefix)) continue;
        const bucketStr = key.slice(keyPrefix.length);
        const b = parseInt(bucketStr, 10);
        if (!isNaN(b)) {
          strategies.push({ bucket: b, probs: entry.probs, actions: entry.actions });
        }
      }

      strategies.sort((a, b) => a.bucket - b.bucket);
      return res.json({ ok: true, config: configName, boardId, player, street, history, strategies, count: strategies.length });
    } catch (e) {
      return res.status(500).json({ ok: false, error: (e as Error).message });
    }
  });
}
