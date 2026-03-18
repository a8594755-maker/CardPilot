// Type definitions for the preflop solver.
//
// Seat indexing convention:
// - Seats are ordered by preflop action order.
// - Seat 0 is first-to-act preflop.
// - Last two seats are always SB, BB.
// - For 6-max this is: UTG(0), HJ(1), CO(2), BTN(3), SB(4), BB(5).

export type Position = 'UTG' | 'LJ' | 'HJ' | 'CO' | 'BTN' | 'SB' | 'BB' | `P${number}`;
export type SeatIndex = number;

export const POSITION_6MAX: Position[] = ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB'];
export const POSITION_LABELS: Record<number, Position> = {
  0: 'UTG',
  1: 'HJ',
  2: 'CO',
  3: 'BTN',
  4: 'SB',
  5: 'BB',
};

/**
 * Build default position labels for arbitrary player counts while preserving
 * canonical 6-max labels.
 */
export function defaultPositionsForPlayers(players: number): Position[] {
  if (!Number.isFinite(players) || players < 2) {
    throw new Error(`invalid player count: ${players}`);
  }

  if (players === 6) return [...POSITION_6MAX];
  if (players === 2) return ['SB', 'BB'];
  if (players === 3) return ['BTN', 'SB', 'BB'];

  const earlyCount = players - 3; // seats before BTN
  const early: Position[] = [];
  if (earlyCount === 1) {
    early.push('UTG');
  } else if (earlyCount === 2) {
    early.push('HJ', 'CO');
  } else if (earlyCount === 3) {
    early.push('UTG', 'HJ', 'CO');
  } else if (earlyCount === 4) {
    early.push('UTG', 'LJ', 'HJ', 'CO');
  } else {
    early.push('UTG');
    const extra = earlyCount - 4;
    for (let i = 0; i < extra; i++) {
      early.push(`P${i + 1}`);
    }
    early.push('LJ', 'HJ', 'CO');
  }

  return [...early, 'BTN', 'SB', 'BB'];
}

export const NUM_PLAYERS = 6;

// ── Hand classes ──

/** All 169 strategically distinct preflop hand classes. */
export const RANKS = 'AKQJT98765432';
export const NUM_RANKS = 13;
export const NUM_HAND_CLASSES = 169; // 13 pairs + 78 suited + 78 offsuit

/**
 * Generate ordered list of all 169 hand classes.
 * Order: pairs first (AA, KK, ..., 22), then suited (AKs, AQs, ..., 32s),
 * then offsuit (AKo, AQo, ..., 32o).
 */
export function allHandClasses(): string[] {
  const classes: string[] = [];
  // Pairs: AA, KK, ..., 22
  for (let r = 0; r < NUM_RANKS; r++) {
    classes.push(RANKS[r] + RANKS[r]);
  }
  // Suited: AKs, AQs, ..., 32s
  for (let r1 = 0; r1 < NUM_RANKS; r1++) {
    for (let r2 = r1 + 1; r2 < NUM_RANKS; r2++) {
      classes.push(RANKS[r1] + RANKS[r2] + 's');
    }
  }
  // Offsuit: AKo, AQo, ..., 32o
  for (let r1 = 0; r1 < NUM_RANKS; r1++) {
    for (let r2 = r1 + 1; r2 < NUM_RANKS; r2++) {
      classes.push(RANKS[r1] + RANKS[r2] + 'o');
    }
  }
  return classes;
}

/** Map hand class string to index 0..168. */
export function handClassIndex(handClass: string): number {
  const ALL = allHandClasses();
  const idx = ALL.indexOf(handClass);
  if (idx === -1) throw new Error(`Unknown hand class: ${handClass}`);
  return idx;
}

// Build a static lookup for performance
const _HC_LIST = allHandClasses();
const _HC_INDEX = new Map<string, number>();
for (let i = 0; i < _HC_LIST.length; i++) _HC_INDEX.set(_HC_LIST[i], i);

/** Fast hand class → index lookup. */
export function handClassToIndex(hc: string): number {
  const idx = _HC_INDEX.get(hc);
  if (idx === undefined) throw new Error(`Unknown hand class: ${hc}`);
  return idx;
}

/** Fast index → hand class lookup. */
export function indexToHandClass(idx: number): string {
  if (idx < 0 || idx >= _HC_LIST.length) throw new Error(`Invalid hand class index: ${idx}`);
  return _HC_LIST[idx];
}

/**
 * Given two card indices (0-51), return the hand class string.
 * rank = cardIndex >> 2 (0=2, 1=3, ..., 12=A)
 * suit = cardIndex & 3
 */
export function comboToHandClass(c1: number, c2: number): string {
  const r1 = c1 >> 2;
  const r2 = c2 >> 2;
  const s1 = c1 & 3;
  const s2 = c2 & 3;

  // Ensure higher rank first
  const hi = Math.max(r1, r2);
  const lo = Math.min(r1, r2);

  if (hi === lo) {
    // Pair
    return RANKS[12 - hi] + RANKS[12 - hi]; // rank 12=A, 0=2 in card-index, but RANKS[0]='A'
  }

  // Wait: card-index.ts uses rank 0=2, ..., 12=A
  // But RANKS here is 'AKQJT98765432', so RANKS[0]='A', RANKS[12]='2'
  // So card rank 12 (=A) maps to RANKS index 0.
  // Mapping: RANKS_index = 12 - card_rank

  const hiRankChar = RANKS[12 - hi];
  const loRankChar = RANKS[12 - lo];
  const suited = s1 === s2;

  return hiRankChar + loRankChar + (suited ? 's' : 'o');
}

// ── Game tree nodes ──

export type PreflopAction = string;
// Possible actions:
// 'fold'          - fold hand
// 'call'          - call current bet / limp
// 'check'         - check (BB option when no raise)
// 'open_X'        - open raise to X bb (e.g., 'open_2.5')
// '3bet_X'        - 3-bet to X bb
// '4bet_X'        - 4-bet to X bb
// 'allin'         - all-in (push remaining stack)
// 'squeeze_X'     - squeeze (3-bet after caller)

export interface PreflopActionNode {
  type: 'action';
  seat: number; // seat index in preflop action order
  position: Position; // position label
  pot: number; // current pot in bb
  stacks: number[]; // remaining stack per seat (length players)
  investments: number[]; // total invested per seat this hand (length players)
  actions: PreflopAction[]; // available actions
  children: Map<PreflopAction, PreflopGameNode>;
  historyKey: string; // encoded action sequence for info-set key
  activePlayers: Set<number>; // seat indices still in the hand
}

export interface PreflopTerminalNode {
  type: 'terminal';
  pot: number;
  investments: number[]; // total invested per seat
  activePlayers: number[]; // seat indices remaining (for showdown/see-flop)
  showdown: boolean; // true = see flop or all-in showdown
  folder?: number; // seat index of folder (if fold terminal)
}

export type PreflopGameNode = PreflopActionNode | PreflopTerminalNode;

// ── Solver configuration ──

export interface PreflopSolveConfig {
  name: string; // 'cash_6max_100bb'
  players: number; // >=2
  positionLabels?: Position[]; // optional explicit seat labels in preflop order
  stackSize: number; // 100 (bb)
  sbSize: number; // 0.5
  bbSize: number; // 1.0
  ante: number; // 0 for cash, e.g. 0.25/player for ante games
  openSize: number; // 2.5 (bb)
  threeBetIPMultiplier: number; // 3.0 (× open = 7.5bb)
  threeBetOOPMultiplier: number; // 3.5 (× open = 8.75bb)
  fourBetMultiplier: number; // 2.25 (× 3bet)
  reRaiseMultiplier?: number; // >=5-bet sizing multiplier (defaults to fourBetMultiplier)
  maxRaiseLevel?: number; // 1=open, 2=3bet, 3=4bet, 4=5bet ... default 4
  allowSmallBlindComplete?: boolean; // default true
  autoFoldUninvolvedAfterThreeBet?: boolean; // default false for generic trees
  iterations: number; // 1_000_000
  realizationIP: number; // 1.0
  realizationOOP: number; // 0.85
}

// ── Spot / scenario types (for export) ──

export type ScenarioType = 'RFI' | 'facing_open' | 'facing_3bet' | 'facing_4bet' | 'squeeze';

export interface SpotSolution {
  spot: string; // e.g., 'BB_vs_BTN_open'
  format: string; // e.g., 'cash_6max_100bb'
  heroPosition: Position;
  villainPosition?: Position;
  scenario: ScenarioType;
  potSize: number;
  actions: string[];
  /** 169 hand classes → action frequency map */
  grid: Record<string, Record<string, number>>;
  summary: {
    totalCombos: number;
    rangeSize: number; // combos with any non-fold action
    actionFrequencies: Record<string, number>; // aggregate freq per action
  };
  metadata: {
    iterations: number;
    exploitability: number;
    solveDate: string;
    solver: string;
  };
}

export interface SolutionIndex {
  format: string;
  configs: string[];
  spots: Array<{
    file: string;
    spot: string;
    heroPosition: Position;
    scenario: ScenarioType;
  }>;
  solveDate: string;
}
