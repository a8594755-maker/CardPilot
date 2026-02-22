/**
 * Minimal Multi-Layer Perceptron (MLP) implementation.
 * Pure TypeScript, zero dependencies. Supports:
 *   - Forward pass (inference) with ReLU hidden layers + softmax output
 *   - Model loading from JSON weights
 */

import type { ModelWeights, StrategyMix } from './types.js';

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
  const exps = logits.map(v => Math.exp(v - maxVal));
  const sum = exps.reduce((a, b) => a + b, 0);
  return exps.map(e => e / sum);
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

export class MLP {
  private weights: ModelWeights;

  constructor(weights: ModelWeights) {
    this.weights = weights;
  }

  /**
   * Forward pass: features → {raise, call, fold} probabilities.
   * Hidden layers use ReLU, output uses softmax.
   */
  predict(features: number[]): StrategyMix {
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

    return {
      raise: probs[0],
      call: probs[1],
      fold: probs[2],
    };
  }

  /** Number of features the model expects */
  get inputSize(): number {
    return this.weights.inputSize;
  }
}

/**
 * Initialize a random model with the given architecture.
 * Uses Xavier initialization for weights.
 */
export function createRandomModel(
  inputSize: number,
  hiddenSizes: number[],
  outputSize: number,
): ModelWeights {
  const layerSizes = [inputSize, ...hiddenSizes, outputSize];
  const layers = [];

  for (let l = 0; l < layerSizes.length - 1; l++) {
    const fanIn = layerSizes[l];
    const fanOut = layerSizes[l + 1];
    const scale = Math.sqrt(2 / (fanIn + fanOut)); // Xavier init

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

    const biases = new Array<number>(fanOut).fill(0);
    layers.push({ weights, biases });
  }

  return {
    layers,
    inputSize,
    trainedAt: new Date().toISOString(),
    trainingSamples: 0,
    valLoss: Infinity,
  };
}
