import { existsSync } from 'node:fs';
import type {
  PostflopOracle,
  PostflopOracleBatchRequest,
  PostflopOracleBatchResult,
  PostflopOracleSample,
} from './postflop-oracle.js';
import { toFloat32Vector } from './postflop-oracle.js';

const dynamicImport = new Function('modulePath', 'return import(modulePath);') as (
  modulePath: string,
) => Promise<any>;

export interface FvnRuntimeOptions {
  modelPath?: string;
  minBatchSize?: number;
  maxBatchSize?: number;
  forceCpu?: boolean;
  verbose?: boolean;
  allowSyntheticFallback?: boolean;
}

interface OrtSession {
  inputNames: string[];
  outputNames: string[];
  run(feeds: Record<string, unknown>): Promise<Record<string, { data: Float32Array | number[] }>>;
}

function batchBounds(options: FvnRuntimeOptions): { minBatchSize: number; maxBatchSize: number } {
  const minBatch = Math.max(1, options.minBatchSize ?? 1024);
  const envMax = Number(process.env.EZ_GTO_FVN_MAX_BATCH ?? 0);
  const maxFromEnv = Number.isFinite(envMax) && envMax > 0 ? envMax : undefined;
  const maxBatch = Math.max(minBatch, options.maxBatchSize ?? maxFromEnv ?? 8192);
  return { minBatchSize: minBatch, maxBatchSize: maxBatch };
}

function syntheticEv(sample: PostflopOracleSample): number {
  const vec = toFloat32Vector(sample.featureVector);
  let acc = 0;
  for (let i = 0; i < vec.length; i++) {
    const weight = (i % 17) * 0.013 + 0.07;
    acc += vec[i] * weight;
  }
  return Math.tanh(acc / Math.max(1, vec.length)) * 5;
}

function createSyntheticOracle(options: FvnRuntimeOptions): PostflopOracle {
  const bounds = batchBounds(options);
  return {
    provider: 'synthetic-fallback',
    coverage: 'approx',
    minBatchSize: bounds.minBatchSize,
    maxBatchSize: bounds.maxBatchSize,
    async evaluateBatch(input: PostflopOracleBatchRequest): Promise<PostflopOracleBatchResult> {
      const start = Date.now();
      const results = input.samples.map((sample) => ({ ev: syntheticEv(sample) }));
      return {
        provider: 'synthetic-fallback',
        coverage: 'approx',
        batchSize: input.samples.length,
        latencyMs: Date.now() - start,
        results,
      };
    },
    async dispose(): Promise<void> {},
  };
}

async function createOrtSession(
  modelPath: string,
  forceCpu: boolean,
  verbose: boolean,
): Promise<{
  ort: any;
  session: OrtSession;
  provider: string;
}> {
  const ort = await dynamicImport('onnxruntime-node');

  const supportedBackends = new Set<string>();
  if (!forceCpu && typeof ort.listSupportedBackends === 'function') {
    try {
      const listed = await ort.listSupportedBackends();
      if (Array.isArray(listed)) {
        for (const entry of listed) {
          if (entry && typeof entry.name === 'string') {
            supportedBackends.add(entry.name.toLowerCase());
          }
        }
      }
    } catch (error) {
      if (verbose) {
        console.warn('  [FVN] failed to query supported backends:', error);
      }
    }
  }

  const primaryProviders: string[] = [];
  if (!forceCpu) {
    if (supportedBackends.has('cuda')) primaryProviders.push('cuda');
    if (supportedBackends.has('dml')) primaryProviders.push('dml');
    if (supportedBackends.has('webgpu')) primaryProviders.push('webgpu');
  }

  const providerAttempts: string[][] = forceCpu
    ? [['cpu']]
    : primaryProviders.length > 0
      ? primaryProviders.map((p) => [p, 'cpu']).concat([['cpu']])
      : [['cpu']];

  let lastError: unknown;
  for (const providers of providerAttempts) {
    try {
      const session = (await ort.InferenceSession.create(modelPath, {
        executionProviders: providers,
        graphOptimizationLevel: 'all',
      })) as OrtSession;

      const primary = providers[0] ?? 'cpu';
      const providerLabel = `onnxruntime-${primary}`;
      if (verbose) {
        console.log(`  [FVN] loaded ${modelPath} with providers=${providers.join(',')}`);
      }
      return { ort, session, provider: providerLabel };
    } catch (error) {
      lastError = error;
      if (verbose) {
        console.warn(`  [FVN] provider attempt failed (${providers.join(',')}):`, error);
      }
    }
  }

  throw lastError instanceof Error ? lastError : new Error('failed to create ONNX runtime session');
}

function flattenBatch(
  samples: PostflopOracleSample[],
  expectedBatch: number,
): {
  featureSize: number;
  data: Float32Array;
} {
  if (samples.length === 0) {
    return { featureSize: 0, data: new Float32Array(0) };
  }

  const vectors = samples.map((sample) => toFloat32Vector(sample.featureVector));
  const featureSize = vectors[0].length;
  for (let i = 1; i < vectors.length; i++) {
    if (vectors[i].length !== featureSize) {
      throw new Error(
        `inconsistent feature size in batch (${vectors[i].length} vs ${featureSize})`,
      );
    }
  }

  const batchSize = Math.max(samples.length, expectedBatch);
  const data = new Float32Array(batchSize * featureSize);

  for (let i = 0; i < batchSize; i++) {
    const src = vectors[i < vectors.length ? i : vectors.length - 1];
    data.set(src, i * featureSize);
  }

  return { featureSize, data };
}

function isOomError(error: unknown): boolean {
  const text = error instanceof Error ? error.message : String(error);
  return /out of memory|oom|cuda_error_out_of_memory/i.test(text);
}

export async function createFvnRuntime(options: FvnRuntimeOptions = {}): Promise<PostflopOracle> {
  const bounds = batchBounds(options);
  const modelPath = options.modelPath?.trim();
  const allowSynthetic = options.allowSyntheticFallback ?? true;

  if (!modelPath || !existsSync(modelPath)) {
    if (!allowSynthetic) {
      throw new Error('FVN model is required but not found');
    }
    if (options.verbose) {
      console.warn('[FVN] model not found, using synthetic fallback');
    }
    return createSyntheticOracle(options);
  }

  let ortBundle: { ort: any; session: OrtSession; provider: string };
  try {
    ortBundle = await createOrtSession(
      modelPath,
      options.forceCpu ?? false,
      options.verbose ?? false,
    );
  } catch (error) {
    if (!allowSynthetic) {
      throw error instanceof Error ? error : new Error(String(error));
    }
    if (options.verbose) {
      console.warn('[FVN] failed to initialize onnxruntime-node, using synthetic fallback:', error);
    }
    return createSyntheticOracle(options);
  }

  const { ort, session, provider } = ortBundle;
  const inputName = session.inputNames[0];
  const outputName = session.outputNames[0];

  async function runChunkWithFallback(
    samples: PostflopOracleSample[],
    targetBatch: number,
  ): Promise<number[]> {
    let currentBatch = targetBatch;

    while (currentBatch >= samples.length) {
      try {
        const { featureSize, data } = flattenBatch(samples, currentBatch);
        const tensor = new ort.Tensor('float32', data, [
          Math.max(samples.length, currentBatch),
          featureSize,
        ]);
        const output = await session.run({ [inputName]: tensor });
        const out = output[outputName];
        if (!out || !out.data) {
          throw new Error(`FVN output '${outputName}' missing`);
        }

        const flat = Array.from(out.data as Float32Array | number[]);
        return flat.slice(0, samples.length).map(Number);
      } catch (error) {
        if (
          !isOomError(error) ||
          currentBatch <= samples.length ||
          currentBatch <= bounds.minBatchSize
        ) {
          throw error;
        }
        currentBatch = Math.max(bounds.minBatchSize, Math.floor(currentBatch / 2));
        if (options.verbose) {
          console.warn(`[FVN] OOM fallback triggered, reducing batch to ${currentBatch}`);
        }
      }
    }

    throw new Error('unable to run batch inference');
  }

  return {
    provider,
    coverage: 'approx',
    minBatchSize: bounds.minBatchSize,
    maxBatchSize: bounds.maxBatchSize,
    async evaluateBatch(input: PostflopOracleBatchRequest): Promise<PostflopOracleBatchResult> {
      const start = Date.now();
      if (!input.samples.length) {
        return {
          provider,
          coverage: 'approx',
          batchSize: 0,
          latencyMs: 0,
          results: [],
        };
      }

      const requested = input.requestedBatchSize ?? bounds.maxBatchSize;
      const maxBatch = Math.max(bounds.minBatchSize, Math.min(requested, bounds.maxBatchSize));
      const results: number[] = [];

      for (let i = 0; i < input.samples.length; i += maxBatch) {
        const chunk = input.samples.slice(i, i + maxBatch);
        const chunkValues = await runChunkWithFallback(
          chunk,
          Math.max(bounds.minBatchSize, chunk.length),
        );
        results.push(...chunkValues);
      }

      return {
        provider,
        coverage: 'approx',
        batchSize: input.samples.length,
        latencyMs: Date.now() - start,
        results: results.map((ev) => ({ ev })),
      };
    },
    async dispose(): Promise<void> {},
  };
}
