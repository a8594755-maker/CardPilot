// Pre-allocated buffers for CFR traversal to avoid allocations in the hot loop.
//
// ActionValueBuffer: Float64Array per depth level for action values (higher precision).
// StrategyBuffer: Float32Array per depth level for current strategy probabilities.

/**
 * Pre-allocated Float64Array pool indexed by tree depth.
 * Used to store per-action counterfactual values during traversal.
 */
export class ActionValueBuffer {
  private buffers: Float64Array[];

  constructor(maxDepth: number, maxActions: number) {
    this.buffers = [];
    for (let d = 0; d < maxDepth; d++) {
      this.buffers.push(new Float64Array(maxActions));
    }
  }

  /** Get the buffer for the given depth level. */
  get64(depth: number): Float64Array {
    return this.buffers[depth];
  }
}

/**
 * Pre-allocated Float32Array pool indexed by tree depth.
 * Used to store current strategy probabilities during traversal.
 */
export class StrategyBuffer {
  private buffers: Float32Array[];

  constructor(maxDepth: number, maxActions: number) {
    this.buffers = [];
    for (let d = 0; d < maxDepth; d++) {
      this.buffers.push(new Float32Array(maxActions));
    }
  }

  /** Get the buffer for the given depth level. */
  get(depth: number): Float32Array {
    return this.buffers[depth];
  }
}
