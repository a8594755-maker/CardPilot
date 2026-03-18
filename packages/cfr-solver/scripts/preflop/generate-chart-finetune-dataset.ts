#!/usr/bin/env tsx
import { mkdirSync, openSync, writeSync, closeSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { loadPreflopLibrary } from '../../src/preflop/preflop-library.js';
import { allHandClasses } from '../../src/preflop/preflop-types.js';
import { buildPreflopFeatureVector } from '../../src/preflop/preflop-fvn-engine.js';

interface DatasetRecord {
  spotId: string;
  sampleIndex: number;
  featureVector: number[];
  ev: number;
  generatedAt: string;
  source: string;
}

function getArg(name: string, fallback: string): string {
  const idx = process.argv.indexOf(`--${name}`);
  if (idx >= 0 && process.argv[idx + 1]) return process.argv[idx + 1];
  return fallback;
}

function main(): void {
  const outPath = resolve(
    getArg('out', resolve(process.cwd(), 'data', 'nn-training', 'fvn_chart_finetune.jsonl')),
  );
  const repeat = Math.max(1, parseInt(getArg('repeat', '8'), 10));
  const generatedAt = new Date().toISOString();

  const library = loadPreflopLibrary();
  if (!library) throw new Error('preflop library not found. run parse-chart first.');

  const handClasses = allHandClasses();
  mkdirSync(dirname(outPath), { recursive: true });
  const fd = openSync(outPath, 'w');

  let sampleIndex = 0;
  try {
    for (let r = 0; r < repeat; r++) {
      for (let s = 0; s < library.spots.length; s++) {
        const spot = library.spots[s];
        for (let h = 0; h < handClasses.length; h++) {
          const hand = handClasses[h];
          const mix = spot.grid[hand];

          let bestAction = spot.actions[0];
          let bestValue = Number(mix[bestAction] ?? 0);
          for (const action of spot.actions) {
            const v = Number(mix[action] ?? 0);
            if (v > bestValue) {
              bestValue = v;
              bestAction = action;
            }
          }

          for (let a = 0; a < spot.actions.length; a++) {
            const action = spot.actions[a];
            const prob = Number(mix[action] ?? 0);
            const ev = action === bestAction ? 1 + prob : -1 + prob;
            const row: DatasetRecord = {
              spotId: spot.id,
              sampleIndex,
              featureVector: buildPreflopFeatureVector(s, h, a),
              ev,
              generatedAt,
              source: 'chart_finetune_v1',
            };
            sampleIndex++;
            writeSync(fd, JSON.stringify(row) + '\n');
          }
        }
      }
    }
  } finally {
    closeSync(fd);
  }

  console.log(`Wrote chart finetune dataset: ${outPath}`);
  console.log(`Samples: ${sampleIndex}`);
}

main();
