#!/usr/bin/env tsx
/**
 * Offline trainer for the fast-advice MLP model.
 *
 * Usage:
 *   V1:  npx tsx packages/fast-model/src/trainer.ts [--data <dir>] [--out <path>]
 *   V2:  npx tsx packages/fast-model/src/trainer.ts --v2 [--data <dir>] [--out <path>]
 *   CFR: npx tsx packages/fast-model/src/trainer.ts --v2 --hidden 256,128 --streaming \
 *          --val-by-flop --val-flop-count 100 --data data/training/cfr_srp/ --out models/cfr-v3.json
 *
 * V1: Single-head (48→64→32→3), cross-entropy loss on action labels.
 * V2: Multi-head (54→64→32→[3 action, 5 sizing]), combined loss,
 *     anti-bias sampling, hard example mining, evaluation metrics.
 * Streaming: Chunked training for large datasets (10M+ samples).
 */

import {
  readFileSync,
  writeFileSync,
  appendFileSync,
  readdirSync,
  existsSync,
  mkdirSync,
} from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRandomModel, createRandomModelV2 } from './mlp.js';
import { FEATURE_COUNT, FEATURE_COUNT_V2 } from './feature-encoder.js';
import { evaluateModel, printMetrics } from './evaluate.js';
import type { ModelWeights, TrainingSample, LayerWeights } from './types.js';

// ── Config ──

const HIDDEN_SIZES = [64, 32];
const ACTION_OUTPUT_SIZE = 3; // raise, call, fold
const SIZING_OUTPUT_SIZE = 5; // 33%, 50%, 66%, 100%, all-in
const SIZING_LOSS_WEIGHT = 1.0;
const SIZING_RAISE_THRESHOLD = 0.2; // only train sizing when raise label > this
const LEARNING_RATE_INIT = 0.01;
const LR_DECAY_FACTOR = 0.5;
const LR_DECAY_EVERY = 20;
const BATCH_SIZE = 64;
const MAX_EPOCHS = 100;
const EARLY_STOP_PATIENCE = 10;
const TRAIN_SPLIT = 0.9;
const HARD_EXAMPLE_FRACTION = 0.2;

// ── CLI args ──

interface TrainerArgs {
  dataDirs: string[];
  outPath: string;
  isV2: boolean;
  warmStart: string | null; // path to V1 model for transfer learning
  maxSamples: number | null; // optional cap for staged training
  trainSplit: number; // fraction for train set (default 0.9)
  maxOversampleRatio: number; // V2 anti-bias cap
  hardExampleFraction: number; // V2 hard mining fraction
  disableHardMining: boolean; // V2 hard mining toggle
  initialLr: number; // initial learning rate override
  // ── New: configurable architecture + streaming ──
  hiddenSizes: number[]; // backbone hidden layer sizes (e.g. [256, 128])
  streaming: boolean; // enable chunked streaming training
  chunkSize: number; // samples per streaming chunk
  resume: string | null; // path to model to resume training from
  valByFlop: boolean; // hold out entire flops for validation (not random)
  valFlopCount: number; // number of flops to hold out
  batchSize: number; // batch size override
  maxEpochs: number; // max epochs override
  filesPerPass: number; // max files per pass (0 = all)
  logFile: string | null; // direct file logging (bypasses stdout buffering)
}

/** Direct-write logger that bypasses stdout block buffering */
let _logFile: string | null = null;
function logSync(msg: string): void {
  console.log(msg);
  if (_logFile) {
    appendFileSync(_logFile, msg + '\n');
  }
}

function parseTrainerArgs(): TrainerArgs {
  const __dirname = dirname(fileURLToPath(import.meta.url));
  let dataDirs = [join(__dirname, '..', '..', '..', 'data')];
  let outPath = join(__dirname, '..', 'models', 'model-latest.json');
  let isV2 = false;
  let warmStart: string | null = null;
  let maxSamples: number | null = null;
  let trainSplit = TRAIN_SPLIT;
  let maxOversampleRatio = MAX_OVERSAMPLE_RATIO;
  let hardExampleFraction = HARD_EXAMPLE_FRACTION;
  let disableHardMining = false;
  let initialLr = LEARNING_RATE_INIT;
  let hiddenSizes = HIDDEN_SIZES;
  let streaming = false;
  let chunkSize = 500000;
  let resume: string | null = null;
  let valByFlop = false;
  let valFlopCount = 100;
  let batchSize = BATCH_SIZE;
  let maxEpochs = MAX_EPOCHS;
  let filesPerPass = 0; // 0 = all files
  let logFile: string | null = null;

  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--data' && argv[i + 1]) dataDirs = argv[++i].split(',').map((d) => d.trim());
    if (argv[i] === '--out' && argv[i + 1]) outPath = argv[++i];
    if (argv[i] === '--v2') isV2 = true;
    if (argv[i] === '--warm-start' && argv[i + 1]) warmStart = argv[++i];
    if (argv[i] === '--max-samples' && argv[i + 1]) {
      const parsed = parseInt(argv[++i], 10);
      if (Number.isFinite(parsed) && parsed > 0) maxSamples = parsed;
    }
    if (argv[i] === '--train-split' && argv[i + 1]) {
      const parsed = parseFloat(argv[++i]);
      if (Number.isFinite(parsed) && parsed > 0 && parsed <= 1) trainSplit = parsed;
    }
    if (argv[i] === '--max-oversample-ratio' && argv[i + 1]) {
      const parsed = parseFloat(argv[++i]);
      if (Number.isFinite(parsed) && parsed >= 1) maxOversampleRatio = parsed;
    }
    if (argv[i] === '--hard-example-fraction' && argv[i + 1]) {
      const parsed = parseFloat(argv[++i]);
      if (Number.isFinite(parsed) && parsed >= 0 && parsed <= 1) hardExampleFraction = parsed;
    }
    if (argv[i] === '--disable-hard-mining') {
      disableHardMining = true;
    }
    if (argv[i] === '--lr' && argv[i + 1]) {
      const parsed = parseFloat(argv[++i]);
      if (Number.isFinite(parsed) && parsed > 0) initialLr = parsed;
    }
    if (argv[i] === '--hidden' && argv[i + 1]) {
      hiddenSizes = argv[++i]
        .split(',')
        .map((s) => parseInt(s.trim(), 10))
        .filter((n) => n > 0);
    }
    if (argv[i] === '--streaming') streaming = true;
    if (argv[i] === '--chunk-size' && argv[i + 1]) {
      const parsed = parseInt(argv[++i], 10);
      if (Number.isFinite(parsed) && parsed > 0) chunkSize = parsed;
    }
    if (argv[i] === '--resume' && argv[i + 1]) resume = argv[++i];
    if (argv[i] === '--val-by-flop') valByFlop = true;
    if (argv[i] === '--val-flop-count' && argv[i + 1]) {
      const parsed = parseInt(argv[++i], 10);
      if (Number.isFinite(parsed) && parsed > 0) valFlopCount = parsed;
    }
    if (argv[i] === '--batch-size' && argv[i + 1]) {
      const parsed = parseInt(argv[++i], 10);
      if (Number.isFinite(parsed) && parsed > 0) batchSize = parsed;
    }
    if (argv[i] === '--max-epochs' && argv[i + 1]) {
      const parsed = parseInt(argv[++i], 10);
      if (Number.isFinite(parsed) && parsed > 0) maxEpochs = parsed;
    }
    if (argv[i] === '--files-per-pass' && argv[i + 1]) {
      const parsed = parseInt(argv[++i], 10);
      if (Number.isFinite(parsed) && parsed > 0) filesPerPass = parsed;
    }
    if (argv[i] === '--log' && argv[i + 1]) logFile = argv[++i];
  }

  return {
    dataDirs,
    outPath,
    isV2,
    warmStart,
    maxSamples,
    trainSplit,
    maxOversampleRatio,
    hardExampleFraction,
    disableHardMining,
    initialLr,
    hiddenSizes,
    streaming,
    chunkSize,
    resume,
    valByFlop,
    valFlopCount,
    batchSize,
    maxEpochs,
    filesPerPass,
    logFile,
  };
}

// ── Data loading ──

function collectFiles(dataDirs: string | string[]): string[] {
  const dirs = Array.isArray(dataDirs) ? dataDirs : [dataDirs];
  const files: string[] = [];
  for (const dir of dirs) {
    if (!existsSync(dir)) {
      console.error(`Data directory not found: ${dir}`);
      process.exit(1);
    }
    for (const f of readdirSync(dir).filter((f) => f.endsWith('.jsonl'))) {
      files.push(join(dir, f)); // full path
    }
  }
  return files.sort();
}

function loadSamples(
  dataDirs: string | string[],
  expectedFeatureCount: number,
  maxSamples: number | null = null,
  fileFilter?: string[],
): TrainingSample[] {
  const files = fileFilter ?? collectFiles(dataDirs);
  if (files.length === 0) {
    console.error(`No .jsonl files found`);
    process.exit(1);
  }

  const samples: TrainingSample[] = [];
  for (const file of files) {
    const filepath =
      file.includes('/') || file.includes('\\')
        ? file
        : join(Array.isArray(dataDirs) ? dataDirs[0] : dataDirs, file);
    if (!existsSync(filepath)) continue;
    const lines = readFileSync(filepath, 'utf-8').split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const sample = JSON.parse(trimmed) as TrainingSample;
        if (
          sample.f &&
          sample.l &&
          sample.f.length === expectedFeatureCount &&
          sample.l.length === 3
        ) {
          samples.push(sample);
          if (maxSamples != null && samples.length >= maxSamples) {
            return samples;
          }
        }
      } catch {
        // skip malformed lines
      }
    }
  }

  return samples;
}

// ── Shuffle (Fisher-Yates) ──

function shuffle<T>(arr: T[]): void {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
}

// ── Anti-bias sampling (V2) ──

function argmax(arr: number[]): number {
  let maxIdx = 0;
  for (let i = 1; i < arr.length; i++) {
    if (arr[i] > arr[maxIdx]) maxIdx = i;
  }
  return maxIdx;
}

const MAX_OVERSAMPLE_RATIO = 3; // cap at 3x original dataset size

function balanceSamples(
  samples: TrainingSample[],
  maxOversampleRatio: number = MAX_OVERSAMPLE_RATIO,
): TrainingSample[] {
  // Step 1: Group by street
  const byStreet = new Map<string, TrainingSample[]>();
  for (const s of samples) {
    const street = s.s || 'UNKNOWN';
    if (!byStreet.has(street)) byStreet.set(street, []);
    byStreet.get(street)!.push(s);
  }

  // Cap target to avoid massive oversampling (e.g. 6K PREFLOP vs 100 RIVER)
  const maxStreetCount = Math.max(...[...byStreet.values()].map((g) => g.length));
  const medianCount = [...byStreet.values()].map((g) => g.length).sort((a, b) => a - b)[
    Math.floor(byStreet.size / 2)
  ];
  const streetTarget = Math.min(maxStreetCount, medianCount * 4);

  // Step 2: Oversample minority streets to capped target
  const streetBalanced: TrainingSample[] = [];
  for (const [, group] of byStreet) {
    const target = Math.min(streetTarget, group.length * 10); // never oversample a single street more than 10x
    for (const sample of group) streetBalanced.push(sample);
    let needed = target - group.length;
    while (needed > 0) {
      streetBalanced.push(group[Math.floor(Math.random() * group.length)]);
      needed--;
    }
  }

  // Step 3: Within each street, balance by dominant action
  const byStreetAction = new Map<string, TrainingSample[]>();
  for (const s of streetBalanced) {
    const street = s.s || 'UNKNOWN';
    const action = argmax(s.l);
    const key = `${street}:${action}`;
    if (!byStreetAction.has(key)) byStreetAction.set(key, []);
    byStreetAction.get(key)!.push(s);
  }

  const streetActionCounts = new Map<string, number>();
  for (const [key, group] of byStreetAction) {
    const street = key.split(':')[0];
    const current = streetActionCounts.get(street) ?? 0;
    streetActionCounts.set(street, Math.max(current, group.length));
  }

  const balanced: TrainingSample[] = [];
  for (const [key, group] of byStreetAction) {
    const street = key.split(':')[0];
    const target = streetActionCounts.get(street) ?? group.length;
    for (const sample of group) balanced.push(sample);
    let needed = target - group.length;
    while (needed > 0) {
      balanced.push(group[Math.floor(Math.random() * group.length)]);
      needed--;
    }
  }

  // Final safety cap: don't exceed MAX_OVERSAMPLE_RATIO × original size
  const maxTotal = Math.floor(samples.length * maxOversampleRatio);
  if (balanced.length > maxTotal) {
    shuffle(balanced);
    return balanced.slice(0, maxTotal);
  }

  return balanced;
}

// ══════════════════════════════════════════════
//   V1 TRAINING (unchanged from original)
// ══════════════════════════════════════════════

interface ForwardCache {
  inputs: number[][];
  outputs: number[][];
  probs: number[];
}

function forwardWithCache(model: ModelWeights, features: number[]): ForwardCache {
  const inputs: number[][] = [];
  const outputs: number[][] = [];
  let current = features;

  for (let l = 0; l < model.layers.length; l++) {
    const layer = model.layers[l];
    const isOutput = l === model.layers.length - 1;
    const outDim = layer.weights.length;
    const preAct = new Array<number>(outDim);

    for (let j = 0; j < outDim; j++) {
      let sum = layer.biases[j];
      const w = layer.weights[j];
      for (let i = 0; i < current.length; i++) {
        sum += current[i] * w[i];
      }
      preAct[j] = sum;
    }

    inputs.push(current);

    if (isOutput) {
      const maxVal = Math.max(...preAct);
      const exps = preAct.map((v) => Math.exp(v - maxVal));
      const sum = exps.reduce((a, b) => a + b, 0);
      const probs = exps.map((e) => e / sum);
      outputs.push(probs);
      return { inputs, outputs, probs };
    } else {
      const activated = preAct.map((v) => (v > 0 ? v : 0));
      outputs.push(activated);
      current = activated;
    }
  }

  return { inputs, outputs, probs: outputs[outputs.length - 1] };
}

function crossEntropyLoss(probs: number[], target: number[]): number {
  let loss = 0;
  for (let i = 0; i < target.length; i++) {
    loss -= target[i] * Math.log(Math.max(probs[i], 1e-10));
  }
  return loss;
}

interface Gradients {
  layers: LayerWeights[];
}

function backprop(model: ModelWeights, cache: ForwardCache, target: number[]): Gradients {
  const { layers } = model;
  const numLayers = layers.length;
  const grads: LayerWeights[] = layers.map((l) => ({
    weights: l.weights.map((row) => new Array<number>(row.length).fill(0)),
    biases: new Array<number>(l.biases.length).fill(0),
  }));

  let delta = cache.probs.map((p, i) => p - target[i]);

  for (let l = numLayers - 1; l >= 0; l--) {
    const input = cache.inputs[l];
    const layer = layers[l];
    const outDim = layer.weights.length;
    const inDim = input.length;

    for (let j = 0; j < outDim; j++) {
      grads[l].biases[j] = delta[j];
      for (let i = 0; i < inDim; i++) {
        grads[l].weights[j][i] = delta[j] * input[i];
      }
    }

    if (l > 0) {
      const prevDelta = new Array<number>(inDim).fill(0);
      for (let i = 0; i < inDim; i++) {
        let sum = 0;
        for (let j = 0; j < outDim; j++) {
          sum += delta[j] * layer.weights[j][i];
        }
        prevDelta[i] = cache.outputs[l - 1][i] > 0 ? sum : 0;
      }
      delta = prevDelta;
    }
  }

  return { layers: grads };
}

function sgdUpdate(model: ModelWeights, grads: Gradients, lr: number, batchSize: number): void {
  const scale = lr / batchSize;
  for (let l = 0; l < model.layers.length; l++) {
    const layer = model.layers[l];
    const grad = grads.layers[l];
    for (let j = 0; j < layer.weights.length; j++) {
      layer.biases[j] -= scale * grad.biases[j];
      for (let i = 0; i < layer.weights[j].length; i++) {
        layer.weights[j][i] -= scale * grad.weights[j][i];
      }
    }
  }
}

function accumulateGrads(acc: Gradients, grads: Gradients): void {
  for (let l = 0; l < acc.layers.length; l++) {
    for (let j = 0; j < acc.layers[l].biases.length; j++) {
      acc.layers[l].biases[j] += grads.layers[l].biases[j];
      for (let i = 0; i < acc.layers[l].weights[j].length; i++) {
        acc.layers[l].weights[j][i] += grads.layers[l].weights[j][i];
      }
    }
  }
}

function zeroGrads(model: ModelWeights): Gradients {
  return {
    layers: model.layers.map((l) => ({
      weights: l.weights.map((row) => new Array<number>(row.length).fill(0)),
      biases: new Array<number>(l.biases.length).fill(0),
    })),
  };
}

function evaluateV1(model: ModelWeights, samples: TrainingSample[]): number {
  let totalLoss = 0;
  for (const sample of samples) {
    const cache = forwardWithCache(model, sample.f);
    totalLoss += crossEntropyLoss(cache.probs, sample.l);
  }
  return totalLoss / samples.length;
}

function cloneLayer(l: LayerWeights): LayerWeights {
  return {
    weights: l.weights.map((row) => row.slice()),
    biases: l.biases.slice(),
  };
}

function cloneWeights(model: ModelWeights): ModelWeights {
  const clone: ModelWeights = {
    layers: model.layers.map(cloneLayer),
    inputSize: model.inputSize,
    trainedAt: model.trainedAt,
    trainingSamples: model.trainingSamples,
    valLoss: model.valLoss,
    version: model.version,
  };
  if (model.actionHead) clone.actionHead = cloneLayer(model.actionHead);
  if (model.sizingHead) clone.sizingHead = cloneLayer(model.sizingHead);
  return clone;
}

function trainV1(trainSet: TrainingSample[], valSet: TrainingSample[]): ModelWeights {
  console.log(
    `Initializing V1 MLP: input=${FEATURE_COUNT} → [${HIDDEN_SIZES.join(', ')}] → ${ACTION_OUTPUT_SIZE}`,
  );

  const model = createRandomModel(FEATURE_COUNT, HIDDEN_SIZES, ACTION_OUTPUT_SIZE);
  let bestModel = cloneWeights(model);
  let bestValLoss = Infinity;
  let patience = 0;
  let lr = LEARNING_RATE_INIT;

  for (let epoch = 1; epoch <= MAX_EPOCHS; epoch++) {
    if (epoch > 1 && (epoch - 1) % LR_DECAY_EVERY === 0) {
      lr *= LR_DECAY_FACTOR;
      console.log(`  LR decay → ${lr.toExponential(2)}`);
    }

    shuffle(trainSet);

    let epochLoss = 0;
    for (let start = 0; start < trainSet.length; start += BATCH_SIZE) {
      const end = Math.min(start + BATCH_SIZE, trainSet.length);
      const batchSize = end - start;
      const accGrads = zeroGrads(model);

      for (let b = start; b < end; b++) {
        const sample = trainSet[b];
        const cache = forwardWithCache(model, sample.f);
        epochLoss += crossEntropyLoss(cache.probs, sample.l);
        const grads = backprop(model, cache, sample.l);
        accumulateGrads(accGrads, grads);
      }

      sgdUpdate(model, accGrads, lr, batchSize);
    }

    const trainLoss = epochLoss / trainSet.length;
    const valLoss = valSet.length > 0 ? evaluateV1(model, valSet) : trainLoss;

    const indicator = valLoss < bestValLoss ? ' *' : '';
    console.log(
      `Epoch ${String(epoch).padStart(3)}/${MAX_EPOCHS}  ` +
        `train_loss=${trainLoss.toFixed(4)}  val_loss=${valLoss.toFixed(4)}  ` +
        `lr=${lr.toExponential(2)}${indicator}`,
    );

    if (valLoss < bestValLoss) {
      bestValLoss = valLoss;
      bestModel = cloneWeights(model);
      bestModel.valLoss = valLoss;
      patience = 0;
    } else {
      patience++;
      if (patience >= EARLY_STOP_PATIENCE) {
        console.log(`\nEarly stopping at epoch ${epoch} (patience=${EARLY_STOP_PATIENCE})`);
        break;
      }
    }
  }

  bestModel.trainedAt = new Date().toISOString();
  bestModel.trainingSamples = trainSet.length;
  bestModel.version = 'v1';
  return bestModel;
}

// ══════════════════════════════════════════════
//   V1→V2 WARM-START (TRANSFER LEARNING)
// ══════════════════════════════════════════════

/**
 * Create a V2 model by transferring weights from a trained V1 model.
 *
 * V1 layout: layers[0] (48→64), layers[1] (64→32), layers[2] (32→3)
 * V2 layout: layers[0] (54→64), layers[1] (64→32), actionHead (32→3), sizingHead (32→5)
 *
 * Transfer strategy:
 *   - layers[0]: copy V1 weights, pad 6 new feature columns with zeros
 *   - layers[1]: copy directly (64→32 is identical)
 *   - actionHead: copy from V1 layers[2] (32→3 is identical)
 *   - sizingHead: Xavier-initialize (new capability)
 */
function warmStartV2FromV1(v1Path: string): ModelWeights {
  const raw = readFileSync(v1Path, 'utf-8');
  const v1: ModelWeights = JSON.parse(raw);

  if (!v1.layers || v1.layers.length < 3) {
    throw new Error(`Invalid V1 model: expected 3 layers, got ${v1.layers?.length}`);
  }

  const v1Layer0 = v1.layers[0]; // 48→64
  const v1Layer1 = v1.layers[1]; // 64→32
  const v1Layer2 = v1.layers[2]; // 32→3

  // Pad layers[0] weights: each row gets 6 extra zeros for new V2 features
  const paddedWeights0 = v1Layer0.weights.map((row) => {
    const padded = [...row];
    for (let i = 0; i < FEATURE_COUNT_V2 - FEATURE_COUNT; i++) {
      padded.push(0);
    }
    return padded;
  });

  // Xavier-initialize sizingHead (32→5)
  const sizingScale = Math.sqrt(2 / (HIDDEN_SIZES[HIDDEN_SIZES.length - 1] + SIZING_OUTPUT_SIZE));
  const sizingWeights: number[][] = [];
  for (let j = 0; j < SIZING_OUTPUT_SIZE; j++) {
    const row: number[] = [];
    for (let i = 0; i < HIDDEN_SIZES[HIDDEN_SIZES.length - 1]; i++) {
      const u1 = Math.random() || 1e-10;
      const u2 = Math.random();
      row.push(Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2) * sizingScale);
    }
    sizingWeights.push(row);
  }

  console.log('  Warm-start transfer:');
  console.log(`    layers[0]: ${FEATURE_COUNT}→64 padded to ${FEATURE_COUNT_V2}→64`);
  console.log(`    layers[1]: 64→32 copied directly`);
  console.log(`    actionHead: 32→3 copied from V1 output layer`);
  console.log(`    sizingHead: 32→5 Xavier-initialized (new)`);

  return {
    layers: [
      { weights: paddedWeights0, biases: [...v1Layer0.biases] },
      { weights: v1Layer1.weights.map((r) => [...r]), biases: [...v1Layer1.biases] },
    ],
    actionHead: {
      weights: v1Layer2.weights.map((r) => [...r]),
      biases: [...v1Layer2.biases],
    },
    sizingHead: {
      weights: sizingWeights,
      biases: new Array<number>(SIZING_OUTPUT_SIZE).fill(0),
    },
    inputSize: FEATURE_COUNT_V2,
    version: 'v2',
    trainedAt: new Date().toISOString(),
    trainingSamples: 0,
    valLoss: Infinity,
  };
}

// ══════════════════════════════════════════════
//   V2 MULTI-HEAD TRAINING (optimized: pre-allocated buffers, Float64Array)
// ══════════════════════════════════════════════

/**
 * Pre-allocated scratch buffers for V2 forward/backward passes.
 * Avoids creating thousands of temporary arrays per epoch.
 */
interface V2Buffers {
  // Forward cache
  backboneInputs: Float64Array[]; // one per backbone layer
  backboneOutputs: Float64Array[]; // one per backbone layer
  actionPreAct: Float64Array;
  actionProbs: Float64Array;
  sizingPreAct: Float64Array;
  sizingProbs: Float64Array;
  // Backward scratch
  actionDelta: Float64Array;
  sizingDelta: Float64Array;
  backboneDeltaAction: Float64Array;
  backboneDeltaSizing: Float64Array;
  delta: Float64Array;
  prevDelta: Float64Array; // for largest input dim
}

interface GradientsV2Flat {
  /** Flat Float64Arrays for each backbone layer's weights and biases */
  layerWeights: Float64Array[]; // [outDim * inDim] per layer
  layerBiases: Float64Array[]; // [outDim] per layer
  layerInDims: number[]; // input dim per layer
  actionWeights: Float64Array; // [ACTION_OUTPUT_SIZE * backboneDim]
  actionBiases: Float64Array;
  sizingWeights: Float64Array; // [SIZING_OUTPUT_SIZE * backboneDim]
  sizingBiases: Float64Array;
  backboneDim: number;
}

function createV2Buffers(model: ModelWeights): V2Buffers {
  const backboneInputs: Float64Array[] = [];
  const backboneOutputs: Float64Array[] = [];

  // Determine dimensions from model
  let inDim = model.layers[0].weights[0].length; // input feature count
  let maxInDim = inDim;
  for (const layer of model.layers) {
    backboneInputs.push(new Float64Array(inDim));
    const outDim = layer.weights.length;
    backboneOutputs.push(new Float64Array(outDim));
    inDim = outDim;
    if (inDim > maxInDim) maxInDim = inDim;
  }

  const backboneDim = model.layers[model.layers.length - 1].weights.length;
  const actionDim = model.actionHead!.weights.length;
  const sizingDim = model.sizingHead!.weights.length;

  return {
    backboneInputs,
    backboneOutputs,
    actionPreAct: new Float64Array(actionDim),
    actionProbs: new Float64Array(actionDim),
    sizingPreAct: new Float64Array(sizingDim),
    sizingProbs: new Float64Array(sizingDim),
    actionDelta: new Float64Array(actionDim),
    sizingDelta: new Float64Array(sizingDim),
    backboneDeltaAction: new Float64Array(backboneDim),
    backboneDeltaSizing: new Float64Array(backboneDim),
    delta: new Float64Array(Math.max(backboneDim, maxInDim)),
    prevDelta: new Float64Array(Math.max(backboneDim, maxInDim)),
  };
}

function createGradsV2Flat(model: ModelWeights): GradientsV2Flat {
  const layerWeights: Float64Array[] = [];
  const layerBiases: Float64Array[] = [];
  const layerInDims: number[] = [];

  for (const layer of model.layers) {
    const outDim = layer.weights.length;
    const inDim = layer.weights[0].length;
    layerWeights.push(new Float64Array(outDim * inDim));
    layerBiases.push(new Float64Array(outDim));
    layerInDims.push(inDim);
  }

  const backboneDim = model.layers[model.layers.length - 1].weights.length;
  const actionDim = model.actionHead!.weights.length;
  const sizingDim = model.sizingHead!.weights.length;

  return {
    layerWeights,
    layerBiases,
    layerInDims,
    actionWeights: new Float64Array(actionDim * backboneDim),
    actionBiases: new Float64Array(actionDim),
    sizingWeights: new Float64Array(sizingDim * backboneDim),
    sizingBiases: new Float64Array(sizingDim),
    backboneDim,
  };
}

function zeroGradsV2Flat(grads: GradientsV2Flat): void {
  for (let l = 0; l < grads.layerWeights.length; l++) {
    grads.layerWeights[l].fill(0);
    grads.layerBiases[l].fill(0);
  }
  grads.actionWeights.fill(0);
  grads.actionBiases.fill(0);
  grads.sizingWeights.fill(0);
  grads.sizingBiases.fill(0);
}

function softmaxInto(preAct: Float64Array, out: Float64Array, len: number): void {
  let maxVal = preAct[0];
  for (let i = 1; i < len; i++) if (preAct[i] > maxVal) maxVal = preAct[i];
  let sum = 0;
  for (let i = 0; i < len; i++) {
    out[i] = Math.exp(preAct[i] - maxVal);
    sum += out[i];
  }
  for (let i = 0; i < len; i++) out[i] /= sum;
}

function forwardV2Into(model: ModelWeights, features: number[], buf: V2Buffers): void {
  // Copy input features into first backbone input
  const firstInput = buf.backboneInputs[0];
  for (let i = 0; i < features.length; i++) firstInput[i] = features[i];

  // Backbone forward (all layers use ReLU)
  for (let l = 0; l < model.layers.length; l++) {
    const layer = model.layers[l];
    const input = buf.backboneInputs[l];
    const output = buf.backboneOutputs[l];
    const outDim = layer.weights.length;
    const inDim = layer.weights[0].length;

    for (let j = 0; j < outDim; j++) {
      let sum = layer.biases[j];
      const w = layer.weights[j];
      for (let i = 0; i < inDim; i++) sum += input[i] * w[i];
      output[j] = sum > 0 ? sum : 0; // ReLU
    }

    // Feed output as next layer's input
    if (l < model.layers.length - 1) {
      const nextInput = buf.backboneInputs[l + 1];
      for (let i = 0; i < outDim; i++) nextInput[i] = output[i];
    }
  }

  // Backbone output = last backbone layer output
  const backbone = buf.backboneOutputs[model.layers.length - 1];
  const backboneDim = model.layers[model.layers.length - 1].weights.length;

  // Action head forward
  const actionHead = model.actionHead!;
  const actionDim = actionHead.weights.length;
  for (let j = 0; j < actionDim; j++) {
    let sum = actionHead.biases[j];
    const w = actionHead.weights[j];
    for (let i = 0; i < backboneDim; i++) sum += backbone[i] * w[i];
    buf.actionPreAct[j] = sum;
  }
  softmaxInto(buf.actionPreAct, buf.actionProbs, actionDim);

  // Sizing head forward
  const sizingHead = model.sizingHead!;
  const sizingDim = sizingHead.weights.length;
  for (let j = 0; j < sizingDim; j++) {
    let sum = sizingHead.biases[j];
    const w = sizingHead.weights[j];
    for (let i = 0; i < backboneDim; i++) sum += backbone[i] * w[i];
    buf.sizingPreAct[j] = sum;
  }
  softmaxInto(buf.sizingPreAct, buf.sizingProbs, sizingDim);
}

function backpropV2Into(
  model: ModelWeights,
  buf: V2Buffers,
  grads: GradientsV2Flat,
  actionTarget: number[],
  sizingTarget: number[] | null,
  sizingWeight: number,
): void {
  const backboneDim = grads.backboneDim;
  const backbone = buf.backboneOutputs[model.layers.length - 1];

  // ── Action head gradients ──
  const actionHead = model.actionHead!;
  const actionDim = actionHead.weights.length;
  for (let j = 0; j < actionDim; j++) {
    const d = buf.actionProbs[j] - actionTarget[j];
    buf.actionDelta[j] = d;
    grads.actionBiases[j] += d;
    const off = j * backboneDim;
    for (let i = 0; i < backboneDim; i++) {
      grads.actionWeights[off + i] += d * backbone[i];
    }
  }

  // Backbone delta from action head
  const bda = buf.backboneDeltaAction;
  for (let i = 0; i < backboneDim; i++) {
    let sum = 0;
    for (let j = 0; j < actionDim; j++) {
      sum += buf.actionDelta[j] * actionHead.weights[j][i];
    }
    bda[i] = sum;
  }

  // ── Sizing head gradients ──
  const bds = buf.backboneDeltaSizing;
  if (sizingTarget && sizingWeight > 0) {
    const sizingHead = model.sizingHead!;
    const sizingDim = sizingHead.weights.length;
    for (let j = 0; j < sizingDim; j++) {
      const d = (buf.sizingProbs[j] - sizingTarget[j]) * sizingWeight;
      buf.sizingDelta[j] = d;
      grads.sizingBiases[j] += d;
      const off = j * backboneDim;
      for (let i = 0; i < backboneDim; i++) {
        grads.sizingWeights[off + i] += d * backbone[i];
      }
    }

    for (let i = 0; i < backboneDim; i++) {
      let sum = 0;
      for (let j = 0; j < sizingDim; j++) {
        sum += buf.sizingDelta[j] * sizingHead.weights[j][i];
      }
      bds[i] = sum;
    }
  } else {
    bds.fill(0);
  }

  // ── Combined backbone delta ──
  const delta = buf.delta;
  const lastIdx = model.layers.length - 1;
  const lastOutput = buf.backboneOutputs[lastIdx];
  for (let i = 0; i < backboneDim; i++) {
    delta[i] = (bda[i] + bds[i]) * (lastOutput[i] > 0 ? 1 : 0);
  }

  // ── Backprop through backbone layers ──
  for (let l = model.layers.length - 1; l >= 0; l--) {
    const input = buf.backboneInputs[l];
    const layer = model.layers[l];
    const outDim = layer.weights.length;
    const inDim = grads.layerInDims[l];

    for (let j = 0; j < outDim; j++) {
      grads.layerBiases[l][j] += delta[j];
      const off = j * inDim;
      for (let i = 0; i < inDim; i++) {
        grads.layerWeights[l][off + i] += delta[j] * input[i];
      }
    }

    if (l > 0) {
      const prevDelta = buf.prevDelta;
      const prevOutput = buf.backboneOutputs[l - 1];
      for (let i = 0; i < inDim; i++) {
        let sum = 0;
        for (let j = 0; j < outDim; j++) {
          sum += delta[j] * layer.weights[j][i];
        }
        prevDelta[i] = prevOutput[i] > 0 ? sum : 0;
      }
      // Swap delta ↔ prevDelta
      for (let i = 0; i < inDim; i++) {
        delta[i] = prevDelta[i];
      }
    }
  }
}

function sgdUpdateV2Flat(
  model: ModelWeights,
  grads: GradientsV2Flat,
  lr: number,
  batchSize: number,
): void {
  const scale = lr / batchSize;

  // Backbone
  for (let l = 0; l < model.layers.length; l++) {
    const layer = model.layers[l];
    const inDim = grads.layerInDims[l];
    const outDim = layer.weights.length;
    for (let j = 0; j < outDim; j++) {
      layer.biases[j] -= scale * grads.layerBiases[l][j];
      const off = j * inDim;
      const w = layer.weights[j];
      for (let i = 0; i < inDim; i++) {
        w[i] -= scale * grads.layerWeights[l][off + i];
      }
    }
  }

  // Action head
  const ah = model.actionHead!;
  const backboneDim = grads.backboneDim;
  for (let j = 0; j < ah.weights.length; j++) {
    ah.biases[j] -= scale * grads.actionBiases[j];
    const off = j * backboneDim;
    const w = ah.weights[j];
    for (let i = 0; i < backboneDim; i++) {
      w[i] -= scale * grads.actionWeights[off + i];
    }
  }

  // Sizing head
  const sh = model.sizingHead!;
  for (let j = 0; j < sh.weights.length; j++) {
    sh.biases[j] -= scale * grads.sizingBiases[j];
    const off = j * backboneDim;
    const w = sh.weights[j];
    for (let i = 0; i < backboneDim; i++) {
      w[i] -= scale * grads.sizingWeights[off + i];
    }
  }
}

function evaluateV2Loss(model: ModelWeights, samples: TrainingSample[]): number {
  const buf = createV2Buffers(model);
  let totalLoss = 0;
  for (const sample of samples) {
    forwardV2Into(model, sample.f, buf);
    let loss = 0;
    for (let i = 0; i < sample.l.length; i++) {
      loss -= sample.l[i] * Math.log(Math.max(buf.actionProbs[i], 1e-10));
    }
    if (sample.sz && sample.l[0] > SIZING_RAISE_THRESHOLD) {
      for (let i = 0; i < sample.sz.length; i++) {
        loss +=
          SIZING_LOSS_WEIGHT * (-sample.sz[i] * Math.log(Math.max(buf.sizingProbs[i], 1e-10)));
      }
    }
    totalLoss += loss;
  }
  return totalLoss / samples.length;
}

interface V2TrainOptions {
  hardExampleFraction: number;
  disableHardMining: boolean;
  initialLr: number;
  batchSize?: number;
  maxEpochs?: number;
  hiddenSizes?: number[];
}

function trainV2(
  trainSet: TrainingSample[],
  valSet: TrainingSample[],
  warmStartModel?: ModelWeights,
  options?: V2TrainOptions,
): ModelWeights {
  const batchSize = options?.batchSize ?? BATCH_SIZE;
  const maxEpochs = options?.maxEpochs ?? MAX_EPOCHS;
  const hs = options?.hiddenSizes ?? HIDDEN_SIZES;
  const model = warmStartModel
    ? warmStartModel
    : createRandomModelV2(FEATURE_COUNT_V2, hs, ACTION_OUTPUT_SIZE, SIZING_OUTPUT_SIZE);

  logSync(
    `Initializing V2 MLP: input=${FEATURE_COUNT_V2} → [${hs.join(', ')}] → action(${ACTION_OUTPUT_SIZE}) + sizing(${SIZING_OUTPUT_SIZE})${warmStartModel ? ' [warm-started]' : ''}`,
  );
  logSync(
    `  Train: ${trainSet.length.toLocaleString()}, Val: ${valSet.length.toLocaleString()}, Batch: ${batchSize}, MaxEpochs: ${maxEpochs}`,
  );

  // Pre-allocate all scratch buffers once
  const buf = createV2Buffers(model);
  const accGrads = createGradsV2Flat(model);

  let bestModel = cloneWeights(model);
  let bestValLoss = Infinity;
  let patience = 0;
  let lr = options?.initialLr ?? LEARNING_RATE_INIT;
  let workingTrainSet = [...trainSet];
  const hardExampleFraction = options?.hardExampleFraction ?? HARD_EXAMPLE_FRACTION;
  const enableHardMining = !options?.disableHardMining && hardExampleFraction > 0;

  for (let epoch = 1; epoch <= maxEpochs; epoch++) {
    if (epoch > 1 && (epoch - 1) % LR_DECAY_EVERY === 0) {
      lr *= LR_DECAY_FACTOR;
      console.log(`  LR decay → ${lr.toExponential(2)}`);
    }

    // Hard example mining after epoch 1 (reuses pre-allocated buffers)
    if (epoch === 2 && enableHardMining) {
      console.log('  Hard example mining: identifying difficult samples...');
      const losses = trainSet.map((s) => {
        forwardV2Into(model, s.f, buf);
        let loss = 0;
        for (let i = 0; i < s.l.length; i++) {
          loss -= s.l[i] * Math.log(Math.max(buf.actionProbs[i], 1e-10));
        }
        return { sample: s, loss };
      });
      losses.sort((a, b) => b.loss - a.loss);
      const hardCount = Math.floor(losses.length * hardExampleFraction);
      const hardExamples = losses.slice(0, hardCount).map((x) => x.sample);
      workingTrainSet = [...trainSet, ...hardExamples];
      console.log(`  Added ${hardCount} hard examples (${workingTrainSet.length} total)`);
    }

    shuffle(workingTrainSet);

    const epochStart = Date.now();
    let epochLoss = 0;
    const totalBatches = Math.ceil(workingTrainSet.length / batchSize);
    const logEvery = Math.max(1, Math.floor(totalBatches / 10)); // log 10 times per epoch

    for (let start = 0; start < workingTrainSet.length; start += batchSize) {
      const end = Math.min(start + batchSize, workingTrainSet.length);
      const bs = end - start;
      zeroGradsV2Flat(accGrads);

      for (let b = start; b < end; b++) {
        const sample = workingTrainSet[b];
        forwardV2Into(model, sample.f, buf);

        // Action loss (inline for speed)
        let loss = 0;
        for (let i = 0; i < sample.l.length; i++) {
          loss -= sample.l[i] * Math.log(Math.max(buf.actionProbs[i], 1e-10));
        }

        // Sizing target: only when raise label is significant
        const hasSizing = sample.sz && sample.l[0] > SIZING_RAISE_THRESHOLD;
        if (hasSizing) {
          for (let i = 0; i < sample.sz!.length; i++) {
            loss +=
              SIZING_LOSS_WEIGHT * (-sample.sz![i] * Math.log(Math.max(buf.sizingProbs[i], 1e-10)));
          }
        }
        epochLoss += loss;

        backpropV2Into(
          model,
          buf,
          accGrads,
          sample.l,
          hasSizing ? sample.sz! : null,
          SIZING_LOSS_WEIGHT,
        );
      }

      sgdUpdateV2Flat(model, accGrads, lr, bs);

      // Progress logging within epoch
      const batchIdx = Math.floor(start / batchSize);
      if (batchIdx > 0 && batchIdx % logEvery === 0) {
        const pct = ((start / workingTrainSet.length) * 100).toFixed(0);
        const elapsed = ((Date.now() - epochStart) / 1000).toFixed(0);
        logSync(`  Epoch ${epoch}: ${pct}% (${elapsed}s)`);
      }
    }

    const epochSec = ((Date.now() - epochStart) / 1000).toFixed(1);
    const trainLoss = epochLoss / workingTrainSet.length;
    const valLoss = valSet.length > 0 ? evaluateV2Loss(model, valSet) : trainLoss;

    const indicator = valLoss < bestValLoss ? ' *' : '';
    logSync(
      `Epoch ${String(epoch).padStart(3)}/${maxEpochs}  ` +
        `train_loss=${trainLoss.toFixed(4)}  val_loss=${valLoss.toFixed(4)}  ` +
        `lr=${lr.toExponential(2)}  ${epochSec}s${indicator}`,
    );

    if (valLoss < bestValLoss) {
      bestValLoss = valLoss;
      bestModel = cloneWeights(model);
      bestModel.valLoss = valLoss;
      patience = 0;
    } else {
      patience++;
      if (patience >= EARLY_STOP_PATIENCE) {
        console.log(`\nEarly stopping at epoch ${epoch} (patience=${EARLY_STOP_PATIENCE})`);
        break;
      }
    }
  }

  bestModel.trainedAt = new Date().toISOString();
  bestModel.trainingSamples = trainSet.length;
  bestModel.version = 'v2';
  return bestModel;
}

function loadModelFromPath(modelPath: string): ModelWeights {
  if (!existsSync(modelPath)) {
    throw new Error(`Model file not found: ${modelPath}`);
  }
  return JSON.parse(readFileSync(modelPath, 'utf-8')) as ModelWeights;
}

// ══════════════════════════════════════════════
//   STREAMING TRAINING (for large CFR datasets)
// ══════════════════════════════════════════════

/**
 * Split data files by flop (using filename pattern flop_XXXX.jsonl) into
 * train and validation sets. Holds out entire flops, not random samples.
 */
function splitByFlop(
  dataDirs: string | string[],
  featureCount: number,
  valFlopCount: number,
): { trainFiles: string[]; valFiles: string[]; valSet: TrainingSample[] } {
  // Collect all files as full paths from all directories
  const allFiles = collectFiles(dataDirs);

  // Separate flop files from other JSONL files
  const flopFiles: string[] = [];
  const otherFiles: string[] = [];
  for (const f of allFiles) {
    if (/flop_\d+(?:\.training)?\.jsonl$/.test(f)) {
      flopFiles.push(f);
    } else {
      otherFiles.push(f);
    }
  }

  // If no flop files found, fall back to treating all files as training
  if (flopFiles.length === 0) {
    return { trainFiles: allFiles, valFiles: [], valSet: [] };
  }

  // Hold out the last N flop files as validation (sorted by boardId)
  const actualValCount = Math.min(valFlopCount, Math.floor(flopFiles.length * 0.1));
  // Select evenly spaced flops for validation (diversity)
  const step = Math.max(1, Math.floor(flopFiles.length / Math.max(1, actualValCount)));
  const valIndices = new Set<number>();
  for (let i = 0; i < actualValCount; i++) {
    valIndices.add(Math.min(i * step, flopFiles.length - 1));
  }

  const trainFiles: string[] = [...otherFiles];
  const valFiles: string[] = [];
  for (let i = 0; i < flopFiles.length; i++) {
    if (valIndices.has(i)) {
      valFiles.push(flopFiles[i]);
    } else {
      trainFiles.push(flopFiles[i]);
    }
  }

  // Load validation set into memory (should be small: ~100 flops × 4K samples)
  const valSet: TrainingSample[] = [];
  for (const f of valFiles) {
    const lines = readFileSync(f, 'utf-8').split('\n'); // f is already full path
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const sample = JSON.parse(trimmed) as TrainingSample;
        if (sample.f?.length === featureCount && sample.l?.length === 3) {
          valSet.push(sample);
        }
      } catch {
        /* skip */
      }
    }
  }

  console.log(
    `  Flop split: ${trainFiles.length} train files, ${valFiles.length} val files (${valSet.length} val samples)`,
  );
  return { trainFiles, valFiles, valSet };
}

/**
 * Streaming V2 trainer: processes data in chunks for large datasets.
 * Loads one file at a time into memory, runs mini-epochs, then moves to the next.
 */
function trainStreamingV2(
  trainFiles: string[], // full paths
  valSet: TrainingSample[],
  featureCount: number,
  opts: {
    hiddenSizes: number[];
    batchSize: number;
    maxEpochs: number;
    initialLr: number;
    filesPerPass: number;
    resumeModel?: ModelWeights;
  },
): ModelWeights {
  const { hiddenSizes, batchSize, initialLr, resumeModel, filesPerPass } = opts;
  const maxPasses = opts.maxEpochs; // each "epoch" = one full pass through all files

  // Initialize or resume model
  let model: ModelWeights;
  if (resumeModel) {
    model = resumeModel;
    console.log(
      `Resuming from model (inputSize=${model.inputSize}, layers=${model.layers.length})`,
    );
  } else {
    model = createRandomModelV2(featureCount, hiddenSizes, ACTION_OUTPUT_SIZE, SIZING_OUTPUT_SIZE);
  }
  model.architecture = { hiddenSizes };

  console.log(
    `Streaming V2: input=${featureCount} → [${hiddenSizes.join(', ')}] → action(${ACTION_OUTPUT_SIZE}) + sizing(${SIZING_OUTPUT_SIZE})`,
  );
  const effectiveFilesPerPass =
    filesPerPass > 0 ? Math.min(filesPerPass, trainFiles.length) : trainFiles.length;
  console.log(`  ${trainFiles.length} training files, ${valSet.length} validation samples`);
  console.log(
    `  Batch size: ${batchSize}, Max passes: ${maxPasses}, Files/pass: ${effectiveFilesPerPass}`,
  );

  // Pre-allocate buffers
  const buf = createV2Buffers(model);
  const accGrads = createGradsV2Flat(model);

  let bestModel = cloneWeights(model);
  let bestValLoss = Infinity;
  let patience = 0;
  let lr = initialLr;

  for (let pass = 1; pass <= maxPasses; pass++) {
    if (pass > 1 && (pass - 1) % LR_DECAY_EVERY === 0) {
      lr *= LR_DECAY_FACTOR;
      console.log(`  LR decay → ${lr.toExponential(2)}`);
    }

    // Shuffle file order each pass and subsample
    const shuffledFiles = [...trainFiles];
    for (let i = shuffledFiles.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [shuffledFiles[i], shuffledFiles[j]] = [shuffledFiles[j], shuffledFiles[i]];
    }
    const passFiles = shuffledFiles.slice(0, effectiveFilesPerPass);

    let passLoss = 0;
    let passSamples = 0;

    for (const file of passFiles) {
      // Load chunk
      const chunk = loadSamples([], featureCount, null, [file]); // file is full path
      if (chunk.length === 0) continue;

      // Run 1 mini-epoch on this chunk
      shuffle(chunk);

      for (let start = 0; start < chunk.length; start += batchSize) {
        const end = Math.min(start + batchSize, chunk.length);
        const bs = end - start;
        zeroGradsV2Flat(accGrads);

        for (let b = start; b < end; b++) {
          const sample = chunk[b];
          forwardV2Into(model, sample.f, buf);

          let loss = 0;
          for (let i = 0; i < sample.l.length; i++) {
            loss -= sample.l[i] * Math.log(Math.max(buf.actionProbs[i], 1e-10));
          }

          const hasSizing = sample.sz && sample.l[0] > SIZING_RAISE_THRESHOLD;
          if (hasSizing) {
            for (let i = 0; i < sample.sz!.length; i++) {
              loss +=
                SIZING_LOSS_WEIGHT *
                (-sample.sz![i] * Math.log(Math.max(buf.sizingProbs[i], 1e-10)));
            }
          }
          passLoss += loss;
          passSamples++;

          backpropV2Into(
            model,
            buf,
            accGrads,
            sample.l,
            hasSizing ? sample.sz! : null,
            SIZING_LOSS_WEIGHT,
          );
        }

        sgdUpdateV2Flat(model, accGrads, lr, bs);
      }
    }

    const trainLoss = passSamples > 0 ? passLoss / passSamples : 0;
    const valLoss = valSet.length > 0 ? evaluateV2Loss(model, valSet) : trainLoss;

    const indicator = valLoss < bestValLoss ? ' *' : '';
    console.log(
      `Pass ${String(pass).padStart(3)}/${maxPasses}  ` +
        `train_loss=${trainLoss.toFixed(4)}  val_loss=${valLoss.toFixed(4)}  ` +
        `samples=${passSamples.toLocaleString()}  lr=${lr.toExponential(2)}${indicator}`,
    );

    if (valLoss < bestValLoss) {
      bestValLoss = valLoss;
      bestModel = cloneWeights(model);
      bestModel.valLoss = valLoss;
      patience = 0;
    } else {
      patience++;
      if (patience >= EARLY_STOP_PATIENCE) {
        console.log(`\nEarly stopping at pass ${pass} (patience=${EARLY_STOP_PATIENCE})`);
        break;
      }
    }
  }

  bestModel.trainedAt = new Date().toISOString();
  bestModel.trainingSamples = trainFiles.length * 5000; // approximate
  bestModel.version = 'v2';
  bestModel.architecture = { hiddenSizes };
  return bestModel;
}

// ── Entry point ──

function main(): void {
  const args = parseTrainerArgs();
  const {
    dataDirs,
    outPath,
    isV2,
    warmStart,
    maxSamples,
    trainSplit,
    maxOversampleRatio,
    hardExampleFraction,
    disableHardMining,
    initialLr,
    hiddenSizes,
    streaming,
    resume,
    valByFlop,
    valFlopCount,
    batchSize,
    maxEpochs,
  } = args;
  const featureCount = isV2 ? FEATURE_COUNT_V2 : FEATURE_COUNT;

  // Set up direct log file if specified (bypasses stdout block buffering)
  if (args.logFile) {
    _logFile = args.logFile;
    writeFileSync(_logFile, ''); // truncate
    logSync(`Log file: ${_logFile}`);
  }

  logSync(`Loading samples from: ${dataDirs.join(', ')}`);
  console.log(`Mode: ${isV2 ? 'V2 (multi-head)' : 'V1 (single-head)'}`);
  console.log(`Architecture: [${hiddenSizes.join(', ')}]`);
  if (streaming) console.log(`Streaming mode: ON`);
  if (resume) console.log(`Resuming from: ${resume}`);
  if (valByFlop) console.log(`Validation: by flop (${valFlopCount} flops held out)`);

  // ── Streaming mode (for large CFR datasets) ──
  if (streaming && isV2) {
    const { trainFiles, valSet } = splitByFlop(dataDirs, featureCount, valFlopCount);

    if (trainFiles.length === 0) {
      console.error('No training files found.');
      process.exit(1);
    }

    let resumeModel: ModelWeights | undefined;
    if (resume) {
      resumeModel = loadModelFromPath(resume);
      console.log(`Loaded resume model: ${resume}`);
    }

    const bestModel = trainStreamingV2(trainFiles, valSet, featureCount, {
      hiddenSizes,
      batchSize,
      maxEpochs,
      initialLr,
      filesPerPass: args.filesPerPass,
      resumeModel,
    });

    // Save model
    const outDir = dirname(outPath);
    if (!existsSync(outDir)) mkdirSync(outDir, { recursive: true });
    writeFileSync(outPath, JSON.stringify(bestModel));

    const sizeMB = (Buffer.byteLength(JSON.stringify(bestModel)) / 1024 / 1024).toFixed(2);
    console.log(`\nModel saved: ${outPath}`);
    console.log(`  Size: ${sizeMB} MB`);
    console.log(`  Val loss: ${bestModel.valLoss.toFixed(4)}`);

    // Evaluate
    if (valSet.length > 0) {
      const metrics = evaluateModel(bestModel, valSet);
      printMetrics(metrics);
      const metricsPath = outPath.replace('.json', '-metrics.json');
      writeFileSync(metricsPath, JSON.stringify(metrics, null, 2));
      console.log(`\nMetrics saved: ${metricsPath}`);
    }
    return;
  }

  // ── Standard mode (original logic) ──
  if (maxSamples != null) console.log(`Sample cap: ${maxSamples}`);
  if (isV2) {
    const hardMiningText = disableHardMining ? 'off' : `on(${hardExampleFraction})`;
    console.log(
      `V2 options: maxOversampleRatio=${maxOversampleRatio}, hardMining=${hardMiningText}, lr=${initialLr}`,
    );
  }
  let allSamples = loadSamples(dataDirs, featureCount, maxSamples);
  console.log(`Loaded ${allSamples.length} samples`);

  if (allSamples.length < 100) {
    console.error('Need at least 100 samples to train. Collect more data first.');
    process.exit(1);
  }

  // V2: apply anti-bias sampling before split (skip when hard mining disabled)
  if (isV2 && !disableHardMining) {
    console.log('Applying anti-bias sampling...');
    const beforeCount = allSamples.length;
    allSamples = balanceSamples(allSamples, maxOversampleRatio);
    console.log(`  ${beforeCount} → ${allSamples.length} samples after balancing`);
  } else if (isV2) {
    console.log('Skipping anti-bias sampling (hard mining disabled)');
  }

  // Shuffle and split
  shuffle(allSamples);
  const splitIdx = Math.floor(allSamples.length * trainSplit);
  const trainSet = allSamples.slice(0, splitIdx);
  const valSet = allSamples.slice(splitIdx);
  console.log(`Split: ${trainSet.length} train / ${valSet.length} validation\n`);

  // Warm-start / resume
  let warmStartModel: ModelWeights | undefined;
  if (resume) {
    warmStartModel = loadModelFromPath(resume);
    console.log(`Resuming V2 from checkpoint: ${resume}`);
  } else if (isV2 && warmStart) {
    const sourceModel = loadModelFromPath(warmStart);
    if (sourceModel.actionHead && sourceModel.sizingHead) {
      console.log(`Warm-starting V2 from V2 checkpoint: ${warmStart}`);
      warmStartModel = sourceModel;
    } else {
      console.log(`Warm-starting V2 from V1 model: ${warmStart}`);
      warmStartModel = warmStartV2FromV1(warmStart);
    }
  } else if (isV2 && !warmStart) {
    // Skip auto warm-start when custom architecture is specified (incompatible layer shapes)
    const customArch = hiddenSizes[0] !== HIDDEN_SIZES[0] || hiddenSizes[1] !== HIDDEN_SIZES[1];
    if (!customArch) {
      const __dirname = dirname(fileURLToPath(import.meta.url));
      const defaultV1Path = join(__dirname, '..', 'models', 'model-latest.json');
      if (existsSync(defaultV1Path)) {
        console.log(`Auto-detected V1 model for warm-start: ${defaultV1Path}`);
        try {
          warmStartModel = warmStartV2FromV1(defaultV1Path);
        } catch (err) {
          console.log(`  Warm-start failed (using random init): ${(err as Error).message}`);
        }
      }
    }
  }

  // If custom hidden sizes differ from default and no warm start, create fresh model
  if (
    isV2 &&
    !warmStartModel &&
    (hiddenSizes[0] !== HIDDEN_SIZES[0] || hiddenSizes[1] !== HIDDEN_SIZES[1])
  ) {
    warmStartModel = createRandomModelV2(
      featureCount,
      hiddenSizes,
      ACTION_OUTPUT_SIZE,
      SIZING_OUTPUT_SIZE,
    );
    warmStartModel.architecture = { hiddenSizes };
    console.log(`Custom architecture: [${hiddenSizes.join(', ')}]`);
  }

  // Train
  const bestModel = isV2
    ? trainV2(trainSet, valSet, warmStartModel, {
        hardExampleFraction,
        disableHardMining,
        initialLr,
        batchSize,
        maxEpochs,
        hiddenSizes,
      })
    : trainV1(trainSet, valSet);

  bestModel.architecture = { hiddenSizes };

  // Save model
  const outDir = dirname(outPath);
  if (!existsSync(outDir)) mkdirSync(outDir, { recursive: true });
  writeFileSync(outPath, JSON.stringify(bestModel));

  const sizeMB = (Buffer.byteLength(JSON.stringify(bestModel)) / 1024 / 1024).toFixed(2);
  console.log(`\nModel saved: ${outPath}`);
  console.log(`  Size: ${sizeMB} MB`);
  console.log(`  Val loss: ${bestModel.valLoss.toFixed(4)}`);
  console.log(`  Samples: ${bestModel.trainingSamples}`);

  // Evaluate and save metrics
  const evalSet = valSet.length > 0 ? valSet : trainSet;
  const metrics = evaluateModel(bestModel, evalSet);
  printMetrics(metrics);

  const metricsPath = outPath.replace('.json', '-metrics.json');
  writeFileSync(metricsPath, JSON.stringify(metrics, null, 2));
  console.log(`\nMetrics saved: ${metricsPath}`);
}

main();
