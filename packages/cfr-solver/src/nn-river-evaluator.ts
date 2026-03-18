/**
 * nn-river-evaluator.ts
 *
 * Manages the ONNX worker thread and provides a synchronous NNRiverValueFn
 * callback for use with solveWithWasm().
 *
 * Architecture:
 *   Main thread (CFR/WASM) →Atomics.notify→ Worker (ONNX inference)
 *   Main thread (Atomics.wait) ←Atomics.notify← Worker (writes CFV output)
 *
 * Atomics.wait() is allowed on the Node.js main thread (unlike browsers).
 * Round-trip latency: ~0.5ms IPC + ~0.5ms ONNX = ~1ms per river node.
 * With ~200 turn nodes per solve: ~200ms total — vs. 20s for tree expansion.
 */

import { Worker } from 'worker_threads';
import { fileURLToPath } from 'url';
import { join, dirname } from 'path';
import type { NNRiverValueFn } from './vectorized/wasm-cfr-bridge.js';

const NUM_COMBOS = 1326;
const BOARD_DIM = 208; // 4 cards × 52-dim one-hot
const POT_DIM = 3; // [potOffset/es, startingPot/es, es/200]

// SharedArrayBuffer byte offsets (must match nn-evaluator-worker.ts)
const SIGNAL_OFFSET = 0;
const DATA_OFFSET = 8;
const BOARD_OFFSET = DATA_OFFSET;
const POT_OFFSET = BOARD_OFFSET + BOARD_DIM * 4;
const OOP_OFFSET = POT_OFFSET + POT_DIM * 4;
const IP_OFFSET = OOP_OFFSET + NUM_COMBOS * 4;
const CFV_OOP_OFFSET = IP_OFFSET + NUM_COMBOS * 4;
const CFV_IP_OFFSET = CFV_OOP_OFFSET + NUM_COMBOS * 4;

// Total SAB size in bytes
const SAB_BYTES = CFV_IP_OFFSET + NUM_COMBOS * 4;

const __dirname_esm = dirname(fileURLToPath(import.meta.url));

export class NeuralRiverEvaluator {
  private worker: Worker | null = null;
  private sab!: SharedArrayBuffer;
  private signalArr!: Int32Array;
  private boardArr!: Float32Array;
  private potArr!: Float32Array;
  private oopArr!: Float32Array;
  private ipArr!: Float32Array;
  private cfvOopArr!: Float32Array;
  private cfvIpArr!: Float32Array;

  /**
   * Load the ONNX model into the worker thread and warm it up.
   * Must be called before makeCallback().
   */
  async load(modelPath: string): Promise<void> {
    this.sab = new SharedArrayBuffer(SAB_BYTES);

    this.signalArr = new Int32Array(this.sab, SIGNAL_OFFSET, 2);
    this.boardArr = new Float32Array(this.sab, BOARD_OFFSET, BOARD_DIM);
    this.potArr = new Float32Array(this.sab, POT_OFFSET, POT_DIM);
    this.oopArr = new Float32Array(this.sab, OOP_OFFSET, NUM_COMBOS);
    this.ipArr = new Float32Array(this.sab, IP_OFFSET, NUM_COMBOS);
    this.cfvOopArr = new Float32Array(this.sab, CFV_OOP_OFFSET, NUM_COMBOS);
    this.cfvIpArr = new Float32Array(this.sab, CFV_IP_OFFSET, NUM_COMBOS);

    // Prefer the .ts source file (tsx runner), fall back to compiled .js
    const workerTs = join(__dirname_esm, 'nn-evaluator-worker.ts');
    const workerJs = join(__dirname_esm, 'nn-evaluator-worker.js');
    const { existsSync } = await import('fs');
    const workerPath = existsSync(workerTs) ? workerTs : workerJs;

    this.worker = new Worker(workerPath, {
      execArgv: ['--import', 'tsx'],
      workerData: { sabBuffer: this.sab, modelPath },
    });

    await new Promise<void>((resolve, reject) => {
      this.worker!.once('message', (msg) => {
        if (msg === 'ready') resolve();
        else reject(new Error(`Unexpected worker message: ${msg}`));
      });
      this.worker!.once('error', reject);
    });
  }

  /**
   * Create the NNRiverValueFn callback to pass into solveWithWasm().
   * wasmModule is the loaded Emscripten module (has HEAP32, HEAPF32).
   */
  makeCallback(wasmModule: {
    HEAP32: { buffer: ArrayBufferLike };
    HEAPF32: { buffer: ArrayBufferLike };
  }): NNRiverValueFn {
    const { signalArr, boardArr, potArr, oopArr, ipArr, cfvOopArr, cfvIpArr } = this;

    return (
      boardPtr: number, // HEAP32 ptr → int32[boardLen] flop cards
      boardLen: number,
      turnCard: number, // 0-51
      potOffset: number,
      startingPot: number,
      effectiveStack: number,
      turnNC: number, // number of valid turn combos
      comboGlobalIdsPtr: number, // HEAP32 ptr → int32[turnNC]
      oopReachPtr: number, // HEAPF32 ptr → float32[turnNC]
      ipReachPtr: number, // HEAPF32 ptr → float32[turnNC]
      traverser: number, // 0=OOP, 1=IP
      outEVPtr: number, // HEAPF32 ptr → float32[turnNC] output
    ): void => {
      // 1. Read WASM heap
      const comboIds = new Int32Array(wasmModule.HEAP32.buffer, comboGlobalIdsPtr, turnNC);
      const oopReach = new Float32Array(wasmModule.HEAPF32.buffer, oopReachPtr, turnNC);
      const ipReach = new Float32Array(wasmModule.HEAPF32.buffer, ipReachPtr, turnNC);
      const flopCards = new Int32Array(wasmModule.HEAP32.buffer, boardPtr, boardLen);

      // 2. Scatter turn-level reaches into 1326-dim vectors
      oopArr.fill(0);
      ipArr.fill(0);
      for (let i = 0; i < turnNC; i++) {
        const gid = comboIds[i];
        oopArr[gid] = oopReach[i];
        ipArr[gid] = ipReach[i];
      }

      // 3. Board one-hot: 4 cards × 52 = 208 dims
      //    flopCards gives the 3 flop card indices; turnCard is the 4th
      boardArr.fill(0);
      const allCards = [...flopCards, turnCard];
      for (let slot = 0; slot < allCards.length; slot++) {
        const card = allCards[slot];
        if (card >= 0 && card < 52) {
          boardArr[slot * 52 + card] = 1.0;
        }
      }

      // 4. Pot geometry (3 dims)
      const es = Math.max(effectiveStack, 1);
      potArr[0] = potOffset / es;
      potArr[1] = startingPot / es;
      potArr[2] = es / 200.0;

      // 5. Signal worker and synchronously wait for result
      //    (Atomics.wait is allowed on Node.js main thread)
      Atomics.store(signalArr, 0, 1);
      Atomics.notify(signalArr, 0, 1);
      Atomics.wait(signalArr, 0, 1); // blocks until worker sets signal back to 0

      // 6. Gather CFVs from 1326-dim output back to turnNC-dim WASM array,
      //    and de-normalise (model outputs cfv / effectiveStack)
      const outEV = new Float32Array(wasmModule.HEAPF32.buffer, outEVPtr, turnNC);
      const cfvSrc = traverser === 0 ? cfvOopArr : cfvIpArr;
      for (let i = 0; i < turnNC; i++) {
        outEV[i] = cfvSrc[comboIds[i]] * es;
      }
    };
  }

  /**
   * Direct inference API for bot use: given the 4-card board, pot geometry and
   * uniform ranges, returns the raw CFV output for every combo.
   *
   * This is SYNCHRONOUS (blocks ~1ms for Atomics + ONNX).
   * Call from an async context so Node.js event loop is not starved.
   *
   * @param flopCards - Three flop card indices (0-51)
   * @param turnCard  - Turn card index (0-51)
   * @param potOffset - Amount added to pot since starting pot
   * @param startingPot - Initial pot at flop
   * @param effectiveStack - Effective stack size
   * @param oopReach - Float32Array(1326) OOP reach probabilities
   * @param ipReach  - Float32Array(1326) IP reach probabilities
   * @returns Copies of cfvOOP and cfvIP arrays (both Float32Array(1326), normalised)
   */
  evalRiver(
    flopCards: [number, number, number],
    turnCard: number,
    potOffset: number,
    startingPot: number,
    effectiveStack: number,
    oopReach: Float32Array,
    ipReach: Float32Array,
  ): { cfvOOP: Float32Array; cfvIP: Float32Array } {
    if (!this.worker) throw new Error('NeuralRiverEvaluator not loaded — call load() first');

    // 1. Fill board one-hot (208 dims: 4 cards × 52)
    this.boardArr.fill(0);
    const allCards: number[] = [...flopCards, turnCard];
    for (let slot = 0; slot < allCards.length; slot++) {
      const c = allCards[slot];
      if (c >= 0 && c < 52) this.boardArr[slot * 52 + c] = 1.0;
    }

    // 2. Pot geometry (3 dims)
    const es = Math.max(effectiveStack, 1);
    this.potArr[0] = potOffset / es;
    this.potArr[1] = startingPot / es;
    this.potArr[2] = es / 200.0;

    // 3. Reach vectors (1326-dim)
    this.oopArr.set(oopReach);
    this.ipArr.set(ipReach);

    // 4. Signal worker and synchronously wait
    Atomics.store(this.signalArr, 0, 1);
    Atomics.notify(this.signalArr, 0, 1);
    Atomics.wait(this.signalArr, 0, 1);

    // 5. Return copies (SAB will be overwritten on next call)
    return {
      cfvOOP: this.cfvOopArr.slice(),
      cfvIP: this.cfvIpArr.slice(),
    };
  }

  /** Shut down the worker thread cleanly. */
  dispose(): void {
    if (this.worker) {
      Atomics.store(this.signalArr, 0, -1);
      Atomics.notify(this.signalArr, 0, 1);
      this.worker.terminate();
      this.worker = null;
    }
  }
}
