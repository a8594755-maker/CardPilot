/**
 * Model Calibration: compare neural network predictions against CFR ground truth.
 *
 * Metrics:
 *   - KL divergence: avg KL(CFR || model) across info sets
 *   - Action accuracy: % where argmax(model) matches argmax(CFR)
 *   - Per-street breakdown (FLOP / TURN / RIVER)
 *   - Per-bucket-tier (low 0-33, mid 34-66, high 67-99)
 *   - Worst info sets (highest KL divergence)
 */

import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';

import {
  loadHUSRPRanges,
  getWeightedRangeCombos,
} from '../integration/preflop-ranges.js';
import {
  computeEquityBuckets,
  comboKey,
} from '../engine/cfr-engine.js';
import {
  getTreeConfig,
  type TreeConfigName,
} from '../tree/tree-config.js';

import {
  parseInfoSetKey,
  replayHistory,
  inferActionsFromHistory,
  mapCfrProbsToV2Labels,
  encodeCfrFeatures,
} from './cfr-to-training-data.js';

import type { Street, TreeConfig } from '../types.js';

// ── Types ──

export interface CalibrationResult {
  overall: {
    klDivergence: number;
    actionAccuracy: number;
    totalInfoSets: number;
    totalPredictions: number;
  };
  perStreet: Record<string, {
    klDivergence: number;
    actionAccuracy: number;
    count: number;
  }>;
  perBucketTier: Record<string, {
    klDivergence: number;
    actionAccuracy: number;
    count: number;
  }>;
  worstInfoSets: Array<{
    key: string;
    cfrProbs: number[];
    modelProbs: [number, number, number];
    kl: number;
  }>;
}

// ── Model interface (minimal, avoids importing fast-model) ──

interface ModelWeights {
  layers: Array<{ weights: number[][]; biases: number[] }>;
  actionHead?: { weights: number[][]; biases: number[] };
  sizingHead?: { weights: number[][]; biases: number[] };
  inputSize: number;
}

function loadModel(path: string): ModelWeights {
  return JSON.parse(readFileSync(path, 'utf-8'));
}

function relu(x: number): number { return x > 0 ? x : 0; }

function predictAction(model: ModelWeights, features: number[]): [number, number, number] {
  const isV2 = !!(model.actionHead && model.sizingHead);

  if (isV2) {
    // V2: backbone → action head
    let current = features;
    for (const layer of model.layers) {
      const output = new Array(layer.weights.length);
      for (let j = 0; j < layer.weights.length; j++) {
        let sum = layer.biases[j];
        const w = layer.weights[j];
        for (let i = 0; i < current.length; i++) sum += current[i] * w[i];
        output[j] = relu(sum);
      }
      current = output;
    }

    // Action head
    const ah = model.actionHead!;
    const logits = new Array(ah.weights.length);
    for (let j = 0; j < ah.weights.length; j++) {
      let sum = ah.biases[j];
      const w = ah.weights[j];
      for (let i = 0; i < current.length; i++) sum += current[i] * w[i];
      logits[j] = sum;
    }

    // Softmax
    const maxVal = Math.max(...logits);
    const exps = logits.map((v: number) => Math.exp(v - maxVal));
    const total = exps.reduce((a: number, b: number) => a + b, 0);
    return exps.map((e: number) => e / total) as [number, number, number];
  } else {
    // V1: sequential
    let current = features;
    for (let l = 0; l < model.layers.length; l++) {
      const layer = model.layers[l];
      const isOutput = l === model.layers.length - 1;
      const output = new Array(layer.weights.length);
      for (let j = 0; j < layer.weights.length; j++) {
        let sum = layer.biases[j];
        const w = layer.weights[j];
        for (let i = 0; i < current.length; i++) sum += current[i] * w[i];
        output[j] = isOutput ? sum : relu(sum);
      }
      if (isOutput) {
        const maxVal = Math.max(...output);
        const exps = output.map((v: number) => Math.exp(v - maxVal));
        const total = exps.reduce((a: number, b: number) => a + b, 0);
        return exps.map((e: number) => e / total) as [number, number, number];
      }
      current = output;
    }
    return [0.33, 0.33, 0.34]; // fallback
  }
}

// ── Math ──

function klDivergence(p: number[], q: number[]): number {
  let kl = 0;
  for (let i = 0; i < p.length; i++) {
    if (p[i] > 1e-10) {
      kl += p[i] * Math.log(p[i] / Math.max(q[i], 1e-10));
    }
  }
  return kl;
}

function argmax(arr: number[]): number {
  let maxIdx = 0;
  for (let i = 1; i < arr.length; i++) {
    if (arr[i] > arr[maxIdx]) maxIdx = i;
  }
  return maxIdx;
}

// ── Calibration ──

export function calibrate(
  modelPath: string,
  cfrDir: string,
  configName: TreeConfigName,
  chartsPath: string,
  maxFlops: number,
): CalibrationResult {
  const model = loadModel(modelPath);
  const treeConfig = getTreeConfig(configName);
  const { oopRange, ipRange } = loadHUSRPRanges(chartsPath);
  const oopCombos = getWeightedRangeCombos(oopRange);
  const ipCombos = getWeightedRangeCombos(ipRange);

  // Discover flops
  const files = readdirSync(cfrDir).filter((f: string) => f.endsWith('.meta.json'));
  const flops = files.slice(0, maxFlops);

  console.log(`Calibrating ${flops.length} flops against model...`);

  // Accumulators
  let totalKL = 0;
  let totalCorrect = 0;
  let totalPredictions = 0;
  const streetStats: Record<string, { kl: number; correct: number; count: number }> = {};
  const tierStats: Record<string, { kl: number; correct: number; count: number }> = {};
  const worstInfoSets: Array<{ key: string; cfrProbs: number[]; modelProbs: [number, number, number]; kl: number }> = [];

  for (const metaFile of flops) {
    const metaPath = join(cfrDir, metaFile);
    const jsonlPath = metaPath.replace('.meta.json', '.jsonl');
    if (!existsSync(jsonlPath)) continue;

    const meta = JSON.parse(readFileSync(metaPath, 'utf-8'));
    const flopCards = meta.flopCards as [number, number, number];
    const boardId = meta.boardId as number;
    const bucketCount = meta.bucketCount as number;

    // Build flop bucket mapping
    const deadCards = new Set<number>(flopCards);
    const oopFlopBuckets = computeEquityBuckets(oopCombos, flopCards, bucketCount, deadCards);
    const ipFlopBuckets = computeEquityBuckets(ipCombos, flopCards, bucketCount, deadCards);

    // Invert to get bucket → combo
    const oopBucketCombos = new Map<number, Array<[number, number]>>();
    const ipBucketCombos = new Map<number, Array<[number, number]>>();

    for (const { combo } of oopCombos) {
      if (deadCards.has(combo[0]) || deadCards.has(combo[1])) continue;
      const b = oopFlopBuckets.get(comboKey(combo));
      if (b !== undefined) {
        if (!oopBucketCombos.has(b)) oopBucketCombos.set(b, []);
        oopBucketCombos.get(b)!.push(combo);
      }
    }
    for (const { combo } of ipCombos) {
      if (deadCards.has(combo[0]) || deadCards.has(combo[1])) continue;
      const b = ipFlopBuckets.get(comboKey(combo));
      if (b !== undefined) {
        if (!ipBucketCombos.has(b)) ipBucketCombos.set(b, []);
        ipBucketCombos.get(b)!.push(combo);
      }
    }

    // Parse JSONL
    const lines = readFileSync(jsonlPath, 'utf-8').split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      let entry: { key: string; probs: number[] };
      try {
        entry = JSON.parse(trimmed);
      } catch { continue; }

      // Only calibrate FLOP entries for now (turn/river need runout sampling)
      const parsed = parseInfoSetKey(entry.key);
      if (parsed.street !== 'FLOP') continue;

      const actions = inferActionsFromHistory(parsed.historyKey, treeConfig);
      if (actions.length !== entry.probs.length) continue;

      const { l: cfrLabel } = mapCfrProbsToV2Labels(actions, entry.probs, treeConfig, parsed.street);

      // Get a representative combo for this bucket
      const bucket = parseInt(parsed.bucketStr, 10);
      const bucketCombos = parsed.player === 0 ? oopBucketCombos : ipBucketCombos;
      const combos = bucketCombos.get(bucket);
      if (!combos || combos.length === 0) continue;

      // Use first combo as representative
      const combo = combos[0];
      const gameState = replayHistory(parsed.historyKey, treeConfig);
      const features = encodeCfrFeatures(combo, [...flopCards], gameState, parsed.player, parsed.historyKey);

      // Predict with model
      const modelProbs = predictAction(model, features);

      // Compare
      const kl = klDivergence(cfrLabel, modelProbs);
      const cfrAction = argmax(cfrLabel);
      const modelAction = argmax(modelProbs);
      const correct = cfrAction === modelAction;

      totalKL += kl;
      totalPredictions++;
      if (correct) totalCorrect++;

      // Per-street
      const streetKey = parsed.street;
      if (!streetStats[streetKey]) streetStats[streetKey] = { kl: 0, correct: 0, count: 0 };
      streetStats[streetKey].kl += kl;
      streetStats[streetKey].count++;
      if (correct) streetStats[streetKey].correct++;

      // Per-bucket tier
      const tier = bucket < bucketCount / 3 ? 'low' : bucket < (2 * bucketCount) / 3 ? 'mid' : 'high';
      if (!tierStats[tier]) tierStats[tier] = { kl: 0, correct: 0, count: 0 };
      tierStats[tier].kl += kl;
      tierStats[tier].count++;
      if (correct) tierStats[tier].correct++;

      // Track worst
      if (worstInfoSets.length < 20 || kl > worstInfoSets[worstInfoSets.length - 1].kl) {
        worstInfoSets.push({ key: entry.key, cfrProbs: cfrLabel, modelProbs, kl });
        worstInfoSets.sort((a, b) => b.kl - a.kl);
        if (worstInfoSets.length > 20) worstInfoSets.pop();
      }
    }
  }

  // Compile result
  const result: CalibrationResult = {
    overall: {
      klDivergence: totalPredictions > 0 ? totalKL / totalPredictions : 0,
      actionAccuracy: totalPredictions > 0 ? totalCorrect / totalPredictions : 0,
      totalInfoSets: flops.length,
      totalPredictions,
    },
    perStreet: {},
    perBucketTier: {},
    worstInfoSets,
  };

  for (const [key, stats] of Object.entries(streetStats)) {
    result.perStreet[key] = {
      klDivergence: stats.count > 0 ? stats.kl / stats.count : 0,
      actionAccuracy: stats.count > 0 ? stats.correct / stats.count : 0,
      count: stats.count,
    };
  }

  for (const [key, stats] of Object.entries(tierStats)) {
    result.perBucketTier[key] = {
      klDivergence: stats.count > 0 ? stats.kl / stats.count : 0,
      actionAccuracy: stats.count > 0 ? stats.correct / stats.count : 0,
      count: stats.count,
    };
  }

  return result;
}

export function printCalibrationReport(result: CalibrationResult): void {
  console.log('\n╔═══════════════════════════════════════════╗');
  console.log('║   Calibration Report                      ║');
  console.log('╚═══════════════════════════════════════════╝');

  console.log(`\n  Overall:`);
  console.log(`    KL Divergence:   ${result.overall.klDivergence.toFixed(4)}`);
  console.log(`    Action Accuracy: ${(result.overall.actionAccuracy * 100).toFixed(1)}%`);
  console.log(`    Predictions:     ${result.overall.totalPredictions.toLocaleString()}`);

  console.log(`\n  Per Street:`);
  for (const [street, stats] of Object.entries(result.perStreet)) {
    console.log(`    ${street.padEnd(6)} KL=${stats.klDivergence.toFixed(4)}  Acc=${(stats.actionAccuracy * 100).toFixed(1)}%  (${stats.count} samples)`);
  }

  console.log(`\n  Per Bucket Tier:`);
  for (const [tier, stats] of Object.entries(result.perBucketTier)) {
    console.log(`    ${tier.padEnd(6)} KL=${stats.klDivergence.toFixed(4)}  Acc=${(stats.actionAccuracy * 100).toFixed(1)}%  (${stats.count} samples)`);
  }

  if (result.worstInfoSets.length > 0) {
    console.log(`\n  Worst 5 Info Sets (highest KL):`);
    for (const w of result.worstInfoSets.slice(0, 5)) {
      console.log(`    ${w.key}  KL=${w.kl.toFixed(4)}`);
      console.log(`      CFR:   [${w.cfrProbs.map(p => p.toFixed(3)).join(', ')}]`);
      console.log(`      Model: [${w.modelProbs.map(p => p.toFixed(3)).join(', ')}]`);
    }
  }
}
