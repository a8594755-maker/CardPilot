// In-memory regret and strategy storage for CFR+
// Uses Float32Array for memory efficiency and GC-friendliness.

// A single V8 Map caps at ~16.7M (2^24) entries. Deep (200bb) trees exceed this
// per board, so we shard each store across SHARD_COUNT Maps keyed by a hash of the
// info-set key. Behaviour is otherwise identical (same keys → same arrays).
const SHARD_COUNT = 16; // must be a power of two
const SHARD_MASK = SHARD_COUNT - 1;

/** djb2 string hash, masked to the shard count. */
function shardIndex(key: string): number {
  let h = 5381;
  for (let i = 0; i < key.length; i++) {
    h = (h * 33) ^ key.charCodeAt(i);
  }
  return (h >>> 0) & SHARD_MASK;
}

export class InfoSetStore {
  // regretSum[infoSetKey] = Float32Array of cumulative regrets per action
  // strategySum[infoSetKey] = Float32Array of cumulative strategy weights
  // Sharded across SHARD_COUNT Maps to bypass the 16.7M single-Map limit.
  private regretShards: Array<Map<string, Float32Array>> = Array.from(
    { length: SHARD_COUNT },
    () => new Map<string, Float32Array>(),
  );
  private strategyShards: Array<Map<string, Float32Array>> = Array.from(
    { length: SHARD_COUNT },
    () => new Map<string, Float32Array>(),
  );

  get size(): number {
    let n = 0;
    for (const shard of this.regretShards) n += shard.size;
    return n;
  }

  /**
   * Get or create regret array for this info-set.
   */
  getRegret(key: string, numActions: number): Float32Array {
    const shard = this.regretShards[shardIndex(key)];
    let arr = shard.get(key);
    if (!arr) {
      arr = new Float32Array(numActions);
      shard.set(key, arr);
    }
    return arr;
  }

  /**
   * Get or create strategy-sum array for this info-set.
   */
  getStrategySum(key: string, numActions: number): Float32Array {
    const shard = this.strategyShards[shardIndex(key)];
    let arr = shard.get(key);
    if (!arr) {
      arr = new Float32Array(numActions);
      shard.set(key, arr);
    }
    return arr;
  }

  /**
   * Regret matching: convert cumulative regrets to current iteration strategy.
   * In CFR+, all regrets are already >= 0.
   */
  getCurrentStrategy(key: string, numActions: number): Float32Array {
    const regret = this.getRegret(key, numActions);
    const strategy = new Float32Array(numActions);
    let sum = 0;

    for (let i = 0; i < numActions; i++) {
      const r = regret[i]; // already >= 0 in CFR+
      strategy[i] = r;
      sum += r;
    }

    if (sum > 0) {
      for (let i = 0; i < numActions; i++) {
        strategy[i] /= sum;
      }
    } else {
      // Uniform when all regrets are zero
      const uniform = 1 / numActions;
      for (let i = 0; i < numActions; i++) {
        strategy[i] = uniform;
      }
    }

    return strategy;
  }

  /**
   * Regret matching into a pre-allocated buffer (zero-allocation hot path).
   */
  getCurrentStrategyInto(key: string, numActions: number, out: Float32Array): Float32Array {
    const regret = this.getRegret(key, numActions);
    let sum = 0;

    for (let i = 0; i < numActions; i++) {
      const r = regret[i];
      out[i] = r;
      sum += r;
    }

    if (sum > 0) {
      for (let i = 0; i < numActions; i++) {
        out[i] /= sum;
      }
    } else {
      const uniform = 1 / numActions;
      for (let i = 0; i < numActions; i++) {
        out[i] = uniform;
      }
    }

    return out;
  }

  /**
   * Get the average strategy (converged Nash approximation).
   * This is what gets exported to the reference library.
   */
  getAverageStrategy(key: string, numActions: number): Float32Array {
    const stratSum = this.getStrategySum(key, numActions);
    const strategy = new Float32Array(numActions);
    let sum = 0;

    for (let i = 0; i < numActions; i++) {
      sum += stratSum[i];
    }

    if (sum > 0) {
      for (let i = 0; i < numActions; i++) {
        strategy[i] = stratSum[i] / sum;
      }
    } else {
      const uniform = 1 / numActions;
      for (let i = 0; i < numActions; i++) {
        strategy[i] = uniform;
      }
    }

    return strategy;
  }

  /**
   * Update regrets for CFR+: add regret delta and floor at 0.
   */
  updateRegret(key: string, actionIndex: number, delta: number, numActions: number): void {
    const regret = this.getRegret(key, numActions);
    regret[actionIndex] = Math.max(0, regret[actionIndex] + delta);
  }

  /**
   * Accumulate strategy weight.
   */
  addStrategyWeight(key: string, actionIndex: number, weight: number, numActions: number): void {
    const stratSum = this.getStrategySum(key, numActions);
    stratSum[actionIndex] += weight;
  }

  /**
   * Iterate over all info-sets for export.
   */
  *entries(): IterableIterator<{
    key: string;
    numActions: number;
    averageStrategy: Float32Array;
  }> {
    for (const shard of this.strategyShards) {
      for (const [key, stratSum] of shard) {
        const numActions = stratSum.length;
        yield {
          key,
          numActions,
          averageStrategy: this.getAverageStrategy(key, numActions),
        };
      }
    }
  }

  /**
   * Estimate memory usage in bytes.
   */
  estimateMemoryBytes(): number {
    let bytes = 0;
    for (const shard of this.regretShards) {
      for (const arr of shard.values()) bytes += arr.byteLength;
    }
    for (const shard of this.strategyShards) {
      for (const arr of shard.values()) bytes += arr.byteLength;
    }
    // Rough overhead for Map entries and string keys
    bytes += this.size * 100;
    return bytes;
  }
}
