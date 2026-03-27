/**
 * Minimal Multi-Layer Perceptron (MLP) implementation.
 * Pure TypeScript, zero dependencies. Supports:
 *   - V1: Sequential forward pass (48→64→32→3) with single action head
 *   - V2: Multi-head forward pass (54→64→32→[3 action, 5 sizing])
 *   - Model loading from JSON weights
 */

import type {
  ModelWeights,
  StrategyMix,
  PredictResult,
  LayerWeights,
  LayerWithNorm,
} from './types.js';

/**
 * ReLU activation: max(0, x)
 */
function relu(x: number): number {
  return x > 0 ? x : 0;
}

/**
 * Softmax: convert raw logits to probabilities summing to 1.
 * Uses the max-subtract trick for numerical stability.
 */
function softmax(logits: number[]): number[] {
  const maxVal = Math.max(...logits);
  const exps = logits.map((v) => Math.exp(v - maxVal));
  const sum = exps.reduce((a, b) => a + b, 0);
  return exps.map((e) => e / sum);
}

/**
 * Dense layer forward pass: output = activation(input @ W^T + bias)
 *
 * @param input - Input vector [inputDim]
 * @param weights - Weight matrix [outputDim][inputDim]
 * @param biases - Bias vector [outputDim]
 * @param activation - Activation function (null for linear/output layer)
 */
function denseForward(
  input: number[],
  weights: number[][],
  biases: number[],
  activation: ((x: number) => number) | null,
): number[] {
  const outputDim = weights.length;
  const output = new Array<number>(outputDim);

  for (let j = 0; j < outputDim; j++) {
    let sum = biases[j];
    const w = weights[j];
    for (let i = 0; i < input.length; i++) {
      sum += input[i] * w[i];
    }
    output[j] = activation ? activation(sum) : sum;
  }

  return output;
}

/** Check if model is V2 (has separate action/sizing heads) */
function isV2Model(weights: ModelWeights): boolean {
  return !!(weights.actionHead && weights.sizingHead);
}

/** Check if model is V3 (has embedding layers) */
function isV3Model(weights: ModelWeights): boolean {
  return weights.version === 'v3' && !!weights.handEmbedding;
}

/**
 * LayerNorm forward pass: x → (x - mean) / sqrt(var + eps) * scale + bias
 */
function layerNormForward(x: number[], scale: number[], bias: number[]): number[] {
  const n = x.length;
  let mean = 0;
  for (let i = 0; i < n; i++) mean += x[i];
  mean /= n;
  let variance = 0;
  for (let i = 0; i < n; i++) variance += (x[i] - mean) ** 2;
  variance /= n;
  const invStd = 1 / Math.sqrt(variance + 1e-5);
  const out = new Array<number>(n);
  for (let i = 0; i < n; i++) out[i] = scale[i] * (x[i] - mean) * invStd + bias[i];
  return out;
}

/**
 * Compute hand category index (0-168) from rank values.
 * 0-12: pairs (22=0, 33=1, ..., AA=12)
 * 13-90: suited hands
 * 91-168: offsuit hands
 */
function handCategoryIndex(rank1Norm: number, rank2Norm: number, suited: number): number {
  const r1 = Math.round(rank1Norm * 14); // 2..14
  const r2 = Math.round(rank2Norm * 14);
  const hi = Math.max(r1, r2) - 2; // 0=2, ..., 12=A
  const lo = Math.min(r1, r2) - 2;
  if (hi === lo) return hi; // pair
  const nonpairIdx = (hi * (hi - 1)) / 2 + lo;
  return suited > 0.5 ? 13 + nonpairIdx : 91 + nonpairIdx;
}

/**
 * Extract board card index (0-51, 52=padding) from 5 feature values at given offset.
 */
function boardCardIndex(features: number[], base: number): number {
  if (features[base] < 0.01) return 52; // empty slot
  const rank = Math.round(features[base] * 14); // 2..14
  let suit = 0;
  let maxVal = features[base + 1];
  for (let s = 1; s < 4; s++) {
    if (features[base + 1 + s] > maxVal) {
      maxVal = features[base + 1 + s];
      suit = s;
    }
  }
  return (rank - 2) * 4 + suit;
}

export class MLP {
  private weights: ModelWeights;

  constructor(weights: ModelWeights) {
    this.weights = weights;
  }

  /**
   * V1 backward-compatible predict: features → {raise, call, fold}.
   * For V2 models, returns only the action head output.
   */
  predict(features: number[]): StrategyMix {
    const result = this.predictFull(features);
    return result.action;
  }

  /**
   * V2/V3 full prediction: features → action mix + sizing mix.
   * For V1 models, sizing is undefined.
   */
  predictFull(features: number[]): PredictResult {
    if (isV3Model(this.weights)) {
      return this.forwardV3(features);
    }
    if (isV2Model(this.weights)) {
      return this.forwardV2(features);
    }
    return { action: this.forwardV1(features) };
  }

  /** V1 sequential forward pass */
  private forwardV1(features: number[]): StrategyMix {
    const { layers } = this.weights;
    let current = features;

    // Hidden layers (all except last) use ReLU
    for (let i = 0; i < layers.length - 1; i++) {
      current = denseForward(current, layers[i].weights, layers[i].biases, relu);
    }

    // Output layer: linear then softmax
    const lastLayer = layers[layers.length - 1];
    const logits = denseForward(current, lastLayer.weights, lastLayer.biases, null);
    const probs = softmax(logits);

    return { raise: probs[0], call: probs[1], fold: probs[2] };
  }

  /** V2 multi-head forward pass: shared backbone → action head + sizing head */
  private forwardV2(features: number[]): PredictResult {
    const { layers, actionHead, sizingHead } = this.weights;

    // Shared backbone: all layers use ReLU
    let current = features;
    for (const layer of layers) {
      current = denseForward(current, layer.weights, layer.biases, relu);
    }

    // Action head: backbone → 3 logits → softmax
    const actionLogits = denseForward(current, actionHead!.weights, actionHead!.biases, null);
    const actionProbs = softmax(actionLogits);

    // Sizing head: backbone → 5 logits → softmax
    const sizingLogits = denseForward(current, sizingHead!.weights, sizingHead!.biases, null);
    const sizingProbs = softmax(sizingLogits);

    return {
      action: {
        raise: actionProbs[0],
        call: actionProbs[1],
        fold: actionProbs[2],
      },
      sizing: {
        third: sizingProbs[0],
        half: sizingProbs[1],
        twoThirds: sizingProbs[2],
        pot: sizingProbs[3],
        allIn: sizingProbs[4],
      },
    };
  }

  /**
   * V3 embedding forward pass:
   * Extract card indices from 54-float features → embedding lookup → trunk → heads
   */
  private forwardV3(features: number[]): PredictResult {
    const w = this.weights;
    const handEmbed = w.handEmbedding!;
    const cardEmbed = w.cardEmbedding!;

    // ── Extract card indices from 54-float features ──
    const handCat = handCategoryIndex(features[0], features[1], features[2]);
    const boardIndices: number[] = [];
    for (let i = 0; i < 5; i++) boardIndices.push(boardCardIndex(features, 5 + i * 5));

    // ── Hand embedding + raw hole features → hole encoder ──
    const handVec = handEmbed[handCat]; // [embedDim]
    const holeRaw = features.slice(0, 5); // rank1, rank2, suited, paired, gap
    const holeInput = handVec.concat(holeRaw); // [embedDim + 5]
    const holeRepr = denseForward(holeInput, w.holeEncoder!.weights, w.holeEncoder!.biases, relu);

    // ── Board card embeddings → sum pool → board encoder ──
    const embedDim = cardEmbed[0].length;
    const boardSum = new Array<number>(embedDim).fill(0);
    let boardCount = 0;
    for (const idx of boardIndices) {
      if (idx < 52) {
        const vec = cardEmbed[idx];
        for (let d = 0; d < embedDim; d++) boardSum[d] += vec[d];
        boardCount++;
      }
    }
    // Mean pool (fallback to zeros if no board cards)
    if (boardCount > 0) {
      for (let d = 0; d < embedDim; d++) boardSum[d] /= boardCount;
    }
    const boardRepr = denseForward(boardSum, w.boardEncoder!.weights, w.boardEncoder!.biases, relu);

    // ── Context float features → context encoder ──
    const contextFeats = features.slice(30, 54); // 24D
    const contextRepr = denseForward(
      contextFeats,
      w.contextEncoder!.weights,
      w.contextEncoder!.biases,
      relu,
    );

    // ── Fusion: concat all three streams ──
    let current = holeRepr.concat(boardRepr, contextRepr);

    // ── Trunk with LayerNorm ──
    for (const layer of w.trunk!) {
      current = denseForward(current, layer.weights, layer.biases, null);
      current = layerNormForward(current, layer.lnScale, layer.lnBias);
      current = current.map(relu);
    }

    // ── Action head (multi-layer) ──
    let actionH = current;
    const actionLayers = w.actionHeadV3!.layers;
    for (let i = 0; i < actionLayers.length - 1; i++) {
      actionH = denseForward(actionH, actionLayers[i].weights, actionLayers[i].biases, relu);
    }
    const actionLast = actionLayers[actionLayers.length - 1];
    const actionLogits = denseForward(actionH, actionLast.weights, actionLast.biases, null);
    const actionProbs = softmax(actionLogits);

    // ── Sizing head (multi-layer) ──
    let sizingH = current;
    const sizingLayers = w.sizingHeadV3!.layers;
    for (let i = 0; i < sizingLayers.length - 1; i++) {
      sizingH = denseForward(sizingH, sizingLayers[i].weights, sizingLayers[i].biases, relu);
    }
    const sizingLast = sizingLayers[sizingLayers.length - 1];
    const sizingLogits = denseForward(sizingH, sizingLast.weights, sizingLast.biases, null);
    const sizingProbs = softmax(sizingLogits);

    return {
      action: { raise: actionProbs[0], call: actionProbs[1], fold: actionProbs[2] },
      sizing: {
        third: sizingProbs[0],
        half: sizingProbs[1],
        twoThirds: sizingProbs[2],
        pot: sizingProbs[3],
        allIn: sizingProbs[4],
      },
    };
  }

  /** Number of features the model expects */
  get inputSize(): number {
    return this.weights.inputSize;
  }

  /** Whether this is a V2 multi-head model */
  get isMultiHead(): boolean {
    return isV2Model(this.weights);
  }
}

// ── Xavier-initialized random layer ──

function createRandomLayer(fanIn: number, fanOut: number): LayerWeights {
  const scale = Math.sqrt(2 / (fanIn + fanOut));
  const weights: number[][] = [];

  for (let j = 0; j < fanOut; j++) {
    const row: number[] = [];
    for (let i = 0; i < fanIn; i++) {
      // Box-Muller transform for normal distribution
      const u1 = Math.random() || 1e-10;
      const u2 = Math.random();
      row.push(Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2) * scale);
    }
    weights.push(row);
  }

  return { weights, biases: new Array<number>(fanOut).fill(0) };
}

/**
 * Initialize a random V1 model with the given architecture.
 * Layout: [input→hidden1, hidden1→hidden2, ..., lastHidden→output]
 */
export function createRandomModel(
  inputSize: number,
  hiddenSizes: number[],
  outputSize: number,
): ModelWeights {
  const layerSizes = [inputSize, ...hiddenSizes, outputSize];
  const layers = [];

  for (let l = 0; l < layerSizes.length - 1; l++) {
    layers.push(createRandomLayer(layerSizes[l], layerSizes[l + 1]));
  }

  return {
    layers,
    inputSize,
    trainedAt: new Date().toISOString(),
    trainingSamples: 0,
    valLoss: Infinity,
  };
}

/**
 * Initialize a random V2 multi-head model.
 * Layout: backbone [input→h1, h1→h2] + actionHead [h2→3] + sizingHead [h2→5]
 */
export function createRandomModelV2(
  inputSize: number,
  hiddenSizes: number[],
  actionOutputSize: number,
  sizingOutputSize: number,
): ModelWeights {
  // Backbone layers (hidden only, no output)
  const backboneSizes = [inputSize, ...hiddenSizes];
  const layers = [];
  for (let l = 0; l < backboneSizes.length - 1; l++) {
    layers.push(createRandomLayer(backboneSizes[l], backboneSizes[l + 1]));
  }

  const lastHidden = hiddenSizes[hiddenSizes.length - 1];

  return {
    layers,
    actionHead: createRandomLayer(lastHidden, actionOutputSize),
    sizingHead: createRandomLayer(lastHidden, sizingOutputSize),
    inputSize,
    version: 'v2',
    trainedAt: new Date().toISOString(),
    trainingSamples: 0,
    valLoss: Infinity,
  };
}
