// Single-street tree builder for subgame solving.
//
// Unlike the full tree builder which builds Flop→Turn→River,
// this builds a tree for only one street. At street transitions
// (e.g., end of flop betting), it creates "transition" terminal nodes
// instead of continuing to the next street.
//
// This is the foundation for subgame solving (Phase 4):
// 1. Build and solve a Flop-only tree
// 2. When user picks a Turn card, build and solve a Turn-only tree
// 3. When user picks a River card, build and solve a River-only tree

import type { GameNode, ActionNode, TerminalNode, Action, Street, TreeConfig } from '../types.js';
import { calcBetAmount, calcRaiseAmount } from '../tree/tree-config.js';

// Transition terminal: represents the boundary where the next street begins.
// NOT a fold or showdown — it's a "pause point" for subgame solving.
export interface TransitionTerminal extends TerminalNode {
  /** Marks this as a street transition (not fold/showdown) */
  isTransition: true;
  /** The street that would come next */
  nextStreet: Street;
}

interface StreetBuildState {
  targetStreet: Street;
  pot: number;
  stacks: number[];
  player: number;
  history: string;
  raiseCount: number;
  isFirstAction: boolean;
  facingBet: number;
  numPlayers: number;
  roundStartStacks: number[];
}

/**
 * Build a single-street betting tree.
 *
 * At the end of the betting round (when action closes),
 * instead of advancing to the next street, creates a
 * TransitionTerminal node that stores the pot and stacks
 * at the transition point.
 *
 * For the River street, showdowns are normal TerminalNode.
 * For Flop/Turn, the "end of round" creates TransitionTerminal.
 */
export function buildStreetTree(
  config: TreeConfig,
  street: Street,
  numPlayers: number = 2,
): ActionNode {
  if (numPlayers > 2) {
    return buildStreetTreeMultiWay(config, street, numPlayers);
  }

  const state: StreetBuildState = {
    targetStreet: street,
    pot: config.startingPot,
    stacks: [config.effectiveStack, config.effectiveStack],
    player: 0,
    history: '',
    raiseCount: 0,
    isFirstAction: true,
    facingBet: 0,
    numPlayers: 2,
    roundStartStacks: [config.effectiveStack, config.effectiveStack],
  };

  return buildStreetNode(config, state) as ActionNode;
}

function getBetSizesForStreet(config: TreeConfig, street: Street): number[] {
  switch (street) {
    case 'FLOP':
      return config.betSizes.flop;
    case 'TURN':
      return config.betSizes.turn;
    case 'RIVER':
      return config.betSizes.river;
  }
}

function actionChar(action: Action): string {
  if (action === 'fold') return 'f';
  if (action === 'check') return 'x';
  if (action === 'call') return 'c';
  if (action === 'allin') return 'A';
  const match = action.match(/^(?:bet|raise)_(\d+)$/);
  if (match) return String(parseInt(match[1]) + 1);
  return '?';
}

function buildStreetNode(config: TreeConfig, state: StreetBuildState): GameNode {
  const actions = getStreetLegalActions(config, state);
  const children = new Map<Action, GameNode>();

  const node: ActionNode = {
    type: 'action',
    player: state.player,
    street: state.targetStreet,
    pot: state.pot,
    stacks: [...state.stacks],
    actions,
    children,
    historyKey: state.history,
    historyId: 0,
    raiseCount: state.raiseCount,
  };

  for (const action of actions) {
    children.set(action, applyStreetAction(config, state, action));
  }

  return node;
}

function getStreetLegalActions(config: TreeConfig, state: StreetBuildState): Action[] {
  const actions: Action[] = [];
  const playerStack = state.stacks[state.player];
  const sizes = getBetSizesForStreet(config, state.targetStreet);

  if (state.facingBet > 0) {
    actions.push('fold');
    actions.push('call');
    const invested = state.roundStartStacks[state.player] - state.stacks[state.player];
    if (state.raiseCount < config.raiseCapPerStreet && playerStack > state.facingBet) {
      for (let i = 0; i < sizes.length; i++) {
        const amount = calcRaiseAmount(state.pot, state.facingBet, sizes[i], playerStack, invested);
        if (amount >= playerStack) {
          if (!actions.includes('allin')) actions.push('allin');
          break;
        }
        actions.push(`raise_${i}`);
      }
      if (!actions.includes('allin') && playerStack > state.facingBet) {
        actions.push('allin');
      }
    }
  } else {
    actions.push('check');
    if (playerStack > 0) {
      for (let i = 0; i < sizes.length; i++) {
        const amount = calcBetAmount(state.pot, sizes[i], playerStack);
        if (amount >= playerStack) {
          if (!actions.includes('allin')) actions.push('allin');
          break;
        }
        actions.push(`bet_${i}`);
      }
      if (!actions.includes('allin') && playerStack > 0) {
        actions.push('allin');
      }
    }
  }

  return actions;
}

const NEXT_STREET: Record<string, Street | null> = {
  FLOP: 'TURN',
  TURN: 'RIVER',
  RIVER: null,
};

function applyStreetAction(config: TreeConfig, state: StreetBuildState, action: Action): GameNode {
  const p = state.player;
  const opp = 1 - p;
  const newHistory = state.history + actionChar(action);
  const sizes = getBetSizesForStreet(config, state.targetStreet);

  // FOLD
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
      // Both checked → end of street
      return endOfStreetTerminal(state, newHistory);
    }
    return buildStreetNode(config, {
      ...state,
      player: opp,
      history: newHistory,
      isFirstAction: false,
      facingBet: 0,
    });
  }

  // CALL
  if (action === 'call') {
    const callInvested = state.roundStartStacks[p] - state.stacks[p];
    const callAmount = Math.min(state.facingBet - callInvested, state.stacks[p]);
    const newStacks = [...state.stacks];
    newStacks[p] -= callAmount;
    const newPot = state.pot + callAmount;

    if (newStacks[0] <= 0 || newStacks[1] <= 0) {
      // All-in → showdown (even in street tree, all-in goes to showdown)
      return {
        type: 'terminal',
        pot: newPot,
        showdown: true,
        lastToAct: p,
        playerStacks: newStacks,
      } satisfies TerminalNode;
    }

    // End of street (call closes action)
    return endOfStreetTerminalWithState(state, newPot, newStacks);
  }

  // BET / RAISE / ALL-IN
  // betAmount = ADDITIONAL chips from the player's stack
  let betAmount: number;
  const invested = state.roundStartStacks[p] - state.stacks[p];
  if (action === 'allin') {
    betAmount = state.stacks[p];
  } else {
    const match = action.match(/^(bet|raise)_(\d+)$/);
    if (match) {
      const idx = parseInt(match[2]);
      betAmount =
        match[1] === 'bet'
          ? calcBetAmount(state.pot, sizes[idx], state.stacks[p])
          : calcRaiseAmount(state.pot, state.facingBet, sizes[idx], state.stacks[p], invested);
    } else {
      betAmount = state.stacks[p];
    }
  }

  const newStacks = [...state.stacks];
  newStacks[p] -= betAmount;
  const newPot = state.pot + betAmount;
  const isRaise = state.facingBet > 0;
  const totalBetLevel = invested + betAmount;

  return buildStreetNode(config, {
    ...state,
    pot: newPot,
    stacks: newStacks,
    player: opp,
    history: newHistory,
    raiseCount: state.raiseCount + (isRaise ? 1 : 0),
    isFirstAction: false,
    facingBet: totalBetLevel,
    roundStartStacks: state.roundStartStacks,
  });
}

/**
 * Create a terminal node at the end of a street.
 *
 * For River: this is a showdown.
 * For Flop/Turn: this is a transition to the next street.
 */
function endOfStreetTerminal(state: StreetBuildState, _history: string): GameNode {
  return endOfStreetTerminalWithState(state, state.pot, state.stacks);
}

function endOfStreetTerminalWithState(
  state: StreetBuildState,
  pot: number,
  stacks: number[],
): GameNode {
  const nextStreet = NEXT_STREET[state.targetStreet];

  if (!nextStreet) {
    // River → showdown
    return {
      type: 'terminal',
      pot,
      showdown: true,
      lastToAct: state.player,
      playerStacks: [...stacks],
    } satisfies TerminalNode;
  }

  // Flop/Turn → transition terminal
  return {
    type: 'terminal',
    pot,
    showdown: false,
    lastToAct: state.player,
    playerStacks: [...stacks],
    isTransition: true,
    nextStreet,
  } as TransitionTerminal;
}

// ─── Multi-Way Street Tree ───

interface MWStreetBuildState {
  targetStreet: Street;
  numPlayers: number;
  pot: number;
  stacks: number[];
  activePlayers: boolean[];
  currentBets: number[];
  maxBet: number;
  playerToAct: number;
  history: string;
  raiseCount: number;
  hasActedThisRound: boolean[];
}

function buildStreetTreeMultiWay(
  config: TreeConfig,
  street: Street,
  numPlayers: number,
): ActionNode {
  const state: MWStreetBuildState = {
    targetStreet: street,
    numPlayers,
    pot: config.startingPot,
    stacks: Array(numPlayers).fill(config.effectiveStack),
    activePlayers: Array(numPlayers).fill(true),
    currentBets: Array(numPlayers).fill(0),
    maxBet: 0,
    playerToAct: 0,
    history: '',
    raiseCount: 0,
    hasActedThisRound: Array(numPlayers).fill(false),
  };

  return buildStreetNodeMW(config, state) as ActionNode;
}

function nextActingPlayer(state: MWStreetBuildState, after: number): number | null {
  for (let i = 1; i <= state.numPlayers; i++) {
    const p = (after + i) % state.numPlayers;
    if (state.activePlayers[p] && state.stacks[p] > 0) return p;
  }
  return null;
}

function isRoundComplete(state: MWStreetBuildState): boolean {
  for (let i = 0; i < state.numPlayers; i++) {
    if (!state.activePlayers[i]) continue;
    if (state.stacks[i] <= 0) continue;
    if (!state.hasActedThisRound[i]) return false;
    if (state.currentBets[i] < state.maxBet) return false;
  }
  return true;
}

function buildStreetNodeMW(config: TreeConfig, state: MWStreetBuildState): GameNode {
  const p = state.playerToAct;
  const facingBet = state.maxBet - state.currentBets[p];
  const playerStack = state.stacks[p];
  const sizes = getBetSizesForStreet(config, state.targetStreet);

  const actions: Action[] = [];
  if (facingBet > 0) {
    actions.push('fold');
    actions.push('call');
    if (state.raiseCount < config.raiseCapPerStreet && playerStack > facingBet) {
      for (let i = 0; i < sizes.length; i++) {
        const amount = calcRaiseAmount(state.pot, facingBet, sizes[i], playerStack);
        if (amount >= playerStack) {
          if (!actions.includes('allin')) actions.push('allin');
          break;
        }
        actions.push(`raise_${i}`);
      }
      if (!actions.includes('allin') && playerStack > facingBet) {
        actions.push('allin');
      }
    }
  } else {
    actions.push('check');
    if (playerStack > 0) {
      for (let i = 0; i < sizes.length; i++) {
        const amount = calcBetAmount(state.pot, sizes[i], playerStack);
        if (amount >= playerStack) {
          if (!actions.includes('allin')) actions.push('allin');
          break;
        }
        actions.push(`bet_${i}`);
      }
      if (!actions.includes('allin') && playerStack > 0) {
        actions.push('allin');
      }
    }
  }

  const children = new Map<Action, GameNode>();
  const node: ActionNode = {
    type: 'action',
    player: p,
    street: state.targetStreet,
    pot: state.pot,
    stacks: [...state.stacks],
    activePlayers: [...state.activePlayers],
    actions,
    children,
    historyKey: state.history,
    historyId: 0,
    raiseCount: state.raiseCount,
  };

  for (const action of actions) {
    children.set(action, applyStreetActionMW(config, state, action));
  }

  return node;
}

function applyStreetActionMW(
  config: TreeConfig,
  state: MWStreetBuildState,
  action: Action,
): GameNode {
  const p = state.playerToAct;
  const newHistory = state.history + actionChar(action);
  const facingBet = state.maxBet - state.currentBets[p];
  const sizes = getBetSizesForStreet(config, state.targetStreet);

  // FOLD
  if (action === 'fold') {
    const newActive = [...state.activePlayers];
    newActive[p] = false;
    const activeCount = newActive.filter((a) => a).length;

    if (activeCount === 1) {
      const winner = newActive.indexOf(true);
      return {
        type: 'terminal',
        pot: state.pot,
        showdown: false,
        lastToAct: p,
        playerStacks: [...state.stacks],
        foldedPlayers: newActive.map((a) => !a),
        winner,
      } satisfies TerminalNode;
    }

    const newState: MWStreetBuildState = {
      ...state,
      activePlayers: newActive,
      hasActedThisRound: [...state.hasActedThisRound],
      currentBets: [...state.currentBets],
      stacks: [...state.stacks],
      history: newHistory,
    };
    newState.hasActedThisRound[p] = true;

    if (isRoundComplete(newState)) {
      return endOfStreetTerminalMW(newState);
    }

    const next = nextActingPlayer(newState, p);
    if (next === null) return endOfStreetTerminalMW(newState);
    newState.playerToAct = next;
    return buildStreetNodeMW(config, newState);
  }

  // CHECK
  if (action === 'check') {
    const newState: MWStreetBuildState = {
      ...state,
      hasActedThisRound: [...state.hasActedThisRound],
      currentBets: [...state.currentBets],
      stacks: [...state.stacks],
      activePlayers: [...state.activePlayers],
      history: newHistory,
    };
    newState.hasActedThisRound[p] = true;

    if (isRoundComplete(newState)) return endOfStreetTerminalMW(newState);
    const next = nextActingPlayer(newState, p);
    if (next === null) return endOfStreetTerminalMW(newState);
    newState.playerToAct = next;
    return buildStreetNodeMW(config, newState);
  }

  // CALL
  if (action === 'call') {
    const callAmount = Math.min(facingBet, state.stacks[p]);
    const newStacks = [...state.stacks];
    newStacks[p] -= callAmount;
    const newBets = [...state.currentBets];
    newBets[p] += callAmount;
    const newPot = state.pot + callAmount;

    const newState: MWStreetBuildState = {
      ...state,
      pot: newPot,
      stacks: newStacks,
      currentBets: newBets,
      hasActedThisRound: [...state.hasActedThisRound],
      activePlayers: [...state.activePlayers],
      history: newHistory,
    };
    newState.hasActedThisRound[p] = true;

    if (isRoundComplete(newState)) {
      const activeWithChips = newState.activePlayers.filter((a, i) => a && newStacks[i] > 0).length;
      if (activeWithChips <= 1) {
        // All-in: showdown
        return {
          type: 'terminal',
          pot: newPot,
          showdown: true,
          lastToAct: p,
          playerStacks: newStacks,
          foldedPlayers: newState.activePlayers.map((a) => !a),
        } satisfies TerminalNode;
      }
      return endOfStreetTerminalMW(newState);
    }

    const next = nextActingPlayer(newState, p);
    if (next === null) return endOfStreetTerminalMW(newState);
    newState.playerToAct = next;
    return buildStreetNodeMW(config, newState);
  }

  // BET / RAISE / ALL-IN
  let betAmount: number;
  if (action === 'allin') {
    betAmount = state.stacks[p];
  } else {
    const match = action.match(/^(bet|raise)_(\d+)$/);
    if (match) {
      const idx = parseInt(match[2]);
      betAmount =
        match[1] === 'bet'
          ? calcBetAmount(state.pot, sizes[idx], state.stacks[p])
          : calcRaiseAmount(state.pot, facingBet, sizes[idx], state.stacks[p]);
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

  const newHasActed = Array(state.numPlayers).fill(false);
  newHasActed[p] = true;

  const newState: MWStreetBuildState = {
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

  const next = nextActingPlayer(newState, p);
  if (next === null) return endOfStreetTerminalMW(newState);
  newState.playerToAct = next;
  return buildStreetNodeMW(config, newState);
}

function endOfStreetTerminalMW(state: MWStreetBuildState): GameNode {
  const nextStreet = NEXT_STREET[state.targetStreet];

  if (!nextStreet) {
    return {
      type: 'terminal',
      pot: state.pot,
      showdown: true,
      lastToAct: state.playerToAct,
      playerStacks: [...state.stacks],
      foldedPlayers: state.activePlayers.map((a) => !a),
    } satisfies TerminalNode;
  }

  return {
    type: 'terminal',
    pot: state.pot,
    showdown: false,
    lastToAct: state.playerToAct,
    playerStacks: [...state.stacks],
    foldedPlayers: state.activePlayers.map((a) => !a),
    isTransition: true,
    nextStreet,
  } as TransitionTerminal;
}
