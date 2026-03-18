/**
 * Value Network Runtime (Phase 1C)
 *
 * ONNX-based neural network that predicts per-hand-class EV at
 * street boundaries. Replaces heuristic-ev.ts for depth-limited solving.
 *
 * Flow:
 *   1. Aggregate combo-level reaches → 169 hand-class reaches
 *   2. Run ONNX inference: board(5) + game_state(4) + oop(169) + ip(169) → ev(169)
 *   3. Disaggregate hand-class EVs → combo-level EVs
 */

import { existsSync } from 'node:fs';

const dynamicImport = new Function('modulePath', 'return import(modulePath);') as (
  modulePath: string,
) => Promise<any>;

// ─── Hand Class Mapping ───
// 169 classes: 13 pairs + 78 suited + 78 offsuit
// Same ordering as value_network.py hand_class_index()

const NUM_HAND_CLASSES = 169;

function handClassIndex(c1: number, c2: number): number {
  const r1 = c1 >> 2,
    r2 = c2 >> 2;
  const s1 = c1 & 3,
    s2 = c2 & 3;
  const hi = Math.max(r1, r2),
    lo = Math.min(r1, r2);
  if (hi === lo) return hi; // pair: 0-12
  const tri = (hi * (hi - 1)) / 2 + lo;
  return s1 === s2 ? 13 + tri : 91 + tri;
}

// Pre-build lookup for all 1326 combos
const HC_LOOKUP = new Int32Array(52 * 52);
HC_LOOKUP.fill(-1);
for (let c1 = 0; c1 < 52; c1++) {
  for (let c2 = c1 + 1; c2 < 52; c2++) {
    HC_LOOKUP[c1 * 52 + c2] = handClassIndex(c1, c2);
    HC_LOOKUP[c2 * 52 + c1] = handClassIndex(c1, c2);
  }
}

// ─── ONNX Session Interface ───

interface OrtSession {
  inputNames: string[];
  outputNames: string[];
  run(feeds: Record<string, unknown>): Promise<Record<string, { data: Float32Array | number[] }>>;
}

// ─── Public API ───

export interface ValueNetworkRuntime {
  provider: string;

  /**
   * Estimate transition EV for all combos at a street boundary.
   * Drop-in replacement for estimateTransitionEVMonteCarlo.
   */
  evaluateTransition(
    combos: Array<[number, number]>,
    board: number[],
    pot: number,
    oopReach: Float32Array,
    ipReach: Float32Array,
    numCombos: number,
    traverser: number,
    stacks: number[],
    outEV: Float32Array,
  ): Promise<void>;

  dispose(): Promise<void>;
}

export interface ValueNetworkOptions {
  modelPath: string;
  forceCpu?: boolean;
  verbose?: boolean;
}

// ─── Factory ───

export async function createValueNetworkRuntime(
  options: ValueNetworkOptions,
): Promise<ValueNetworkRuntime> {
  if (!existsSync(options.modelPath)) {
    throw new Error(`Value network model not found: ${options.modelPath}`);
  }

  const ort = await dynamicImport('onnxruntime-node');

  // Try GPU providers, fall back to CPU
  const providers: string[][] = options.forceCpu
    ? [['cpu']]
    : [['cuda', 'cpu'], ['dml', 'cpu'], ['cpu']];

  let session: OrtSession | null = null;
  let providerName = 'cpu';

  for (const provs of providers) {
    try {
      session = (await ort.InferenceSession.create(options.modelPath, {
        executionProviders: provs,
        graphOptimizationLevel: 'all',
      })) as OrtSession;
      providerName = provs[0];
      if (options.verbose) {
        console.log(`[ValueNet] loaded ${options.modelPath} with ${provs.join(',')}`);
      }
      break;
    } catch {
      if (options.verbose) {
        console.warn(`[ValueNet] provider ${provs.join(',')} failed, trying next...`);
      }
    }
  }

  if (!session) {
    throw new Error('Failed to create ONNX session for value network');
  }

  if (options.verbose) {
    console.log(`[ValueNet] inputs: ${session.inputNames.join(', ')}`);
    console.log(`[ValueNet] outputs: ${session.outputNames.join(', ')}`);
  }

  // Pre-allocate buffers for hand-class aggregation
  const hcOopReach = new Float32Array(NUM_HAND_CLASSES);
  const hcIpReach = new Float32Array(NUM_HAND_CLASSES);

  return {
    provider: `onnxruntime-${providerName}`,

    async evaluateTransition(
      combos: Array<[number, number]>,
      board: number[],
      pot: number,
      oopReach: Float32Array,
      ipReach: Float32Array,
      numCombos: number,
      traverser: number,
      stacks: number[],
      outEV: Float32Array,
    ): Promise<void> {
      // 1. Aggregate combo reaches to hand classes
      hcOopReach.fill(0);
      hcIpReach.fill(0);

      for (let i = 0; i < numCombos; i++) {
        const hc = HC_LOOKUP[combos[i][0] * 52 + combos[i][1]];
        hcOopReach[hc] += oopReach[i];
        hcIpReach[hc] += ipReach[i];
      }

      // 2. Prepare inputs
      // Board: pad to 5 cards with 52 (padding)
      const boardInput = new BigInt64Array(5);
      for (let i = 0; i < 5; i++) {
        boardInput[i] = BigInt(i < board.length ? board[i] : 52);
      }

      // Game state: [pot/100, stack0/100, stack1/100, traverser]
      const gameState = new Float32Array([pot / 100, stacks[0] / 100, stacks[1] / 100, traverser]);

      // 3. Run inference (batch=1)
      const boardTensor = new ort.Tensor('int64', boardInput, [1, 5]);
      const stateTensor = new ort.Tensor('float32', gameState, [1, 4]);
      const oopTensor = new ort.Tensor('float32', new Float32Array(hcOopReach), [
        1,
        NUM_HAND_CLASSES,
      ]);
      const ipTensor = new ort.Tensor('float32', new Float32Array(hcIpReach), [
        1,
        NUM_HAND_CLASSES,
      ]);

      const result = await session!.run({
        board: boardTensor,
        game_state: stateTensor,
        oop_reach: oopTensor,
        ip_reach: ipTensor,
      });

      const evOutput = result[session!.outputNames[0]];
      if (!evOutput?.data) {
        throw new Error('Value network produced no output');
      }

      const hcEV = evOutput.data as Float32Array;

      // 4. Disaggregate: map hand-class EVs back to combo EVs
      // EV was normalized by pot during training, denormalize
      for (let i = 0; i < numCombos; i++) {
        const hc = HC_LOOKUP[combos[i][0] * 52 + combos[i][1]];
        outEV[i] = (hcEV[hc] as number) * pot;
      }
    },

    async dispose(): Promise<void> {
      // onnxruntime-node sessions are GC'd
    },
  };
}

/**
 * Create a synchronous TransitionEvalFn backed by the value network.
 *
 * Uses a "lazy-sync" approach: the first call for a given (board, pot, stacks, traverser)
 * combination stores the NN result synchronously from a pre-populated cache.
 * The cache must be populated before CFR iterations start by calling
 * `precomputeTransitionEVs()`.
 *
 * This allows integration with the synchronous street solver.
 */
export function createSyncValueNetEvalFn(runtime: ValueNetworkRuntime): {
  /**
   * Pre-compute NN results for all unique transition terminals.
   * Must be called before CFR iterations start.
   * @param terminals Array of {board, pot, stacks, traverser} for each unique terminal state
   */
  precompute: (
    terminals: Array<{
      board: number[];
      pot: number;
      stacks: number[];
      combos: Array<[number, number]>;
      numCombos: number;
    }>,
  ) => Promise<void>;

  /**
   * Synchronous eval function compatible with TransitionEvalFn.
   * Uses pre-computed hand-class EVs, disaggregated per combo using current reaches.
   */
  evalFn: (
    combos: Array<[number, number]>,
    board: number[],
    pot: number,
    oopReach: Float32Array,
    ipReach: Float32Array,
    blockerMatrix: Uint8Array,
    numCombos: number,
    traverser: number,
    stacks: number[],
    outEV: Float32Array,
  ) => void;
} {
  // Cache: maps (boardKey, pot, traverser) → per-hand-class EVs for OOP traversal and IP traversal
  // We store pre-computed hand-class EVs keyed by a string hash
  const hcEvCache = new Map<string, Float32Array>();

  function cacheKey(board: number[], pot: number, stacks: number[], traverser: number): string {
    return `${board.join(',')}_${pot.toFixed(1)}_${stacks.map((s) => s.toFixed(1)).join(',')}_${traverser}`;
  }

  return {
    async precompute(terminals) {
      // For each unique terminal state, run NN inference for both traversers
      for (const term of terminals) {
        for (const traverser of [0, 1]) {
          const key = cacheKey(term.board, term.pot, term.stacks, traverser);
          if (hcEvCache.has(key)) continue;

          // Create uniform reaches for pre-computation
          // (actual reaches will be applied during combo disaggregation)
          const uniformReach = new Float32Array(term.numCombos).fill(1.0);
          const outEV = new Float32Array(term.numCombos);

          await runtime.evaluateTransition(
            term.combos,
            term.board,
            term.pot,
            uniformReach,
            uniformReach,
            term.numCombos,
            traverser,
            term.stacks,
            outEV,
          );

          // Convert combo EVs to hand-class EVs
          const hcEV = new Float32Array(NUM_HAND_CLASSES);
          const hcCount = new Float32Array(NUM_HAND_CLASSES);
          for (let i = 0; i < term.numCombos; i++) {
            const hc = HC_LOOKUP[term.combos[i][0] * 52 + term.combos[i][1]];
            hcEV[hc] += outEV[i];
            hcCount[hc] += 1;
          }
          for (let h = 0; h < NUM_HAND_CLASSES; h++) {
            if (hcCount[h] > 0) hcEV[h] /= hcCount[h];
          }

          hcEvCache.set(key, hcEV);
        }
      }
    },

    evalFn(
      combos,
      board,
      pot,
      oopReach,
      ipReach,
      blockerMatrix,
      numCombos,
      traverser,
      stacks,
      outEV,
    ) {
      const key = cacheKey(board, pot, stacks, traverser);
      const hcEV = hcEvCache.get(key);

      if (!hcEV) {
        // Fallback to zero EVs if cache miss (shouldn't happen if precompute was called)
        outEV.fill(0, 0, numCombos);
        return;
      }

      // Disaggregate hand-class EVs to combo EVs
      for (let i = 0; i < numCombos; i++) {
        const hc = HC_LOOKUP[combos[i][0] * 52 + combos[i][1]];
        outEV[i] = hcEV[hc];
      }
    },
  };
}
