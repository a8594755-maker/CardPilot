// CFR Lookup API — standalone endpoints for querying solved CFR strategies.
// Used by the web frontend's CFR Lookup page for studying GTO strategies.
// Supports both local filesystem (development) and S3 (production).

import type { Express, Request, Response, NextFunction } from "express";
import { resolve } from "node:path";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import {
  isS3Configured,
  downloadText,
  downloadJson,
} from "@cardpilot/advice-engine/s3-client";

// --- Rate limiter (per-IP sliding window) ---
const CFR_RATE_LIMIT = parseInt(process.env.CFR_RATE_LIMIT || '100', 10);       // max requests per window
const CFR_RATE_WINDOW_MS = parseInt(process.env.CFR_RATE_WINDOW_MS || String(60 * 60 * 1000), 10); // default 1 hour

interface RateBucket {
  timestamps: number[];
}

const rateBuckets = new Map<string, RateBucket>();

// Cleanup stale entries every 10 minutes
setInterval(() => {
  const now = Date.now();
  for (const [ip, bucket] of rateBuckets) {
    bucket.timestamps = bucket.timestamps.filter(ts => now - ts < CFR_RATE_WINDOW_MS);
    if (bucket.timestamps.length === 0) rateBuckets.delete(ip);
  }
}, 10 * 60 * 1000);

function getClientIp(req: Request): string {
  const forwarded = req.headers['x-forwarded-for'];
  if (typeof forwarded === 'string') return forwarded.split(',')[0].trim();
  return req.ip || req.socket.remoteAddress || 'unknown';
}

function cfrRateLimit(req: Request, res: Response, next: NextFunction): void {
  const ip = getClientIp(req);
  const now = Date.now();

  let bucket = rateBuckets.get(ip);
  if (!bucket) {
    bucket = { timestamps: [] };
    rateBuckets.set(ip, bucket);
  }

  // Prune expired timestamps
  bucket.timestamps = bucket.timestamps.filter(ts => now - ts < CFR_RATE_WINDOW_MS);

  if (bucket.timestamps.length >= CFR_RATE_LIMIT) {
    const oldest = bucket.timestamps[0];
    const resetMs = oldest + CFR_RATE_WINDOW_MS - now;
    const resetMin = Math.ceil(resetMs / 60_000);
    res.setHeader('Retry-After', Math.ceil(resetMs / 1000));
    res.setHeader('X-RateLimit-Limit', CFR_RATE_LIMIT);
    res.setHeader('X-RateLimit-Remaining', 0);
    res.status(429).json({
      ok: false,
      error: `Rate limit exceeded. You can make ${CFR_RATE_LIMIT} solver queries per ${Math.round(CFR_RATE_WINDOW_MS / 60_000)} minutes. Try again in ${resetMin} minute(s).`,
    });
    return;
  }

  bucket.timestamps.push(now);
  res.setHeader('X-RateLimit-Limit', CFR_RATE_LIMIT);
  res.setHeader('X-RateLimit-Remaining', CFR_RATE_LIMIT - bucket.timestamps.length);
  next();
}

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

// --- LRU cache for JSONL content (S3 mode) ---
const MAX_JSONL_CACHE = 50; // max cached flops
const jsonlCache = new Map<string, { content: string; ts: number }>();

function cacheGet(key: string): string | undefined {
  const entry = jsonlCache.get(key);
  if (entry) { entry.ts = Date.now(); return entry.content; }
  return undefined;
}

function cacheSet(key: string, content: string): void {
  if (jsonlCache.size >= MAX_JSONL_CACHE) {
    // evict oldest
    let oldest = '';
    let oldestTs = Infinity;
    for (const [k, v] of jsonlCache) {
      if (v.ts < oldestTs) { oldest = k; oldestTs = v.ts; }
    }
    if (oldest) jsonlCache.delete(oldest);
  }
  jsonlCache.set(key, { content, ts: Date.now() });
}

// --- Meta index cache (S3 mode) ---
interface MetaEntry {
  boardId: number;
  flopCards: number[];
  infoSets?: number;
  iterations?: number;
}
const metaIndexCache = new Map<string, { data: MetaEntry[]; ts: number }>();
const META_CACHE_TTL = 5 * 60 * 1000; // 5 minutes

async function getMetaIndex(configDir: string): Promise<MetaEntry[]> {
  const cached = metaIndexCache.get(configDir);
  if (cached && Date.now() - cached.ts < META_CACHE_TTL) return cached.data;

  const key = `meta/${configDir}/_index.json`;
  const data = await downloadJson<MetaEntry[]>(key);
  const result = data ?? [];
  metaIndexCache.set(configDir, { data: result, ts: Date.now() });
  return result;
}

// --- JSONL fetcher (S3 or local) ---
async function getJsonlContent(
  configDir: string, boardId: number, dataDir: string
): Promise<string | null> {
  const paddedId = String(boardId).padStart(3, '0');

  if (isS3Configured()) {
    const cacheKey = `${configDir}/${paddedId}`;
    const cached = cacheGet(cacheKey);
    if (cached !== undefined) return cached;

    const s3Key = `jsonl/${configDir}/flop_${paddedId}.jsonl`;
    const content = await downloadText(s3Key);
    if (content) cacheSet(cacheKey, content);
    return content;
  }

  // Local fallback
  const jsonlPath = resolve(dataDir, configDir, `flop_${paddedId}.jsonl`);
  if (!existsSync(jsonlPath)) return null;
  return readFileSync(jsonlPath, 'utf-8');
}

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

export function setupCfrLookupRoutes(app: Express): void {
  const dataDir = findDataDir();
  const useS3 = isS3Configured();

  if (useS3) {
    console.log('[cfr-lookup] S3 mode enabled — reading CFR data from iDrive e2');
  } else {
    console.log(`[cfr-lookup] local mode — reading CFR data from ${dataDir}`);
  }
  console.log(`[cfr-lookup] rate limit: ${CFR_RATE_LIMIT} requests per ${Math.round(CFR_RATE_WINDOW_MS / 60_000)} min`);

  // GET /api/cfr/configs — list all available configs with solve status (no rate limit — lightweight)
  app.get("/api/cfr/configs", async (_req: Request, res: Response) => {
    try {
      const configs = await Promise.all(CFR_CONFIGS.map(async cfg => {
        const configDir = OUTPUT_DIRS[cfg.name] ?? cfg.name;
        let solvedFlops = 0;
        const totalFlops = 1755;

        if (useS3) {
          const metas = await getMetaIndex(configDir);
          solvedFlops = metas.length;
        } else {
          const outputDir = resolve(dataDir, configDir);
          if (existsSync(outputDir)) {
            try {
              const files = readdirSync(outputDir);
              solvedFlops = files.filter(f => f.endsWith('.meta.json')).length;
            } catch { /* ignore */ }
          }
        }

        return {
          ...cfg,
          solvedFlops,
          totalFlops,
          progress: Math.round((solvedFlops / totalFlops) * 100),
          available: solvedFlops > 0,
        };
      }));

      res.json({ ok: true, configs, dataDir: useS3 ? 's3' : dataDir });
    } catch (e) {
      res.status(500).json({ ok: false, error: (e as Error).message });
    }
  });

  // GET /api/cfr/flops?config=X — list solved flops for a config
  app.get("/api/cfr/flops", cfrRateLimit, async (req: Request, res: Response) => {
    const configName = req.query.config as string;
    if (!configName) {
      return res.status(400).json({ ok: false, error: 'Missing config parameter' });
    }

    const configDir = OUTPUT_DIRS[configName] ?? configName;

    try {
      if (useS3) {
        const metas = await getMetaIndex(configDir);
        const flops = metas.map(meta => ({
          boardId: meta.boardId,
          flopCards: meta.flopCards,
          flopLabel: meta.flopCards?.map(cardIndexToLabel).join(' ') ?? `Board ${meta.boardId}`,
          infoSets: meta.infoSets,
          iterations: meta.iterations,
        }));
        return res.json({ ok: true, flops, total: flops.length });
      }

      // Local fallback
      const outputDir = resolve(dataDir, configDir);
      if (!existsSync(outputDir)) {
        return res.json({ ok: true, flops: [] });
      }

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
  app.get("/api/cfr/lookup", cfrRateLimit, async (req: Request, res: Response) => {
    const configName = req.query.config as string;
    const boardId = parseInt(req.query.boardId as string, 10);
    const player = parseInt(req.query.player as string, 10);
    const history = (req.query.history as string) ?? '';
    const bucket = parseInt(req.query.bucket as string, 10);
    const street = (req.query.street as string) ?? 'FLOP';

    if (!configName || isNaN(boardId) || isNaN(player) || isNaN(bucket)) {
      return res.status(400).json({ ok: false, error: 'Missing required parameters: config, boardId, player, bucket' });
    }

    const configDir = OUTPUT_DIRS[configName] ?? configName;

    try {
      const content = await getJsonlContent(configDir, boardId, dataDir);
      if (!content) {
        return res.status(404).json({ ok: false, error: `No JSONL data for board ${boardId} in config ${configName}` });
      }

      const streetChar = street === 'FLOP' ? 'F' : street === 'TURN' ? 'T' : 'R';
      const keyPrefix = `${streetChar}|${boardId}|${player}|${history}|`;
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
  app.get("/api/cfr/board-strategy", cfrRateLimit, async (req: Request, res: Response) => {
    const configName = req.query.config as string;
    const boardId = parseInt(req.query.boardId as string, 10);
    const player = parseInt(req.query.player as string, 10);
    const history = (req.query.history as string) ?? '';
    const street = (req.query.street as string) ?? 'FLOP';

    if (!configName || isNaN(boardId) || isNaN(player)) {
      return res.status(400).json({ ok: false, error: 'Missing required parameters' });
    }

    const configDir = OUTPUT_DIRS[configName] ?? configName;

    try {
      const content = await getJsonlContent(configDir, boardId, dataDir);
      if (!content) {
        return res.status(404).json({ ok: false, error: `No data for board ${boardId}` });
      }

      const streetChar = street === 'FLOP' ? 'F' : street === 'TURN' ? 'T' : 'R';
      const keyPrefix = `${streetChar}|${boardId}|${player}|${history}|`;
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
