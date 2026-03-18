/**
 * @cardpilot/fast-model — Imitation-learned fast advice model
 *
 * Public API:
 *   - encodeFeatures()    — V1: convert game state to 48-feature vector
 *   - encodeFeaturesV2()  — V2: convert game state to 54-feature vector
 *   - MLP                 — forward-pass inference (V1 single-head + V2 multi-head)
 *   - loadModel()         — load trained model from disk
 *   - evaluateModel()     — offline evaluation metrics
 *   - FEATURE_COUNT       — V1 feature vector length (48)
 *   - FEATURE_COUNT_V2    — V2 feature vector length (54)
 */

export {
  encodeFeatures,
  encodeFeaturesV2,
  FEATURE_COUNT,
  FEATURE_COUNT_V2,
} from './feature-encoder.js';
export type { ActionRecord, PlayerRecord } from './feature-encoder.js';
export { MLP, createRandomModel, createRandomModelV2 } from './mlp.js';
export { evaluateModel, printMetrics } from './evaluate.js';
export type { EvalMetrics, CalibrationBin, StreetMetrics } from './evaluate.js';
export type {
  ModelWeights,
  TrainingSample,
  StrategyMix,
  SizingMix,
  PredictResult,
  LayerWeights,
} from './types.js';

import { readFileSync, existsSync } from 'node:fs';
import { MLP } from './mlp.js';
import type { ModelWeights } from './types.js';

/**
 * Load a trained model from a JSON file.
 * Returns null if the file doesn't exist (graceful fallback).
 * Works for both V1 and V2 models.
 */
export function loadModel(path: string): MLP | null {
  if (!existsSync(path)) return null;
  try {
    const raw = readFileSync(path, 'utf-8');
    const weights: ModelWeights = JSON.parse(raw);
    return new MLP(weights);
  } catch {
    return null;
  }
}
