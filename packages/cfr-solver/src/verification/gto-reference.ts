// Parse and validate GTO Wizard reference data files.
// Reference files are manually created JSON with strategies from GTO Wizard.

import { cardToIndex } from '../abstraction/card-index.js';
import { expandHandClassToCombos } from '../data-loaders/gto-wizard-json.js';

export interface ReferenceScenario {
  board: string; // e.g. "As Kd 7c"
  street: 'flop' | 'turn' | 'river';
  position: 'OOP' | 'IP';
  spot: string; // e.g. "SRP", "3BP"
  stack: string; // e.g. "100bb"
  history: string; // action history, e.g. "" (root), "x" (after check)
}

export interface ReferenceHand {
  handClass: string; // e.g. "AA", "AKs", "AKo"
  frequencies: number[]; // one per action, aligned with actions array
  totalCombos: number; // unblocked combos for this hand class
  combos: Array<[number, number]>; // card index combos (unblocked)
}

export interface ReferenceData {
  scenario: ReferenceScenario;
  actions: string[]; // action labels from reference, e.g. ["check", "bet33", "bet75"]
  hands: ReferenceHand[];
  boardIndices: number[]; // board as card indices
}

interface RawReference {
  scenario: {
    board: string;
    street: string;
    position: string;
    spot: string;
    stack: string;
    history?: string;
  };
  actions: string[];
  hands: Record<string, Record<string, number>>;
}

const VALID_STREETS = ['flop', 'turn', 'river'] as const;
const VALID_POSITIONS = ['OOP', 'IP'] as const;

/**
 * Parse a board string like "As Kd 7c" into card indices.
 */
export function parseBoardString(board: string): number[] {
  const cards = board.trim().split(/\s+/);
  if (cards.length < 3 || cards.length > 5) {
    throw new Error(`Board must have 3-5 cards, got ${cards.length}: "${board}"`);
  }
  const indices = cards.map((c) => {
    try {
      return cardToIndex(c);
    } catch {
      throw new Error(`Invalid card "${c}" in board "${board}"`);
    }
  });
  // Check for duplicates
  const unique = new Set(indices);
  if (unique.size !== indices.length) {
    throw new Error(`Duplicate cards in board: "${board}"`);
  }
  return indices;
}

/**
 * Parse and validate a reference JSON file.
 */
export function parseReference(raw: unknown, filePath?: string): ReferenceData {
  const ctx = filePath ? ` (${filePath})` : '';
  if (typeof raw !== 'object' || raw === null) {
    throw new Error(`Reference data must be an object${ctx}`);
  }

  const data = raw as RawReference;

  // Validate scenario
  if (!data.scenario || typeof data.scenario !== 'object') {
    throw new Error(`Missing or invalid "scenario" field${ctx}`);
  }
  if (!data.scenario.board || typeof data.scenario.board !== 'string') {
    throw new Error(`Missing or invalid "scenario.board"${ctx}`);
  }
  const boardIndices = parseBoardString(data.scenario.board);

  const street = (data.scenario.street ?? 'flop').toLowerCase();
  if (!VALID_STREETS.includes(street as any)) {
    throw new Error(
      `Invalid street "${street}", must be one of: ${VALID_STREETS.join(', ')}${ctx}`,
    );
  }

  const position = (data.scenario.position ?? 'OOP').toUpperCase();
  if (!VALID_POSITIONS.includes(position as any)) {
    throw new Error(`Invalid position "${position}", must be OOP or IP${ctx}`);
  }

  // Validate actions
  if (!Array.isArray(data.actions) || data.actions.length === 0) {
    throw new Error(`Missing or empty "actions" array${ctx}`);
  }
  for (const a of data.actions) {
    if (typeof a !== 'string' || !a.trim()) {
      throw new Error(`Invalid action: ${JSON.stringify(a)}${ctx}`);
    }
  }

  // Validate and expand hands
  if (!data.hands || typeof data.hands !== 'object') {
    throw new Error(`Missing or invalid "hands" field${ctx}`);
  }

  const boardSet = new Set(boardIndices);
  const hands: ReferenceHand[] = [];

  for (const [handClass, freqMap] of Object.entries(data.hands)) {
    // Validate hand class
    const normalized = normalizeHandClass(handClass);

    // Validate frequencies
    if (typeof freqMap !== 'object' || freqMap === null) {
      throw new Error(`Frequencies for "${handClass}" must be an object${ctx}`);
    }

    const frequencies: number[] = [];
    for (const action of data.actions) {
      const freq = freqMap[action];
      if (typeof freq !== 'number' || !Number.isFinite(freq)) {
        throw new Error(`Missing or invalid frequency for "${handClass}.${action}"${ctx}`);
      }
      if (freq < 0 || freq > 1) {
        throw new Error(
          `Frequency for "${handClass}.${action}" must be in [0, 1], got ${freq}${ctx}`,
        );
      }
      frequencies.push(freq);
    }

    // Frequency sum check (can be < 1.0 if fold is implied, but not > 1.0)
    const sum = frequencies.reduce((a, b) => a + b, 0);
    if (sum > 1.05) {
      throw new Error(`Frequencies for "${handClass}" sum to ${sum.toFixed(3)} (> 1.0)${ctx}`);
    }

    // Expand to combos, filtering board-blocked
    const allCombos = expandHandClassToCombos(normalized);
    const combos = allCombos.filter(([c1, c2]) => !boardSet.has(c1) && !boardSet.has(c2));

    if (combos.length === 0) {
      // All combos blocked by board — skip with warning
      continue;
    }

    hands.push({
      handClass: normalized,
      frequencies,
      totalCombos: combos.length,
      combos,
    });
  }

  if (hands.length === 0) {
    throw new Error(`No valid hands after filtering board-blocked combos${ctx}`);
  }

  return {
    scenario: {
      board: data.scenario.board.trim(),
      street: street as ReferenceScenario['street'],
      position: position as ReferenceScenario['position'],
      spot: data.scenario.spot ?? 'SRP',
      stack: data.scenario.stack ?? '100bb',
      history: data.scenario.history ?? '',
    },
    actions: data.actions,
    hands,
    boardIndices,
  };
}

/**
 * Normalize a hand class to standard format: pairs as "AA", non-pairs as "AKs"/"AKo".
 */
function normalizeHandClass(hand: string): string {
  const RANKS = '23456789TJQKA';
  const h = hand.trim().toUpperCase();

  if (h.length === 2) {
    if (!RANKS.includes(h[0]) || !RANKS.includes(h[1])) {
      throw new Error(`Invalid hand class: "${hand}"`);
    }
    if (h[0] !== h[1]) {
      throw new Error(`Non-pair hand "${hand}" must include s/o suffix`);
    }
    return h;
  }

  if (h.length === 3) {
    if (!RANKS.includes(h[0]) || !RANKS.includes(h[1])) {
      throw new Error(`Invalid hand class: "${hand}"`);
    }
    const suffix = h[2];
    if (suffix !== 'S' && suffix !== 'O') {
      throw new Error(`Hand class "${hand}" must end with s or o`);
    }
    return h[0] + h[1] + suffix.toLowerCase();
  }

  throw new Error(`Invalid hand class: "${hand}"`);
}

/**
 * Map user-friendly action labels to solver action indices.
 *
 * Convention for user labels:
 * - "check"   → check action
 * - "fold"    → fold action
 * - "call"    → call action
 * - "bet33"   → 33% pot bet (matches closest bet size)
 * - "bet50"   → 50% pot bet
 * - "bet75"   → 75% pot bet
 * - "bet100"  → 100% pot bet
 * - "bet150"  → 150% pot bet
 * - "allin"   → all-in
 *
 * Returns the solver action index for each reference action,
 * or -1 if no match found.
 */
export function mapActionsToSolverIndices(
  refActions: string[],
  solverActions: string[],
  betSizes: number[], // bet sizes for the current street as pot fractions
): number[] {
  return refActions.map((label) => {
    const lower = label.toLowerCase().trim();

    if (lower === 'check') return solverActions.indexOf('check');
    if (lower === 'fold') return solverActions.indexOf('fold');
    if (lower === 'call') return solverActions.indexOf('call');
    if (lower === 'allin') return solverActions.indexOf('allin');

    // betXX → match to closest bet_N
    const betMatch = lower.match(/^bet(\d+)$/);
    if (betMatch) {
      const pct = parseInt(betMatch[1], 10) / 100;
      // Find closest bet size
      let bestIdx = -1;
      let bestDist = Infinity;
      for (let i = 0; i < betSizes.length; i++) {
        const dist = Math.abs(betSizes[i] - pct);
        if (dist < bestDist) {
          bestDist = dist;
          bestIdx = i;
        }
      }
      if (bestIdx >= 0 && bestDist < 0.15) {
        return solverActions.indexOf(`bet_${bestIdx}`);
      }
    }

    // raiseXX → match to closest raise_N
    const raiseMatch = lower.match(/^raise(\d+)$/);
    if (raiseMatch) {
      const pct = parseInt(raiseMatch[1], 10) / 100;
      let bestIdx = -1;
      let bestDist = Infinity;
      for (let i = 0; i < betSizes.length; i++) {
        const dist = Math.abs(betSizes[i] - pct);
        if (dist < bestDist) {
          bestDist = dist;
          bestIdx = i;
        }
      }
      if (bestIdx >= 0 && bestDist < 0.15) {
        return solverActions.indexOf(`raise_${bestIdx}`);
      }
    }

    return -1;
  });
}

/**
 * Infer the expected solver actions at a decision point based on config.
 *
 * @param history - Action history string (e.g. "" for root, "x" after check)
 * @param betSizes - Bet sizes for the current street
 * @param raiseCapPerStreet - Max raises allowed per street
 * @returns Expected solver action names
 */
export function inferSolverActions(
  history: string,
  betSizes: number[],
  raiseCapPerStreet: number,
): string[] {
  // Determine if facing a bet by looking at last action in current street
  const streetHistory = history.split('/').pop() ?? '';
  const lastChar = streetHistory.slice(-1);
  const facingBet =
    lastChar === '1' ||
    lastChar === '2' ||
    lastChar === '3' ||
    lastChar === '4' ||
    lastChar === '5' ||
    lastChar === 'A';

  if (facingBet) {
    const actions = ['fold', 'call'];
    // Count raises in current street
    const raiseCount = (streetHistory.match(/[1-5]/g) || []).length;
    if (raiseCount <= raiseCapPerStreet) {
      for (let i = 0; i < betSizes.length; i++) {
        actions.push(`raise_${i}`);
      }
    }
    actions.push('allin');
    return actions;
  }

  const actions = ['check'];
  for (let i = 0; i < betSizes.length; i++) {
    actions.push(`bet_${i}`);
  }
  actions.push('allin');
  return actions;
}
