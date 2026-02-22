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
}

function parseTrainerArgs(): TrainerArgs {
  const __dirname = dirname(fileURLToPath(import.meta.url));
  let dataDir = join(__dirname, '..', '..', '..', 'data');
  let outPath = join(__dirname, '..', 'models', 'model-latest.json');
  let isV2 = false;

  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--data' && argv[i + 1]) dataDir = argv[++i];
    if (argv[i] === '--out' && argv[i + 1]) outPath = argv[++i];
    if (argv[i] === '--v2') isV2 = true;
  }

  return { dataDir, outPath, isV2 };
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

function balanceSamples(samples: TrainingSample[]): TrainingSample[] {
  // Step 1: Group by street
  const byStreet = new Map<string, TrainingSample[]>();
  for (const s of samples) {
    const street = s.s || 'UNKNOWN';
    if (!byStreet.has(street)) byStreet.set(street, []);
    byStreet.get(street)!.push(s);
  }

  const maxStreetCount = Math.max(...[...byStreet.values()].map(g => g.length));

  // Step 2: Oversample minority streets to match majority
  const streetBalanced: TrainingSample[] = [];
  for (const [, group] of byStreet) {
    streetBalanced.push(...group);
    // Oversample to reach target
    let needed = maxStreetCount - group.length;
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

  // Find max per street-action pair across streets
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

function cloneWeights(model: ModelWeights): ModelWeights {
  return JSON.parse(JSON.stringify(model));
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
//   V2 MULTI-HEAD TRAINING
// ══════════════════════════════════════════════

interface ForwardCacheV2 {
  /** Inputs to each backbone layer */
  backboneInputs: number[][];
  /** Outputs of each backbone layer (post-ReLU) */
  backboneOutputs: number[][];
  /** Final backbone output (input to both heads) */
  backbone: number[];
  /** Action head softmax probabilities */
  actionProbs: number[];
  /** Sizing head softmax probabilities */
  sizingProbs: number[];
}

function softmaxArr(preAct: number[]): number[] {
  const maxVal = Math.max(...preAct);
  const exps = preAct.map(v => Math.exp(v - maxVal));
  const sum = exps.reduce((a, b) => a + b, 0);
  return exps.map(e => e / sum);
}

function forwardV2WithCache(model: ModelWeights, features: number[]): ForwardCacheV2 {
  const backboneInputs: number[][] = [];
  const backboneOutputs: number[][] = [];
  let current = features;

  // Backbone forward (all layers use ReLU)
  for (const layer of model.layers) {
    backboneInputs.push(current);
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
    const activated = preAct.map(v => v > 0 ? v : 0);
    backboneOutputs.push(activated);
    current = activated;
  }

  const backbone = current;

  // Action head forward
  const actionHead = model.actionHead!;
  const actionPreAct = new Array<number>(actionHead.weights.length);
  for (let j = 0; j < actionHead.weights.length; j++) {
    let sum = actionHead.biases[j];
    const w = actionHead.weights[j];
    for (let i = 0; i < backbone.length; i++) {
      sum += backbone[i] * w[i];
    }
    actionPreAct[j] = sum;
  }
  const actionProbs = softmaxArr(actionPreAct);

  // Sizing head forward
  const sizingHead = model.sizingHead!;
  const sizingPreAct = new Array<number>(sizingHead.weights.length);
  for (let j = 0; j < sizingHead.weights.length; j++) {
    let sum = sizingHead.biases[j];
    const w = sizingHead.weights[j];
    for (let i = 0; i < backbone.length; i++) {
      sum += backbone[i] * w[i];
    }
    sizingPreAct[j] = sum;
  }
  const sizingProbs = softmaxArr(sizingPreAct);

  return { backboneInputs, backboneOutputs, backbone, actionProbs, sizingProbs };
}

interface GradientsV2 {
  layers: LayerWeights[];       // backbone
  actionHead: LayerWeights;
  sizingHead: LayerWeights;
}

function zeroGradsV2(model: ModelWeights): GradientsV2 {
  return {
    layers: model.layers.map(l => ({
      weights: l.weights.map(row => new Array<number>(row.length).fill(0)),
      biases: new Array<number>(l.biases.length).fill(0),
    })),
    actionHead: {
      weights: model.actionHead!.weights.map(row => new Array<number>(row.length).fill(0)),
      biases: new Array<number>(model.actionHead!.biases.length).fill(0),
    },
    sizingHead: {
      weights: model.sizingHead!.weights.map(row => new Array<number>(row.length).fill(0)),
      biases: new Array<number>(model.sizingHead!.biases.length).fill(0),
    },
  };
}

function backpropV2(
  model: ModelWeights,
  cache: ForwardCacheV2,
  actionTarget: number[],
  sizingTarget: number[] | null,
  sizingWeight: number,
): GradientsV2 {
  const grads = zeroGradsV2(model);
  const backboneDim = cache.backbone.length;

  // ── Action head gradients: dL/dz = probs - target ──
  const actionDelta = cache.actionProbs.map((p, i) => p - actionTarget[i]);
  const actionHead = model.actionHead!;
  for (let j = 0; j < actionHead.weights.length; j++) {
    grads.actionHead.biases[j] = actionDelta[j];
    for (let i = 0; i < backboneDim; i++) {
      grads.actionHead.weights[j][i] = actionDelta[j] * cache.backbone[i];
    }
  }

  // Backbone delta from action head
  const backboneDeltaFromAction = new Array<number>(backboneDim).fill(0);
  for (let i = 0; i < backboneDim; i++) {
    for (let j = 0; j < actionHead.weights.length; j++) {
      backboneDeltaFromAction[i] += actionDelta[j] * actionHead.weights[j][i];
    }
  }

  // ── Sizing head gradients (only when sizing target exists) ──
  const backboneDeltaFromSizing = new Array<number>(backboneDim).fill(0);
  if (sizingTarget && sizingWeight > 0) {
    const sizingDelta = cache.sizingProbs.map((p, i) => p - sizingTarget[i]);
    const sizingHead = model.sizingHead!;
    for (let j = 0; j < sizingHead.weights.length; j++) {
      grads.sizingHead.biases[j] = sizingDelta[j] * sizingWeight;
      for (let i = 0; i < backboneDim; i++) {
        grads.sizingHead.weights[j][i] = sizingDelta[j] * cache.backbone[i] * sizingWeight;
      }
    }

    for (let i = 0; i < backboneDim; i++) {
      for (let j = 0; j < sizingHead.weights.length; j++) {
        backboneDeltaFromSizing[i] += sizingDelta[j] * sizingHead.weights[j][i] * sizingWeight;
      }
    }
  }

  // ── Combined backbone delta ──
  let delta = new Array<number>(backboneDim);
  for (let i = 0; i < backboneDim; i++) {
    // Apply ReLU derivative for last backbone layer
    const lastBackboneIdx = model.layers.length - 1;
    const activated = cache.backboneOutputs[lastBackboneIdx][i] > 0 ? 1 : 0;
    delta[i] = (backboneDeltaFromAction[i] + backboneDeltaFromSizing[i]) * activated;
  }

  // ── Backprop through backbone layers (reverse) ──
  for (let l = model.layers.length - 1; l >= 0; l--) {
    const input = cache.backboneInputs[l];
    const layer = model.layers[l];
    const outDim = layer.weights.length;
    const inDim = input.length;

    for (let j = 0; j < outDim; j++) {
      grads.layers[l].biases[j] = delta[j];
      for (let i = 0; i < inDim; i++) {
        grads.layers[l].weights[j][i] = delta[j] * input[i];
      }
    }

    if (l > 0) {
      const prevDelta = new Array<number>(inDim).fill(0);
      for (let i = 0; i < inDim; i++) {
        let sum = 0;
        for (let j = 0; j < outDim; j++) {
          sum += delta[j] * layer.weights[j][i];
        }
        prevDelta[i] = cache.backboneOutputs[l - 1][i] > 0 ? sum : 0;
      }
      delta = prevDelta;
    }
  }

  return grads;
}

function accumulateGradsV2(acc: GradientsV2, grads: GradientsV2): void {
  // Backbone
  for (let l = 0; l < acc.layers.length; l++) {
    for (let j = 0; j < acc.layers[l].biases.length; j++) {
      acc.layers[l].biases[j] += grads.layers[l].biases[j];
      for (let i = 0; i < acc.layers[l].weights[j].length; i++) {
        acc.layers[l].weights[j][i] += grads.layers[l].weights[j][i];
      }
    }
  }
  // Action head
  for (let j = 0; j < acc.actionHead.biases.length; j++) {
    acc.actionHead.biases[j] += grads.actionHead.biases[j];
    for (let i = 0; i < acc.actionHead.weights[j].length; i++) {
      acc.actionHead.weights[j][i] += grads.actionHead.weights[j][i];
    }
  }
  // Sizing head
  for (let j = 0; j < acc.sizingHead.biases.length; j++) {
    acc.sizingHead.biases[j] += grads.sizingHead.biases[j];
    for (let i = 0; i < acc.sizingHead.weights[j].length; i++) {
      acc.sizingHead.weights[j][i] += grads.sizingHead.weights[j][i];
    }
  }
}

function sgdUpdateV2(model: ModelWeights, grads: GradientsV2, lr: number, batchSize: number): void {
  const scale = lr / batchSize;

  // Backbone
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
  // Action head
  const ah = model.actionHead!;
  const ahg = grads.actionHead;
  for (let j = 0; j < ah.weights.length; j++) {
    ah.biases[j] -= scale * ahg.biases[j];
    for (let i = 0; i < ah.weights[j].length; i++) {
      ah.weights[j][i] -= scale * ahg.weights[j][i];
    }
  }
  // Sizing head
  const sh = model.sizingHead!;
  const shg = grads.sizingHead;
  for (let j = 0; j < sh.weights.length; j++) {
    sh.biases[j] -= scale * shg.biases[j];
    for (let i = 0; i < sh.weights[j].length; i++) {
      sh.weights[j][i] -= scale * shg.weights[j][i];
    }
  }
}

function evaluateV2Loss(model: ModelWeights, samples: TrainingSample[]): number {
  let totalLoss = 0;
  for (const sample of samples) {
    const cache = forwardV2WithCache(model, sample.f);
    let loss = crossEntropyLoss(cache.actionProbs, sample.l);
    if (sample.sz && sample.l[0] > SIZING_RAISE_THRESHOLD) {
      loss += SIZING_LOSS_WEIGHT * crossEntropyLoss(cache.sizingProbs, sample.sz);
    }
    totalLoss += loss;
  }
  return totalLoss / samples.length;
}

function trainV2(trainSet: TrainingSample[], valSet: TrainingSample[]): ModelWeights {
  console.log(`Initializing V2 MLP: input=${FEATURE_COUNT_V2} → [${HIDDEN_SIZES.join(', ')}] → action(${ACTION_OUTPUT_SIZE}) + sizing(${SIZING_OUTPUT_SIZE})`);

  const model = createRandomModelV2(FEATURE_COUNT_V2, HIDDEN_SIZES, ACTION_OUTPUT_SIZE, SIZING_OUTPUT_SIZE);
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

    // Hard example mining after epoch 1
    if (epoch === 2) {
      console.log('  Hard example mining: identifying difficult samples...');
      const losses = trainSet.map(s => {
        const cache = forwardV2WithCache(model, s.f);
        return { sample: s, loss: crossEntropyLoss(cache.actionProbs, s.l) };
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
      const accGrads = zeroGradsV2(model);

      for (let b = start; b < end; b++) {
        const sample = workingTrainSet[b];
        const cache = forwardV2WithCache(model, sample.f);

        // Action loss
        let loss = crossEntropyLoss(cache.actionProbs, sample.l);

        // Sizing target: only when raise label is significant
        const hasSizing = sample.sz && sample.l[0] > SIZING_RAISE_THRESHOLD;
        if (hasSizing) {
          loss += SIZING_LOSS_WEIGHT * crossEntropyLoss(cache.sizingProbs, sample.sz!);
        }
        epochLoss += loss;

        const grads = backpropV2(
          model, cache, sample.l,
          hasSizing ? sample.sz! : null,
          SIZING_LOSS_WEIGHT,
        );
        accumulateGradsV2(accGrads, grads);
      }

      sgdUpdateV2(model, accGrads, lr, batchSize);
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
  const { dataDir, outPath, isV2 } = parseTrainerArgs();
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

  // Train
  const bestModel = isV2 ? trainV2(trainSet, valSet) : trainV1(trainSet, valSet);

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
