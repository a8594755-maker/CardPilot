/**
 * Coaching Model ONNX Runtime
 *
 * Runs the coaching model (policy + Q-values + embedding) via onnxruntime-node.
 * Supports CUDA, DML, and CPU backends (same as fvn-runtime.ts).
 *
 * Input tensors:
 *   hole:           (B, 2) int64 - hole card indices
 *   board:          (B, 5) int64 - board card indices (pad with 52)
 *   position:       (B, 6) float32 - one-hot position
 *   game_state:     (B, 7) float32 - [pot, stack, spr, facingBet, s_f, s_t, s_r]
 *   action_history: (B, 30) int64 - action history tokens
 *   legal_mask:     (B, 16) float32 - legal action mask
 *
 * Output tensors:
 *   policy:    (B, 16) float32 - action probabilities
 *   q_values:  (B, 16) float32 - per-action EV
 *   embedding: (B, 64) float32 - learned strategic embedding
 */

import { existsSync } from 'node:fs';

const dynamicImport = new Function('modulePath', 'return import(modulePath);') as (
  modulePath: string,
) => Promise<any>;

// ── Types ──

export interface CoachingInput {
  hole: [number, number]; // card indices 0-51
  board: number[]; // 3-5 card indices, will be padded to 5
  position: number; // 0-5 (or 0=OOP, 1=IP)
  street: number; // 0=flop, 1=turn, 2=river
  pot: number; // in BB
  stack: number; // effective stack in BB
  spr: number; // stack-to-pot ratio
  facingBet: number; // in BB, 0 if no facing bet
  actionHistory: number[]; // token IDs, max 30
  legalMask: number[]; // 16-dim, 1=legal
}

export interface CoachingInference {
  policy: Float32Array; // 16-dim action probabilities
  qValues: Float32Array; // 16-dim per-action EV
  embedding: Float32Array; // 64-dim strategic embedding
}

export interface CoachingOracle {
  provider: string;
  infer(input: CoachingInput): Promise<CoachingInference>;
  inferBatch(inputs: CoachingInput[]): Promise<CoachingInference[]>;
  dispose(): Promise<void>;
}

// ── Constants ──

const NUM_ACTIONS = 16;
const NUM_POSITIONS = 6;
const GAME_STATE_DIM = 7;
const MAX_HISTORY_LEN = 30;
const EMBEDDING_DIM = 64;

// ── Input encoding ──

function encodeInputs(inputs: CoachingInput[]): {
  hole: BigInt64Array;
  board: BigInt64Array;
  position: Float32Array;
  gameState: Float32Array;
  actionHistory: BigInt64Array;
  legalMask: Float32Array;
} {
  const B = inputs.length;

  const hole = new BigInt64Array(B * 2);
  const board = new BigInt64Array(B * 5);
  const position = new Float32Array(B * NUM_POSITIONS);
  const gameState = new Float32Array(B * GAME_STATE_DIM);
  const actionHistory = new BigInt64Array(B * MAX_HISTORY_LEN);
  const legalMask = new Float32Array(B * NUM_ACTIONS);

  for (let i = 0; i < B; i++) {
    const inp = inputs[i];

    // Hole cards
    hole[i * 2] = BigInt(inp.hole[0]);
    hole[i * 2 + 1] = BigInt(inp.hole[1]);

    // Board (pad to 5 with 52)
    for (let j = 0; j < 5; j++) {
      board[i * 5 + j] = BigInt(j < inp.board.length ? inp.board[j] : 52);
    }

    // Position one-hot
    const posIdx = Math.min(inp.position, NUM_POSITIONS - 1);
    position[i * NUM_POSITIONS + posIdx] = 1.0;

    // Game state: [pot, stack, spr, facingBet, s_flop, s_turn, s_river]
    const gsOff = i * GAME_STATE_DIM;
    gameState[gsOff + 0] = inp.pot / 100;
    gameState[gsOff + 1] = inp.stack / 100;
    gameState[gsOff + 2] = Math.min(inp.spr, 20) / 20;
    gameState[gsOff + 3] = inp.facingBet / 100;
    gameState[gsOff + 4] = inp.street === 0 ? 1 : 0;
    gameState[gsOff + 5] = inp.street === 1 ? 1 : 0;
    gameState[gsOff + 6] = inp.street === 2 ? 1 : 0;

    // Action history (pad to 30)
    for (let j = 0; j < MAX_HISTORY_LEN; j++) {
      actionHistory[i * MAX_HISTORY_LEN + j] = BigInt(
        j < inp.actionHistory.length ? inp.actionHistory[j] : 0,
      );
    }

    // Legal mask
    for (let j = 0; j < NUM_ACTIONS; j++) {
      legalMask[i * NUM_ACTIONS + j] = j < inp.legalMask.length ? inp.legalMask[j] : 0;
    }
  }

  return { hole, board, position, gameState, actionHistory, legalMask };
}

// ── ONNX Runtime session ──

interface OrtSession {
  run(feeds: Record<string, unknown>): Promise<Record<string, { data: Float32Array }>>;
}

async function createSession(
  modelPath: string,
  forceCpu: boolean,
  verbose: boolean,
): Promise<{ session: OrtSession; provider: string; ort: any }> {
  const ort = await dynamicImport('onnxruntime-node');

  const providers: string[] = [];
  if (!forceCpu) {
    // Try GPU backends first
    if (typeof ort.listSupportedBackends === 'function') {
      try {
        const backends = await ort.listSupportedBackends();
        if (Array.isArray(backends)) {
          for (const b of backends) {
            const name = typeof b === 'string' ? b : b?.name;
            if (name) providers.push(name);
          }
        }
      } catch {
        /* ignore */
      }
    }
    if (providers.length === 0) {
      providers.push('CUDAExecutionProvider', 'DmlExecutionProvider');
    }
  }
  providers.push('CPUExecutionProvider');

  let session: OrtSession | null = null;
  let usedProvider = 'cpu';

  for (const prov of providers) {
    try {
      const opts = new ort.SessionOptions();
      opts.graphOptimizationLevel = 'extended';
      session = await ort.InferenceSession.create(modelPath, {
        executionProviders: [prov],
        sessionOptions: opts,
      });
      usedProvider = prov;
      if (verbose) console.log(`[coaching-runtime] Using provider: ${prov}`);
      break;
    } catch {
      if (verbose) console.log(`[coaching-runtime] Provider ${prov} unavailable`);
    }
  }

  if (!session) {
    session = await ort.InferenceSession.create(modelPath, {
      executionProviders: ['CPUExecutionProvider'],
    });
    usedProvider = 'CPUExecutionProvider';
  }

  return { session: session!, provider: usedProvider, ort };
}

// ── Public API ──

export interface CoachingRuntimeOptions {
  modelPath: string;
  forceCpu?: boolean;
  verbose?: boolean;
}

export async function createCoachingOracle(
  options: CoachingRuntimeOptions,
): Promise<CoachingOracle> {
  if (!existsSync(options.modelPath)) {
    throw new Error(`Coaching model not found: ${options.modelPath}`);
  }

  const { session, provider, ort } = await createSession(
    options.modelPath,
    options.forceCpu ?? false,
    options.verbose ?? false,
  );

  async function runInference(inputs: CoachingInput[]): Promise<CoachingInference[]> {
    const B = inputs.length;
    const encoded = encodeInputs(inputs);

    const Tensor = ort.Tensor;
    const feeds: Record<string, unknown> = {
      hole: new Tensor('int64', encoded.hole, [B, 2]),
      board: new Tensor('int64', encoded.board, [B, 5]),
      position: new Tensor('float32', encoded.position, [B, NUM_POSITIONS]),
      game_state: new Tensor('float32', encoded.gameState, [B, GAME_STATE_DIM]),
      action_history: new Tensor('int64', encoded.actionHistory, [B, MAX_HISTORY_LEN]),
      legal_mask: new Tensor('float32', encoded.legalMask, [B, NUM_ACTIONS]),
    };

    const results = await (session as OrtSession).run(feeds);

    const policyData = results.policy?.data as Float32Array;
    const qData = results.q_values?.data as Float32Array;
    const embedData = results.embedding?.data as Float32Array;

    const outputs: CoachingInference[] = [];
    for (let i = 0; i < B; i++) {
      outputs.push({
        policy: policyData.slice(i * NUM_ACTIONS, (i + 1) * NUM_ACTIONS),
        qValues: qData.slice(i * NUM_ACTIONS, (i + 1) * NUM_ACTIONS),
        embedding: embedData.slice(i * EMBEDDING_DIM, (i + 1) * EMBEDDING_DIM),
      });
    }

    return outputs;
  }

  return {
    provider,

    async infer(input: CoachingInput): Promise<CoachingInference> {
      const [result] = await runInference([input]);
      return result;
    },

    async inferBatch(inputs: CoachingInput[]): Promise<CoachingInference[]> {
      return runInference(inputs);
    },

    async dispose(): Promise<void> {
      // ORT sessions don't need explicit cleanup in Node.js
    },
  };
}
