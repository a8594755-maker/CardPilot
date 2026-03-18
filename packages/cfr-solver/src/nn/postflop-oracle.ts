export type OracleCoverage = 'exact' | 'approx';

export interface PostflopOracleSample {
  /** Spot identifier from the preflop traversal context. */
  spotId: string;
  /** Flattened numeric features consumed by the value model. */
  featureVector: number[] | Float32Array;
  /** Optional metadata for logging/debug only. */
  metadata?: Record<string, string | number | boolean>;
}

export interface PostflopOracleBatchRequest {
  samples: PostflopOracleSample[];
  /** Optional hard override; runtime still enforces provider limits. */
  requestedBatchSize?: number;
}

export interface PostflopOracleSampleResult {
  /** Predicted EV in bb for the hero perspective. */
  ev: number;
  /** Optional confidence/uncertainty signal. */
  uncertainty?: number;
}

export interface PostflopOracleBatchResult {
  provider: string;
  coverage: OracleCoverage;
  batchSize: number;
  latencyMs: number;
  results: PostflopOracleSampleResult[];
}

export interface PostflopOracle {
  provider: string;
  coverage: OracleCoverage;
  minBatchSize: number;
  maxBatchSize: number;
  evaluateBatch(input: PostflopOracleBatchRequest): Promise<PostflopOracleBatchResult>;
  dispose(): Promise<void>;
}

export function toFloat32Vector(vector: number[] | Float32Array): Float32Array {
  return vector instanceof Float32Array ? vector : Float32Array.from(vector);
}
