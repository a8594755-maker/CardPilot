/**
 * @cardpilot/fast-model — Imitation-learned fast advice model
 *
 * Public API:
 *   - encodeFeatures()  — convert game state to feature vector
 *   - MLP               — forward-pass inference
 *   - loadModel()        — load trained model from disk
 *   - FEATURE_COUNT      — expected feature vector length
 */

export { encodeFeatures, FEATURE_COUNT } from './feature-encoder.js';
export { MLP, createRandomModel } from './mlp.js';
export type { ModelWeights, TrainingSample, StrategyMix, LayerWeights } from './types.js';

import { readFileSync, existsSync } from 'node:fs';
import { MLP } from './mlp.js';
import type { ModelWeights } from './types.js';

/**
 * Load a trained model from a JSON file.
 * Returns null if the file doesn't exist (graceful fallback).
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
