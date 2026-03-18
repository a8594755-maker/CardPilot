#!/usr/bin/env tsx
/**
 * mine-river-worker-wasm.ts
 *
 * WASM-powered worker for the NN river value data mining pipeline.
 * Uses the C++ Emscripten solver for 10-50x speedup over the JS worker.
 *
 * Launched by mine-river-values.ts via child_process.fork().
 */

import { existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';
import { buildTree } from '../src/tree/tree-builder.js';
import { flattenTree } from '../src/vectorized/flat-tree.js';
import type { TreeConfig } from '../src/types.js';
import type { MineTask, MineResult, WorkerReady, WorkerError } from './mine-river-worker.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const _require = createRequire(import.meta.url);

// ─── WASM Module Types ───

interface EmscriptenModule {
  _malloc(size: number): number;
  _free(ptr: number): void;
  HEAPU8: Uint8Array;
  HEAPF32: Float32Array;
  HEAP32: Int32Array;
  CfrSolver: new () => WasmCfrSolver;
}

interface WasmCfrSolver {
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
  destroy(): void;
}

// ─── Cached State ───

let wasmModule: EmscriptenModule;
let solver: WasmCfrSolver;

// Pre-allocated WASM heap pointers for the tree template (reused across tasks)
let treePtrs: {
  pNodePlayer: number;
  pNodeNumActions: number;
  pNodeActionOffset: number;
  pChildNodeId: number;
  pTerminalPot: number;
  pTerminalStacks: number;
  pTerminalIsShowdown: number;
  pTerminalFolder: number;
  numNodes: number;
  numTerminals: number;
  totalActions: number;
};

// Pre-allocated buffers for per-task data
let pTurnBoard: number;
let pOopReach: number;
let pIpReach: number;

function copyToWasm(data: ArrayBufferView): number {
  const bytes = new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  const ptr = wasmModule._malloc(bytes.length);
  wasmModule.HEAPU8.set(bytes, ptr);
  return ptr;
}

// ─── Process Task ───

function processTask(task: MineTask): MineResult {
  const {
    turnBoard,
    potOffset,
    startingPot,
    effectiveStack,
    oopReach1326,
    ipReach1326,
    riverIters,
    rakePercentage,
    rakeCap,
  } = task;

  const flopBoard = turnBoard.slice(0, 3);
  const turnCard = turnBoard[3];

  // Copy turn board to WASM heap (reuse buffer)
  const boardArr = new Int32Array(turnBoard);
  wasmModule.HEAPU8.set(
    new Uint8Array(boardArr.buffer, boardArr.byteOffset, boardArr.byteLength),
    pTurnBoard,
  );

  // Copy reaches to WASM heap (reuse buffers)
  const oopArr = new Float32Array(oopReach1326);
  const ipArr = new Float32Array(ipReach1326);
  wasmModule.HEAPU8.set(
    new Uint8Array(oopArr.buffer, oopArr.byteOffset, oopArr.byteLength),
    pOopReach,
  );
  wasmModule.HEAPU8.set(new Uint8Array(ipArr.buffer, ipArr.byteOffset, ipArr.byteLength), pIpReach);

  // Call C++ solver
  solver.solveTurnRivers(
    pTurnBoard,
    turnBoard.length,
    treePtrs.pNodePlayer,
    treePtrs.pNodeNumActions,
    treePtrs.pNodeActionOffset,
    treePtrs.pChildNodeId,
    treePtrs.pTerminalPot,
    treePtrs.pTerminalStacks,
    treePtrs.pTerminalIsShowdown,
    treePtrs.pTerminalFolder,
    treePtrs.numNodes,
    treePtrs.numTerminals,
    treePtrs.totalActions,
    pOopReach,
    pIpReach,
    potOffset,
    startingPot,
    effectiveStack,
    riverIters,
    rakePercentage,
    rakeCap,
  );

  // Read results from WASM heap
  const oopPtr = solver.getMineResultOOPPtr();
  const ipPtr = solver.getMineResultIPPtr();
  const cfvOOP1326 = new Float32Array(new Float32Array(wasmModule.HEAPF32.buffer, oopPtr, 1326));
  const cfvIP1326 = new Float32Array(new Float32Array(wasmModule.HEAPF32.buffer, ipPtr, 1326));

  return {
    type: 'result',
    taskId: task.taskId,
    flopBoard,
    turnCard,
    potOffset,
    startingPot,
    effectiveStack,
    oopReach1326: new Float32Array(oopReach1326),
    ipReach1326: new Float32Array(ipReach1326),
    cfvOOP1326,
    cfvIP1326,
  };
}

// ─── Initialization ───

async function init() {
  // Load WASM module
  const wasmPath = join(__dirname, '..', 'build', 'cpp', 'cfr_core.js');
  if (!existsSync(wasmPath)) {
    throw new Error(`WASM module not found at ${wasmPath}`);
  }

  const createModule = _require(wasmPath);
  wasmModule = await createModule();
  solver = new wasmModule.CfrSolver();

  // Build the river tree template (same for all tasks)
  // The tree config will be sent with the first task, but the structure
  // (bet sizes, raise cap) is constant. Build a default tree.
  // We'll rebuild if the first task has different config.
}

// ─── IPC Message Handler ───

let treeConfigHash = '';

if (process.send) {
  init()
    .then(() => {
      const ready: WorkerReady = { type: 'ready' };
      process.send!(ready);
    })
    .catch((err) => {
      console.error('WASM worker init failed:', err.message);
      process.exit(1);
    });

  process.on('message', (msg: MineTask | { type: 'shutdown' }) => {
    if (msg.type === 'shutdown') {
      // Cleanup
      if (pTurnBoard) wasmModule._free(pTurnBoard);
      if (pOopReach) wasmModule._free(pOopReach);
      if (pIpReach) wasmModule._free(pIpReach);
      if (treePtrs) {
        wasmModule._free(treePtrs.pNodePlayer);
        wasmModule._free(treePtrs.pNodeNumActions);
        wasmModule._free(treePtrs.pNodeActionOffset);
        wasmModule._free(treePtrs.pChildNodeId);
        wasmModule._free(treePtrs.pTerminalPot);
        wasmModule._free(treePtrs.pTerminalStacks);
        wasmModule._free(treePtrs.pTerminalIsShowdown);
        wasmModule._free(treePtrs.pTerminalFolder);
      }
      solver.destroy();
      process.exit(0);
    }

    if (msg.type === 'task') {
      try {
        // Lazy-initialize tree template from first task's config
        const configHash = JSON.stringify(msg.riverTreeConfig);
        if (configHash !== treeConfigHash) {
          treeConfigHash = configHash;

          // Build and flatten the river tree template
          const riverConfig: TreeConfig = {
            ...msg.riverTreeConfig,
            singleStreet: true,
          };
          const riverRoot = buildTree(riverConfig);
          const riverFlat = flattenTree(riverRoot, 2);

          // Free old tree pointers if they exist
          if (treePtrs) {
            wasmModule._free(treePtrs.pNodePlayer);
            wasmModule._free(treePtrs.pNodeNumActions);
            wasmModule._free(treePtrs.pNodeActionOffset);
            wasmModule._free(treePtrs.pChildNodeId);
            wasmModule._free(treePtrs.pTerminalPot);
            wasmModule._free(treePtrs.pTerminalStacks);
            wasmModule._free(treePtrs.pTerminalIsShowdown);
            wasmModule._free(treePtrs.pTerminalFolder);
          }

          // Copy tree template to WASM heap (persistent)
          treePtrs = {
            pNodePlayer: copyToWasm(riverFlat.nodePlayer),
            pNodeNumActions: copyToWasm(riverFlat.nodeNumActions),
            pNodeActionOffset: copyToWasm(riverFlat.nodeActionOffset),
            pChildNodeId: copyToWasm(riverFlat.childNodeId),
            pTerminalPot: copyToWasm(riverFlat.terminalPot),
            pTerminalStacks: copyToWasm(riverFlat.terminalStacks),
            pTerminalIsShowdown: copyToWasm(riverFlat.terminalIsShowdown),
            pTerminalFolder: copyToWasm(riverFlat.terminalFolder),
            numNodes: riverFlat.numNodes,
            numTerminals: riverFlat.numTerminals,
            totalActions: riverFlat.totalActions,
          };

          // Allocate per-task buffers (reused across tasks)
          if (pTurnBoard) wasmModule._free(pTurnBoard);
          if (pOopReach) wasmModule._free(pOopReach);
          if (pIpReach) wasmModule._free(pIpReach);
          pTurnBoard = wasmModule._malloc(4 * 4); // 4 int32s
          pOopReach = wasmModule._malloc(1326 * 4); // 1326 float32s
          pIpReach = wasmModule._malloc(1326 * 4);
        }

        const result = processTask(msg);

        // Send Float32Arrays as plain arrays for IPC serialization
        process.send!({
          ...result,
          oopReach1326: Array.from(result.oopReach1326),
          ipReach1326: Array.from(result.ipReach1326),
          cfvOOP1326: Array.from(result.cfvOOP1326),
          cfvIP1326: Array.from(result.cfvIP1326),
        });
      } catch (err) {
        const errMsg: WorkerError = {
          type: 'error',
          taskId: msg.taskId,
          message: (err as Error).message,
        };
        process.send!(errMsg);
      }
    }
  });
}
