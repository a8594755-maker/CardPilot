// Build the abstract betting tree for postflop play.
// Supports HU (2-player) and multi-way (3+ player) trees.
// The tree is a "skeleton" — same shape for all boards.
// Only card abstraction (hand buckets) varies per board.

import type {
  GameNode, ActionNode, TerminalNode,
  Action, Street, Player, TreeConfig,
} from '../types.js';
import { calcBetAmount, calcRaiseAmount } from './tree-config.js';

const NEXT_STREET: Record<string, Street | null> = {
  'FLOP': 'TURN',
  'TURN': 'RIVER',
  'RIVER': null,
};

interface BuildState {
  street: Street;
  pot: number;
  stacks: number[];   // remaining stack per player
  player: Player;           // whose turn to act
  history: string;          // encoded action history
  raiseCount: number;       // raises on this street
  isFirstAction: boolean;   // first action on this street
  facingBet: number;        // bet the current player must respond to (0 if none)
}

/**
 * Build the complete postflop game tree from config.
 * Dispatches to HU or multi-way builder based on numPlayers.
 * Returns the root ActionNode (OOP acts first on flop).
 */
export function buildTree(config: TreeConfig): ActionNode {
  const numPlayers = config.numPlayers ?? 2;
  if (numPlayers > 2) {
    return buildTreeMultiWay(config);
  }
  const initialState: BuildState = {
    street: 'FLOP',
    pot: config.startingPot,
    stacks: [config.effectiveStack, config.effectiveStack],
    player: 0, // OOP (BB) acts first
    history: '',
    raiseCount: 0,
    isFirstAction: true,
    facingBet: 0,
  };
  return buildNode(config, initialState) as ActionNode;
}

function buildNode(config: TreeConfig, state: BuildState): GameNode {
  const actions = getLegalActions(config, state);
  const children = new Map<Action, GameNode>();

  const node: ActionNode = {
    type: 'action',
    player: state.player,
    street: state.street,
    pot: state.pot,
    stacks: [...state.stacks],
    actions,
    children,
    historyKey: state.history,
    raiseCount: state.raiseCount,
  };

  for (const action of actions) {
    const child = applyAction(config, state, action);
    children.set(action, child);
  }

  return node;
}

function getLegalActions(config: TreeConfig, state: BuildState): Action[] {
  const actions: Action[] = [];
  const playerStack = state.stacks[state.player];
  const betSizes = getBetSizesForStreet(config, state.street);

  if (state.facingBet > 0) {
    // Facing a bet/raise
    actions.push('fold');
    actions.push('call');

    // Can only raise if under the raise cap and have enough stack
    if (state.raiseCount < config.raiseCapPerStreet && playerStack > state.facingBet) {
      const raiseSizes = getRaiseSizesAvailable(
        config, state.pot, state.facingBet, playerStack, state.street
      );
      actions.push(...raiseSizes);
    }
  } else {
    // No bet to face — can check or bet
    actions.push('check');

    if (playerStack > 0) {
      const available = getBetActionsAvailable(
        config, state.pot, playerStack, state.street
      );
      actions.push(...available);
    }
  }

  return actions;
}

function getBetActionsAvailable(
  config: TreeConfig,
  pot: number,
  playerStack: number,
  street: Street
): Action[] {
  const sizes = getBetSizesForStreet(config, street);
  const actions: Action[] = [];

  for (let i = 0; i < sizes.length; i++) {
    const amount = calcBetAmount(pot, sizes[i], playerStack);
    if (amount >= playerStack) {
      // This size is effectively all-in; add allin and stop
      if (!actions.includes('allin')) actions.push('allin');
      break;
    }
    actions.push(`bet_${i}`);
  }

  // Always allow all-in if not already added and stack > 0
  if (!actions.includes('allin') && playerStack > 0) {
    actions.push('allin');
  }

  return actions;
}

function getRaiseSizesAvailable(
  config: TreeConfig,
  pot: number,
  facingBet: number,
  playerStack: number,
  street: Street
): Action[] {
  const sizes = getBetSizesForStreet(config, street);
  const actions: Action[] = [];

  for (let i = 0; i < sizes.length; i++) {
    const amount = calcRaiseAmount(pot, facingBet, sizes[i], playerStack);
    if (amount >= playerStack) {
      if (!actions.includes('allin')) actions.push('allin');
      break;
    }
    actions.push(`raise_${i}`);
  }

  if (!actions.includes('allin') && playerStack > facingBet) {
    actions.push('allin');
  }

  return actions;
}

function getBetSizesForStreet(config: TreeConfig, street: Street): number[] {
  switch (street) {
    case 'FLOP': return config.betSizes.flop;
    case 'TURN': return config.betSizes.turn;
    case 'RIVER': return config.betSizes.river;
  }
}

function actionChar(action: Action): string {
  if (action === 'fold') return 'f';
  if (action === 'check') return 'x';
  if (action === 'call') return 'c';
  if (action === 'allin') return 'A';
  // bet_0 → '1', bet_1 → '2', ..., raise_0 → '1', raise_1 → '2', ...
  const match = action.match(/^(?:bet|raise)_(\d+)$/);
  if (match) return String(parseInt(match[1]) + 1);
  return '?';
}

function applyAction(
  config: TreeConfig,
  state: BuildState,
  action: Action
): GameNode {
  const p = state.player;
  const opp: Player = 1 - p;
  const newHistory = state.history + actionChar(action);

  // FOLD → terminal (opponent wins)
  if (action === 'fold') {
    return {
      type: 'terminal',
      pot: state.pot,
      showdown: false,
      lastToAct: p,
      playerStacks: [...state.stacks],
    } satisfies TerminalNode;
  }

  // CHECK
  if (action === 'check') {
    if (!state.isFirstAction) {
      // Both players checked → advance to next street or showdown
      return advanceStreet(config, state, newHistory);
    }
    // First action check → opponent acts
    return buildNode(config, {
      ...state,
      player: opp,
      history: newHistory,
      isFirstAction: false,
      facingBet: 0,
    });
  }

  // CALL
  if (action === 'call') {
    const callAmount = Math.min(state.facingBet, state.stacks[p]);
    const newStacks = [...state.stacks];
    newStacks[p] -= callAmount;
    const newPot = state.pot + callAmount;

    // Check if either player is all-in
    if (newStacks[0] <= 0 || newStacks[1] <= 0) {
      return {
        type: 'terminal',
        pot: newPot,
        showdown: true,
        lastToAct: p,
        playerStacks: newStacks,
      } satisfies TerminalNode;
    }

    // Advance to next street
    return advanceStreet(config, {
      ...state,
      pot: newPot,
      stacks: newStacks,
    }, newHistory);
  }

  // BET / RAISE / ALL-IN
  let betAmount: number;
  const sizes = getBetSizesForStreet(config, state.street);

  if (action === 'allin') {
    betAmount = state.stacks[p];
  } else {
    const match = action.match(/^(bet|raise)_(\d+)$/);
    if (match) {
      const idx = parseInt(match[2]);
      if (match[1] === 'bet') {
        betAmount = calcBetAmount(state.pot, sizes[idx], state.stacks[p]);
      } else {
        betAmount = calcRaiseAmount(state.pot, state.facingBet, sizes[idx], state.stacks[p]);
      }
    } else {
      betAmount = state.stacks[p]; // fallback
    }
  }

  const newStacks = [...state.stacks];
  newStacks[p] -= betAmount;
  const newPot = state.pot + betAmount;
  const isRaise = state.facingBet > 0;

  // Opponent now faces the bet
  const facingAmount = betAmount - state.facingBet; // additional chips opponent must put in

  return buildNode(config, {
    street: state.street,
    pot: newPot,
    stacks: newStacks,
    player: opp,
    history: newHistory,
    raiseCount: state.raiseCount + (isRaise ? 1 : 0),
    isFirstAction: false,
    facingBet: facingAmount > 0 ? betAmount : state.facingBet,
  });
}

function advanceStreet(
  config: TreeConfig,
  state: BuildState,
  history: string
): GameNode {
  const nextStreet = NEXT_STREET[state.street];

  if (!nextStreet) {
    // River is done → showdown
    return {
      type: 'terminal',
      pot: state.pot,
      showdown: true,
      lastToAct: state.player,
      playerStacks: [...state.stacks],
    } satisfies TerminalNode;
  }

  // New street: OOP acts first, reset raise count
  return buildNode(config, {
    street: nextStreet,
    pot: state.pot,
    stacks: [...state.stacks],
    player: 0, // OOP first
    history: history + '/',
    raiseCount: 0,
    isFirstAction: true,
    facingBet: 0,
  });
}

// Stats helper for debugging
export function countNodes(node: GameNode): { action: number; terminal: number } {
  if (node.type === 'terminal') return { action: 0, terminal: 1 };
  let action = 1;
  let terminal = 0;
  for (const child of node.children.values()) {
    const sub = countNodes(child);
    action += sub.action;
    terminal += sub.terminal;
  }
  return { action, terminal };
}

// ═══════════════════════════════════════════════════════════
// Multi-way (3+ player) tree builder
// ═══════════════════════════════════════════════════════════

interface MultiWayBuildState {
  numPlayers: number;
  street: Street;
  pot: number;
  stacks: number[];
  activePlayers: boolean[];    // true = in the hand (not folded)
  currentBets: number[];       // amount each player bet THIS round
  maxBet: number;              // highest bet this round
  playerToAct: number;         // current player index
  history: string;
  raiseCount: number;
  hasActedThisRound: boolean[]; // whether each player has had a turn this round
}

function buildTreeMultiWay(config: TreeConfig): ActionNode {
  const n = config.numPlayers!;
  const state: MultiWayBuildState = {
    numPlayers: n,
    street: 'FLOP',
    pot: config.startingPot,
    stacks: Array(n).fill(config.effectiveStack),
    activePlayers: Array(n).fill(true),
    currentBets: Array(n).fill(0),
    maxBet: 0,
    playerToAct: 0, // Player 0 (BB/OOP) acts first postflop
    history: '',
    raiseCount: 0,
    hasActedThisRound: Array(n).fill(false),
  };
  return buildNodeMW(config, state) as ActionNode;
}

/** Find next player who can act (active + has chips) */
function nextActingPlayerMW(state: MultiWayBuildState, after: number): number | null {
  for (let i = 1; i <= state.numPlayers; i++) {
    const p = (after + i) % state.numPlayers;
    if (state.activePlayers[p] && state.stacks[p] > 0) return p;
  }
  return null;
}

/** Count players who haven't folded */
function countActiveMW(state: MultiWayBuildState): number {
  return state.activePlayers.filter(a => a).length;
}

/** Check if the current betting round is complete */
function isRoundCompleteMW(state: MultiWayBuildState): boolean {
  for (let i = 0; i < state.numPlayers; i++) {
    if (!state.activePlayers[i]) continue;
    if (state.stacks[i] <= 0) continue; // all-in, can't act
    if (!state.hasActedThisRound[i]) return false;
    if (state.currentBets[i] < state.maxBet) return false;
  }
  return true;
}

function buildNodeMW(config: TreeConfig, state: MultiWayBuildState): GameNode {
  const p = state.playerToAct;
  const actions = getLegalActionsMW(config, state);
  const children = new Map<Action, GameNode>();

  const node: ActionNode = {
    type: 'action',
    player: p,
    street: state.street,
    pot: state.pot,
    stacks: [...state.stacks],
    activePlayers: [...state.activePlayers],
    actions,
    children,
    historyKey: state.history,
    raiseCount: state.raiseCount,
  };

  for (const action of actions) {
    children.set(action, applyActionMW(config, state, action));
  }

  return node;
}

function getLegalActionsMW(config: TreeConfig, state: MultiWayBuildState): Action[] {
  const p = state.playerToAct;
  const playerStack = state.stacks[p];
  const facingBet = state.maxBet - state.currentBets[p];
  const actions: Action[] = [];

  if (facingBet > 0) {
    actions.push('fold');
    actions.push('call');
    if (state.raiseCount < config.raiseCapPerStreet && playerStack > facingBet) {
      const raiseSizes = getRaiseSizesAvailable(
        config, state.pot, facingBet, playerStack, state.street
      );
      actions.push(...raiseSizes);
    }
  } else {
    actions.push('check');
    if (playerStack > 0) {
      const available = getBetActionsAvailable(
        config, state.pot, playerStack, state.street
      );
      actions.push(...available);
    }
  }

  return actions;
}

function applyActionMW(
  config: TreeConfig,
  state: MultiWayBuildState,
  action: Action,
): GameNode {
  const p = state.playerToAct;
  const newHistory = state.history + actionChar(action);
  const facingBet = state.maxBet - state.currentBets[p];

  // FOLD
  if (action === 'fold') {
    const newActive = [...state.activePlayers];
    newActive[p] = false;
    const activeCount = newActive.filter(a => a).length;

    // Only 1 player left → terminal fold
    if (activeCount === 1) {
      const winner = newActive.indexOf(true);
      return {
        type: 'terminal',
        pot: state.pot,
        showdown: false,
        lastToAct: p,
        playerStacks: [...state.stacks],
        foldedPlayers: newActive.map(a => !a),
        winner,
      } satisfies TerminalNode;
    }

    // Continue with fewer players
    const newState: MultiWayBuildState = {
      ...state,
      activePlayers: newActive,
      hasActedThisRound: [...state.hasActedThisRound],
      currentBets: [...state.currentBets],
      stacks: [...state.stacks],
      history: newHistory,
    };
    newState.hasActedThisRound[p] = true;

    // Check if round is complete after this fold
    if (isRoundCompleteMW(newState)) {
      return advanceStreetMW(config, newState, newHistory);
    }

    // Next player acts
    const next = nextActingPlayerMW(newState, p);
    if (next === null) {
      return advanceStreetMW(config, newState, newHistory);
    }
    newState.playerToAct = next;
    return buildNodeMW(config, newState);
  }

  // CHECK
  if (action === 'check') {
    const newState: MultiWayBuildState = {
      ...state,
      hasActedThisRound: [...state.hasActedThisRound],
      currentBets: [...state.currentBets],
      stacks: [...state.stacks],
      activePlayers: [...state.activePlayers],
      history: newHistory,
    };
    newState.hasActedThisRound[p] = true;

    if (isRoundCompleteMW(newState)) {
      return advanceStreetMW(config, newState, newHistory);
    }

    const next = nextActingPlayerMW(newState, p);
    if (next === null) {
      return advanceStreetMW(config, newState, newHistory);
    }
    newState.playerToAct = next;
    return buildNodeMW(config, newState);
  }

  // CALL
  if (action === 'call') {
    const callAmount = Math.min(facingBet, state.stacks[p]);
    const newStacks = [...state.stacks];
    newStacks[p] -= callAmount;
    const newBets = [...state.currentBets];
    newBets[p] += callAmount;
    const newPot = state.pot + callAmount;

    const newState: MultiWayBuildState = {
      ...state,
      pot: newPot,
      stacks: newStacks,
      currentBets: newBets,
      hasActedThisRound: [...state.hasActedThisRound],
      activePlayers: [...state.activePlayers],
      history: newHistory,
    };
    newState.hasActedThisRound[p] = true;

    // Check if everyone is all-in or round complete
    if (isRoundCompleteMW(newState)) {
      // If any active player is all-in and we have 2+ active, check if all-in runout
      const activeWithChips = newState.activePlayers.filter((a, i) => a && newStacks[i] > 0).length;
      if (activeWithChips <= 1) {
        // All-in: straight to showdown terminal
        return {
          type: 'terminal',
          pot: newPot,
          showdown: true,
          lastToAct: p,
          playerStacks: newStacks,
          foldedPlayers: newState.activePlayers.map(a => !a),
        } satisfies TerminalNode;
      }
      return advanceStreetMW(config, newState, newHistory);
    }

    const next = nextActingPlayerMW(newState, p);
    if (next === null) {
      return advanceStreetMW(config, newState, newHistory);
    }
    newState.playerToAct = next;
    return buildNodeMW(config, newState);
  }

  // BET / RAISE / ALL-IN
  let betAmount: number;
  const sizes = getBetSizesForStreet(config, state.street);

  if (action === 'allin') {
    betAmount = state.stacks[p];
  } else {
    const match = action.match(/^(bet|raise)_(\d+)$/);
    if (match) {
      const idx = parseInt(match[2]);
      if (match[1] === 'bet') {
        betAmount = calcBetAmount(state.pot, sizes[idx], state.stacks[p]);
      } else {
        betAmount = calcRaiseAmount(state.pot, facingBet, sizes[idx], state.stacks[p]);
      }
    } else {
      betAmount = state.stacks[p];
    }
  }

  const newStacks = [...state.stacks];
  newStacks[p] -= betAmount;
  const newBets = [...state.currentBets];
  newBets[p] += betAmount;
  const newMaxBet = Math.max(state.maxBet, newBets[p]);
  const newPot = state.pot + betAmount;
  const isRaise = facingBet > 0;

  // Bet/raise reopens action for all other active players
  const newHasActed = Array(state.numPlayers).fill(false);
  newHasActed[p] = true;

  const newState: MultiWayBuildState = {
    ...state,
    pot: newPot,
    stacks: newStacks,
    currentBets: newBets,
    maxBet: newMaxBet,
    hasActedThisRound: newHasActed,
    activePlayers: [...state.activePlayers],
    history: newHistory,
    raiseCount: state.raiseCount + (isRaise ? 1 : 0),
  };

  const next = nextActingPlayerMW(newState, p);
  if (next === null) {
    return advanceStreetMW(config, newState, newHistory);
  }
  newState.playerToAct = next;
  return buildNodeMW(config, newState);
}

function advanceStreetMW(
  config: TreeConfig,
  state: MultiWayBuildState,
  history: string,
): GameNode {
  const nextStreet = NEXT_STREET[state.street];

  if (!nextStreet) {
    return {
      type: 'terminal',
      pot: state.pot,
      showdown: true,
      lastToAct: state.playerToAct,
      playerStacks: [...state.stacks],
      foldedPlayers: state.activePlayers.map(a => !a),
    } satisfies TerminalNode;
  }

  // New street: first active player with chips acts first
  const firstActive = nextActingPlayerMW(
    { ...state, playerToAct: state.numPlayers - 1 }, // wrap around to find player 0 first
    state.numPlayers - 1,
  );

  if (firstActive === null) {
    // Everyone is all-in → showdown
    return {
      type: 'terminal',
      pot: state.pot,
      showdown: true,
      lastToAct: state.playerToAct,
      playerStacks: [...state.stacks],
      foldedPlayers: state.activePlayers.map(a => !a),
    } satisfies TerminalNode;
  }

  return buildNodeMW(config, {
    ...state,
    street: nextStreet,
    stacks: [...state.stacks],
    activePlayers: [...state.activePlayers],
    currentBets: Array(state.numPlayers).fill(0),
    maxBet: 0,
    playerToAct: firstActive,
    history: history + '/',
    raiseCount: 0,
    hasActedThisRound: Array(state.numPlayers).fill(false),
  });
}
