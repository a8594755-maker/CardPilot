// Type definitions for 6-max preflop GTO solver
//
// The preflop tree models a full 6-player sequential decision process:
// UTG → HJ → CO → BTN → SB → BB
//
// Key simplifications (GTO Wizard "Simple solutions" approach):
// - After a 3-bet, remaining uninvolved players auto-fold
// - Non-BB facing an open must 3bet or fold (no cold-calling)
// - Raise cap: open → 3bet → 4bet → 5bet/allin
// - One sizing per action type

export type Position = 'UTG' | 'MP' | 'HJ' | 'CO' | 'BTN' | 'SB' | 'BB';

/** Seat index: 0=UTG, 1=MP, 2=HJ, 3=CO, 4=BTN, 5=SB, 6=BB */
export type SeatIndex = 0 | 1 | 2 | 3 | 4 | 5 | 6;

export const POSITIONS: Position[] = ['UTG', 'MP', 'HJ', 'CO', 'BTN', 'SB', 'BB'];
export const NUM_SEATS = 6; // 6-max (UTG through BB, but BB is seat index 5 in 6-max)

// In 6-max, we have 6 seats: UTG(0), MP(1), HJ(2), CO(3), BTN(4), SB(5)
// BB is the 7th conceptual position but seat index is modular.
// For simplicity, we use 0-5 as seat indices matching the 6 positions in preflop order.
export const SEAT_POSITIONS: Position[] = ['UTG', 'MP', 'HJ', 'CO', 'BTN', 'SB'];

// Wait — in 6-max there ARE 6 players: UTG, MP (sometimes called LJ), HJ, CO, BTN, SB, BB = 7 names but only 6 seats.
// Standard 6-max: UTG, HJ, CO, BTN, SB, BB — but many use UTG, MP, CO, BTN, SB, BB.
// Let's standardize: 6 seats with preflop action order:
//   Seat 0 = UTG (first to act preflop)
//   Seat 1 = HJ
//   Seat 2 = CO
//   Seat 3 = BTN (dealer)
//   Seat 4 = SB (small blind)
//   Seat 5 = BB (big blind, last to act preflop)
export const POSITION_6MAX: Position[] = ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB'];
export const POSITION_LABELS: Record<number, Position> = {
  0: 'UTG',
  1: 'HJ',
  2: 'CO',
  3: 'BTN',
  4: 'SB',
  5: 'BB',
};

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
// 'call'          - call current bet (BB only vs open)
// 'check'         - check (BB option when no raise)
// 'open_X'        - open raise to X bb (e.g., 'open_2.5')
// '3bet_X'        - 3-bet to X bb
// '4bet_X'        - 4-bet to X bb
// 'allin'         - all-in (push remaining stack)

export interface PreflopActionNode {
  type: 'action';
  seat: number;              // 0-5 seat index
  position: Position;        // position label
  pot: number;               // current pot in bb
  stacks: number[];          // remaining stack per seat (length 6)
  investments: number[];     // total invested per seat this hand (length 6)
  actions: PreflopAction[];  // available actions
  children: Map<PreflopAction, PreflopGameNode>;
  historyKey: string;        // encoded action sequence for info-set key
  activePlayers: Set<number>; // seat indices still in the hand
}

export interface PreflopTerminalNode {
  type: 'terminal';
  pot: number;
  investments: number[];     // total invested per seat
  activePlayers: number[];   // seat indices remaining (for showdown/see-flop)
  showdown: boolean;         // true = see flop or all-in showdown
  folder?: number;           // seat index of folder (if fold terminal)
}

export type PreflopGameNode = PreflopActionNode | PreflopTerminalNode;

// ── Solver configuration ──

export interface PreflopSolveConfig {
  name: string;              // 'cash_6max_100bb'
  players: number;           // 6
  stackSize: number;         // 100 (bb)
  sbSize: number;            // 0.5
  bbSize: number;            // 1.0
  ante: number;              // 0 for cash, e.g. 0.25/player for ante games
  openSize: number;          // 2.5 (bb)
  threeBetIPMultiplier: number;  // 3.0 (× open = 7.5bb)
  threeBetOOPMultiplier: number; // 3.5 (× open = 8.75bb)
  fourBetMultiplier: number;     // 2.25 (× 3bet)
  iterations: number;        // 1_000_000
  realizationIP: number;     // 1.0
  realizationOOP: number;    // 0.70
  rake: number;              // 0.05 (5% of pot)
  rakeCap: number;           // 3.0 (max 3bb rake)
}

// ── Spot / scenario types (for export) ──

export type ScenarioType = 'RFI' | 'facing_open' | 'facing_3bet' | 'facing_4bet';

export interface SpotSolution {
  spot: string;              // e.g., 'BB_vs_BTN_open'
  format: string;            // e.g., 'cash_6max_100bb'
  heroPosition: Position;
  villainPosition?: Position;
  scenario: ScenarioType;
  potSize: number;
  actions: string[];
  /** 169 hand classes → action frequency map */
  grid: Record<string, Record<string, number>>;
  summary: {
    totalCombos: number;
    rangeSize: number;       // combos with any non-fold action
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
