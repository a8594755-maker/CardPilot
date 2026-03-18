// Export solved strategies to JSONL format

import { openSync, writeSync, closeSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import type { InfoSetStore } from '../engine/info-set-store.js';

export interface ExportConfig {
  outputPath: string;
  boardId: number;
  flopCards: [number, number, number];
  iterations: number;
  bucketCount: number;
  elapsedMs: number;
  stackLabel?: string; // e.g. '50bb', '100bb'
  configName?: string; // e.g. 'standard_50bb'
  betSizes?: { flop: number[]; turn: number[]; river: number[] };
}

/**
 * Export solved strategies to a JSONL file.
 * Each line is one info set: { key, actions, probs }
 */
export function exportToJSONL(
  store: InfoSetStore,
  config: ExportConfig,
): {
  infoSets: number;
  fileSize: number;
} {
  mkdirSync(dirname(config.outputPath), { recursive: true });

  // Stream line-by-line to avoid buffering entire file in memory
  // (100bb boards can produce millions of info sets; buffering all would OOM)
  const fd = openSync(config.outputPath, 'w');
  let infoSets = 0;
  let fileSize = 0;

  for (const entry of store.entries()) {
    const probs = Array.from(entry.averageStrategy).map((p) => Math.round(p * 1000) / 1000);
    // Skip near-uniform strategies (they're uninteresting)
    const maxProb = Math.max(...probs);
    if (maxProb < 0.01) continue;

    const line = JSON.stringify({ key: entry.key, probs }) + '\n';
    const buf = Buffer.from(line, 'utf-8');
    writeSync(fd, buf);
    fileSize += buf.byteLength;
    infoSets++;
  }

  closeSync(fd);

  return { infoSets, fileSize };
}

/**
 * Export an ArrayStore (vectorized solver) to JSONL format.
 * Stub — will be fully implemented when vectorized engine is ported.
 */
export function exportArrayStoreToJSONL(
  _store: unknown,
  _tree: unknown,
  _combos: unknown,
  _config: Record<string, unknown>,
): { infoSets: number; fileSize: number } {
  throw new Error('exportArrayStoreToJSONL: not yet implemented (vectorized engine WIP)');
}

/**
 * Export metadata about the solve.
 */
export function exportMeta(
  config: ExportConfig & {
    infoSets: number;
    peakMemoryMB: number;
  },
): void {
  const meta: Record<string, any> = {
    version: 'v2',
    keyFormat: 'v2',
    game: 'HU_NLHE_SRP',
    stack: config.stackLabel || '50bb',
    config: config.configName || 'v1_50bb',
    boardId: config.boardId,
    flopCards: config.flopCards,
    iterations: config.iterations,
    bucketCount: config.bucketCount,
    infoSets: config.infoSets,
    elapsedMs: config.elapsedMs,
    peakMemoryMB: config.peakMemoryMB,
    timestamp: new Date().toISOString(),
  };
  if (config.betSizes) {
    meta.betSizes = config.betSizes;
  }

  const metaPath = config.outputPath.replace(/\.jsonl$/, '.meta.json');
  writeFileSync(metaPath, JSON.stringify(meta, null, 2), 'utf-8');
}
