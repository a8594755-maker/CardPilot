#!/usr/bin/env tsx
import { mkdirSync, openSync, writeSync, closeSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { allHandClasses } from '../../src/preflop/preflop-types.js';
import { loadPreflopLibrary, type LibrarySpot } from '../../src/preflop/preflop-library.js';
import { createFvnRuntime } from '../../src/nn/fvn-runtime.js';
import type { PostflopOracleSample } from '../../src/nn/postflop-oracle.js';

interface Options {
  outPath: string;
  modelPath?: string;
  samplesPerSpot: number;
  batchSize: number;
  seed: number;
}

interface DatasetRecord {
  spotId: string;
  sampleIndex: number;
  featureVector: number[];
  ev: number;
  generatedAt: string;
  source: string;
}

const HAND_CLASSES = allHandClasses();

function parseArgs(argv: string[]): Options {
  const outPath = getArg(
    argv,
    'out',
    resolve(process.cwd(), 'data', 'nn-training', 'fvn_dataset.jsonl'),
  );
  const modelPath = getArg(argv, 'model', '').trim();
  const samplesPerSpot = parseInt(getArg(argv, 'samples-per-spot', '20000'), 10);
  const batchSize = parseInt(getArg(argv, 'batch', '1024'), 10);
  const seed = parseInt(getArg(argv, 'seed', '42'), 10);

  return {
    outPath,
    modelPath: modelPath || undefined,
    samplesPerSpot: Number.isFinite(samplesPerSpot) ? samplesPerSpot : 20000,
    batchSize: Number.isFinite(batchSize) ? batchSize : 1024,
    seed: Number.isFinite(seed) ? seed : 42,
  };
}

function getArg(argv: string[], name: string, fallback: string): string {
  const idx = argv.indexOf(`--${name}`);
  if (idx >= 0 && argv[idx + 1]) return argv[idx + 1];
  return fallback;
}

function nextRng(state: number): number {
  state = (state + 0x9e3779b9) | 0;
  let z = state;
  z = Math.imul(z ^ (z >>> 16), 0x85ebca6b);
  z = Math.imul(z ^ (z >>> 13), 0xc2b2ae35);
  return (z ^ (z >>> 16)) >>> 0;
}

function handClassComboCount(handClass: string): number {
  if (handClass.length === 2) return 6;
  return handClass.endsWith('s') ? 4 : 12;
}

function makeBoardFeatures(rngSeed: number): { features: number[]; nextSeed: number } {
  const values: number[] = [];
  let seed = rngSeed;
  for (let i = 0; i < 12; i++) {
    seed = nextRng(seed);
    values.push((seed % 10000) / 10000);
  }
  return { features: values, nextSeed: seed };
}

function randomRangeVector(rngSeed: number): { vector: number[]; nextSeed: number } {
  const vector = new Array<number>(HAND_CLASSES.length);
  let seed = rngSeed;
  let total = 0;
  for (let i = 0; i < HAND_CLASSES.length; i++) {
    seed = nextRng(seed);
    const v = ((seed >>> 3) % 1000) + 1;
    vector[i] = v;
    total += v;
  }
  for (let i = 0; i < vector.length; i++) {
    vector[i] /= total;
  }
  return { vector, nextSeed: seed };
}

function dominantAction(spot: LibrarySpot, handClass: string): string {
  const mix = spot.grid[handClass];
  let best = spot.actions[0];
  let bestValue = -1;
  for (const action of spot.actions) {
    const value = Number(mix[action] ?? 0);
    if (value >= bestValue) {
      bestValue = value;
      best = action;
    }
  }
  return best;
}

function heroRangeVector(spot: LibrarySpot): number[] {
  const vector = new Array<number>(HAND_CLASSES.length);
  let totalWeight = 0;
  for (let i = 0; i < HAND_CLASSES.length; i++) {
    const hand = HAND_CLASSES[i];
    const action = dominantAction(spot, hand);
    const mix = spot.grid[hand][action] ?? 0;
    const weighted = handClassComboCount(hand) * mix;
    vector[i] = weighted;
    totalWeight += weighted;
  }

  if (totalWeight <= 0) return vector.map(() => 0);
  return vector.map((v) => v / totalWeight);
}

function makeFeatureVector(
  heroRange: number[],
  villainRange: number[],
  boardFeatures: number[],
  spotIndex: number,
  sampleIndex: number,
): number[] {
  const context = [
    spotIndex / 32,
    sampleIndex / 1000000,
    heroRange.length / 256,
    boardFeatures.length / 32,
  ];
  return [...heroRange, ...villainRange, ...boardFeatures, ...context];
}

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2));
  const library = loadPreflopLibrary();
  if (!library) {
    throw new Error('preflop library not found. run parse-chart first.');
  }

  mkdirSync(dirname(options.outPath), { recursive: true });
  const outFd = openSync(options.outPath, 'w');

  const runtime = await createFvnRuntime({
    modelPath: options.modelPath,
    minBatchSize: Math.max(1024, options.batchSize),
    maxBatchSize: Math.max(1024, options.batchSize),
    verbose: true,
  });

  let seed = options.seed | 0;
  let totalSamples = 0;
  const generatedAt = new Date().toISOString();

  try {
    console.log('=== FVN Dataset Generator ===');
    console.log(`Output: ${options.outPath}`);
    console.log(`Provider: ${runtime.provider}`);
    console.log(`Spots: ${library.spots.length}`);
    console.log(`Samples/spot: ${options.samplesPerSpot}`);

    for (let s = 0; s < library.spots.length; s++) {
      const spot = library.spots[s];
      const heroRange = heroRangeVector(spot);

      for (let offset = 0; offset < options.samplesPerSpot; offset += options.batchSize) {
        const chunkSize = Math.min(options.batchSize, options.samplesPerSpot - offset);
        const samples: PostflopOracleSample[] = [];

        for (let i = 0; i < chunkSize; i++) {
          const sampleIndex = offset + i;
          const villain = randomRangeVector(seed);
          seed = villain.nextSeed;

          const board = makeBoardFeatures(seed);
          seed = board.nextSeed;

          const featureVector = makeFeatureVector(
            heroRange,
            villain.vector,
            board.features,
            s,
            sampleIndex,
          );
          samples.push({
            spotId: spot.id,
            featureVector,
            metadata: {
              spot: spot.id,
              index: sampleIndex,
            },
          });
        }

        const result = await runtime.evaluateBatch({
          samples,
          requestedBatchSize: options.batchSize,
        });

        const lines: string[] = [];
        for (let i = 0; i < samples.length; i++) {
          const record: DatasetRecord = {
            spotId: samples[i].spotId,
            sampleIndex: offset + i,
            featureVector: Array.from(samples[i].featureVector as number[]),
            ev: result.results[i]?.ev ?? 0,
            generatedAt,
            source: runtime.provider,
          };
          lines.push(JSON.stringify(record));
        }
        writeSync(outFd, lines.join('\n') + '\n');
        totalSamples += samples.length;
      }

      console.log(`  ${spot.id}: ${options.samplesPerSpot} samples`);
    }

    console.log(`Done. Wrote ${totalSamples} samples.`);
  } finally {
    await runtime.dispose();
    closeSync(outFd);
  }
}

main().catch((error) => {
  console.error('generate-flop-ev-dataset failed:', error);
  process.exit(1);
});
