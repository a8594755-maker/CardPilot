// Off-tree bet translation for the coaching system.
//
// When an opponent bets a size not in the action abstraction,
// maps to the nearest in-tree action(s) via linear interpolation.
//
// The neural network handles arbitrary sizes natively (continuous facingBet input),
// so this is only needed when querying the CFR blueprint directly.

export interface TranslatedAction {
  /** Weighted set of in-tree actions that approximate the off-tree bet. */
  actions: Array<{ action: string; weight: number }>;
}

/**
 * Translate an off-tree bet size (pot fraction) to weighted in-tree actions.
 *
 * Uses linear interpolation between the two bracketing sizes.
 * If the actual size is below the smallest or above the largest,
 * snaps to the nearest boundary.
 *
 * @param actualFraction - The actual bet as a fraction of pot (e.g. 0.40 = 40% pot)
 * @param availableFractions - The in-tree bet size fractions (sorted ascending)
 * @param isRaise - Whether this is a raise (prefix = 'raise_') or bet (prefix = 'bet_')
 */
export function translateBetSize(
  actualFraction: number,
  availableFractions: number[],
  isRaise = false,
): TranslatedAction {
  const sorted = [...availableFractions].sort((a, b) => a - b);
  const prefix = isRaise ? 'raise' : 'bet';

  if (sorted.length === 0) {
    return { actions: [{ action: 'allin', weight: 1.0 }] };
  }

  // Below smallest → snap to smallest
  if (actualFraction <= sorted[0]) {
    return { actions: [{ action: `${prefix}_0`, weight: 1.0 }] };
  }

  // Above largest → snap to allin
  if (actualFraction >= sorted[sorted.length - 1] * 1.5) {
    return { actions: [{ action: 'allin', weight: 1.0 }] };
  }

  // Above largest but not allin-range → snap to largest
  if (actualFraction >= sorted[sorted.length - 1]) {
    return { actions: [{ action: `${prefix}_${sorted.length - 1}`, weight: 1.0 }] };
  }

  // Linear interpolation between brackets
  for (let i = 0; i < sorted.length - 1; i++) {
    if (actualFraction >= sorted[i] && actualFraction <= sorted[i + 1]) {
      const t = (actualFraction - sorted[i]) / (sorted[i + 1] - sorted[i]);
      return {
        actions: [
          { action: `${prefix}_${i}`, weight: 1 - t },
          { action: `${prefix}_${i + 1}`, weight: t },
        ],
      };
    }
  }

  // Fallback (shouldn't reach)
  return { actions: [{ action: `${prefix}_0`, weight: 1.0 }] };
}

/**
 * Canonical action vocabulary for the coaching NN.
 * Fixed 16-dim output, same order across all configs.
 */
export const COACHING_ACTION_VOCAB = [
  'fold', // 0
  'check', // 1
  'call', // 2
  'bet_0', // 3  (25% pot)
  'bet_1', // 4  (33% pot)
  'bet_2', // 5  (50% pot)
  'bet_3', // 6  (75% pot)
  'bet_4', // 7  (100% pot)
  'bet_5', // 8  (150% pot)
  'raise_0', // 9  (25% pot raise / 2.5x raise)
  'raise_1', // 10 (33% pot raise / 3.0x raise)
  'raise_2', // 11 (50% pot raise)
  'raise_3', // 12 (75% pot raise)
  'raise_4', // 13 (100% pot raise)
  'raise_5', // 14 (150% pot raise)
  'allin', // 15
] as const;

export const COACHING_NUM_ACTIONS = COACHING_ACTION_VOCAB.length; // 16

/** Map an action string to its canonical index (0-15). Returns -1 if unknown. */
export function actionToIndex(action: string): number {
  const idx = (COACHING_ACTION_VOCAB as readonly string[]).indexOf(action);
  return idx;
}

/** Map a canonical index (0-15) to action string. */
export function indexToAction(index: number): string {
  return COACHING_ACTION_VOCAB[index];
}

/**
 * Action history token vocabulary for transformer input.
 * 19 tokens total.
 */
export const HISTORY_TOKEN_VOCAB = {
  PAD: 0,
  check: 1,
  fold: 2,
  call: 3,
  bet_0: 4, // bet 25%
  bet_1: 5, // bet 33%
  bet_2: 6, // bet 50%
  bet_3: 7, // bet 75%
  bet_4: 8, // bet 100%
  bet_5: 9, // bet 150%
  bet_allin: 10,
  raise_0: 11, // raise 25% / 2.5x
  raise_1: 12, // raise 33% / 3.0x
  raise_2: 13, // raise 50%
  raise_3: 14, // raise 75%
  raise_4: 15, // raise 100%
  raise_5: 16, // raise 150%
  raise_allin: 17,
  street_sep: 18, // '/' street separator
} as const;

export const HISTORY_VOCAB_SIZE = 19;
export const MAX_HISTORY_LENGTH = 30;

/** Convert an action string to a history token ID. */
export function actionToHistoryToken(action: string): number {
  if (action === 'allin') return HISTORY_TOKEN_VOCAB.bet_allin;
  const token = (HISTORY_TOKEN_VOCAB as Record<string, number>)[action];
  return token ?? HISTORY_TOKEN_VOCAB.PAD;
}
