/**
 * TypeScript bridge to the C++/Emscripten WASM CFR solver.
 *
 * Loads the compiled WASM module and provides a high-level API
 * that accepts the same parameters as the TS solver.
 * Falls back to the TS solver if WASM is not available.
 */

import { existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';
import type { FlatTree } from './flat-tree.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const _require = createRequire(import.meta.url);

// Path to compiled WASM module
const WASM_JS_PATH = join(__dirname, '..', '..', 'build', 'cpp', 'cfr_core.cjs');

interface EmscriptenModule {
  _malloc(size: number): number;
  _free(ptr: number): void;
  HEAPU8: Uint8Array;
  HEAPU32: Uint32Array;
  HEAPF32: Float32Array;
  HEAP32: Int32Array;
  HEAP8: Int8Array;
  CfrSolver: new () => WasmCfrSolver;
}

interface WasmCfrSolver {
  initFlop(
    nodePlayer: number,
    nodeNumActions: number,
    nodeActionOffset: number,
    childNodeId: number,
    terminalPot: number,
    terminalStacks: number,
    terminalIsShowdown: number,
    terminalFolder: number,
    numNodes: number,
    numTerminals: number,
    totalActions: number,
    comboCards: number,
    numCombos: number,
    oopReach: number,
    ipReach: number,
    startingPot: number,
    effectiveStack: number,
  ): void;

  buildSubtrees(
    boardCards: number,
    boardLen: number,
    innerNodePlayer: number,
    innerNodeNumActions: number,
    innerNodeActionOffset: number,
    innerChildNodeId: number,
    innerTerminalPot: number,
    innerTerminalStacks: number,
    innerTerminalIsShowdown: number,
    innerTerminalFolder: number,
    innerNumNodes: number,
    innerNumTerminals: number,
    innerTotalActions: number,
    rakePercentage: number,
    rakeCap: number,
    skipRiverSubtrees: boolean,
  ): void;

  solve(iterations: number, mccfr: boolean, globalIterOffset: number): void;
  setSeed(seed: number): void;

  enableNNRiverValue(callback: (...args: number[]) => void): void;
  disableNNRiverValue(): void;

  solveTurnRivers(
    turnBoard: number,
    turnBoardLen: number,
    nodePlayer: number,
    nodeNumActions: number,
    nodeActionOffset: number,
    childNodeId: number,
    terminalPot: number,
    terminalStacks: number,
    terminalIsShowdown: number,
    terminalFolder: number,
    numNodes: number,
    numTerminals: number,
    totalActions: number,
    oopReach1326: number,
    ipReach1326: number,
    potOffset: number,
    startingPot: number,
    effectiveStack: number,
    iterations: number,
    rakePercentage: number,
    rakeCap: number,
  ): void;

  getMineResultOOPPtr(): number;
  getMineResultIPPtr(): number;

  solveRiverBatch(
    turnBoard: number,
    turnBoardLen: number,
    comboCards: number,
    numCombos: number,
    oopReach: number,
    ipReach: number,
    nodePlayer: number,
    nodeNumActions: number,
    nodeActionOffset: number,
    childNodeId: number,
    terminalPot: number,
    terminalStacks: number,
    terminalIsShowdown: number,
    terminalFolder: number,
    numNodes: number,
    numTerminals: number,
    totalActions: number,
    iterations: number,
    rakePercentage: number,
    rakeCap: number,
    potOffset: number,
    outCfvOOP: number,
    outCfvIP: number,
  ): void;

  getStrategySumsPtr(): number;
  getStrategySumsLen(): number;
  getRegretsPtr(): number;
  getFlopNC(): number;
  destroy(): void;
}

let _module: EmscriptenModule | null = null;
let _loadAttempted = false;
let _activeModule: EmscriptenModule | null = null;

export interface ActiveWasmModuleHeap {
  HEAPU8: Uint8Array;
  HEAP32: Int32Array;
  HEAPF32: Float32Array;
}

/**
 * Returns the currently active WASM heap during solveWithWasm().
 * Only valid while a solve call is in progress.
 */
export function getActiveWasmModule(): ActiveWasmModuleHeap | null {
  if (!_activeModule) return null;
  return {
    HEAPU8: _activeModule.HEAPU8,
    HEAP32: _activeModule.HEAP32,
    HEAPF32: _activeModule.HEAPF32,
  };
}

/**
 * Attempt to load the WASM module. Returns null if not available.
 */
async function loadWasmModule(): Promise<EmscriptenModule | null> {
  if (_loadAttempted) return _module;
  _loadAttempted = true;

  if (!existsSync(WASM_JS_PATH)) {
    console.log('  [WASM] Module not found at', WASM_JS_PATH);
    return null;
  }

  try {
    // Load Emscripten JS glue via require (CommonJS module)
    const createModule = _require(WASM_JS_PATH);
    _module = await createModule();
    console.log('  [WASM] C++ CFR module loaded successfully');
    return _module;
  } catch (err) {
    console.log('  [WASM] Failed to load module:', (err as Error).message);
    return null;
  }
}

/**
 * Copy a TypedArray into WASM heap and return the pointer.
 */
function copyToWasm(module: EmscriptenModule, data: ArrayBufferView): number {
  const bytes = new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  const ptr = module._malloc(bytes.length);
  module.HEAPU8.set(bytes, ptr);
  return ptr;
}

/**
 * NN river value callback signature.
 *
 * Called by C++ at each turn "showdown" terminal (river chance node) instead of
 * enumerating all 48 river subtrees. The callback reads turn-level reaches from
 * the WASM heap, runs neural network inference, and writes predicted CFVs back.
 *
 * All pointer arguments are byte offsets into the WASM linear memory (HEAPF32/HEAP32).
 */
export type NNRiverValueFn = (
  boardPtr: number, // HEAP32 ptr -> int32[boardLen] flop board card indices
  boardLen: number, // 3 for flop
  turnCard: number, // turn card index (0-51)
  potOffset: number, // pot - startingPot at this terminal
  startingPot: number, // tree config starting pot
  effectiveStack: number, // tree config effective stack
  turnNC: number, // number of valid turn combos
  comboGlobalIdsPtr: number, // HEAP32 ptr -> int32[turnNC] canonical 0..1325 indices
  oopReachPtr: number, // HEAPF32 ptr -> float32[turnNC] OOP reach probs
  ipReachPtr: number, // HEAPF32 ptr -> float32[turnNC] IP reach probs
  traverser: number, // 0 (OOP) or 1 (IP)
  outEVPtr: number, // HEAPF32 ptr -> float32[turnNC] -- write predicted CFVs here
) => void;

export interface WasmSolveParams {
  // Flop tree (flattened)
  flopTree: FlatTree;
  flopNumCombos: number;
  flopComboCards: Int32Array; // [nc * 2]
  flopOopReach: Float32Array;
  flopIpReach: Float32Array;
  startingPot: number;
  effectiveStack: number;

  // Inner tree template (for turn/river subtrees)
  innerTree: FlatTree;

  // Board
  board: number[];

  // Config
  rakePercentage: number;
  rakeCap: number;

  // Solve params
  iterations: number;
  mccfr: boolean;
  globalIterOffset?: number;
  rngSeed?: number;

  /**
   * When provided, enables NN-based river evaluation.
   * Skips building river subtrees (~635 MB saved).
   * The callback is invoked at every turn terminal during CFR traversal.
   */
  nnRiverValueFn?: NNRiverValueFn;
}

export interface WasmSolveResult {
  strategySums: Float32Array;
  flopNC: number;
}

/**
 * Solve a full-game CFR problem using the C++ WASM engine.
 * Returns null if WASM is not available (caller should fall back to TS).
 */
export async function solveWithWasm(params: WasmSolveParams): Promise<WasmSolveResult | null> {
  const module = await loadWasmModule();
  if (!module) return null;

  const solver = new module.CfrSolver();
  const ptrs: number[] = []; // track all malloc'd pointers for cleanup

  try {
    // Copy flop tree arrays to WASM heap
    const flopTree = params.flopTree;
    const pNodePlayer = copyToWasm(module, flopTree.nodePlayer);
    ptrs.push(pNodePlayer);
    const pNodeNumActions = copyToWasm(module, flopTree.nodeNumActions);
    ptrs.push(pNodeNumActions);
    const pNodeActionOffset = copyToWasm(module, flopTree.nodeActionOffset);
    ptrs.push(pNodeActionOffset);
    const pChildNodeId = copyToWasm(module, flopTree.childNodeId);
    ptrs.push(pChildNodeId);
    const pTerminalPot = copyToWasm(module, flopTree.terminalPot);
    ptrs.push(pTerminalPot);
    const pTerminalStacks = copyToWasm(module, flopTree.terminalStacks);
    ptrs.push(pTerminalStacks);
    const pTerminalIsShowdown = copyToWasm(module, flopTree.terminalIsShowdown);
    ptrs.push(pTerminalIsShowdown);
    const pTerminalFolder = copyToWasm(module, flopTree.terminalFolder);
    ptrs.push(pTerminalFolder);
    const pComboCards = copyToWasm(module, params.flopComboCards);
    ptrs.push(pComboCards);
    const pOopReach = copyToWasm(module, params.flopOopReach);
    ptrs.push(pOopReach);
    const pIpReach = copyToWasm(module, params.flopIpReach);
    ptrs.push(pIpReach);

    solver.initFlop(
      pNodePlayer,
      pNodeNumActions,
      pNodeActionOffset,
      pChildNodeId,
      pTerminalPot,
      pTerminalStacks,
      pTerminalIsShowdown,
      pTerminalFolder,
      flopTree.numNodes,
      flopTree.numTerminals,
      flopTree.totalActions,
      pComboCards,
      params.flopNumCombos,
      pOopReach,
      pIpReach,
      params.startingPot,
      params.effectiveStack,
    );

    // Copy inner tree arrays
    const innerTree = params.innerTree;
    const pInnerNodePlayer = copyToWasm(module, innerTree.nodePlayer);
    ptrs.push(pInnerNodePlayer);
    const pInnerNodeNumActions = copyToWasm(module, innerTree.nodeNumActions);
    ptrs.push(pInnerNodeNumActions);
    const pInnerNodeActionOffset = copyToWasm(module, innerTree.nodeActionOffset);
    ptrs.push(pInnerNodeActionOffset);
    const pInnerChildNodeId = copyToWasm(module, innerTree.childNodeId);
    ptrs.push(pInnerChildNodeId);
    const pInnerTerminalPot = copyToWasm(module, innerTree.terminalPot);
    ptrs.push(pInnerTerminalPot);
    const pInnerTerminalStacks = copyToWasm(module, innerTree.terminalStacks);
    ptrs.push(pInnerTerminalStacks);
    const pInnerTerminalIsShowdown = copyToWasm(module, innerTree.terminalIsShowdown);
    ptrs.push(pInnerTerminalIsShowdown);
    const pInnerTerminalFolder = copyToWasm(module, innerTree.terminalFolder);
    ptrs.push(pInnerTerminalFolder);

    // Copy board
    const boardArr = new Int32Array(params.board);
    const pBoard = copyToWasm(module, boardArr);
    ptrs.push(pBoard);

    const useNN = !!params.nnRiverValueFn;

    solver.buildSubtrees(
      pBoard,
      params.board.length,
      pInnerNodePlayer,
      pInnerNodeNumActions,
      pInnerNodeActionOffset,
      pInnerChildNodeId,
      pInnerTerminalPot,
      pInnerTerminalStacks,
      pInnerTerminalIsShowdown,
      pInnerTerminalFolder,
      innerTree.numNodes,
      innerTree.numTerminals,
      innerTree.totalActions,
      params.rakePercentage,
      params.rakeCap,
      useNN, // skipRiverSubtrees when NN mode is active
    );

    // Enable NN river value callback if provided
    if (useNN) {
      solver.enableNNRiverValue(params.nnRiverValueFn!);
    }

    // Set RNG seed if provided (for parallel workers)
    if (params.rngSeed !== undefined) {
      solver.setSeed(params.rngSeed);
    }

    // Solve
    _activeModule = module;
    try {
      solver.solve(params.iterations, params.mccfr, params.globalIterOffset ?? 0);
    } finally {
      _activeModule = null;
      if (useNN) {
        solver.disableNNRiverValue();
      }
    }

    // Read results from WASM heap (copy to TS-owned buffer)
    const sumsPtr = solver.getStrategySumsPtr();
    const sumsLen = solver.getStrategySumsLen();
    const flopNC = solver.getFlopNC();

    // Create a Float32Array view into the WASM heap, then copy
    const sumsView = new Float32Array(module.HEAPF32.buffer, sumsPtr, sumsLen);
    const strategySums = new Float32Array(sumsView); // copy

    return { strategySums, flopNC };
  } finally {
    // Free all malloc'd pointers
    for (const ptr of ptrs) {
      module._free(ptr);
    }
    solver.destroy();
  }
}

/**
 * Check if the WASM CFR module is available.
 */
export function isWasmAvailable(): boolean {
  return existsSync(WASM_JS_PATH);
}

/**
 * Params for river batch solving via WASM.
 */
export interface RiverBatchParams {
  turnBoard: number[]; // 4 cards
  turnComboCards: Int32Array; // [turnNC * 2]
  turnNC: number;
  oopReach: Float32Array; // [turnNC]
  ipReach: Float32Array; // [turnNC]
  riverTree: FlatTree;
  iterations: number;
  rakePercentage: number;
  rakeCap: number;
  potOffset: number;
}

export interface RiverBatchResult {
  cfvOOP: Float32Array; // [turnNC]
  cfvIP: Float32Array; // [turnNC]
}

/**
 * Solve all 48 river subtrees for a given turn board using the C++ WASM engine.
 * Returns null if WASM is not available (caller should fall back to TS).
 */
export async function solveRiverBatchWasm(
  params: RiverBatchParams,
): Promise<RiverBatchResult | null> {
  const module = await loadWasmModule();
  if (!module) return null;

  const solver = new module.CfrSolver();
  const ptrs: number[] = [];

  try {
    // Copy turn board to WASM heap
    const pTurnBoard = copyToWasm(module, new Int32Array(params.turnBoard));
    ptrs.push(pTurnBoard);

    // Copy turn combo cards
    const pTurnComboCards = copyToWasm(module, params.turnComboCards);
    ptrs.push(pTurnComboCards);

    // Copy reaches
    const pOopReach = copyToWasm(module, params.oopReach);
    ptrs.push(pOopReach);
    const pIpReach = copyToWasm(module, params.ipReach);
    ptrs.push(pIpReach);

    // Copy river tree template
    const tree = params.riverTree;
    const pNodePlayer = copyToWasm(module, tree.nodePlayer);
    ptrs.push(pNodePlayer);
    const pNodeNumActions = copyToWasm(module, tree.nodeNumActions);
    ptrs.push(pNodeNumActions);
    const pNodeActionOffset = copyToWasm(module, tree.nodeActionOffset);
    ptrs.push(pNodeActionOffset);
    const pChildNodeId = copyToWasm(module, tree.childNodeId);
    ptrs.push(pChildNodeId);
    const pTerminalPot = copyToWasm(module, tree.terminalPot);
    ptrs.push(pTerminalPot);
    const pTerminalStacks = copyToWasm(module, tree.terminalStacks);
    ptrs.push(pTerminalStacks);
    const pTerminalIsShowdown = copyToWasm(module, tree.terminalIsShowdown);
    ptrs.push(pTerminalIsShowdown);
    const pTerminalFolder = copyToWasm(module, tree.terminalFolder);
    ptrs.push(pTerminalFolder);

    // Allocate output buffers
    const turnNC = params.turnNC;
    const pOutCfvOOP = module._malloc(turnNC * 4);
    ptrs.push(pOutCfvOOP);
    const pOutCfvIP = module._malloc(turnNC * 4);
    ptrs.push(pOutCfvIP);

    // Call C++ river batch solver
    solver.solveRiverBatch(
      pTurnBoard,
      params.turnBoard.length,
      pTurnComboCards,
      turnNC,
      pOopReach,
      pIpReach,
      pNodePlayer,
      pNodeNumActions,
      pNodeActionOffset,
      pChildNodeId,
      pTerminalPot,
      pTerminalStacks,
      pTerminalIsShowdown,
      pTerminalFolder,
      tree.numNodes,
      tree.numTerminals,
      tree.totalActions,
      params.iterations,
      params.rakePercentage,
      params.rakeCap,
      params.potOffset,
      pOutCfvOOP,
      pOutCfvIP,
    );

    // Read results from WASM heap (copy to TS-owned buffers)
    const cfvOOP = new Float32Array(module.HEAPF32.buffer, pOutCfvOOP, turnNC).slice();
    const cfvIP = new Float32Array(module.HEAPF32.buffer, pOutCfvIP, turnNC).slice();

    return { cfvOOP, cfvIP };
  } finally {
    for (const ptr of ptrs) module._free(ptr);
    solver.destroy();
  }
}

/**
 * Serialize WasmSolveParams for IPC (convert TypedArrays to plain arrays).
 */
export function serializeWasmParams(params: WasmSolveParams): Record<string, unknown> {
  const serializeTree = (tree: FlatTree) => ({
    numNodes: tree.numNodes,
    numTerminals: tree.numTerminals,
    numPlayers: tree.numPlayers,
    totalActions: tree.totalActions,
    nodePlayer: Array.from(tree.nodePlayer),
    nodeStreet: Array.from(tree.nodeStreet),
    nodeNumActions: Array.from(tree.nodeNumActions),
    nodeActionOffset: Array.from(tree.nodeActionOffset),
    nodePot: Array.from(tree.nodePot),
    nodeStacks: Array.from(tree.nodeStacks),
    childNodeId: Array.from(tree.childNodeId),
    actionType: Array.from(tree.actionType),
    terminalPot: Array.from(tree.terminalPot),
    terminalStacks: Array.from(tree.terminalStacks),
    terminalIsShowdown: Array.from(tree.terminalIsShowdown),
    terminalFolder: Array.from(tree.terminalFolder),
    terminalWinner: Array.from(tree.terminalWinner),
    terminalFolded: Array.from(tree.terminalFolded),
    nodeHistoryKey: tree.nodeHistoryKey,
    nodeActionLabels: tree.nodeActionLabels,
  });

  return {
    flopTree: serializeTree(params.flopTree),
    flopNumCombos: params.flopNumCombos,
    flopComboCards: Array.from(params.flopComboCards),
    flopOopReach: Array.from(params.flopOopReach),
    flopIpReach: Array.from(params.flopIpReach),
    startingPot: params.startingPot,
    effectiveStack: params.effectiveStack,
    innerTree: serializeTree(params.innerTree),
    board: params.board,
    rakePercentage: params.rakePercentage,
    rakeCap: params.rakeCap,
    iterations: params.iterations,
    mccfr: params.mccfr,
    globalIterOffset: params.globalIterOffset ?? 0,
    rngSeed: params.rngSeed ?? 42,
  };
}

// --- Mining: River-batch solver via WASM ---

export interface WasmMineParams {
  turnBoard: number[]; // 4 cards
  innerTree: FlatTree; // river betting tree template
  oopReach1326: Float32Array;
  ipReach1326: Float32Array;
  potOffset: number;
  startingPot: number;
  effectiveStack: number;
  iterations: number;
  rakePercentage: number;
  rakeCap: number;
}

export interface WasmMineResult {
  cfvOOP1326: Float32Array;
  cfvIP1326: Float32Array;
}

/**
 * Solve all 48 river subtrees for a turn state using C++ WASM.
 * Returns per-combo CFVs in canonical 1326-space.
 */
export async function solveTurnRiversWasm(params: WasmMineParams): Promise<WasmMineResult | null> {
  const module = await loadWasmModule();
  if (!module) return null;

  const solver = new module.CfrSolver();
  const ptrs: number[] = [];

  try {
    // Copy turn board
    const boardArr = new Int32Array(params.turnBoard);
    const pBoard = copyToWasm(module, boardArr);
    ptrs.push(pBoard);

    // Copy inner tree template
    const t = params.innerTree;
    const pNodePlayer = copyToWasm(module, t.nodePlayer);
    ptrs.push(pNodePlayer);
    const pNodeNumActions = copyToWasm(module, t.nodeNumActions);
    ptrs.push(pNodeNumActions);
    const pNodeActionOffset = copyToWasm(module, t.nodeActionOffset);
    ptrs.push(pNodeActionOffset);
    const pChildNodeId = copyToWasm(module, t.childNodeId);
    ptrs.push(pChildNodeId);
    const pTerminalPot = copyToWasm(module, t.terminalPot);
    ptrs.push(pTerminalPot);
    const pTerminalStacks = copyToWasm(module, t.terminalStacks);
    ptrs.push(pTerminalStacks);
    const pTerminalIsShowdown = copyToWasm(module, t.terminalIsShowdown);
    ptrs.push(pTerminalIsShowdown);
    const pTerminalFolder = copyToWasm(module, t.terminalFolder);
    ptrs.push(pTerminalFolder);

    // Copy reaches
    const pOopReach = copyToWasm(module, params.oopReach1326);
    ptrs.push(pOopReach);
    const pIpReach = copyToWasm(module, params.ipReach1326);
    ptrs.push(pIpReach);

    // Solve
    solver.solveTurnRivers(
      pBoard,
      params.turnBoard.length,
      pNodePlayer,
      pNodeNumActions,
      pNodeActionOffset,
      pChildNodeId,
      pTerminalPot,
      pTerminalStacks,
      pTerminalIsShowdown,
      pTerminalFolder,
      t.numNodes,
      t.numTerminals,
      t.totalActions,
      pOopReach,
      pIpReach,
      params.potOffset,
      params.startingPot,
      params.effectiveStack,
      params.iterations,
      params.rakePercentage,
      params.rakeCap,
    );

    // Read results from WASM heap
    const oopPtr = solver.getMineResultOOPPtr();
    const ipPtr = solver.getMineResultIPPtr();
    const cfvOOP1326 = new Float32Array(new Float32Array(module.HEAPF32.buffer, oopPtr, 1326));
    const cfvIP1326 = new Float32Array(new Float32Array(module.HEAPF32.buffer, ipPtr, 1326));

    return { cfvOOP1326, cfvIP1326 };
  } finally {
    for (const ptr of ptrs) {
      module._free(ptr);
    }
    solver.destroy();
  }
}

/**
 * Deserialize WasmSolveParams from IPC.
 */
export function deserializeWasmParams(data: Record<string, any>): WasmSolveParams {
  const deserializeTree = (t: any): FlatTree => ({
    numNodes: t.numNodes,
    numTerminals: t.numTerminals,
    numPlayers: t.numPlayers ?? 2,
    totalActions: t.totalActions,
    nodePlayer: new Uint8Array(t.nodePlayer),
    nodeStreet: new Uint8Array(t.nodeStreet ?? new Array(t.numNodes).fill(0)),
    nodeNumActions: new Uint8Array(t.nodeNumActions),
    nodeActionOffset: new Uint32Array(t.nodeActionOffset),
    nodePot: new Float32Array(t.nodePot ?? new Array(t.numNodes).fill(0)),
    nodeStacks: new Float32Array(
      t.nodeStacks ?? new Array((t.numNodes ?? 0) * (t.numPlayers ?? 2)).fill(0),
    ),
    childNodeId: new Int32Array(t.childNodeId),
    actionType: new Uint8Array(t.actionType ?? new Array(t.totalActions).fill(0)),
    terminalPot: new Float32Array(t.terminalPot),
    terminalStacks: new Float32Array(t.terminalStacks),
    terminalIsShowdown: new Uint8Array(t.terminalIsShowdown),
    terminalFolder: new Int8Array(t.terminalFolder),
    terminalWinner: new Int8Array(t.terminalWinner ?? new Array(t.numTerminals).fill(-1)),
    terminalFolded: new Uint8Array(t.terminalFolded ?? new Array(t.numTerminals).fill(0)),
    nodeHistoryKey: Array.isArray(t.nodeHistoryKey)
      ? t.nodeHistoryKey
      : new Array(t.numNodes).fill(''),
    nodeActionLabels: Array.isArray(t.nodeActionLabels)
      ? t.nodeActionLabels
      : new Array(t.totalActions).fill(''),
  });

  return {
    flopTree: deserializeTree(data.flopTree),
    flopNumCombos: data.flopNumCombos,
    flopComboCards: new Int32Array(data.flopComboCards),
    flopOopReach: new Float32Array(data.flopOopReach),
    flopIpReach: new Float32Array(data.flopIpReach),
    startingPot: data.startingPot,
    effectiveStack: data.effectiveStack,
    innerTree: deserializeTree(data.innerTree),
    board: data.board,
    rakePercentage: data.rakePercentage,
    rakeCap: data.rakeCap,
    iterations: data.iterations,
    mccfr: data.mccfr,
    globalIterOffset: data.globalIterOffset,
    rngSeed: data.rngSeed,
  };
}
