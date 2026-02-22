/**
 * Offline evaluation metrics for model quality assessment.
 *
 * Computes KL divergence, Top-1 accuracy, calibration, and per-street
 * breakdown after each training run. Used to compare V1 vs V2 models.
 */

import type { ModelWeights, TrainingSample } from './types.js';

// ── Types ──

export interface CalibrationBin {
  binCenter: number;
  avgConfidence: number;
  avgAccuracy: number;
  count: number;
}

export interface StreetMetrics {
  klDivergence: number;
  top1Accuracy: number;
  sampleCount: number;
}

export interface EvalMetrics {
  klDivergence: number;
  top1Accuracy: number;
  calibration: CalibrationBin[];
  perStreet: Record<string, StreetMetrics>;
  sizingTop1Accuracy?: number;  // V2 only: sizing head accuracy
  sampleCount: number;
}

// ── Forward pass (standalone, doesn't import MLP to avoid circular deps) ──

function relu(x: number): number {
  return x > 0 ? x : 0;
}

function softmax(logits: number[]): number[] {
  const maxVal = Math.max(...logits);
  const exps = logits.map(v => Math.exp(v - maxVal));
  const sum = exps.reduce((a, b) => a + b, 0);
  return exps.map(e => e / sum);
}

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

interface PredictionResult {
  actionProbs: number[];
  sizingProbs?: number[];
}

function predict(model: ModelWeights, features: number[]): PredictionResult {
  const isV2 = !!(model.actionHead && model.sizingHead);

  if (isV2) {
    // V2: backbone → two heads
    let current = features;
    for (const layer of model.layers) {
      current = denseForward(current, layer.weights, layer.biases, relu);
    }
    const actionLogits = denseForward(current, model.actionHead!.weights, model.actionHead!.biases, null);
    const sizingLogits = denseForward(current, model.sizingHead!.weights, model.sizingHead!.biases, null);
    return {
      actionProbs: softmax(actionLogits),
      sizingProbs: softmax(sizingLogits),
    };
  } else {
    // V1: sequential
    let current = features;
    for (let i = 0; i < model.layers.length - 1; i++) {
      current = denseForward(current, model.layers[i].weights, model.layers[i].biases, relu);
    }
    const last = model.layers[model.layers.length - 1];
    const logits = denseForward(current, last.weights, last.biases, null);
    return { actionProbs: softmax(logits) };
  }
}

// ── Metric computations ──

function klDivergence(teacher: number[], student: number[]): number {
  let kl = 0;
  for (let i = 0; i < teacher.length; i++) {
    const p = Math.max(teacher[i], 1e-10);
    const q = Math.max(student[i], 1e-10);
    kl += p * Math.log(p / q);
  }
  return Math.max(0, kl); // clamp rounding errors
}

function argmax(arr: number[]): number {
  let maxIdx = 0;
  for (let i = 1; i < arr.length; i++) {
    if (arr[i] > arr[maxIdx]) maxIdx = i;
  }
  return maxIdx;
}

// ── Main export ──

/**
 * Evaluate a trained model against validation samples.
 * Computes KL divergence, Top-1 accuracy, calibration, and per-street metrics.
 */
export function evaluateModel(model: ModelWeights, samples: TrainingSample[]): EvalMetrics {
  if (samples.length === 0) {
    return {
      klDivergence: 0, top1Accuracy: 0, calibration: [],
      perStreet: {}, sampleCount: 0,
    };
  }

  const isV2 = !!(model.actionHead && model.sizingHead);
  let totalKL = 0;
  let top1Matches = 0;
  let sizingMatches = 0;
  let sizingTotal = 0;

  // Per-street accumulators
  const streetKL: Record<string, number[]> = {};
  const streetTop1: Record<string, boolean[]> = {};

  // Calibration bins (10 bins: 0-0.1, 0.1-0.2, ..., 0.9-1.0)
  const NUM_BINS = 10;
  const binConfidence: number[][] = Array.from({ length: NUM_BINS }, () => []);
  const binCorrect: boolean[][] = Array.from({ length: NUM_BINS }, () => []);

  for (const sample of samples) {
    const pred = predict(model, sample.f);
    const teacher = sample.l;
    const student = pred.actionProbs;

    // KL divergence
    const kl = klDivergence(teacher, student);
    totalKL += kl;

    // Top-1 accuracy
    const teacherAction = argmax(teacher);
    const studentAction = argmax(student);
    const match = teacherAction === studentAction;
    if (match) top1Matches++;

    // Calibration: bin by student's confidence (max prob)
    const confidence = Math.max(...student);
    const binIdx = Math.min(Math.floor(confidence * NUM_BINS), NUM_BINS - 1);
    binConfidence[binIdx].push(confidence);
    binCorrect[binIdx].push(match);

    // Per-street
    const street = sample.s || 'UNKNOWN';
    if (!streetKL[street]) { streetKL[street] = []; streetTop1[street] = []; }
    streetKL[street].push(kl);
    streetTop1[street].push(match);

    // V2: sizing accuracy (only when teacher says raise is significant)
    if (isV2 && sample.sz && pred.sizingProbs && teacher[0] > 0.2) {
      const teacherSizing = argmax(sample.sz);
      const studentSizing = argmax(pred.sizingProbs);
      if (teacherSizing === studentSizing) sizingMatches++;
      sizingTotal++;
    }
  }

  // Build calibration bins
  const calibration: CalibrationBin[] = [];
  for (let b = 0; b < NUM_BINS; b++) {
    const count = binConfidence[b].length;
    if (count === 0) {
      calibration.push({ binCenter: (b + 0.5) / NUM_BINS, avgConfidence: 0, avgAccuracy: 0, count: 0 });
      continue;
    }
    const avgConf = binConfidence[b].reduce((a, v) => a + v, 0) / count;
    const avgAcc = binCorrect[b].filter(Boolean).length / count;
    calibration.push({ binCenter: (b + 0.5) / NUM_BINS, avgConfidence: avgConf, avgAccuracy: avgAcc, count });
  }

  // Build per-street metrics
  const perStreet: Record<string, StreetMetrics> = {};
  for (const street of Object.keys(streetKL)) {
    const kls = streetKL[street];
    const tops = streetTop1[street];
    perStreet[street] = {
      klDivergence: kls.reduce((a, v) => a + v, 0) / kls.length,
      top1Accuracy: tops.filter(Boolean).length / tops.length,
      sampleCount: kls.length,
    };
  }

  const result: EvalMetrics = {
    klDivergence: totalKL / samples.length,
    top1Accuracy: top1Matches / samples.length,
    calibration,
    perStreet,
    sampleCount: samples.length,
  };

  if (isV2 && sizingTotal > 0) {
    result.sizingTop1Accuracy = sizingMatches / sizingTotal;
  }

  return result;
}

/**
 * Print evaluation metrics to console in a readable format.
 */
export function printMetrics(metrics: EvalMetrics): void {
  console.log('\n=== Evaluation Metrics ===');
  console.log(`  KL Divergence:    ${metrics.klDivergence.toFixed(4)}`);
  console.log(`  Top-1 Accuracy:   ${(metrics.top1Accuracy * 100).toFixed(1)}%`);
  if (metrics.sizingTop1Accuracy != null) {
    console.log(`  Sizing Accuracy:  ${(metrics.sizingTop1Accuracy * 100).toFixed(1)}%`);
  }
  console.log(`  Samples:          ${metrics.sampleCount}`);

  console.log('  Per-Street:');
  for (const [street, sm] of Object.entries(metrics.perStreet)) {
    console.log(
      `    ${street.padEnd(8)}: ` +
      `KL=${sm.klDivergence.toFixed(4)}  ` +
      `Acc=${(sm.top1Accuracy * 100).toFixed(1)}%  ` +
      `N=${sm.sampleCount}`
    );
  }

  console.log('  Calibration:');
  for (const bin of metrics.calibration) {
    if (bin.count > 0) {
      console.log(
        `    [${(bin.binCenter - 0.05).toFixed(2)}-${(bin.binCenter + 0.05).toFixed(2)}]: ` +
        `conf=${bin.avgConfidence.toFixed(3)}  ` +
        `acc=${bin.avgAccuracy.toFixed(3)}  ` +
        `n=${bin.count}`
      );
    }
  }
}
