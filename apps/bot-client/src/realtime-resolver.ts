/**
 * Real-Time Subgame Resolver — Pluribus-style on-the-fly CFR solving.
 *
 * Architecture:
 *   1. On new hand (flop dealt): solve the flop tree (~5-20s, cached)
 *   2. On turn card: resolveSubgame from flop boundary (~0.5-2s)
 *   3. On river card: resolveSubgame from turn boundary (~0.2-0.5s)
 *   4. Extract hero's strategy at current action node
 *
 * The value network (VN V2) is injected as a TransitionEvalFn into the
 * street solver, replacing the default Monte Carlo heuristic at street
 * boundaries (flop→turn, turn→river transitions).
 *
 * Card format bridge:
 *   - Bot uses string cards: "Ah", "Ks", "2c"
 *   - Solver uses integer indices 0-51: rank*4 + suit (2c=0, 2d=1, ..., As=51)
 */

import { loadModel, type MLP } from '@cardpilot/fast-model';
import { cardToIndex, comboIndex } from '@cardpilot/cfr-solver/src/abstraction/card-index.js';
import {
  solveStreet,
  solveStreetSync,
  type StreetSolveResult,
  type TransitionEvalFn,
} from '@cardpilot/cfr-solver/src/vectorized/street-solver.js';
import { preloadWasmModule } from '@cardpilot/cfr-solver/src/vectorized/wasm-cfr-bridge.js';
import {
  resolveSubgame,
  type ResolveResult,
} from '@cardpilot/cfr-solver/src/vectorized/subgame-resolver.js';
import {
  loadHUSRPRanges,
  getWeightedRangeCombos,
  type WeightedCombo,
} from '@cardpilot/cfr-solver/src/integration/preflop-ranges.js';
import {
  REALTIME_SRP_50BB_CONFIG,
  REALTIME_SRP_100BB_CONFIG,
  REALTIME_3BET_50BB_CONFIG,
  REALTIME_3BET_100BB_CONFIG,
} from '@cardpilot/cfr-solver/src/tree/tree-config.js';
import type { FlatTree } from '@cardpilot/cfr-solver/src/vectorized/flat-tree.js';
import type { HUSRPRangesOptions } from '@cardpilot/cfr-solver/src/integration/preflop-ranges.js';
import type { TreeConfig } from '@cardpilot/cfr-solver/src/types.js';
import type { HandAction } from './types.js';
import { evaluateHandBoard } from '@cardpilot/poker-evaluator';
import { join } from 'node:path';

// ═══════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════

export interface ResolverConfig {
  /** Path to preflop charts JSON */
  chartsPath?: string;
  /** Path to value network model JSON */
  modelPath?: string;
  /** Tree config for solving (default: REALTIME_SRP_50BB_CONFIG) */
  treeConfig?: TreeConfig;
  /** Range loading options (spot names, action filters) */
  rangeOptions?: HUSRPRangesOptions;
  /** Flop solve iterations (default: 2000) */
  flopIterations?: number;
  /** Turn resolve iterations (default: 1000) */
  turnIterations?: number;
  /** River resolve iterations (default: 500) */
  riverIterations?: number;
  /** MC runout samples for transition EV estimation (default: 50) */
  transitionSamples?: number;
  /** Max time budget in ms for any solve (default: 10000) */
  timeBudgetMs?: number;
  /** Whether to log progress (default: false) */
  verbose?: boolean;
}

// ═══════════════════════════════════════════════════════════
// Scenario-Based Model Selection
// ═══════════════════════════════════════════════════════════

export type ScenarioKey = 'srp_50bb' | 'srp_100bb' | '3bet_50bb' | '3bet_100bb';

interface ScenarioConfig {
  treeConfig: TreeConfig;
  modelPath: string;
  rangeOptions: HUSRPRangesOptions;
}

const SRP_RANGE_OPTIONS: HUSRPRangesOptions = {
  ipSpot: 'BTN_unopened_open2.5x',
  ipAction: 'raise',
  oopSpot: 'BB_vs_BTN_facing_open2.5x',
  oopAction: 'call',
};

const THREEBET_RANGE_OPTIONS: HUSRPRangesOptions = {
  ipSpot: 'BTN_unopened_open2.5x',
  ipAction: 'raise',
  oopSpot: 'BB_vs_BTN_facing_open2.5x',
  oopAction: 'raise',
  minFrequency: 0.4,
};

const SCENARIO_CONFIGS: Record<ScenarioKey, ScenarioConfig> = {
  srp_50bb: {
    treeConfig: REALTIME_SRP_50BB_CONFIG,
    modelPath: 'models/vnet-v2-pipeline.json',
    rangeOptions: SRP_RANGE_OPTIONS,
  },
  srp_100bb: {
    treeConfig: REALTIME_SRP_100BB_CONFIG,
    modelPath: 'models/vnet-v3-srp-100bb.json',
    rangeOptions: SRP_RANGE_OPTIONS,
  },
  '3bet_50bb': {
    treeConfig: REALTIME_3BET_50BB_CONFIG,
    modelPath: 'models/vnet-v5-3bet-50bb.json',
    rangeOptions: THREEBET_RANGE_OPTIONS,
  },
  '3bet_100bb': {
    treeConfig: REALTIME_3BET_100BB_CONFIG,
    modelPath: 'models/vnet-v4-3bet-100bb.json',
    rangeOptions: THREEBET_RANGE_OPTIONS,
  },
};

const STACK_THRESHOLD_BB = 75;

export function selectScenario(is3bet: boolean, effectiveStackBB: number): ScenarioKey {
  const deep = effectiveStackBB > STACK_THRESHOLD_BB;
  if (is3bet) return deep ? '3bet_100bb' : '3bet_50bb';
  return deep ? 'srp_100bb' : 'srp_50bb';
}

export interface ResolvedStrategy {
  /** Action probabilities from CFR solve */
  raise: number;
  call: number;
  fold: number;
  /** Which actions are available at this node */
  availableActions: string[];
  /** Per-action probabilities (indexed by availableActions) */
  actionProbs: number[];
  /** Solve time in ms */
  solveTimeMs: number;
  /** Source street */
  street: string;
  /** Convergence info */
  iterations: number;
}

// ═══════════════════════════════════════════════════════════
// Tree Navigation — walk solved tree following game actions
// ═══════════════════════════════════════════════════════════

interface NavigationResult {
  /** Action node ID where hero acts (-1 if terminal/failed) */
  nodeId: number;
  /** Terminal index if walk ended at a terminal (-1 otherwise) */
  terminalId: number;
}

/** Get a player's stack at a child node (action node or terminal). */
function getChildStack(tree: FlatTree, childId: number, player: number): number {
  if (childId >= 0) {
    return tree.nodeStacks[childId * tree.numPlayers + player];
  }
  const termIdx = -(childId + 1);
  return tree.terminalStacks[termIdx * tree.numPlayers + player];
}

/**
 * Walk a solved FlatTree from root following a sequence of game actions.
 *
 * For fold/check/call: matches by action label.
 * For raise/all_in: computes stack-difference (tree commit) for each candidate
 *   edge and picks the closest match to the game action's commit (in BB).
 *
 * @returns Navigation result with nodeId (if we stopped at an action node)
 *   or terminalId (if we reached a terminal), or null on failure.
 */
function navigateTree(
  tree: FlatTree,
  streetActions: HandAction[],
  seatToPlayer: Map<number, number>,
  bb: number,
  log?: (msg: string) => void,
): NavigationResult | null {
  let nodeId = 0;

  for (const action of streetActions) {
    const treePlayer = seatToPlayer.get(action.seat);
    if (treePlayer === undefined) {
      log?.(`Nav: unknown seat ${action.seat}`);
      return null;
    }

    // Verify acting player matches tree expectation
    if (tree.nodePlayer[nodeId] !== treePlayer) {
      log?.(
        `Nav: player mismatch at node ${nodeId} — expected ${tree.nodePlayer[nodeId]}, got ${treePlayer}`,
      );
      return null;
    }

    const numActions = tree.nodeNumActions[nodeId];
    const offset = tree.nodeActionOffset[nodeId];

    let matchedEdge = -1;

    if (action.type === 'fold') {
      for (let a = 0; a < numActions; a++) {
        if (tree.nodeActionLabels[offset + a] === 'fold') {
          matchedEdge = a;
          break;
        }
      }
    } else if (action.type === 'check') {
      for (let a = 0; a < numActions; a++) {
        if (tree.nodeActionLabels[offset + a] === 'check') {
          matchedEdge = a;
          break;
        }
      }
    } else if (action.type === 'call') {
      for (let a = 0; a < numActions; a++) {
        if (tree.nodeActionLabels[offset + a] === 'call') {
          matchedEdge = a;
          break;
        }
      }
    } else if (action.type === 'all_in') {
      // Prefer exact allin edge, fall back to nearest bet/raise by commit
      for (let a = 0; a < numActions; a++) {
        if (tree.nodeActionLabels[offset + a] === 'allin') {
          matchedEdge = a;
          break;
        }
      }
      if (matchedEdge < 0) {
        matchedEdge = matchBetByCommit(tree, nodeId, treePlayer, action.amount / bb);
      }
    } else if (action.type === 'raise') {
      matchedEdge = matchBetByCommit(tree, nodeId, treePlayer, action.amount / bb);
    }

    if (matchedEdge < 0) {
      log?.(`Nav: no matching edge at node ${nodeId} for ${action.type} amt=${action.amount}`);
      return null;
    }

    const childId = tree.childNodeId[offset + matchedEdge];
    log?.(
      `Nav: node ${nodeId} → ${action.type}(${tree.nodeActionLabels[offset + matchedEdge]}) → child ${childId}`,
    );

    if (childId < 0) {
      // Reached a terminal (street transition or fold/showdown)
      return { nodeId: -1, terminalId: -(childId + 1) };
    }

    nodeId = childId;
  }

  return { nodeId, terminalId: -1 };
}

/**
 * Match a bet/raise game action to the closest tree edge by commit amount.
 * Returns the edge index, or -1 if no bet/raise/allin edges exist.
 */
function matchBetByCommit(
  tree: FlatTree,
  nodeId: number,
  player: number,
  commitBB: number,
): number {
  const numActions = tree.nodeNumActions[nodeId];
  const offset = tree.nodeActionOffset[nodeId];
  const currentStack = tree.nodeStacks[nodeId * tree.numPlayers + player];

  let bestEdge = -1;
  let bestDiff = Infinity;

  for (let a = 0; a < numActions; a++) {
    const label = tree.nodeActionLabels[offset + a];
    if (label === 'fold' || label === 'check' || label === 'call') continue;

    // bet_N, raise_N, allin — compute tree commit from stack difference
    const childId = tree.childNodeId[offset + a];
    const childStack = getChildStack(tree, childId, player);
    const treeCommit = currentStack - childStack;
    const diff = Math.abs(treeCommit - commitBB);

    if (diff < bestDiff) {
      bestDiff = diff;
      bestEdge = a;
    }
  }

  return bestEdge;
}

// ═══════════════════════════════════════════════════════════
// Resolver Class
// ═══════════════════════════════════════════════════════════

export class RealtimeResolver {
  private config: Required<ResolverConfig>;
  private valueNetwork: MLP | null = null;
  private oopRange: WeightedCombo[] = [];
  private ipRange: WeightedCombo[] = [];
  private rangesLoaded = false;

  // Per-hand state
  private flopResult: StreetSolveResult | null = null;
  private turnResult: ResolveResult | null = null;
  private currentBoard: number[] = [];
  private flopBoard: number[] = [];

  // Cache: flop board key → solved result (LRU-style)
  private flopCache = new Map<string, StreetSolveResult>();
  private readonly MAX_CACHE_SIZE = 20;

  constructor(config: ResolverConfig = {}) {
    this.config = {
      chartsPath: config.chartsPath ?? 'data/preflop_charts.json',
      modelPath: config.modelPath ?? 'models/vnet-v2-pipeline.json',
      treeConfig: config.treeConfig ?? REALTIME_SRP_50BB_CONFIG,
      rangeOptions: config.rangeOptions ?? {},
      flopIterations: config.flopIterations ?? 2000,
      turnIterations: config.turnIterations ?? 1000,
      riverIterations: config.riverIterations ?? 500,
      transitionSamples: config.transitionSamples ?? 50,
      timeBudgetMs: config.timeBudgetMs ?? 10000,
      verbose: config.verbose ?? false,
    };
  }

  /**
   * Initialize: load value network and preflop ranges.
   * Call once at startup.
   */
  initialize(): boolean {
    // Load value network
    this.valueNetwork = loadModel(this.config.modelPath);
    if (this.valueNetwork) {
      this.log(
        `Value network loaded: ${this.config.modelPath} (multiHead=${this.valueNetwork.isMultiHead})`,
      );
    } else {
      this.log(`No value network at ${this.config.modelPath} — using MC heuristic`);
    }

    // Preload WASM module in background (non-blocking)
    preloadWasmModule().then((ok) => {
      if (ok) this.log('WASM StreetSolver loaded — CFR iterations will use C++ SIMD');
      else this.log('WASM not available — using TS CFR fallback');
    });

    // Load preflop ranges
    try {
      const ranges = loadHUSRPRanges(this.config.chartsPath, this.config.rangeOptions);
      this.oopRange = getWeightedRangeCombos(ranges.oopRange);
      this.ipRange = getWeightedRangeCombos(ranges.ipRange);
      this.rangesLoaded = true;
      this.log(
        `Ranges loaded: OOP=${this.oopRange.length} combos, IP=${this.ipRange.length} combos`,
      );
    } catch (e) {
      this.log(`Failed to load ranges: ${e}`);
      return false;
    }

    return true;
  }

  /**
   * Reset per-hand state. Call at the start of each new hand.
   */
  resetHand(): void {
    this.flopResult = null;
    this.turnResult = null;
    this.currentBoard = [];
    this.flopBoard = [];
  }

  /**
   * Check if the resolver is ready (initialized with ranges).
   */
  get isReady(): boolean {
    return this.rangesLoaded;
  }

  /**
   * Solve/resolve for the current game state and return hero's strategy.
   *
   * @param heroCards - Hero's hole cards as strings, e.g. ["Ah", "Ks"]
   * @param board - Community cards as strings, e.g. ["2h", "7c", "5d"]
   * @param heroIsIP - Whether hero is in position (BTN/CO)
   * @param actions - Full hand action history (used to navigate to correct tree node)
   * @param heroSeat - Hero's seat number (for seat→player mapping)
   * @param villainSeat - Villain's seat number
   * @param bigBlind - Big blind in chips (for normalizing amounts to BB)
   * @returns Resolved strategy or null if solving fails
   */
  getStrategy(
    heroCards: [string, string],
    board: string[],
    heroIsIP: boolean,
    actions?: HandAction[],
    heroSeat?: number,
    villainSeat?: number,
    bigBlind?: number,
  ): ResolvedStrategy | null {
    if (!this.rangesLoaded) return null;

    const boardIndices = board.map(cardToIndex);

    // Build seat→player mapping (player 0=OOP, 1=IP)
    let seatToPlayer: Map<number, number> | undefined;
    if (heroSeat != null && villainSeat != null) {
      seatToPlayer = new Map();
      seatToPlayer.set(heroSeat, heroIsIP ? 1 : 0);
      seatToPlayer.set(villainSeat, heroIsIP ? 0 : 1);
    }

    const bb = bigBlind || 1;

    try {
      if (board.length === 3) {
        return this.solveFlop(heroCards, boardIndices, heroIsIP, actions, seatToPlayer, bb);
      } else if (board.length === 4) {
        return this.solveTurn(heroCards, boardIndices, heroIsIP, actions, seatToPlayer, bb);
      } else if (board.length === 5) {
        return this.solveRiver(heroCards, boardIndices, heroIsIP, actions, seatToPlayer, bb);
      }
    } catch (e) {
      this.log(`Solve error: ${e}`);
    }

    return null;
  }

  // ── Flop solving ──

  private solveFlop(
    heroCards: [string, string],
    board: number[],
    heroIsIP: boolean,
    actions?: HandAction[],
    seatToPlayer?: Map<number, number>,
    bb: number = 1,
  ): ResolvedStrategy | null {
    const startTime = Date.now();
    const cacheKey = board
      .slice()
      .sort((a, b) => a - b)
      .join(',');

    // Check cache
    let result = this.flopCache.get(cacheKey);
    if (!result) {
      this.log(`Solving flop: [${board.map(indexToCardStr).join(', ')}]`);

      result = solveStreetSync({
        treeConfig: this.config.treeConfig,
        board,
        street: 'FLOP',
        oopRange: this.oopRange,
        ipRange: this.ipRange,
        iterations: this.config.flopIterations,
        transitionEvalFn: this.createTransitionEvalFn(),
        onProgress: this.config.verbose
          ? (iter, elapsed) => {
              if (iter % 200 === 0)
                this.log(`  Flop: ${iter}/${this.config.flopIterations} (${elapsed}ms)`);
            }
          : undefined,
      });

      // Cache with LRU eviction
      if (this.flopCache.size >= this.MAX_CACHE_SIZE) {
        const oldest = this.flopCache.keys().next().value;
        if (oldest !== undefined) this.flopCache.delete(oldest);
      }
      this.flopCache.set(cacheKey, result);
    } else {
      this.log(`Flop cache hit: [${board.map(indexToCardStr).join(', ')}]`);
    }

    this.flopResult = result;
    this.flopBoard = [...board];
    this.currentBoard = [...board];

    // Navigate to the correct decision node using action history
    let nodeId = 0;
    if (actions && seatToPlayer) {
      const flopActions = actions.filter((a) => a.street === 'FLOP');
      if (flopActions.length > 0) {
        const nav = navigateTree(
          result.tree,
          flopActions,
          seatToPlayer,
          bb,
          this.config.verbose ? (msg) => this.log(msg) : undefined,
        );
        if (nav && nav.nodeId >= 0) {
          nodeId = nav.nodeId;
          this.log(`Flop nav: ${flopActions.length} actions → node ${nodeId}`);
        } else if (nav && nav.terminalId >= 0) {
          this.log(`Flop nav reached terminal ${nav.terminalId} — no decision needed`);
          return null;
        } else {
          this.log(`Flop nav failed — falling back to root`);
        }
      }
    }

    return this.extractStrategy(
      result,
      heroCards,
      board,
      heroIsIP,
      'FLOP',
      Date.now() - startTime,
      nodeId,
    );
  }

  // ── Turn resolving ──

  private solveTurn(
    heroCards: [string, string],
    board: number[],
    heroIsIP: boolean,
    actions?: HandAction[],
    seatToPlayer?: Map<number, number>,
    bb: number = 1,
  ): ResolvedStrategy | null {
    const startTime = Date.now();

    // If we don't have a flop result, solve the flop first
    if (!this.flopResult) {
      const flopBoard = board.slice(0, 3);
      this.solveFlop(heroCards, flopBoard, heroIsIP, actions, seatToPlayer, bb);
      if (!this.flopResult) return null;
    }

    const turnCard = board[3];
    this.log(`Resolving turn: ${indexToCardStr(turnCard)}`);

    // Find the correct transition terminal based on flop action history
    let transitionTerminalId: number;
    const transitionIds = [...this.flopResult.boundaryData.keys()];
    if (transitionIds.length === 0) {
      this.log('No transition terminals in flop result');
      return null;
    }

    if (actions && seatToPlayer && transitionIds.length > 1) {
      const flopActions = actions.filter((a) => a.street === 'FLOP');
      const nav = navigateTree(
        this.flopResult.tree,
        flopActions,
        seatToPlayer,
        bb,
        this.config.verbose ? (msg) => this.log(msg) : undefined,
      );
      if (nav && nav.terminalId >= 0 && transitionIds.includes(nav.terminalId)) {
        transitionTerminalId = nav.terminalId;
        this.log(
          `Turn: using flop transition terminal ${transitionTerminalId} (from ${flopActions.length} flop actions)`,
        );
      } else {
        transitionTerminalId = transitionIds[0];
        this.log(
          `Turn: flop nav didn't reach a matching terminal — using first (${transitionTerminalId})`,
        );
      }
    } else {
      transitionTerminalId = transitionIds[0];
    }

    const turnResolveResult = resolveSubgame({
      parentResult: this.flopResult,
      transitionTerminalId,
      newCard: turnCard,
      treeConfig: this.config.treeConfig,
      oopRange: this.oopRange,
      ipRange: this.ipRange,
      parentBoard: this.flopBoard,
      iterations: this.config.turnIterations,
      transitionEvalFn: this.createTransitionEvalFn(),
      onProgress: this.config.verbose
        ? (iter, elapsed) => {
            if (iter % 100 === 0)
              this.log(`  Turn: ${iter}/${this.config.turnIterations} (${elapsed}ms)`);
          }
        : undefined,
    });

    this.turnResult = turnResolveResult;
    this.currentBoard = [...board];

    // Navigate turn tree to the correct decision node
    let nodeId = 0;
    if (actions && seatToPlayer) {
      const turnActions = actions.filter((a) => a.street === 'TURN');
      if (turnActions.length > 0) {
        const nav = navigateTree(
          turnResolveResult.streetResult.tree,
          turnActions,
          seatToPlayer,
          bb,
          this.config.verbose ? (msg) => this.log(msg) : undefined,
        );
        if (nav && nav.nodeId >= 0) {
          nodeId = nav.nodeId;
          this.log(`Turn nav: ${turnActions.length} actions → node ${nodeId}`);
        } else if (nav && nav.terminalId >= 0) {
          this.log(`Turn nav reached terminal — no decision needed`);
          return null;
        } else {
          this.log(`Turn nav failed — falling back to root`);
        }
      }
    }

    return this.extractStrategy(
      turnResolveResult.streetResult,
      heroCards,
      board,
      heroIsIP,
      'TURN',
      Date.now() - startTime,
      nodeId,
    );
  }

  // ── River resolving ──

  private solveRiver(
    heroCards: [string, string],
    board: number[],
    heroIsIP: boolean,
    actions?: HandAction[],
    seatToPlayer?: Map<number, number>,
    bb: number = 1,
  ): ResolvedStrategy | null {
    const startTime = Date.now();

    // If we don't have a turn result, solve flop + turn first
    if (!this.turnResult) {
      const turnBoard = board.slice(0, 4);
      this.solveTurn(heroCards, turnBoard, heroIsIP, actions, seatToPlayer, bb);
      if (!this.turnResult) return null;
    }

    const riverCard = board[4];
    this.log(`Resolving river: ${indexToCardStr(riverCard)}`);

    // Find the correct transition terminal based on turn action history
    let transitionTerminalId: number;
    const transitionIds = [...this.turnResult.streetResult.boundaryData.keys()];
    if (transitionIds.length === 0) {
      this.log('No transition terminals in turn result');
      return null;
    }

    if (actions && seatToPlayer && transitionIds.length > 1) {
      const turnActions = actions.filter((a) => a.street === 'TURN');
      const nav = navigateTree(
        this.turnResult.streetResult.tree,
        turnActions,
        seatToPlayer,
        bb,
        this.config.verbose ? (msg) => this.log(msg) : undefined,
      );
      if (nav && nav.terminalId >= 0 && transitionIds.includes(nav.terminalId)) {
        transitionTerminalId = nav.terminalId;
        this.log(`River: using turn transition terminal ${transitionTerminalId}`);
      } else {
        transitionTerminalId = transitionIds[0];
      }
    } else {
      transitionTerminalId = transitionIds[0];
    }

    const riverResolveResult = resolveSubgame({
      parentResult: this.turnResult.streetResult,
      transitionTerminalId,
      newCard: riverCard,
      treeConfig: this.config.treeConfig,
      oopRange: this.oopRange,
      ipRange: this.ipRange,
      parentBoard: this.turnResult.board,
      iterations: this.config.riverIterations,
      onProgress: this.config.verbose
        ? (iter, elapsed) => {
            if (iter % 100 === 0)
              this.log(`  River: ${iter}/${this.config.riverIterations} (${elapsed}ms)`);
          }
        : undefined,
    });

    this.currentBoard = [...board];

    // Navigate river tree to the correct decision node
    let nodeId = 0;
    if (actions && seatToPlayer) {
      const riverActions = actions.filter((a) => a.street === 'RIVER');
      if (riverActions.length > 0) {
        const nav = navigateTree(
          riverResolveResult.streetResult.tree,
          riverActions,
          seatToPlayer,
          bb,
          this.config.verbose ? (msg) => this.log(msg) : undefined,
        );
        if (nav && nav.nodeId >= 0) {
          nodeId = nav.nodeId;
          this.log(`River nav: ${riverActions.length} actions → node ${nodeId}`);
        } else if (nav && nav.terminalId >= 0) {
          this.log(`River nav reached terminal — no decision needed`);
          return null;
        } else {
          this.log(`River nav failed — falling back to root`);
        }
      }
    }

    return this.extractStrategy(
      riverResolveResult.streetResult,
      heroCards,
      board,
      heroIsIP,
      'RIVER',
      Date.now() - startTime,
      nodeId,
    );
  }

  // ── Strategy extraction ──

  /**
   * Extract hero's action probabilities from a solved tree at the given node.
   */
  private extractStrategy(
    result: StreetSolveResult,
    heroCards: [string, string],
    board: number[],
    heroIsIP: boolean,
    street: string,
    solveTimeMs: number,
    nodeId: number = 0,
  ): ResolvedStrategy | null {
    const { store, tree, validCombos } = result;
    const nc = validCombos.numCombos;

    // Find hero's combo in the valid combo list
    const c1 = cardToIndex(heroCards[0]);
    const c2 = cardToIndex(heroCards[1]);
    const lo = Math.min(c1, c2);
    const hi = Math.max(c1, c2);
    const globalId = comboIndex(lo, hi);
    const heroLocalIdx = validCombos.globalToLocal[globalId];

    if (heroLocalIdx < 0) {
      this.log(`Hero cards blocked by board: ${heroCards.join('')}`);
      return null;
    }

    // Get average strategy at the decision node
    const numActions = tree.nodeNumActions[nodeId];
    const avgStrategy = new Float32Array(numActions * nc);
    store.getAverageStrategy(nodeId, numActions, avgStrategy);

    // Extract per-action probabilities for hero's specific combo
    const actionProbs: number[] = [];
    const actionOffset = tree.nodeActionOffset[nodeId];

    for (let a = 0; a < numActions; a++) {
      actionProbs.push(avgStrategy[a * nc + heroLocalIdx]);
    }

    // Normalize (should already sum to ~1, but ensure numerical stability)
    const sum = actionProbs.reduce((s, p) => s + p, 0);
    if (sum > 0) {
      for (let i = 0; i < actionProbs.length; i++) {
        actionProbs[i] /= sum;
      }
    }

    // Map solver actions to raise/call/fold
    const availableActions: string[] = [];
    for (let a = 0; a < numActions; a++) {
      const actionType = tree.actionType[actionOffset + a];
      availableActions.push(decodeActionType(actionType, a));
    }

    // Aggregate into raise/call/fold buckets
    const strategy = aggregateToMix(availableActions, actionProbs);

    this.log(
      `${street} solved in ${solveTimeMs}ms: ` +
        `R=${strategy.raise.toFixed(3)} C=${strategy.call.toFixed(3)} F=${strategy.fold.toFixed(3)} ` +
        `(${this.config.flopIterations} iters, ${nc} combos)`,
    );

    return {
      ...strategy,
      availableActions,
      actionProbs,
      solveTimeMs,
      street,
      iterations:
        street === 'FLOP'
          ? this.config.flopIterations
          : street === 'TURN'
            ? this.config.turnIterations
            : this.config.riverIterations,
    };
  }

  // ── Value Network Transition Evaluator ──

  /**
   * Create a TransitionEvalFn that estimates EV at street boundaries
   * using Monte Carlo sampling of future runouts.
   *
   * For flop→turn transitions: samples turn+river cards and averages equity
   * across runouts, giving much better EV estimates than current-board-only
   * equity (which ignores card runout entirely on a 3-card board).
   *
   * Falls back to the default MC heuristic if no custom config needed.
   */
  private createTransitionEvalFn(): TransitionEvalFn | undefined {
    const numSamples = this.config.transitionSamples;

    return (
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
    ): void => {
      const cardsNeeded = 5 - board.length; // flop→2, turn→1
      if (cardsNeeded === 0) {
        // Already at river — exact equity on current board
        this.computeEquityEV(
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
        );
        return;
      }

      // Build deck of available cards (excluding board)
      const dead = new Uint8Array(52);
      for (const c of board) dead[c] = 1;
      const available: number[] = [];
      for (let c = 0; c < 52; c++) {
        if (!dead[c]) available.push(c);
      }

      outEV.fill(0);
      const tempEV = new Float32Array(numCombos);
      const fullBoard = [...board, ...new Array(cardsNeeded).fill(0)];

      // Deterministic RNG for reproducibility
      let rng = 42;
      for (let s = 0; s < numSamples; s++) {
        // Fisher-Yates partial shuffle
        const arr = [...available];
        for (let i = 0; i < cardsNeeded && i < arr.length; i++) {
          rng = (rng * 1103515245 + 12345) & 0x7fffffff;
          const j = i + (rng % (arr.length - i));
          [arr[i], arr[j]] = [arr[j], arr[i]];
        }
        for (let k = 0; k < cardsNeeded; k++) {
          fullBoard[board.length + k] = arr[k];
        }

        tempEV.fill(0);
        this.computeEquityEV(
          combos,
          fullBoard,
          pot,
          oopReach,
          ipReach,
          blockerMatrix,
          numCombos,
          traverser,
          stacks,
          tempEV,
        );

        for (let i = 0; i < numCombos; i++) {
          outEV[i] += tempEV[i];
        }
      }

      // Average across samples
      const invN = 1 / numSamples;
      for (let i = 0; i < numCombos; i++) {
        outEV[i] *= invN;
      }
    };
  }

  /**
   * Compute reach-weighted equity EV on a specific board.
   * Used by the MC transition eval for each sampled runout.
   */
  private computeEquityEV(
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
  ): void {
    const opponentReach = traverser === 0 ? ipReach : oopReach;

    const handValues = new Float64Array(numCombos);
    for (let i = 0; i < numCombos; i++) {
      handValues[i] = evaluateHandBoard(combos[i][0], combos[i][1], board);
    }

    const totalChips = pot + stacks.reduce((a, b) => a + b, 0);
    const startTotal = totalChips / stacks.length;
    const traverserStack = stacks[traverser];

    for (let i = 0; i < numCombos; i++) {
      let wins = 0;
      let losses = 0;
      let ties = 0;

      for (let j = 0; j < numCombos; j++) {
        if (blockerMatrix[i * numCombos + j]) continue;
        const oppR = opponentReach[j];
        if (oppR === 0) continue;

        if (handValues[i] > handValues[j]) {
          wins += oppR;
        } else if (handValues[i] < handValues[j]) {
          losses += oppR;
        } else {
          ties += oppR;
        }
      }

      const total = wins + losses + ties;
      if (total === 0) {
        outEV[i] = 0;
        continue;
      }

      const winPayoff = traverserStack + pot - startTotal;
      const losePayoff = traverserStack - startTotal;
      const tiePayoff = traverserStack + pot / 2 - startTotal;

      outEV[i] = wins * winPayoff + losses * losePayoff + ties * tiePayoff;
    }
  }

  // ── Utilities ──

  private log(msg: string): void {
    if (this.config.verbose) {
      console.log(`[Resolver] ${msg}`);
    }
  }
}

// ═══════════════════════════════════════════════════════════
// Resolver Pool — manages one RealtimeResolver per scenario
// ═══════════════════════════════════════════════════════════

export interface ResolverPoolConfig {
  projectRoot: string;
  chartsPath?: string;
  flopIterations?: number;
  turnIterations?: number;
  riverIterations?: number;
  verbose?: boolean;
}

export class ResolverPool {
  private resolvers = new Map<ScenarioKey, RealtimeResolver>();
  private config: ResolverPoolConfig;

  constructor(config: ResolverPoolConfig) {
    this.config = config;
  }

  /**
   * Initialize all 4 scenario resolvers. Returns count of successfully loaded.
   */
  initialize(): number {
    const scenarios = Object.entries(SCENARIO_CONFIGS) as [ScenarioKey, ScenarioConfig][];
    let loaded = 0;

    for (const [key, sc] of scenarios) {
      const modelAbsPath = join(this.config.projectRoot, sc.modelPath);
      const chartsAbsPath =
        this.config.chartsPath ?? join(this.config.projectRoot, 'data', 'preflop_charts.json');

      const resolver = new RealtimeResolver({
        chartsPath: chartsAbsPath,
        modelPath: modelAbsPath,
        treeConfig: sc.treeConfig,
        rangeOptions: sc.rangeOptions,
        flopIterations: this.config.flopIterations,
        turnIterations: this.config.turnIterations,
        riverIterations: this.config.riverIterations,
        verbose: this.config.verbose,
      });

      if (resolver.initialize()) {
        this.resolvers.set(key, resolver);
        loaded++;
      } else {
        this.log(`Scenario ${key} failed to initialize — skipped`);
      }
    }

    this.log(`ResolverPool: ${loaded}/4 scenarios loaded`);
    return loaded;
  }

  /**
   * Get the resolver for a specific scenario.
   * Returns null if that scenario was not loaded.
   */
  get(scenario: ScenarioKey): RealtimeResolver | null {
    return this.resolvers.get(scenario) ?? null;
  }

  /**
   * Reset per-hand state on all resolvers.
   */
  resetHand(): void {
    for (const resolver of this.resolvers.values()) {
      resolver.resetHand();
    }
  }

  /** Number of successfully loaded scenarios */
  get size(): number {
    return this.resolvers.size;
  }

  private log(msg: string): void {
    if (this.config.verbose) {
      console.log(`[ResolverPool] ${msg}`);
    }
  }
}

// ═══════════════════════════════════════════════════════════
// Helper functions
// ═══════════════════════════════════════════════════════════

const RANK_CHARS = '23456789TJQKA';
const SUIT_CHARS = 'cdhs';

function indexToCardStr(index: number): string {
  return RANK_CHARS[index >> 2] + SUIT_CHARS[index & 3];
}

/**
 * Decode numeric action type from FlatTree to human-readable string.
 * actionType encoding: 0=FOLD, 1=CHECK, 2=CALL, 3+=BET/RAISE variants
 */
function decodeActionType(actionType: number, actionIndex: number): string {
  switch (actionType) {
    case 0:
      return 'fold';
    case 1:
      return 'check';
    case 2:
      return 'call';
    default:
      return `bet_${actionIndex}`; // bet/raise sizes
  }
}

/**
 * Aggregate solver action probabilities into raise/call/fold mix.
 *
 * Solver actions: fold, check, call, bet_0, bet_1, ..., allin
 * Bot actions: raise (= all bets/raises), call (= check/call), fold
 */
function aggregateToMix(
  actions: string[],
  probs: number[],
): { raise: number; call: number; fold: number } {
  let raise = 0;
  let call = 0;
  let fold = 0;

  for (let i = 0; i < actions.length; i++) {
    const a = actions[i];
    if (a === 'fold') {
      fold += probs[i];
    } else if (a === 'check' || a === 'call') {
      call += probs[i];
    } else {
      // bet_N, raise_N, allin → all map to "raise"
      raise += probs[i];
    }
  }

  return { raise, call, fold };
}
