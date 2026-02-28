// Preflop game tree builder for 6-max poker.
//
// Builds the full sequential decision tree:
//   UTG(0) → HJ(1) → CO(2) → BTN(3) → SB(4) → BB(5)
//
// Simplifications (GTO Wizard "Simple solutions" approach):
//   1. After a 3-bet, remaining uninvolved players auto-fold
//   2. Non-BB facing an open must 3bet or fold (no cold-calling)
//   3. Raise cap: open → 3bet → 4bet → 5bet(allin)
//   4. One sizing per action type

import type {
  PreflopActionNode,
  PreflopTerminalNode,
  PreflopGameNode,
  PreflopAction,
  PreflopSolveConfig,
} from './preflop-types.js';
import { POSITION_6MAX, NUM_PLAYERS } from './preflop-types.js';
import { compute3BetSize, compute4BetSize, computeInitialPot, isIPPostflop } from './preflop-config.js';

// ── Build state ──

interface BuildState {
  pot: number;
  stacks: number[];           // remaining stack per seat [6]
  investments: number[];      // total invested this hand [6]
  activePlayers: boolean[];   // true = still in the hand [6]
  needsToAct: boolean[];      // true = hasn't responded to current bet level [6]
  nextToAct: number;          // seat index of next player to act
  history: string;            // encoded action history for info-set key
  raiseLevel: number;         // 0=unopened, 1=open, 2=3bet, 3=4bet, 4=5bet
  lastRaiseTotal: number;     // total bet amount of last raise (in bb)
  lastRaiserSeat: number;     // seat of last raiser (-1 if none)
}

// ── History encoding ──

const POS_CHAR: Record<number, string> = {
  0: 'U', 1: 'H', 2: 'C', 3: 'B', 4: 'S', 5: 'b',
};

function encodeAction(seat: number, action: PreflopAction): string {
  const p = POS_CHAR[seat];
  if (action === 'fold') return `${p}f`;
  if (action === 'check') return `${p}x`;
  if (action === 'call') return `${p}c`;
  if (action === 'allin') return `${p}A`;
  if (action.startsWith('open_')) return `${p}o`;
  if (action.startsWith('3bet_')) return `${p}3`;
  if (action.startsWith('4bet_')) return `${p}4`;
  return `${p}?`;
}

// ── Public API ──

export function buildPreflopTree(config: PreflopSolveConfig): PreflopActionNode {
  const initialPot = computeInitialPot(config);

  const stacks: number[] = [];
  const investments: number[] = [];
  for (let i = 0; i < NUM_PLAYERS; i++) {
    let invested = config.ante;
    if (i === 4) invested += config.sbSize; // SB
    if (i === 5) invested += config.bbSize; // BB
    stacks.push(config.stackSize - invested);
    investments.push(invested);
  }

  const state: BuildState = {
    pot: initialPot,
    stacks,
    investments,
    activePlayers: Array(NUM_PLAYERS).fill(true),
    needsToAct: Array(NUM_PLAYERS).fill(true),
    nextToAct: 0, // UTG
    history: '',
    raiseLevel: 0,
    lastRaiseTotal: config.bbSize, // BB is the "current bet" to start
    lastRaiserSeat: -1,
  };

  return buildNode(config, state) as PreflopActionNode;
}

// ── Internal tree construction ──

function buildNode(config: PreflopSolveConfig, state: BuildState): PreflopGameNode {
  // Terminal: only one player remains
  const activeSeat = getActiveSeatsList(state);
  if (activeSeat.length <= 1) {
    return makeTerminal(state, false);
  }

  // Terminal: no one needs to act → round is complete → see flop
  if (!state.needsToAct.some((n, i) => n && state.activePlayers[i])) {
    return makeTerminal(state, true);
  }

  // Find the next seat that needs to act
  const seat = findNextToAct(state);
  if (seat === -1) {
    // No one else needs to act → terminal
    return makeTerminal(state, true);
  }

  const actions = getLegalActions(config, state, seat);

  if (actions.length === 0) {
    // No legal actions → skip this player (shouldn't happen normally)
    const newState = cloneState(state);
    newState.needsToAct[seat] = false;
    return buildNode(config, newState);
  }

  const children = new Map<PreflopAction, PreflopGameNode>();
  const node: PreflopActionNode = {
    type: 'action',
    seat,
    position: POSITION_6MAX[seat],
    pot: state.pot,
    stacks: [...state.stacks],
    investments: [...state.investments],
    actions,
    children,
    historyKey: state.history,
    activePlayers: new Set(getActiveSeatsList(state)),
  };

  for (const action of actions) {
    const child = applyAction(config, state, seat, action);
    children.set(action, child);
  }

  return node;
}

function findNextToAct(state: BuildState): number {
  // Start from nextToAct and go clockwise
  for (let i = 0; i < NUM_PLAYERS; i++) {
    const seat = (state.nextToAct + i) % NUM_PLAYERS;
    if (state.activePlayers[seat] && state.needsToAct[seat] && state.stacks[seat] > 0) {
      return seat;
    }
  }
  return -1;
}

function getLegalActions(config: PreflopSolveConfig, state: BuildState, seat: number): PreflopAction[] {
  const stack = state.stacks[seat];
  const invested = state.investments[seat];
  const totalAvail = stack + invested;
  const actions: PreflopAction[] = [];

  if (stack <= 0) return []; // All-in, no actions

  const currentBet = state.lastRaiseTotal;
  const toCall = Math.max(0, currentBet - invested);

  // ── Unopened pot (player owes money to continue) ──
  if (state.raiseLevel === 0 && toCall > 0) {
    actions.push('fold');

    // Open raise
    if (config.openSize <= totalAvail) {
      actions.push(`open_${config.openSize}`);
    } else if (stack > 0) {
      // Can't afford full open → all-in
      actions.push('allin');
    }

    return actions;
  }

  // ── Facing a bet/raise ──
  if (toCall > 0) {
    actions.push('fold');

    // Call
    if (toCall >= stack) {
      // Calling puts us all-in
      actions.push('allin');
    } else {
      // Non-BB facing an open must 3bet or fold (no cold-calling)
      // BB (seat 5) can call opens; all positions can call 3bet+
      const canCall = state.raiseLevel !== 1 || seat === 5;
      if (canCall) {
        actions.push('call');
      }

      // Re-raise (if under cap)
      const raiseAction = getNextRaise(config, state, seat);
      if (raiseAction) {
        const raiseTotal = parseRaiseTotal(raiseAction);
        if (raiseTotal > totalAvail) {
          // Can't afford raise → offer all-in as raise
          actions.push('allin');
        } else {
          actions.push(raiseAction);
          // All-in as over-raise only at 4-bet+ level (where it's the 5-bet)
          if (state.raiseLevel >= 3 && totalAvail > raiseTotal) {
            actions.push('allin');
          }
        }
      }
    }

    return actions;
  }

  // ── No bet to face (BB walk / check option) ──
  actions.push('check');

  // BB can raise
  const raiseAction = getNextRaise(config, state, seat);
  if (raiseAction) {
    const raiseTotal = parseRaiseTotal(raiseAction);
    if (raiseTotal > totalAvail) {
      // Can't afford full raise → all-in
      actions.push('allin');
    } else {
      actions.push(raiseAction);
    }
  }

  return actions;
}

function getNextRaise(
  config: PreflopSolveConfig,
  state: BuildState,
  seat: number,
): PreflopAction | null {
  if (state.raiseLevel >= 4) return null; // Cap reached (5bet = allin)

  const nextLevel = state.raiseLevel + 1;

  if (nextLevel === 1) {
    // Open
    return `open_${config.openSize}`;
  }

  if (nextLevel === 2) {
    // 3-bet
    const openerSeat = state.lastRaiserSeat;
    const isIP = openerSeat >= 0 ? isIPPostflop(seat, openerSeat) : false;
    const size = compute3BetSize(config, isIP);
    return `3bet_${size}`;
  }

  if (nextLevel === 3) {
    // 4-bet
    const size = compute4BetSize(config, state.lastRaiseTotal);
    return `4bet_${size}`;
  }

  // 5bet = allin
  return null; // Caller should use 'allin'
}

function parseRaiseTotal(action: PreflopAction): number {
  const match = action.match(/(?:open|3bet|4bet)_([\d.]+)/);
  return match ? parseFloat(match[1]) : 0;
}

function applyAction(
  config: PreflopSolveConfig,
  state: BuildState,
  seat: number,
  action: PreflopAction,
): PreflopGameNode {
  const s = cloneState(state);
  const newHistory = state.history + (state.history ? '-' : '') + encodeAction(seat, action);
  s.history = newHistory;
  s.needsToAct[seat] = false;

  // ── Fold ──
  if (action === 'fold') {
    s.activePlayers[seat] = false;
    s.nextToAct = (seat + 1) % NUM_PLAYERS;
    return buildNode(config, s);
  }

  // ── Check ──
  if (action === 'check') {
    s.nextToAct = (seat + 1) % NUM_PLAYERS;
    return buildNode(config, s);
  }

  // ── Call ──
  if (action === 'call') {
    const toCall = Math.max(0, s.lastRaiseTotal - s.investments[seat]);
    const actual = Math.min(toCall, s.stacks[seat]);
    s.stacks[seat] -= actual;
    s.investments[seat] += actual;
    s.pot += actual;

    s.nextToAct = (seat + 1) % NUM_PLAYERS;
    return buildNode(config, s);
  }

  // ── All-in ──
  if (action === 'allin') {
    const amount = s.stacks[seat];
    const newTotal = s.investments[seat] + amount;
    s.pot += amount;
    s.investments[seat] = newTotal;
    s.stacks[seat] = 0;

    // Is this a raise?
    if (newTotal > s.lastRaiseTotal) {
      const prevRaiser = s.lastRaiserSeat;
      s.lastRaiserSeat = seat;
      s.lastRaiseTotal = newTotal;
      s.raiseLevel = Math.min(s.raiseLevel + 1, 4);

      // Everyone active needs to respond (except us)
      resetNeedsToAct(s, seat);

      // After 3bet+, uninvolved players auto-fold
      if (s.raiseLevel >= 2) {
        autoFoldUninvolved(s, seat, prevRaiser);
      }
    }

    s.nextToAct = (seat + 1) % NUM_PLAYERS;
    return buildNode(config, s);
  }

  // ── Sized raises (open_X, 3bet_X, 4bet_X) ──
  const raiseTotal = parseRaiseTotal(action);
  if (raiseTotal > 0) {
    const cost = raiseTotal - s.investments[seat];
    const actual = Math.min(cost, s.stacks[seat]);
    s.stacks[seat] -= actual;
    s.investments[seat] += actual;
    s.pot += actual;
    const prevRaiser = s.lastRaiserSeat;
    s.lastRaiserSeat = seat;
    s.lastRaiseTotal = raiseTotal;
    s.raiseLevel++;

    // Everyone active needs to respond (except us)
    resetNeedsToAct(s, seat);

    // After 3bet+, uninvolved players auto-fold
    if (s.raiseLevel >= 2) {
      autoFoldUninvolved(s, seat, prevRaiser);
    }

    s.nextToAct = (seat + 1) % NUM_PLAYERS;
    return buildNode(config, s);
  }

  throw new Error(`Unknown preflop action: ${action}`);
}

/**
 * After a raise, all active players (except the raiser) need to act again.
 */
function resetNeedsToAct(state: BuildState, raiserSeat: number): void {
  for (let i = 0; i < NUM_PLAYERS; i++) {
    if (i === raiserSeat) {
      state.needsToAct[i] = false; // Raiser doesn't need to act again
    } else if (state.activePlayers[i] && state.stacks[i] > 0) {
      state.needsToAct[i] = true;
    }
  }
}

/**
 * After a 3bet+, auto-fold all uninvolved players.
 * Keep only the current raiser and the previous raiser.
 * With no cold-calling allowed, no other players have voluntary investment.
 */
function autoFoldUninvolved(state: BuildState, currentRaiserSeat: number, prevRaiserSeat: number): void {
  for (let i = 0; i < NUM_PLAYERS; i++) {
    if (!state.activePlayers[i]) continue;
    if (i === currentRaiserSeat) continue;
    if (i === prevRaiserSeat) continue;

    state.activePlayers[i] = false;
    state.needsToAct[i] = false;
  }
}

// ── Utilities ──

function getActiveSeatsList(state: BuildState): number[] {
  const seats: number[] = [];
  for (let i = 0; i < NUM_PLAYERS; i++) {
    if (state.activePlayers[i]) seats.push(i);
  }
  return seats;
}

function makeTerminal(state: BuildState, showdown: boolean): PreflopTerminalNode {
  return {
    type: 'terminal',
    pot: state.pot,
    investments: [...state.investments],
    activePlayers: getActiveSeatsList(state),
    showdown,
  };
}

function cloneState(state: BuildState): BuildState {
  return {
    pot: state.pot,
    stacks: [...state.stacks],
    investments: [...state.investments],
    activePlayers: [...state.activePlayers],
    needsToAct: [...state.needsToAct],
    nextToAct: state.nextToAct,
    history: state.history,
    raiseLevel: state.raiseLevel,
    lastRaiseTotal: state.lastRaiseTotal,
    lastRaiserSeat: state.lastRaiserSeat,
  };
}

// ── Tree statistics ──

export function countPreflopNodes(node: PreflopGameNode): { action: number; terminal: number } {
  if (node.type === 'terminal') return { action: 0, terminal: 1 };
  let action = 1;
  let terminal = 0;
  for (const child of node.children.values()) {
    const sub = countPreflopNodes(child);
    action += sub.action;
    terminal += sub.terminal;
  }
  return { action, terminal };
}

/**
 * Collect all unique info-set keys (position + history) from the tree.
 */
export function collectInfoSetKeys(node: PreflopGameNode, keys = new Set<string>()): Set<string> {
  if (node.type === 'terminal') return keys;
  keys.add(`${node.position}|${node.historyKey}`);
  for (const child of node.children.values()) {
    collectInfoSetKeys(child, keys);
  }
  return keys;
}

/**
 * Print the tree structure for debugging (limited depth).
 */
export function printTree(node: PreflopGameNode, indent = '', maxDepth = 6): void {
  if (maxDepth <= 0) {
    console.log(`${indent}...`);
    return;
  }
  if (node.type === 'terminal') {
    const players = node.activePlayers.join(',');
    console.log(`${indent}[TERMINAL] pot=${node.pot.toFixed(1)} showdown=${node.showdown} players=[${players}]`);
    return;
  }
  console.log(`${indent}[${node.position}] seat=${node.seat} pot=${node.pot.toFixed(1)} actions=[${node.actions.join(',')}] history="${node.historyKey}"`);
  for (const [action, child] of node.children) {
    console.log(`${indent}  → ${action}:`);
    printTree(child, indent + '    ', maxDepth - 1);
  }
}
