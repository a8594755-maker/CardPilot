/**
 * Singleton manager for the CoachingOracle ONNX session.
 *
 * Lazily loads the model on first request and keeps it resident in memory.
 * Typical inference latency: ~10ms on CPU, ~2ms on GPU.
 */

import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { existsSync } from 'node:fs';
import { createCoachingOracle, type CoachingOracle } from '@cardpilot/cfr-solver';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Default model paths (searched in order)
const MODEL_CANDIDATES = [
  process.env.EZ_GTO_COACHING_MODEL,
  resolve(__dirname, '../../../../data/nn-training/coaching_v2.1.onnx'),
  resolve(__dirname, '../../../../data/nn-training/coaching_v2.onnx'),
  resolve(__dirname, '../../../../data/nn-training/coaching_v2_test.onnx'),
  resolve(__dirname, '../../../../data/nn-training/coaching_v1.onnx'),
].filter(Boolean) as string[];

let oraclePromise: Promise<CoachingOracle> | null = null;
let resolvedPath: string | null = null;

/**
 * Get the singleton CoachingOracle instance.
 * Creates the session on first call; subsequent calls return the cached instance.
 */
export function getCoachingOracle(): Promise<CoachingOracle> {
  if (!oraclePromise) {
    oraclePromise = initOracle();
  }
  return oraclePromise;
}

/** Returns the model path that was loaded, or null if not yet loaded. */
export function getModelPath(): string | null {
  return resolvedPath;
}

async function initOracle(): Promise<CoachingOracle> {
  const modelPath = MODEL_CANDIDATES.find((p) => existsSync(p));
  if (!modelPath) {
    const searched = MODEL_CANDIDATES.join(', ');
    throw new Error(
      `No coaching model found. Searched: ${searched}. ` +
        `Set EZ_GTO_COACHING_MODEL env var or place a .onnx file in data/nn-training/.`,
    );
  }

  resolvedPath = modelPath;
  console.log(`[coaching-oracle] Loading model: ${modelPath}`);

  const oracle = await createCoachingOracle({
    modelPath,
    forceCpu: process.env.EZ_GTO_FORCE_CPU === '1',
    verbose: true,
  });

  console.log(`[coaching-oracle] Ready (provider: ${oracle.provider})`);
  return oracle;
}
