// Wasm Kernel Loader & Memory Manager
// =====================================
// Zero-copy shared memory model between JS and WebAssembly.
//
// Architecture:
//   1. Wasm module owns a WebAssembly.Memory (exported).
//   2. JS creates TypedArray views over that memory.
//   3. JS writes data into views → Wasm reads via raw pointers.
//   4. Wasm writes results → JS reads from views.
//   No data copying during the hot loop.
//
// Usage:
//   const wk = new WasmKernels();
//   await wk.init(nc, equityCache, combos);  // one-time setup
//   wk.computeEquityEV(opponentReach, outEV, losePayoff, payoffSpread);

import { readFile } from 'node:fs/promises';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const MAX_COMBOS_PER_CARD = 64;

// Align offset to 16-byte boundary (required for SIMD v128)
function align16(offset: number): number {
  return (offset + 15) & ~15;
}

interface WasmExports {
  memory: WebAssembly.Memory;
  computeEquityEV(
    reachPtr: number,
    outEvPtr: number,
    cardReachPtr: number,
    comboCardsPtr: number,
    validIndicesPtr: number,
    validOffsetsPtr: number,
    validLengthsPtr: number,
    equityMatrixPtr: number,
    cardCombosPtr: number,
    cardCombosLenPtr: number,
    numCombos: number,
    losePayoff: number,
    payoffSpread: number,
  ): void;
  computeFoldEV(
    reachPtr: number,
    outEvPtr: number,
    cardReachPtr: number,
    comboCardsPtr: number,
    cardCombosPtr: number,
    cardCombosLenPtr: number,
    numCombos: number,
    payoff: number,
  ): void;
  reachMultiply(reachPtr: number, strategyPtr: number, numCombos: number): void;
  evAccumulate(
    nodeEvPtr: number,
    strategyPtr: number,
    actionEvPtr: number,
    numCombos: number,
  ): void;
  updateRegrets(regretsPtr: number, deltasPtr: number, count: number): void;
  addStrategyWeights(sumsPtr: number, weightsPtr: number, count: number): void;
  WASM_MAX_COMBOS_PER_CARD: WebAssembly.Global;
}

// ─── Memory Layout ───
// All offsets are computed at init() time based on numCombos.
interface MemoryLayout {
  reachPtr: number; // f32[nc]
  outEvPtr: number; // f32[nc]
  cardReachPtr: number; // f64[52]
  comboCardsPtr: number; // i32[nc * 2]
  validIndicesPtr: number; // i32[totalValid]
  validOffsetsPtr: number; // i32[nc]
  validLengthsPtr: number; // i32[nc]
  equityMatrixPtr: number; // f32[nc * nc]
  cardCombosPtr: number; // i32[52 * MAX_COMBOS_PER_CARD]
  cardCombosLenPtr: number; // i32[52]
  totalBytes: number;
}

function computeLayout(nc: number, totalValid: number): MemoryLayout {
  let ptr = 0;

  const reachPtr = ptr;
  ptr = align16(ptr + nc * 4); // f32[nc]

  const outEvPtr = ptr;
  ptr = align16(ptr + nc * 4); // f32[nc]

  const cardReachPtr = ptr;
  ptr = align16(ptr + 52 * 8); // f64[52]

  const comboCardsPtr = ptr;
  ptr = align16(ptr + nc * 2 * 4); // i32[nc*2]

  const validIndicesPtr = ptr;
  ptr = align16(ptr + totalValid * 4); // i32[totalValid]

  const validOffsetsPtr = ptr;
  ptr = align16(ptr + nc * 4); // i32[nc]

  const validLengthsPtr = ptr;
  ptr = align16(ptr + nc * 4); // i32[nc]

  const equityMatrixPtr = ptr;
  ptr = align16(ptr + nc * nc * 4); // f32[nc*nc]

  const cardCombosPtr = ptr;
  ptr = align16(ptr + 52 * MAX_COMBOS_PER_CARD * 4); // i32[52*64]

  const cardCombosLenPtr = ptr;
  ptr = align16(ptr + 52 * 4); // i32[52]

  return {
    reachPtr,
    outEvPtr,
    cardReachPtr,
    comboCardsPtr,
    validIndicesPtr,
    validOffsetsPtr,
    validLengthsPtr,
    equityMatrixPtr,
    cardCombosPtr,
    cardCombosLenPtr,
    totalBytes: ptr,
  };
}

export class WasmKernels {
  private exports: WasmExports | null = null;
  private layout: MemoryLayout | null = null;
  private nc: number = 0;

  // TypedArray views over shared Wasm memory
  private reachView: Float32Array | null = null;
  private outEvView: Float32Array | null = null;

  private _ready = false;

  get ready(): boolean {
    return this._ready;
  }

  /**
   * Initialize the Wasm module and copy static data into shared memory.
   * Called once per solve setup (before CFR iterations begin).
   */
  async init(
    numCombos: number,
    equityMatrix: Float32Array,
    combos: Array<[number, number]>,
    cardCombos: Int32Array[], // 52 entries: combo indices sharing each card
    validIndices: Int32Array,
    validOffsets: Int32Array,
    validLengths: Int32Array,
  ): Promise<void> {
    this.nc = numCombos;

    const totalValid = validIndices.length;
    this.layout = computeLayout(numCombos, totalValid);

    // Load Wasm binary
    const wasmPath = this.getWasmPath();
    let wasmBytes: BufferSource;
    try {
      wasmBytes = await readFile(wasmPath);
    } catch {
      console.warn(`[WasmKernels] Wasm file not found at ${wasmPath}, falling back to JS`);
      this._ready = false;
      return;
    }

    const { instance } = await WebAssembly.instantiate(wasmBytes, {});

    this.exports = instance.exports as unknown as WasmExports;
    const wasmMemory = this.exports.memory;

    // Grow memory if needed
    if (wasmMemory.buffer.byteLength < this.layout.totalBytes) {
      const neededPages = Math.ceil(
        (this.layout.totalBytes - wasmMemory.buffer.byteLength) / 65536,
      );
      wasmMemory.grow(neededPages);
    }

    // ── Create views and copy static data ──
    this.rebuildViews(wasmMemory.buffer);
    this.copyStaticData(
      wasmMemory.buffer,
      equityMatrix,
      combos,
      cardCombos,
      validIndices,
      validOffsets,
      validLengths,
    );

    this._ready = true;
  }

  /**
   * Synchronous initialization — no async/await needed.
   * Uses WebAssembly.Module + WebAssembly.Instance (sync compile).
   * Safe for Node.js; module size is small enough for sync compilation.
   */
  initSync(
    numCombos: number,
    equityMatrix: Float32Array,
    combos: Array<[number, number]>,
    cardCombos: Int32Array[],
    validIndices: Int32Array,
    validOffsets: Int32Array,
    validLengths: Int32Array,
  ): void {
    this.nc = numCombos;

    const totalValid = validIndices.length;
    this.layout = computeLayout(numCombos, totalValid);

    const wasmPath = this.getWasmPath();
    if (!existsSync(wasmPath)) {
      this._ready = false;
      return;
    }

    let wasmBytes: Buffer;
    try {
      wasmBytes = readFileSync(wasmPath);
    } catch {
      this._ready = false;
      return;
    }

    const wasmModule = new WebAssembly.Module(new Uint8Array(wasmBytes));
    const instance = new WebAssembly.Instance(wasmModule, {});

    this.exports = instance.exports as unknown as WasmExports;
    const wasmMemory = this.exports.memory;

    if (wasmMemory.buffer.byteLength < this.layout.totalBytes) {
      const neededPages = Math.ceil(
        (this.layout.totalBytes - wasmMemory.buffer.byteLength) / 65536,
      );
      wasmMemory.grow(neededPages);
    }

    this.rebuildViews(wasmMemory.buffer);
    this.copyStaticData(
      wasmMemory.buffer,
      equityMatrix,
      combos,
      cardCombos,
      validIndices,
      validOffsets,
      validLengths,
    );

    this._ready = true;
  }

  private getWasmPath(): string {
    // Resolve relative to this file's location
    const thisDir = dirname(fileURLToPath(import.meta.url));
    return join(thisDir, '..', '..', 'build', 'wasm', 'kernels.wasm');
  }

  private rebuildViews(buffer: ArrayBuffer): void {
    const l = this.layout!;
    this.reachView = new Float32Array(buffer, l.reachPtr, this.nc);
    this.outEvView = new Float32Array(buffer, l.outEvPtr, this.nc);
  }

  private copyStaticData(
    buffer: ArrayBuffer,
    equityMatrix: Float32Array,
    combos: Array<[number, number]>,
    cardCombos: Int32Array[],
    validIndices: Int32Array,
    validOffsets: Int32Array,
    validLengths: Int32Array,
  ): void {
    const l = this.layout!;

    // Equity matrix (f32[nc*nc])
    new Float32Array(buffer, l.equityMatrixPtr, this.nc * this.nc).set(equityMatrix);

    // Combo cards (i32[nc*2] — flat interleaved [c1, c2, c1, c2, ...])
    const comboCardsView = new Int32Array(buffer, l.comboCardsPtr, this.nc * 2);
    for (let i = 0; i < this.nc; i++) {
      comboCardsView[i * 2] = combos[i][0];
      comboCardsView[i * 2 + 1] = combos[i][1];
    }

    // Valid indices, offsets, lengths
    new Int32Array(buffer, l.validIndicesPtr, validIndices.length).set(validIndices);
    new Int32Array(buffer, l.validOffsetsPtr, validOffsets.length).set(validOffsets);
    new Int32Array(buffer, l.validLengthsPtr, validLengths.length).set(validLengths);

    // Card → combo index mapping (i32[52 * MAX_COMBOS_PER_CARD])
    const cardCombosView = new Int32Array(buffer, l.cardCombosPtr, 52 * MAX_COMBOS_PER_CARD);
    const cardCombosLenView = new Int32Array(buffer, l.cardCombosLenPtr, 52);
    cardCombosView.fill(0);
    for (let card = 0; card < 52; card++) {
      const list = cardCombos[card];
      const len = Math.min(list.length, MAX_COMBOS_PER_CARD);
      cardCombosLenView[card] = len;
      for (let k = 0; k < len; k++) {
        cardCombosView[card * MAX_COMBOS_PER_CARD + k] = list[k];
      }
    }
  }

  /**
   * Compute equity showdown EV using the Wasm kernel.
   * Writes result directly into `outEV`.
   */
  computeEquityEV(
    opponentReach: Float32Array,
    outEV: Float32Array,
    losePayoff: number,
    payoffSpread: number,
  ): void {
    if (!this._ready || !this.exports || !this.layout) {
      throw new Error('WasmKernels not initialized');
    }

    const l = this.layout;

    // Write opponent reach into shared memory
    this.reachView!.set(opponentReach);

    // Call Wasm kernel
    this.exports.computeEquityEV(
      l.reachPtr,
      l.outEvPtr,
      l.cardReachPtr,
      l.comboCardsPtr,
      l.validIndicesPtr,
      l.validOffsetsPtr,
      l.validLengthsPtr,
      l.equityMatrixPtr,
      l.cardCombosPtr,
      l.cardCombosLenPtr,
      this.nc,
      losePayoff,
      payoffSpread,
    );

    // Read result from shared memory
    outEV.set(this.outEvView!);
  }

  /**
   * Compute fold EV using the Wasm kernel.
   */
  computeFoldEV(opponentReach: Float32Array, outEV: Float32Array, payoff: number): void {
    if (!this._ready || !this.exports || !this.layout) {
      throw new Error('WasmKernels not initialized');
    }

    const l = this.layout;

    this.reachView!.set(opponentReach);

    this.exports.computeFoldEV(
      l.reachPtr,
      l.outEvPtr,
      l.cardReachPtr,
      l.comboCardsPtr,
      l.cardCombosPtr,
      l.cardCombosLenPtr,
      this.nc,
      payoff,
    );

    outEV.set(this.outEvView!);
  }

  /**
   * Tear down and release resources.
   */
  destroy(): void {
    this.exports = null;
    this.layout = null;
    this.reachView = null;
    this.outEvView = null;
    this._ready = false;
  }
}

// ─── Singleton for easy access ───
let wasmKernelsInstance: WasmKernels | null = null;

export function getWasmKernels(): WasmKernels {
  if (!wasmKernelsInstance) {
    wasmKernelsInstance = new WasmKernels();
  }
  return wasmKernelsInstance;
}
