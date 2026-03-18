// Generic preflop game tree builder.
//
// Seat indexing convention:
// - Seats are ordered by preflop action order.
// - Last two seats are SB and BB.
//
// The builder supports:
// - Variable player counts
// - Variable raise cap (open/3bet/4bet/.../N-bet)
// - Optional auto-fold simplification after 3-bets (legacy compatibility)

import type {
  Position,
  PreflopActionNode,
  PreflopTerminalNode,
  PreflopGameNode,
  PreflopAction,
  PreflopSolveConfig,
} from './preflop-types.js';
import { defaultPositionsForPlayers } from './preflop-types.js';
import {
  compute3BetSize,
  compute4BetSize,
  computeInitialPot,
  isIPPostflop,
} from './preflop-config.js';

const EPS = 1e-9;

interface BuildState {
  players: number;
  positions: Position[];
  pot: number;
  stacks: number[];
  investments: number[];
  forcedInvestments: number[];
  activePlayers: boolean[];
  needsToAct: boolean[];
  nextToAct: number;
  history: string;
  raiseLevel: number; // 0 = unopened, 1 = open, 2 = 3bet, ...
  lastRaiseTotal: number; // total invested amount to call
  lastRaiserSeat: number; // current aggressor seat, -1 when unopened
  priorRaiserSeat: number; // previous aggressor seat, for legacy auto-fold rule
  numCallersOfOpen: number;
}

const LEGACY_POS_CHAR: Record<string, string> = {
  UTG: 'U',
  LJ: 'L',
  HJ: 'H',
  CO: 'C',
  BTN: 'B',
  SB: 'S',
  BB: 'b',
};

function seatToken(positions: Position[], seat: number): string {
  const pos = positions[seat];
  return LEGACY_POS_CHAR[pos] ?? `p${seat}`;
}

function raiseActionCode(action: PreflopAction): string {
  if (action === 'fold') return 'f';
  if (action === 'check') return 'x';
  if (action === 'call') return 'c';
  if (action === 'complete') return 'l';
  if (action === 'allin') return 'A';
  if (action.startsWith('open_')) return 'o';
  if (action.startsWith('squeeze_')) return 'q';
  if (action.startsWith('3bet_')) return '3';
  if (action.startsWith('4bet_')) return '4';
  const nbet = action.match(/^([0-9]+)bet_/);
  if (nbet) {
    return nbet[1].length === 1 ? nbet[1] : 'r';
  }
  return '?';
}

function encodeAction(positions: Position[], seat: number, action: PreflopAction): string {
  return `${seatToken(positions, seat)}${raiseActionCode(action)}`;
}

function uniqueActions(actions: PreflopAction[]): PreflopAction[] {
  const seen = new Set<PreflopAction>();
  const out: PreflopAction[] = [];
  for (const action of actions) {
    if (!seen.has(action)) {
      seen.add(action);
      out.push(action);
    }
  }
  return out;
}

function roundBet(value: number): number {
  return Math.round(value * 100) / 100;
}

function getSbSeat(state: BuildState): number {
  return state.players - 2;
}

function getMaxRaiseLevel(config: PreflopSolveConfig): number {
  return Math.max(1, config.maxRaiseLevel ?? 4);
}

function getReRaiseMultiplier(config: PreflopSolveConfig): number {
  return config.reRaiseMultiplier ?? config.fourBetMultiplier;
}

// ── Public API ──

export function buildPreflopTree(config: PreflopSolveConfig): PreflopActionNode {
  const players = Math.max(2, config.players);
  const positionLabels =
    config.positionLabels?.length === players
      ? config.positionLabels
      : defaultPositionsForPlayers(players);
  const initialPot = computeInitialPot(config);

  const sbSeat = players - 2;
  const bbSeat = players - 1;

  const stacks: number[] = [];
  const investments: number[] = [];
  const forcedInvestments: number[] = [];
  for (let i = 0; i < players; i++) {
    let invested = config.ante;
    if (i === sbSeat) invested += config.sbSize;
    if (i === bbSeat) invested += config.bbSize;
    forcedInvestments.push(invested);
    stacks.push(config.stackSize - invested);
    investments.push(invested);
  }

  const state: BuildState = {
    players,
    positions: [...positionLabels],
    pot: initialPot,
    stacks,
    investments,
    forcedInvestments,
    activePlayers: Array(players).fill(true),
    needsToAct: Array(players).fill(true),
    nextToAct: 0,
    history: '',
    raiseLevel: 0,
    lastRaiseTotal: config.bbSize,
    lastRaiserSeat: -1,
    priorRaiserSeat: -1,
    numCallersOfOpen: 0,
  };

  return buildNode(config, state) as PreflopActionNode;
}

// ── Internal tree construction ──

function buildNode(config: PreflopSolveConfig, state: BuildState): PreflopGameNode {
  const activeSeats = getActiveSeatsList(state);
  if (activeSeats.length <= 1) {
    return makeTerminal(state, false);
  }

  if (!state.needsToAct.some((needs, seat) => needs && state.activePlayers[seat])) {
    return makeTerminal(state, true);
  }

  const seat = findNextToAct(state);
  if (seat === -1) {
    return makeTerminal(state, true);
  }

  const actions = getLegalActions(config, state, seat);
  if (actions.length === 0) {
    const skipped = cloneState(state);
    skipped.needsToAct[seat] = false;
    skipped.nextToAct = (seat + 1) % skipped.players;
    return buildNode(config, skipped);
  }

  const children = new Map<PreflopAction, PreflopGameNode>();
  const node: PreflopActionNode = {
    type: 'action',
    seat,
    position: state.positions[seat],
    pot: state.pot,
    stacks: [...state.stacks],
    investments: [...state.investments],
    actions,
    children,
    historyKey: state.history,
    activePlayers: new Set(activeSeats),
  };

  for (const action of actions) {
    children.set(action, applyAction(config, state, seat, action));
  }

  return node;
}

function findNextToAct(state: BuildState): number {
  for (let i = 0; i < state.players; i++) {
    const seat = (state.nextToAct + i) % state.players;
    if (state.activePlayers[seat] && state.needsToAct[seat] && state.stacks[seat] > EPS) {
      return seat;
    }
  }
  return -1;
}

function parseRaiseTotal(action: PreflopAction): number {
  const match = action.match(/(?:open|3bet|4bet|squeeze|[0-9]+bet)_([\d.]+)/);
  return match ? parseFloat(match[1]) : 0;
}

function getNextRaise(
  config: PreflopSolveConfig,
  state: BuildState,
  seat: number,
): PreflopAction | null {
  const maxRaiseLevel = getMaxRaiseLevel(config);
  if (state.raiseLevel >= maxRaiseLevel) return null;

  const nextLevel = state.raiseLevel + 1;
  const totalAvail = state.investments[seat] + state.stacks[seat];

  if (nextLevel === 1) {
    const openSize = roundBet(Math.min(config.openSize, config.stackSize));
    return openSize > state.lastRaiseTotal + EPS ? `open_${openSize}` : null;
  }

  if (nextLevel === 2) {
    const openerSeat = state.lastRaiserSeat;
    const isIP = openerSeat >= 0 ? isIPPostflop(seat, openerSeat, state.players) : false;
    const size = roundBet(Math.min(compute3BetSize(config, isIP), config.stackSize));
    if (size <= state.lastRaiseTotal + EPS) return null;
    if (state.numCallersOfOpen > 0) {
      return `squeeze_${size}`;
    }
    return `3bet_${size}`;
  }

  if (nextLevel === 3) {
    const size = roundBet(
      Math.min(compute4BetSize(config, state.lastRaiseTotal), config.stackSize),
    );
    if (size <= state.lastRaiseTotal + EPS) return null;
    return `4bet_${size}`;
  }

  const mult = getReRaiseMultiplier(config);
  const genericSize = roundBet(Math.min(state.lastRaiseTotal * mult, config.stackSize));
  if (genericSize <= state.lastRaiseTotal + EPS) return null;
  const nBet = nextLevel + 1;
  const capped = Math.min(genericSize, totalAvail);
  if (capped <= state.lastRaiseTotal + EPS) return null;
  return `${nBet}bet_${roundBet(capped)}`;
}

function getLegalActions(
  config: PreflopSolveConfig,
  state: BuildState,
  seat: number,
): PreflopAction[] {
  const stack = state.stacks[seat];
  const invested = state.investments[seat];
  const totalAvail = stack + invested;
  if (stack <= EPS) return [];

  const actions: PreflopAction[] = [];
  const currentBet = state.lastRaiseTotal;
  const toCall = Math.max(0, currentBet - invested);
  const sbSeat = getSbSeat(state);

  // Unopened, facing the blind amount.
  if (state.raiseLevel === 0 && toCall > EPS) {
    actions.push('fold');

    if (seat === sbSeat && (config.allowSmallBlindComplete ?? true)) {
      actions.push('complete');
    }

    const openAction = `open_${roundBet(Math.min(config.openSize, config.stackSize))}`;
    const openTotal = parseRaiseTotal(openAction);
    if (openTotal > 0 && openTotal <= totalAvail + EPS) {
      actions.push(openAction);
    } else {
      actions.push('allin');
    }

    return uniqueActions(actions);
  }

  // Facing a bet.
  if (toCall > EPS) {
    actions.push('fold');

    if (toCall >= stack - EPS) {
      actions.push('allin');
      return uniqueActions(actions);
    }

    actions.push('call');

    const raiseAction = getNextRaise(config, state, seat);
    if (raiseAction) {
      const raiseTotal = parseRaiseTotal(raiseAction);
      if (raiseTotal > totalAvail + EPS) {
        actions.push('allin');
      } else if (raiseTotal > currentBet + EPS) {
        actions.push(raiseAction);
        if (state.raiseLevel >= 3 && totalAvail > raiseTotal + EPS) {
          actions.push('allin');
        }
      }
    }

    return uniqueActions(actions);
  }

  // No bet to face.
  actions.push('check');
  const raiseAction = getNextRaise(config, state, seat);
  if (raiseAction) {
    const raiseTotal = parseRaiseTotal(raiseAction);
    if (raiseTotal > totalAvail + EPS) actions.push('allin');
    else actions.push(raiseAction);
  }

  return uniqueActions(actions);
}

function registerRaise(
  config: PreflopSolveConfig,
  state: BuildState,
  seat: number,
  raiseTotal: number,
): void {
  const prevRaiser = state.lastRaiserSeat;
  state.priorRaiserSeat = prevRaiser;
  state.lastRaiserSeat = seat;
  state.lastRaiseTotal = raiseTotal;
  state.raiseLevel += 1;
  state.numCallersOfOpen = 0;

  resetNeedsToAct(state, seat);

  if (state.raiseLevel >= 2 && (config.autoFoldUninvolvedAfterThreeBet ?? true)) {
    autoFoldUninvolved(state, seat);
  }
}

function applyAction(
  config: PreflopSolveConfig,
  state: BuildState,
  seat: number,
  action: PreflopAction,
): PreflopGameNode {
  const s = cloneState(state);
  s.history =
    state.history + (state.history ? '-' : '') + encodeAction(state.positions, seat, action);
  s.needsToAct[seat] = false;

  if (action === 'fold') {
    s.activePlayers[seat] = false;
    s.needsToAct[seat] = false;
    s.nextToAct = (seat + 1) % s.players;
    return buildNode(config, s);
  }

  if (action === 'check') {
    s.nextToAct = (seat + 1) % s.players;
    return buildNode(config, s);
  }

  if (action === 'complete') {
    const toComplete = Math.max(0, s.lastRaiseTotal - s.investments[seat]);
    const paid = Math.min(toComplete, s.stacks[seat]);
    s.stacks[seat] -= paid;
    s.investments[seat] += paid;
    s.pot += paid;
    s.nextToAct = (seat + 1) % s.players;
    return buildNode(config, s);
  }

  if (action === 'call') {
    const toCall = Math.max(0, s.lastRaiseTotal - s.investments[seat]);
    const paid = Math.min(toCall, s.stacks[seat]);
    s.stacks[seat] -= paid;
    s.investments[seat] += paid;
    s.pot += paid;
    if (s.raiseLevel === 1) {
      s.numCallersOfOpen += 1;
    }
    s.nextToAct = (seat + 1) % s.players;
    return buildNode(config, s);
  }

  if (action === 'allin') {
    const amount = s.stacks[seat];
    const newTotal = s.investments[seat] + amount;
    s.stacks[seat] = 0;
    s.investments[seat] = newTotal;
    s.pot += amount;

    if (newTotal > s.lastRaiseTotal + EPS) {
      registerRaise(config, s, seat, roundBet(newTotal));
    } else if (s.raiseLevel === 1) {
      s.numCallersOfOpen += 1;
    }

    s.nextToAct = (seat + 1) % s.players;
    return buildNode(config, s);
  }

  const raiseTotal = parseRaiseTotal(action);
  if (raiseTotal > 0) {
    const toPay = Math.max(0, raiseTotal - s.investments[seat]);
    const paid = Math.min(toPay, s.stacks[seat]);
    const newTotal = roundBet(s.investments[seat] + paid);
    s.stacks[seat] -= paid;
    s.investments[seat] = newTotal;
    s.pot += paid;

    if (newTotal > s.lastRaiseTotal + EPS) {
      registerRaise(config, s, seat, newTotal);
    }

    s.nextToAct = (seat + 1) % s.players;
    return buildNode(config, s);
  }

  throw new Error(`Unknown preflop action: ${action}`);
}

/**
 * After a raise, every active player except the raiser must respond again.
 */
function resetNeedsToAct(state: BuildState, raiserSeat: number): void {
  for (let seat = 0; seat < state.players; seat++) {
    if (seat === raiserSeat) {
      state.needsToAct[seat] = false;
      continue;
    }
    state.needsToAct[seat] = state.activePlayers[seat] && state.stacks[seat] > EPS;
  }
}

/**
 * Legacy simplification: auto-fold players who have not invested voluntarily.
 * This keeps old tree sizes tractable when desired.
 */
function autoFoldUninvolved(state: BuildState, currentRaiserSeat: number): void {
  const previousRaiserSeat = state.priorRaiserSeat;

  for (let seat = 0; seat < state.players; seat++) {
    if (!state.activePlayers[seat]) continue;
    if (seat === currentRaiserSeat || seat === previousRaiserSeat) continue;

    const voluntary = state.investments[seat] - state.forcedInvestments[seat];
    if (voluntary <= EPS) {
      state.activePlayers[seat] = false;
      state.needsToAct[seat] = false;
    }
  }
}

function getActiveSeatsList(state: BuildState): number[] {
  const seats: number[] = [];
  for (let seat = 0; seat < state.players; seat++) {
    if (state.activePlayers[seat]) seats.push(seat);
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
    players: state.players,
    positions: [...state.positions],
    pot: state.pot,
    stacks: [...state.stacks],
    investments: [...state.investments],
    forcedInvestments: [...state.forcedInvestments],
    activePlayers: [...state.activePlayers],
    needsToAct: [...state.needsToAct],
    nextToAct: state.nextToAct,
    history: state.history,
    raiseLevel: state.raiseLevel,
    lastRaiseTotal: state.lastRaiseTotal,
    lastRaiserSeat: state.lastRaiserSeat,
    priorRaiserSeat: state.priorRaiserSeat,
    numCallersOfOpen: state.numCallersOfOpen,
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
 * Print tree structure for debugging.
 */
export function printTree(node: PreflopGameNode, indent = '', maxDepth = 6): void {
  if (maxDepth <= 0) {
    console.log(`${indent}...`);
    return;
  }
  if (node.type === 'terminal') {
    const players = node.activePlayers.join(',');
    console.log(
      `${indent}[TERMINAL] pot=${node.pot.toFixed(1)} showdown=${node.showdown} players=[${players}]`,
    );
    return;
  }
  console.log(
    `${indent}[${node.position}] seat=${node.seat} pot=${node.pot.toFixed(1)} actions=[${node.actions.join(',')}] history="${node.historyKey}"`,
  );
  for (const [action, child] of node.children) {
    console.log(`${indent}  -> ${action}:`);
    printTree(child, indent + '    ', maxDepth - 1);
  }
}
