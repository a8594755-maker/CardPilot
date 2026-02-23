// Build the abstract betting tree for HU postflop
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
  stacks: [number, number]; // remaining stack per player
  player: Player;           // whose turn to act
  history: string;          // encoded action history
  raiseCount: number;       // raises on this street
  isFirstAction: boolean;   // first action on this street
  facingBet: number;        // bet the current player must respond to (0 if none)
}

/**
 * Build the complete postflop game tree from config.
 * Returns the root ActionNode (OOP acts first on flop).
 */
export function buildTree(config: TreeConfig): ActionNode {
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
    stacks: [state.stacks[0], state.stacks[1]],
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
  const opp: Player = (1 - p) as Player;
  const newHistory = state.history + actionChar(action);

  // FOLD → terminal (opponent wins)
  if (action === 'fold') {
    return {
      type: 'terminal',
      pot: state.pot,
      showdown: false,
      lastToAct: p,
      playerStacks: [state.stacks[0], state.stacks[1]],
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
    const newStacks: [number, number] = [state.stacks[0], state.stacks[1]];
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

  const newStacks: [number, number] = [state.stacks[0], state.stacks[1]];
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
      playerStacks: [state.stacks[0], state.stacks[1]],
    } satisfies TerminalNode;
  }

  // New street: OOP acts first, reset raise count
  return buildNode(config, {
    street: nextStreet,
    pot: state.pot,
    stacks: [state.stacks[0], state.stacks[1]],
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
