#!/usr/bin/env tsx
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { evaluateModel } from '../packages/fast-model/src/evaluate.js';
import type { ModelWeights, TrainingSample } from '../packages/fast-model/src/types.js';
import { FEATURE_COUNT_V2 } from '../packages/fast-model/src/feature-encoder.js';

function loadSamples(dataDir: string, maxSamples: number): TrainingSample[] {
  if (!existsSync(dataDir)) throw new Error(`Data directory not found: ${dataDir}`);
  const files = readdirSync(dataDir).filter(f => f.endsWith('.jsonl'));
  const out: TrainingSample[] = [];
  for (const file of files) {
    const lines = readFileSync(join(dataDir, file), 'utf-8').split('\n');
    for (const line of lines) {
      const t = line.trim();
      if (!t) continue;
      try {
        const s = JSON.parse(t) as TrainingSample;
        if (s.f?.length === FEATURE_COUNT_V2 && s.l?.length === 3) {
          out.push(s);
          if (out.length >= maxSamples) return out;
        }
      } catch {
        // ignore malformed rows
      }
    }
  }
  return out;
}

function printRow(name: string, model: ModelWeights, samples: TrainingSample[]): void {
  const m = evaluateModel(model, samples);
  const sizing = m.sizingTop1Accuracy != null ? `${(m.sizingTop1Accuracy * 100).toFixed(3)}%` : 'n/a';
  console.log(
    `${name}\tKL=${m.klDivergence.toFixed(6)}\tTop1=${(m.top1Accuracy * 100).toFixed(3)}%\tSizing=${sizing}\tN=${m.sampleCount}`,
  );
}

function main(): void {
  const argv = process.argv.slice(2);
  if (argv.length < 2) {
    throw new Error('Usage: compare-models-v2.ts <modelA.json> <modelB.json> [--data data/v2] [--max-samples 200000]');
  }

  const modelAPath = argv[0];
  const modelBPath = argv[1];
  let dataDir = 'data/v2';
  let maxSamples = 200000;

  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === '--data' && argv[i + 1]) dataDir = argv[++i];
    if (argv[i] === '--max-samples' && argv[i + 1]) {
      const parsed = parseInt(argv[++i], 10);
      if (Number.isFinite(parsed) && parsed > 0) maxSamples = parsed;
    }
  }

  const modelA = JSON.parse(readFileSync(modelAPath, 'utf-8')) as ModelWeights;
  const modelB = JSON.parse(readFileSync(modelBPath, 'utf-8')) as ModelWeights;
  const samples = loadSamples(dataDir, maxSamples);

  console.log(`Eval samples: ${samples.length} from ${dataDir}`);
  printRow('modelA', modelA, samples);
  printRow('modelB', modelB, samples);
}

main();
