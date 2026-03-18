// Contiguous TypedArray storage for vectorized CFR+ regrets and strategy sums.
//
// Instead of Map<string, Float32Array> (one small array per info-set),
// we use two giant Float32Arrays where all data is packed contiguously.
//
// Memory layout per node:
//   regrets[nodeOffset[nodeId] + actionIndex * numCombos + comboId]
//   strategySums[nodeOffset[nodeId] + actionIndex * numCombos + comboId]
//
// This gives maximum cache locality and zero GC pressure.

import type { FlatTree } from './flat-tree.js';

export class ArrayStore {
  readonly numCombos: number;
  readonly totalActions: number;
  readonly numNodes: number;

  /** Cumulative action offset for each node into regrets/strategySums */
  readonly nodeOffset: Uint32Array;

  /** Contiguous regret storage: totalActions * numCombos floats */
  regrets: Float32Array;

  /** Contiguous strategy sum storage: totalActions * numCombos floats */
  strategySums: Float32Array;

  constructor(tree: FlatTree, numCombos: number) {
    this.numCombos = numCombos;
    this.totalActions = tree.totalActions;
    this.numNodes = tree.numNodes;

    // Build nodeOffset: maps nodeId → offset into the flat regret/strategy arrays
    this.nodeOffset = new Uint32Array(tree.numNodes);
    let offset = 0;
    for (let n = 0; n < tree.numNodes; n++) {
      this.nodeOffset[n] = offset;
      offset += tree.nodeNumActions[n] * numCombos;
    }

    const totalSize = offset; // should equal tree.totalActions * numCombos
    this.regrets = new Float32Array(totalSize);
    this.strategySums = new Float32Array(totalSize);
  }

  /**
   * Get the index into regrets/strategySums for a specific
   * (nodeId, actionIndex, comboId) triple.
   */
  index(nodeId: number, actionIndex: number, comboId: number): number {
    return this.nodeOffset[nodeId] + actionIndex * this.numCombos + comboId;
  }

  /**
   * Compute current strategy via regret matching for ALL combos at a node.
   * Writes into the provided output buffer.
   *
   * Output layout: out[actionIndex * numCombos + comboId] = strategy probability
   */
  getCurrentStrategy(nodeId: number, numActions: number, out: Float32Array): void {
    const base = this.nodeOffset[nodeId];
    const nc = this.numCombos;

    for (let c = 0; c < nc; c++) {
      // Sum positive regrets across actions for this combo
      let sum = 0;
      for (let a = 0; a < numActions; a++) {
        const r = this.regrets[base + a * nc + c];
        sum += r; // CFR+: regrets are already floored at 0
      }

      if (sum > 0) {
        for (let a = 0; a < numActions; a++) {
          out[a * nc + c] = this.regrets[base + a * nc + c] / sum;
        }
      } else {
        const uniform = 1 / numActions;
        for (let a = 0; a < numActions; a++) {
          out[a * nc + c] = uniform;
        }
      }
    }
  }

  /**
   * Get the average (converged) strategy for ALL combos at a node.
   * This is what gets exported as the GTO solution.
   */
  getAverageStrategy(nodeId: number, numActions: number, out: Float32Array): void {
    const base = this.nodeOffset[nodeId];
    const nc = this.numCombos;

    for (let c = 0; c < nc; c++) {
      let sum = 0;
      for (let a = 0; a < numActions; a++) {
        sum += this.strategySums[base + a * nc + c];
      }

      if (sum > 0) {
        for (let a = 0; a < numActions; a++) {
          out[a * nc + c] = this.strategySums[base + a * nc + c] / sum;
        }
      } else {
        // Zero-reach combo: default to most passive action (index 0 = fold/check).
        // This avoids polluting output with uniform noise for unreachable combos.
        for (let a = 0; a < numActions; a++) {
          out[a * nc + c] = a === 0 ? 1 : 0;
        }
      }
    }
  }

  /**
   * Like getCurrentStrategy but writes into `out` starting at `baseOffset`.
   * Output layout: out[baseOffset + actionIndex * numCombos + comboId]
   * Zero-allocation friendly — no new arrays created.
   */
  getCurrentStrategyAt(
    nodeId: number,
    numActions: number,
    out: Float32Array,
    baseOffset: number,
  ): void {
    const base = this.nodeOffset[nodeId];
    const nc = this.numCombos;

    for (let c = 0; c < nc; c++) {
      let sum = 0;
      for (let a = 0; a < numActions; a++) {
        const r = this.regrets[base + a * nc + c];
        sum += r;
      }

      if (sum > 0) {
        for (let a = 0; a < numActions; a++) {
          out[baseOffset + a * nc + c] = this.regrets[base + a * nc + c] / sum;
        }
      } else {
        const uniform = 1 / numActions;
        for (let a = 0; a < numActions; a++) {
          out[baseOffset + a * nc + c] = uniform;
        }
      }
    }
  }

  /**
   * Like updateRegrets but reads deltas from `deltas` starting at `baseOffset`.
   * Zero-allocation friendly.
   */
  updateRegretsAt(
    nodeId: number,
    numActions: number,
    deltas: Float32Array,
    baseOffset: number,
  ): void {
    const base = this.nodeOffset[nodeId];
    const nc = this.numCombos;

    for (let a = 0; a < numActions; a++) {
      const aOffset = base + a * nc;
      const dOffset = baseOffset + a * nc;
      for (let c = 0; c < nc; c++) {
        const newVal = this.regrets[aOffset + c] + deltas[dOffset + c];
        this.regrets[aOffset + c] = newVal > 0 ? newVal : 0;
      }
    }
  }

  /**
   * Like addStrategyWeights but reads from `weights` starting at `baseOffset`.
   * Zero-allocation friendly.
   */
  addStrategyWeightsAt(
    nodeId: number,
    numActions: number,
    weights: Float32Array,
    baseOffset: number,
  ): void {
    const base = this.nodeOffset[nodeId];
    const nc = this.numCombos;

    for (let a = 0; a < numActions; a++) {
      const aOffset = base + a * nc;
      const wOffset = baseOffset + a * nc;
      for (let c = 0; c < nc; c++) {
        this.strategySums[aOffset + c] += weights[wOffset + c];
      }
    }
  }

  /**
   * Update regrets with CFR+ flooring (max(0, ...)) for ALL combos at a node.
   *
   * For each action a and combo c:
   *   regret[a][c] = max(0, regret[a][c] + delta[a * numCombos + c])
   */
  updateRegrets(nodeId: number, numActions: number, deltas: Float32Array): void {
    const base = this.nodeOffset[nodeId];
    const nc = this.numCombos;

    for (let a = 0; a < numActions; a++) {
      const aOffset = base + a * nc;
      const dOffset = a * nc;
      for (let c = 0; c < nc; c++) {
        const newVal = this.regrets[aOffset + c] + deltas[dOffset + c];
        this.regrets[aOffset + c] = newVal > 0 ? newVal : 0;
      }
    }
  }

  /**
   * Accumulate strategy weights for ALL combos at a node.
   */
  addStrategyWeights(nodeId: number, numActions: number, weights: Float32Array): void {
    const base = this.nodeOffset[nodeId];
    const nc = this.numCombos;

    for (let a = 0; a < numActions; a++) {
      const aOffset = base + a * nc;
      const wOffset = a * nc;
      for (let c = 0; c < nc; c++) {
        this.strategySums[aOffset + c] += weights[wOffset + c];
      }
    }
  }

  /**
   * Estimate memory usage in bytes.
   */
  estimateMemoryBytes(): number {
    return this.regrets.byteLength + this.strategySums.byteLength + this.nodeOffset.byteLength;
  }

  /**
   * Reset all regrets and strategy sums to zero.
   */
  reset(): void {
    this.regrets.fill(0);
    this.strategySums.fill(0);
  }

  /**
   * Re-initialize for a different numCombos without reallocating
   * backing arrays (unless the new size exceeds capacity).
   * Recomputes nodeOffset and zeroes used regions.
   */
  reinit(tree: FlatTree, newNumCombos: number): void {
    (this as { numCombos: number }).numCombos = newNumCombos;

    // Recompute offsets for the new combo count
    let offset = 0;
    for (let n = 0; n < tree.numNodes; n++) {
      this.nodeOffset[n] = offset;
      offset += tree.nodeNumActions[n] * newNumCombos;
    }

    const totalSize = offset;

    // Only reallocate if capacity is insufficient
    if (this.regrets.length < totalSize) {
      this.regrets = new Float32Array(totalSize);
      this.strategySums = new Float32Array(totalSize);
    } else {
      this.regrets.fill(0, 0, totalSize);
      this.strategySums.fill(0, 0, totalSize);
    }
  }
}
