// Export solved strategies to JSONL format

import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import type { InfoSetStore } from '../engine/info-set-store.js';

export interface ExportConfig {
  outputPath: string;
  boardId: number;
  flopCards: [number, number, number];
  iterations: number;
  bucketCount: number;
  elapsedMs: number;
}

/**
 * Export solved strategies to a JSONL file.
 * Each line is one info set: { key, actions, probs }
 */
export function exportToJSONL(store: InfoSetStore, config: ExportConfig): {
  infoSets: number;
  fileSize: number;
} {
  mkdirSync(dirname(config.outputPath), { recursive: true });

  const lines: string[] = [];

  for (const entry of store.entries()) {
    // Parse actions from the key context
    const probs = Array.from(entry.averageStrategy).map(p => Math.round(p * 1000) / 1000);
    // Skip near-uniform strategies (they're uninteresting)
    const maxProb = Math.max(...probs);
    if (maxProb < 0.01) continue;

    lines.push(JSON.stringify({
      key: entry.key,
      probs,
    }));
  }

  const content = lines.join('\n') + '\n';
  writeFileSync(config.outputPath, content, 'utf-8');

  return {
    infoSets: lines.length,
    fileSize: Buffer.byteLength(content),
  };
}

/**
 * Export metadata about the solve.
 */
export function exportMeta(config: ExportConfig & {
  infoSets: number;
  peakMemoryMB: number;
}): void {
  const meta = {
    version: 'v1',
    game: 'HU_NLHE_SRP',
    stack: '50bb',
    boardId: config.boardId,
    flopCards: config.flopCards,
    iterations: config.iterations,
    bucketCount: config.bucketCount,
    infoSets: config.infoSets,
    elapsedMs: config.elapsedMs,
    peakMemoryMB: config.peakMemoryMB,
    timestamp: new Date().toISOString(),
  };

  const metaPath = config.outputPath.replace(/\.jsonl$/, '.meta.json');
  writeFileSync(metaPath, JSON.stringify(meta, null, 2), 'utf-8');
}
