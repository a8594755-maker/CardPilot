#!/usr/bin/env tsx
/**
 * Offline trainer for the fast-advice MLP model.
 *
 * Usage:  npx tsx packages/fast-model/src/trainer.ts [--data <dir>] [--out <path>]
 *
 * Reads JSONL training samples, trains a small MLP via mini-batch SGD
 * with cross-entropy loss, and saves the best model weights to JSON.
 */

import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRandomModel } from './mlp.js';
import { FEATURE_COUNT } from './feature-encoder.js';
import type { ModelWeights, TrainingSample, LayerWeights } from './types.js';

// ── Config ──

const HIDDEN_SIZES = [64, 32];
const OUTPUT_SIZE = 3; // raise, call, fold
const LEARNING_RATE_INIT = 0.01;
const LR_DECAY_FACTOR = 0.5;
const LR_DECAY_EVERY = 20; // epochs
const BATCH_SIZE = 64;
const MAX_EPOCHS = 100;
const EARLY_STOP_PATIENCE = 10;
const TRAIN_SPLIT = 0.9;

// ── CLI args ──

function parseTrainerArgs(): { dataDir: string; outPath: string } {
  const __dirname = dirname(fileURLToPath(import.meta.url));
  let dataDir = join(__dirname, '..', '..', '..', 'data');
  let outPath = join(__dirname, '..', 'models', 'model-latest.json');

  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--data' && argv[i + 1]) dataDir = argv[++i];
    if (argv[i] === '--out' && argv[i + 1]) outPath = argv[++i];
  }

  return { dataDir, outPath };
}

// ── Data loading ──

function loadSamples(dataDir: string): TrainingSample[] {
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
        if (sample.f && sample.l && sample.f.length === FEATURE_COUNT && sample.l.length === 3) {
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

// ── Forward pass with cached activations (for backprop) ──

interface ForwardCache {
  /** Input to each layer (pre-activation values stored) */
  inputs: number[][];
  /** Output of each layer (post-activation) */
  outputs: number[][];
  /** Final softmax probabilities */
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
      // Softmax for output
      const maxVal = Math.max(...preAct);
      const exps = preAct.map(v => Math.exp(v - maxVal));
      const sum = exps.reduce((a, b) => a + b, 0);
      const probs = exps.map(e => e / sum);
      outputs.push(probs);
      return { inputs, outputs, probs };
    } else {
      // ReLU for hidden
      const activated = preAct.map(v => v > 0 ? v : 0);
      outputs.push(activated);
      current = activated;
    }
  }

  // Should not reach here
  return { inputs, outputs, probs: outputs[outputs.length - 1] };
}

// ── Cross-entropy loss ──

function crossEntropyLoss(probs: number[], target: number[]): number {
  let loss = 0;
  for (let i = 0; i < target.length; i++) {
    loss -= target[i] * Math.log(Math.max(probs[i], 1e-10));
  }
  return loss;
}

// ── Backpropagation ──

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

  // Output layer gradient: softmax + cross-entropy → dL/dz = probs - target
  let delta = cache.probs.map((p, i) => p - target[i]);

  // Backprop through layers (reverse order)
  for (let l = numLayers - 1; l >= 0; l--) {
    const input = cache.inputs[l];
    const layer = layers[l];
    const outDim = layer.weights.length;
    const inDim = input.length;

    // Compute weight and bias gradients
    for (let j = 0; j < outDim; j++) {
      grads[l].biases[j] = delta[j];
      for (let i = 0; i < inDim; i++) {
        grads[l].weights[j][i] = delta[j] * input[i];
      }
    }

    // Propagate delta to previous layer (if not first layer)
    if (l > 0) {
      const prevDelta = new Array<number>(inDim).fill(0);
      for (let i = 0; i < inDim; i++) {
        let sum = 0;
        for (let j = 0; j < outDim; j++) {
          sum += delta[j] * layer.weights[j][i];
        }
        // ReLU derivative: 1 if activated, 0 otherwise
        // cache.outputs[l-1] is the post-ReLU output of previous layer
        prevDelta[i] = cache.outputs[l - 1][i] > 0 ? sum : 0;
      }
      delta = prevDelta;
    }
  }

  return { layers: grads };
}

// ── SGD update ──

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

// ── Accumulate gradients ──

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

// ── Evaluate on dataset ──

function evaluate(model: ModelWeights, samples: TrainingSample[]): number {
  let totalLoss = 0;
  for (const sample of samples) {
    const cache = forwardWithCache(model, sample.f);
    totalLoss += crossEntropyLoss(cache.probs, sample.l);
  }
  return totalLoss / samples.length;
}

// ── Deep clone weights ──

function cloneWeights(model: ModelWeights): ModelWeights {
  return JSON.parse(JSON.stringify(model));
}

// ── Main training loop ──

function train(trainSet: TrainingSample[], valSet: TrainingSample[]): ModelWeights {
  console.log(`Initializing MLP: input=${FEATURE_COUNT} → [${HIDDEN_SIZES.join(', ')}] → ${OUTPUT_SIZE}`);

  const model = createRandomModel(FEATURE_COUNT, HIDDEN_SIZES, OUTPUT_SIZE);
  let bestModel = cloneWeights(model);
  let bestValLoss = Infinity;
  let patience = 0;
  let lr = LEARNING_RATE_INIT;

  for (let epoch = 1; epoch <= MAX_EPOCHS; epoch++) {
    // Decay learning rate
    if (epoch > 1 && (epoch - 1) % LR_DECAY_EVERY === 0) {
      lr *= LR_DECAY_FACTOR;
      console.log(`  LR decay → ${lr.toExponential(2)}`);
    }

    // Shuffle training data
    shuffle(trainSet);

    // Mini-batch SGD
    let epochLoss = 0;
    let batchCount = 0;

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
      batchCount++;
    }

    const trainLoss = epochLoss / trainSet.length;
    const valLoss = evaluate(model, valSet);

    const indicator = valLoss < bestValLoss ? ' *' : '';
    console.log(
      `Epoch ${String(epoch).padStart(3)}/${MAX_EPOCHS}  ` +
      `train_loss=${trainLoss.toFixed(4)}  val_loss=${valLoss.toFixed(4)}  ` +
      `lr=${lr.toExponential(2)}${indicator}`
    );

    // Track best model
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
  return bestModel;
}

// ── Entry point ──

function main(): void {
  const { dataDir, outPath } = parseTrainerArgs();

  console.log(`Loading samples from: ${dataDir}`);
  const allSamples = loadSamples(dataDir);
  console.log(`Loaded ${allSamples.length} samples`);

  if (allSamples.length < 100) {
    console.error('Need at least 100 samples to train. Collect more data first.');
    process.exit(1);
  }

  // Shuffle and split
  shuffle(allSamples);
  const splitIdx = Math.floor(allSamples.length * TRAIN_SPLIT);
  const trainSet = allSamples.slice(0, splitIdx);
  const valSet = allSamples.slice(splitIdx);
  console.log(`Split: ${trainSet.length} train / ${valSet.length} validation\n`);

  // Train
  const bestModel = train(trainSet, valSet);

  // Save
  const outDir = dirname(outPath);
  if (!existsSync(outDir)) mkdirSync(outDir, { recursive: true });
  writeFileSync(outPath, JSON.stringify(bestModel));

  const sizeMB = (Buffer.byteLength(JSON.stringify(bestModel)) / 1024 / 1024).toFixed(2);
  console.log(`\nModel saved: ${outPath}`);
  console.log(`  Size: ${sizeMB} MB`);
  console.log(`  Val loss: ${bestModel.valLoss.toFixed(4)}`);
  console.log(`  Samples: ${bestModel.trainingSamples}`);
}

main();
