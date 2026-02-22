#!/usr/bin/env tsx
/**
 * Offline trainer for the fast-advice MLP model.
 *
 * Usage:
 *   V1:  npx tsx packages/fast-model/src/trainer.ts [--data <dir>] [--out <path>]
 *   V2:  npx tsx packages/fast-model/src/trainer.ts --v2 [--data <dir>] [--out <path>]
 *
 * V1: Single-head (48→64→32→3), cross-entropy loss on action labels.
 * V2: Multi-head (54→64→32→[3 action, 5 sizing]), combined loss,
 *     anti-bias sampling, hard example mining, evaluation metrics.
 */

import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRandomModel, createRandomModelV2 } from './mlp.js';
import { FEATURE_COUNT, FEATURE_COUNT_V2 } from './feature-encoder.js';
import { evaluateModel, printMetrics } from './evaluate.js';
import type { ModelWeights, TrainingSample, LayerWeights } from './types.js';

// ── Config ──

const HIDDEN_SIZES = [64, 32];
const ACTION_OUTPUT_SIZE = 3;  // raise, call, fold
const SIZING_OUTPUT_SIZE = 5;  // 33%, 50%, 66%, 100%, all-in
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
  dataDir: string;
  outPath: string;
  isV2: boolean;
  warmStart: string | null; // path to V1 model for transfer learning
}

function parseTrainerArgs(): TrainerArgs {
  const __dirname = dirname(fileURLToPath(import.meta.url));
  let dataDir = join(__dirname, '..', '..', '..', 'data');
  let outPath = join(__dirname, '..', 'models', 'model-latest.json');
  let isV2 = false;
  let warmStart: string | null = null;

  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--data' && argv[i + 1]) dataDir = argv[++i];
    if (argv[i] === '--out' && argv[i + 1]) outPath = argv[++i];
    if (argv[i] === '--v2') isV2 = true;
    if (argv[i] === '--warm-start' && argv[i + 1]) warmStart = argv[++i];
  }

  return { dataDir, outPath, isV2, warmStart };
}

// ── Data loading ──

function loadSamples(dataDir: string, expectedFeatureCount: number): TrainingSample[] {
  if (!existsSync(dataDir)) {
    console.error(`Data directory not found: ${dataDir}`);
    process.exit(1);
  }

  const files = readdirSync(dataDir).filter(f => f.endsWith('.jsonl'));
  if (files.length === 0) {
    console.error(`No .jsonl files found in: ${dataDir}`);
    process.exit(1);
  }

  const samples: TrainingSample[] = [];
  for (const file of files) {
    const lines = readFileSync(join(dataDir, file), 'utf-8').split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const sample = JSON.parse(trimmed) as TrainingSample;
        if (sample.f && sample.l && sample.f.length === expectedFeatureCount && sample.l.length === 3) {
          samples.push(sample);
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

function balanceSamples(samples: TrainingSample[]): TrainingSample[] {
  // Step 1: Group by street
  const byStreet = new Map<string, TrainingSample[]>();
  for (const s of samples) {
    const street = s.s || 'UNKNOWN';
    if (!byStreet.has(street)) byStreet.set(street, []);
    byStreet.get(street)!.push(s);
  }

  // Cap target to avoid massive oversampling (e.g. 6K PREFLOP vs 100 RIVER)
  const maxStreetCount = Math.max(...[...byStreet.values()].map(g => g.length));
  const medianCount = [...byStreet.values()].map(g => g.length).sort((a, b) => a - b)[Math.floor(byStreet.size / 2)];
  const streetTarget = Math.min(maxStreetCount, medianCount * 4);

  // Step 2: Oversample minority streets to capped target
  const streetBalanced: TrainingSample[] = [];
  for (const [, group] of byStreet) {
    const target = Math.min(streetTarget, group.length * 10); // never oversample a single street more than 10x
    streetBalanced.push(...group);
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
    balanced.push(...group);
    let needed = target - group.length;
    while (needed > 0) {
      balanced.push(group[Math.floor(Math.random() * group.length)]);
      needed--;
    }
  }

  // Final safety cap: don't exceed MAX_OVERSAMPLE_RATIO × original size
  const maxTotal = samples.length * MAX_OVERSAMPLE_RATIO;
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
      const exps = preAct.map(v => Math.exp(v - maxVal));
      const sum = exps.reduce((a, b) => a + b, 0);
      const probs = exps.map(e => e / sum);
      outputs.push(probs);
      return { inputs, outputs, probs };
    } else {
      const activated = preAct.map(v => v > 0 ? v : 0);
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
  const grads: LayerWeights[] = layers.map(l => ({
    weights: l.weights.map(row => new Array<number>(row.length).fill(0)),
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
    layers: model.layers.map(l => ({
      weights: l.weights.map(row => new Array<number>(row.length).fill(0)),
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
    weights: l.weights.map(row => row.slice()),
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
  console.log(`Initializing V1 MLP: input=${FEATURE_COUNT} → [${HIDDEN_SIZES.join(', ')}] → ${ACTION_OUTPUT_SIZE}`);

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
    const valLoss = evaluateV1(model, valSet);

    const indicator = valLoss < bestValLoss ? ' *' : '';
    console.log(
      `Epoch ${String(epoch).padStart(3)}/${MAX_EPOCHS}  ` +
      `train_loss=${trainLoss.toFixed(4)}  val_loss=${valLoss.toFixed(4)}  ` +
      `lr=${lr.toExponential(2)}${indicator}`
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
  const paddedWeights0 = v1Layer0.weights.map(row => {
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
      { weights: v1Layer1.weights.map(r => [...r]), biases: [...v1Layer1.biases] },
    ],
    actionHead: {
      weights: v1Layer2.weights.map(r => [...r]),
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
  backboneInputs: Float64Array[];   // one per backbone layer
  backboneOutputs: Float64Array[];  // one per backbone layer
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
  prevDelta: Float64Array;  // for largest input dim
}

interface GradientsV2Flat {
  /** Flat Float64Arrays for each backbone layer's weights and biases */
  layerWeights: Float64Array[];   // [outDim * inDim] per layer
  layerBiases: Float64Array[];    // [outDim] per layer
  layerInDims: number[];          // input dim per layer
  actionWeights: Float64Array;    // [ACTION_OUTPUT_SIZE * backboneDim]
  actionBiases: Float64Array;
  sizingWeights: Float64Array;    // [SIZING_OUTPUT_SIZE * backboneDim]
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
  for (let i = 0; i < len; i++) { out[i] = Math.exp(preAct[i] - maxVal); sum += out[i]; }
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
      for (let i = 0; i < inDim; i++) { delta[i] = prevDelta[i]; }
    }
  }
}

function sgdUpdateV2Flat(model: ModelWeights, grads: GradientsV2Flat, lr: number, batchSize: number): void {
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
        loss += SIZING_LOSS_WEIGHT * (-sample.sz[i] * Math.log(Math.max(buf.sizingProbs[i], 1e-10)));
      }
    }
    totalLoss += loss;
  }
  return totalLoss / samples.length;
}

function trainV2(trainSet: TrainingSample[], valSet: TrainingSample[], warmStartModel?: ModelWeights): ModelWeights {
  const model = warmStartModel
    ? warmStartModel
    : createRandomModelV2(FEATURE_COUNT_V2, HIDDEN_SIZES, ACTION_OUTPUT_SIZE, SIZING_OUTPUT_SIZE);

  console.log(`Initializing V2 MLP: input=${FEATURE_COUNT_V2} → [${HIDDEN_SIZES.join(', ')}] → action(${ACTION_OUTPUT_SIZE}) + sizing(${SIZING_OUTPUT_SIZE})${warmStartModel ? ' [warm-started from V1]' : ''}`);

  // Pre-allocate all scratch buffers once
  const buf = createV2Buffers(model);
  const accGrads = createGradsV2Flat(model);

  let bestModel = cloneWeights(model);
  let bestValLoss = Infinity;
  let patience = 0;
  let lr = LEARNING_RATE_INIT;
  let workingTrainSet = [...trainSet];

  for (let epoch = 1; epoch <= MAX_EPOCHS; epoch++) {
    if (epoch > 1 && (epoch - 1) % LR_DECAY_EVERY === 0) {
      lr *= LR_DECAY_FACTOR;
      console.log(`  LR decay → ${lr.toExponential(2)}`);
    }

    // Hard example mining after epoch 1 (reuses pre-allocated buffers)
    if (epoch === 2) {
      console.log('  Hard example mining: identifying difficult samples...');
      const losses = trainSet.map(s => {
        forwardV2Into(model, s.f, buf);
        let loss = 0;
        for (let i = 0; i < s.l.length; i++) {
          loss -= s.l[i] * Math.log(Math.max(buf.actionProbs[i], 1e-10));
        }
        return { sample: s, loss };
      });
      losses.sort((a, b) => b.loss - a.loss);
      const hardCount = Math.floor(losses.length * HARD_EXAMPLE_FRACTION);
      const hardExamples = losses.slice(0, hardCount).map(x => x.sample);
      workingTrainSet = [...trainSet, ...hardExamples];
      console.log(`  Added ${hardCount} hard examples (${workingTrainSet.length} total)`);
    }

    shuffle(workingTrainSet);

    let epochLoss = 0;
    for (let start = 0; start < workingTrainSet.length; start += BATCH_SIZE) {
      const end = Math.min(start + BATCH_SIZE, workingTrainSet.length);
      const batchSize = end - start;
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
            loss += SIZING_LOSS_WEIGHT * (-sample.sz![i] * Math.log(Math.max(buf.sizingProbs[i], 1e-10)));
          }
        }
        epochLoss += loss;

        backpropV2Into(
          model, buf, accGrads, sample.l,
          hasSizing ? sample.sz! : null,
          SIZING_LOSS_WEIGHT,
        );
      }

      sgdUpdateV2Flat(model, accGrads, lr, batchSize);
    }

    const trainLoss = epochLoss / workingTrainSet.length;
    const valLoss = evaluateV2Loss(model, valSet);

    const indicator = valLoss < bestValLoss ? ' *' : '';
    console.log(
      `Epoch ${String(epoch).padStart(3)}/${MAX_EPOCHS}  ` +
      `train_loss=${trainLoss.toFixed(4)}  val_loss=${valLoss.toFixed(4)}  ` +
      `lr=${lr.toExponential(2)}${indicator}`
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

// ── Entry point ──

function main(): void {
  const { dataDir, outPath, isV2, warmStart } = parseTrainerArgs();
  const featureCount = isV2 ? FEATURE_COUNT_V2 : FEATURE_COUNT;

  console.log(`Loading samples from: ${dataDir}`);
  console.log(`Mode: ${isV2 ? 'V2 (multi-head + anti-bias)' : 'V1 (single-head)'}`);
  let allSamples = loadSamples(dataDir, featureCount);
  console.log(`Loaded ${allSamples.length} samples`);

  if (allSamples.length < 100) {
    console.error('Need at least 100 samples to train. Collect more data first.');
    process.exit(1);
  }

  // V2: apply anti-bias sampling before split
  if (isV2) {
    console.log('Applying anti-bias sampling...');
    const beforeCount = allSamples.length;
    allSamples = balanceSamples(allSamples);
    console.log(`  ${beforeCount} → ${allSamples.length} samples after balancing`);
  }

  // Shuffle and split
  shuffle(allSamples);
  const splitIdx = Math.floor(allSamples.length * TRAIN_SPLIT);
  const trainSet = allSamples.slice(0, splitIdx);
  const valSet = allSamples.slice(splitIdx);
  console.log(`Split: ${trainSet.length} train / ${valSet.length} validation\n`);

  // Warm-start: transfer V1 weights to V2 model
  let warmStartModel: ModelWeights | undefined;
  if (isV2 && warmStart) {
    console.log(`Warm-starting V2 from V1 model: ${warmStart}`);
    warmStartModel = warmStartV2FromV1(warmStart);
  } else if (isV2 && !warmStart) {
    // Auto-detect V1 model for warm-start
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

  // Train
  const bestModel = isV2 ? trainV2(trainSet, valSet, warmStartModel) : trainV1(trainSet, valSet);

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
  const metrics = evaluateModel(bestModel, valSet);
  printMetrics(metrics);

  const metricsPath = outPath.replace('.json', '-metrics.json');
  writeFileSync(metricsPath, JSON.stringify(metrics, null, 2));
  console.log(`\nMetrics saved: ${metricsPath}`);
}

main();
