// In-memory regret and strategy storage for CFR+
// Uses Float32Array for memory efficiency and GC-friendliness.

export class InfoSetStore {
  // regretSum[infoSetKey] = Float32Array of cumulative regrets per action
  // strategySum[infoSetKey] = Float32Array of cumulative strategy weights
  private regrets = new Map<string, Float32Array>();
  private strategies = new Map<string, Float32Array>();

  get size(): number {
    return this.regrets.size;
  }

  /**
   * Get or create regret array for this info-set.
   */
  getRegret(key: string, numActions: number): Float32Array {
    let arr = this.regrets.get(key);
    if (!arr) {
      arr = new Float32Array(numActions);
      this.regrets.set(key, arr);
    }
    return arr;
  }

  /**
   * Get or create strategy-sum array for this info-set.
   */
  getStrategySum(key: string, numActions: number): Float32Array {
    let arr = this.strategies.get(key);
    if (!arr) {
      arr = new Float32Array(numActions);
      this.strategies.set(key, arr);
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
    for (const [key, stratSum] of this.strategies) {
      const numActions = stratSum.length;
      yield {
        key,
        numActions,
        averageStrategy: this.getAverageStrategy(key, numActions),
      };
    }
  }

  /**
   * Estimate memory usage in bytes.
   */
  estimateMemoryBytes(): number {
    let bytes = 0;
    for (const arr of this.regrets.values()) {
      bytes += arr.byteLength;
    }
    for (const arr of this.strategies.values()) {
      bytes += arr.byteLength;
    }
    // Rough overhead for Map entries and string keys
    bytes += this.regrets.size * 100;
    return bytes;
  }
}
