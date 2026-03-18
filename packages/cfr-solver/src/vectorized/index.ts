// Vectorized CFR+ Solver — Data-Oriented, Full-Tree, Zero-Sampling
//
// This module provides a GTO+-class solver engine that processes all hand
// combos simultaneously, uses contiguous TypedArray storage, and supports
// subgame solving for minimal memory usage.

// Phase 1: Data-Oriented Design
export { flattenTree, isTerminal, decodeTerminalId, applyRakeToTree } from './flat-tree.js';
export type { FlatTree } from './flat-tree.js';
export { ArrayStore } from './array-store.js';

// Phase 2: Vectorized CFR Engine
export { enumerateValidCombos, buildBlockerMatrix, buildReachFromRange } from './combo-utils.js';
export type { ValidCombos } from './combo-utils.js';
export {
  buildShowdownMatrix,
  buildEquityCache,
  computeShowdownEV,
  computeFoldEV,
  precomputeHandValues,
  computeShowdownEVMultiWay,
  computeFoldEVMultiWay,
} from './showdown-eval.js';
export { solveVectorized, solveVectorizedMultiWay } from './vectorized-cfr.js';
export type { VectorizedSolveParams, VectorizedSolveParamsMultiWay } from './vectorized-cfr.js';
export { WasmKernels, getWasmKernels } from './wasm-kernels.js';
export { computeExploitability } from './exploitability.js';
export type { ExploitabilityResult, ExploitabilityParams } from './exploitability.js';
export {
  extractEV,
  extractAllNodeQValues,
  fastExtractEV,
  createFastEVPool,
  computeWinRates,
} from './ev-extractor.js';
export type {
  ExtractEVParams,
  ExtractEVResult,
  AllQValuesParams,
  AllQValuesResult,
  FastEVPool,
} from './ev-extractor.js';

// Phase 3: Suit Isomorphism
export {
  computeHandIsomorphism,
  aggregateReachToGroups,
  expandGroupToComboStrategy,
} from './hand-isomorphism.js';
export type { IsomorphismMap } from './hand-isomorphism.js';

// Phase 4: Subgame Solving
export { buildStreetTree } from './street-tree-builder.js';
export type { TransitionTerminal } from './street-tree-builder.js';
export { estimateTransitionEV, estimateTransitionEVMonteCarlo } from './heuristic-ev.js';
export { solveStreet } from './street-solver.js';
export type { StreetSolveParams, StreetSolveResult, TransitionEvalFn } from './street-solver.js';
export { resolveSubgame, solveWithResolving } from './subgame-resolver.js';
export type { ResolveRequest, ResolveResult } from './subgame-resolver.js';
