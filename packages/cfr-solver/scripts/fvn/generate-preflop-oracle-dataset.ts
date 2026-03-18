#!/usr/bin/env tsx
import { mkdirSync, openSync, writeSync, closeSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { loadPreflopLibrary } from '../../src/preflop/preflop-library.js';
import { allHandClasses, RANKS } from '../../src/preflop/preflop-types.js';
import { buildPreflopFeatureVector } from '../../src/preflop/preflop-fvn-engine.js';
import { createFvnRuntime } from '../../src/nn/fvn-runtime.js';
import type { PostflopOracleSample } from '../../src/nn/postflop-oracle.js';

type Mode = 'chart' | 'random' | 'hybrid';

interface RecordRow {
  spotId: string;
  sampleIndex: number;
  featureVector: number[];
  ev: number;
  generatedAt: string;
  source: string;
  mode: Mode;
  handClass?: string;
  action?: string;
  scenario?: Record<string, number | string>;
}

interface PendingSample {
  mode: Mode;
  spotId: string;
  sample: PostflopOracleSample;
  handClass?: string;
  action?: string;
  scenario?: Record<string, number | string>;
}

interface RandomScene {
  id: string;
  players: number;
  stackBb: number;
  potBb: number;
  raiseLevel: number;
  heroSeat: number;
  villainSeat: number;
  aggression: number;
  heroDensity: number;
  villainDensity: number;
}

const HANDS = allHandClasses();

function getArg(name: string, fallback: string): string {
  const idx = process.argv.indexOf(`--${name}`);
  if (idx >= 0 && process.argv[idx + 1]) return process.argv[idx + 1];
  return fallback;
}

function parseIntArg(name: string, fallback: number): number {
  const parsed = Number.parseInt(getArg(name, String(fallback)), 10);
  if (!Number.isFinite(parsed)) throw new Error(`invalid --${name}`);
  return parsed;
}

function clamp01(v: number): number {
  return Math.max(0, Math.min(1, v));
}

function hash32(value: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < value.length; i++) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function makeRng(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x9e3779b9) >>> 0;
    let z = state;
    z = Math.imul(z ^ (z >>> 16), 0x85ebca6b);
    z = Math.imul(z ^ (z >>> 13), 0xc2b2ae35);
    z = (z ^ (z >>> 16)) >>> 0;
    return z / 4294967296;
  };
}

function rankIndex(ch: string): number {
  const idx = RANKS.indexOf(ch);
  return idx < 0 ? RANKS.length - 1 : idx;
}

function handClassFeatures(handClass: string): {
  high: number;
  low: number;
  suited: number;
  paired: number;
} {
  if (handClass.length === 2) {
    const r = rankIndex(handClass[0]);
    return { high: r, low: r, suited: 0, paired: 1 };
  }
  const hi = rankIndex(handClass[0]);
  const lo = rankIndex(handClass[1]);
  const suited = handClass.endsWith('s') ? 1 : 0;
  return { high: hi, low: lo, suited, paired: 0 };
}

function sampleUniqueHandIndexes(rng: () => number, count: number): number[] {
  if (count >= HANDS.length) {
    return HANDS.map((_, i) => i);
  }
  const picked = new Set<number>();
  while (picked.size < count) {
    picked.add(Math.floor(rng() * HANDS.length));
  }
  return Array.from(picked);
}

function randomInt(rng: () => number, min: number, maxInclusive: number): number {
  return min + Math.floor(rng() * (maxInclusive - min + 1));
}

function randomFloat(rng: () => number, min: number, max: number): number {
  return min + rng() * (max - min);
}

function makeRandomScene(
  rng: () => number,
  id: string,
  playersMin: number,
  playersMax: number,
): RandomScene {
  const players = randomInt(rng, playersMin, playersMax);
  const stackBb = randomFloat(rng, 20, 250);
  const potBb = randomFloat(rng, 1.5, Math.max(3, stackBb * 0.8));
  const raiseLevel = randomInt(rng, 0, 7);
  const heroSeat = randomInt(rng, 0, players - 1);
  let villainSeat = randomInt(rng, 0, players - 1);
  if (villainSeat === heroSeat) villainSeat = (villainSeat + 1) % players;
  return {
    id,
    players,
    stackBb,
    potBb,
    raiseLevel,
    heroSeat,
    villainSeat,
    aggression: rng(),
    heroDensity: rng(),
    villainDensity: rng(),
  };
}

function makeRandomActions(rng: () => number, maxActions: number): string[] {
  const count = Math.max(2, randomInt(rng, 2, Math.max(2, maxActions)));
  const actions = ['fold', 'call'];
  for (let i = 2; i < count; i++) {
    const roll = rng();
    if (roll < 0.12) actions.push('allin');
    else actions.push(`raise_${(i - 1) * 0.5 + 1.5}`);
  }
  return actions;
}

function buildRandomFeatureVector(
  scene: RandomScene,
  handClass: string,
  action: string,
  actionIndex: number,
  actionCount: number,
): number[] {
  const hf = handClassFeatures(handClass);
  const hiNorm = 1 - hf.high / 12;
  const loNorm = 1 - hf.low / 12;
  const connector = hf.paired ? 1 : 1 - Math.abs(hf.high - hf.low) / 12;
  const stackNorm = clamp01(scene.stackBb / 250);
  const potNorm = clamp01(scene.potBb / 80);
  const sprNorm = clamp01(scene.stackBb / Math.max(1, scene.potBb) / 25);
  const playersNorm = clamp01((scene.players - 2) / 4);
  const raiseNorm = clamp01(scene.raiseLevel / 8);
  const heroPosNorm = scene.players > 1 ? scene.heroSeat / (scene.players - 1) : 0;
  const villainPosNorm = scene.players > 1 ? scene.villainSeat / (scene.players - 1) : 0;
  const actionNorm = actionCount > 1 ? actionIndex / (actionCount - 1) : 0;
  const allinFlag = action === 'allin' ? 1 : 0;
  const raiseFlag = action.startsWith('raise_') ? 1 : 0;

  return [
    playersNorm,
    stackNorm,
    potNorm,
    sprNorm,
    raiseNorm,
    heroPosNorm,
    villainPosNorm,
    hiNorm,
    loNorm,
    hf.suited * 0.5 + hf.paired * 1.0,
    connector,
    clamp01(actionNorm * 0.4 + allinFlag * 0.6 + raiseFlag * 0.3 + scene.aggression * 0.2),
  ];
}

async function flushBatch(
  runtime: Awaited<ReturnType<typeof createFvnRuntime>>,
  fd: number,
  generatedAt: string,
  pending: PendingSample[],
  sampleIndexStart: number,
): Promise<number> {
  if (pending.length === 0) return sampleIndexStart;

  const result = await runtime.evaluateBatch({
    samples: pending.map((p) => p.sample),
    requestedBatchSize: runtime.maxBatchSize,
  });

  let sampleIndex = sampleIndexStart;
  for (let i = 0; i < pending.length; i++) {
    const row: RecordRow = {
      spotId: pending[i].spotId,
      sampleIndex,
      featureVector: pending[i].sample.featureVector,
      ev: result.results[i]?.ev ?? 0,
      generatedAt,
      source: runtime.provider,
      mode: pending[i].mode,
      handClass: pending[i].handClass,
      action: pending[i].action,
      scenario: pending[i].scenario,
    };
    writeSync(fd, JSON.stringify(row) + '\n');
    sampleIndex++;
  }

  pending.length = 0;
  return sampleIndex;
}

async function main(): Promise<void> {
  const outPath = resolve(
    getArg(
      'out',
      resolve(process.cwd(), 'data', 'nn-training', 'fvn_oracle_preflop12_generic.jsonl'),
    ),
  );
  const mode = getArg('mode', 'hybrid').toLowerCase() as Mode;
  if (!['chart', 'random', 'hybrid'].includes(mode)) {
    throw new Error(`invalid --mode ${mode}, expected chart|random|hybrid`);
  }

  const repeats = Math.max(1, parseIntArg('repeats', 4));
  const randomScenes = Math.max(0, parseIntArg('random-scenes', 800));
  const handsPerScene = Math.max(
    1,
    Math.min(HANDS.length, parseIntArg('hands-per-scene', HANDS.length)),
  );
  const maxActions = Math.max(2, parseIntArg('max-actions', 6));
  const playersMin = Math.max(2, parseIntArg('players-min', 2));
  const playersMax = Math.max(playersMin, Math.min(6, parseIntArg('players-max', 6)));
  const batch = Math.max(256, parseIntArg('batch', 4096));
  const modelPath = getArg('model', '').trim() || undefined;
  const seed = parseIntArg('seed', 42);

  const library = mode === 'random' ? null : loadPreflopLibrary();
  if (mode !== 'random' && !library) {
    throw new Error('preflop library not found');
  }

  const runtime = await createFvnRuntime({
    modelPath,
    minBatchSize: Math.max(256, Math.min(1024, batch)),
    maxBatchSize: batch,
    verbose: true,
    allowSyntheticFallback: true,
  });

  const rng = makeRng(seed);
  mkdirSync(dirname(outPath), { recursive: true });
  const fd = openSync(outPath, 'w');
  const generatedAt = new Date().toISOString();

  let sampleIndex = 0;
  let chartRows = 0;
  let randomRows = 0;
  const pending: PendingSample[] = [];

  try {
    if (mode === 'chart' || mode === 'hybrid') {
      if (!library) throw new Error('chart mode requires preflop library');
      for (let r = 0; r < repeats; r++) {
        for (let s = 0; s < library.spots.length; s++) {
          const spot = library.spots[s];
          for (let h = 0; h < HANDS.length; h++) {
            const hand = HANDS[h];
            for (let a = 0; a < spot.actions.length; a++) {
              const action = spot.actions[a];
              const feature = buildPreflopFeatureVector(s, h, a);
              pending.push({
                mode: 'chart',
                spotId: spot.id,
                sample: { spotId: spot.id, featureVector: feature },
                handClass: hand,
                action,
                scenario: {
                  repeat: r,
                  chartSpotIndex: s,
                },
              });
              chartRows++;

              if (pending.length >= batch) {
                sampleIndex = await flushBatch(runtime, fd, generatedAt, pending, sampleIndex);
              }
            }
          }
        }
      }
    }

    if (mode === 'random' || mode === 'hybrid') {
      for (let sceneIndex = 0; sceneIndex < randomScenes; sceneIndex++) {
        const scene = makeRandomScene(rng, `rnd_${sceneIndex}`, playersMin, playersMax);
        const actions = makeRandomActions(rng, maxActions);
        const handIndexes = sampleUniqueHandIndexes(rng, handsPerScene);

        for (const handIdx of handIndexes) {
          const handClass = HANDS[handIdx];
          for (let a = 0; a < actions.length; a++) {
            const action = actions[a];
            const feature = buildRandomFeatureVector(scene, handClass, action, a, actions.length);
            pending.push({
              mode: 'random',
              spotId: scene.id,
              sample: { spotId: scene.id, featureVector: feature },
              handClass,
              action,
              scenario: {
                players: scene.players,
                stackBb: Math.round(scene.stackBb * 100) / 100,
                potBb: Math.round(scene.potBb * 100) / 100,
                raiseLevel: scene.raiseLevel,
                heroSeat: scene.heroSeat,
                villainSeat: scene.villainSeat,
                aggression: Math.round(scene.aggression * 1000) / 1000,
                heroDensity: Math.round(scene.heroDensity * 1000) / 1000,
                villainDensity: Math.round(scene.villainDensity * 1000) / 1000,
              },
            });
            randomRows++;

            if (pending.length >= batch) {
              sampleIndex = await flushBatch(runtime, fd, generatedAt, pending, sampleIndex);
            }
          }
        }
      }
    }

    sampleIndex = await flushBatch(runtime, fd, generatedAt, pending, sampleIndex);
  } finally {
    closeSync(fd);
    await runtime.dispose();
  }

  const sceneHash = hash32(
    JSON.stringify({
      mode,
      repeats,
      randomScenes,
      handsPerScene,
      maxActions,
      playersMin,
      playersMax,
      batch,
      seed,
    }),
  );

  console.log(`Wrote oracle dataset: ${outPath}`);
  console.log(`Provider: ${runtime.provider}`);
  console.log(`Mode: ${mode}`);
  console.log(`Chart rows: ${chartRows}`);
  console.log(`Random rows: ${randomRows}`);
  console.log(`Total samples: ${sampleIndex}`);
  console.log(`Scenario hash: ${sceneHash}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
