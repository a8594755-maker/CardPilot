import type { GtoPlusCombo } from './api-client';

/**
 * Board-aware hand categorizer for GTO+ analysis.
 * Classifies combos against a given board into standard poker categories
 * (straight, flush, set, two pair, top pair, etc.) and computes
 * per-category action frequency distributions.
 */

export interface HandCategoryWithActions {
  name: string;
  nameZh: string;
  key: string;
  combos: number;
  percentage: number;
  actionDistribution: Record<string, number>; // action -> weighted combos in this category
  comboHands: string[]; // list of combo hand strings in this category
}

const RANK_VALUES: Record<string, number> = {
  A: 14,
  K: 13,
  Q: 12,
  J: 11,
  T: 10,
  '9': 9,
  '8': 8,
  '7': 7,
  '6': 6,
  '5': 5,
  '4': 4,
  '3': 3,
  '2': 2,
};

interface ParsedCard {
  rank: string;
  suit: string;
  value: number;
}

function parseCard(card: string): ParsedCard {
  return {
    rank: card[0],
    suit: card[1],
    value: RANK_VALUES[card[0]] || 0,
  };
}

function parseHand(hand: string): ParsedCard[] {
  const cards: ParsedCard[] = [];
  for (let i = 0; i + 1 < hand.length; i += 2) {
    cards.push(parseCard(hand.substring(i, i + 2)));
  }
  return cards;
}

/** Check if values form a straight (5 consecutive, A can be low) */
function hasStraight(values: number[]): boolean {
  const unique = [...new Set(values)].sort((a, b) => b - a);
  if (unique.length < 5) return false;
  for (let i = 0; i <= unique.length - 5; i++) {
    if (unique[i] - unique[i + 4] === 4) return true;
  }
  // Check wheel: A-2-3-4-5
  if (
    unique.includes(14) &&
    unique.includes(5) &&
    unique.includes(4) &&
    unique.includes(3) &&
    unique.includes(2)
  ) {
    return true;
  }
  return false;
}

/** Check if values form an OESD (open-ended straight draw = 4 consecutive, can complete on both ends) */
function hasOESD(holeValues: number[], boardValues: number[]): boolean {
  const allValues = [...holeValues, ...boardValues];
  const unique = [...new Set(allValues)].sort((a, b) => a - b);

  // Need at least one hole card contributing to the draw
  for (let i = 0; i <= unique.length - 4; i++) {
    if (unique[i + 3] - unique[i] === 3) {
      // 4 consecutive cards - check that at least one hole card is part of it
      const run = [unique[i], unique[i + 1], unique[i + 2], unique[i + 3]];
      const holeInRun = holeValues.some((v) => run.includes(v));
      if (!holeInRun) continue;
      // Check it's open-ended (not a gutshot): can complete on both sides
      const low = run[0];
      const high = run[3];
      // Not open-ended if low end is A(2-3-4-5 needs only A) or high end is A
      if (low === 2 && high === 5 && !unique.includes(14)) return true; // wheel draw
      if (low > 1 && high < 14) return true;
      // Check if wheel draw: A,2,3,4 or 2,3,4,5
      if (high === 14 && low === 2) continue; // gutshot to wheel, not OESD
    }
  }
  return false;
}

/** Check if hole cards have a gutshot draw */
function hasGutshot(holeValues: number[], boardValues: number[]): boolean {
  const allValues = [...new Set([...holeValues, ...boardValues])].sort((a, b) => a - b);

  // Look for 4 out of 5 consecutive with one gap, and at least one hole card involved
  for (let target = 2; target <= 14; target++) {
    // Build 5-card straight targets
    let straightValues: number[];
    if (target === 14) {
      // Wheel: A,2,3,4,5
      straightValues = [14, 2, 3, 4, 5];
    } else if (target + 4 <= 14) {
      straightValues = [target, target + 1, target + 2, target + 3, target + 4];
    } else {
      continue;
    }

    const present = straightValues.filter((v) => allValues.includes(v));
    const missing = straightValues.filter((v) => !allValues.includes(v));

    if (present.length === 4 && missing.length === 1) {
      // Must have at least one hole card in the 4 present
      const holeContributes = holeValues.some((v) => present.includes(v));
      if (holeContributes) return true;
    }
  }
  return false;
}

/** Check if there's a flush draw (4 cards of same suit, at least 1 hole card) */
function hasFlushDraw(holeCards: ParsedCard[], boardCards: ParsedCard[]): boolean {
  const suitCounts: Record<string, { total: number; hole: number }> = {};
  for (const c of [...holeCards, ...boardCards]) {
    if (!suitCounts[c.suit]) suitCounts[c.suit] = { total: 0, hole: 0 };
    suitCounts[c.suit].total++;
  }
  for (const c of holeCards) {
    if (suitCounts[c.suit]) suitCounts[c.suit].hole++;
  }
  return Object.values(suitCounts).some((s) => s.total === 4 && s.hole >= 1);
}

/** Check if there's a flush (5+ cards of same suit, at least 1 hole card) */
function hasFlush(holeCards: ParsedCard[], boardCards: ParsedCard[]): boolean {
  const suitCounts: Record<string, { total: number; hole: number }> = {};
  for (const c of [...holeCards, ...boardCards]) {
    if (!suitCounts[c.suit]) suitCounts[c.suit] = { total: 0, hole: 0 };
    suitCounts[c.suit].total++;
  }
  for (const c of holeCards) {
    if (suitCounts[c.suit]) suitCounts[c.suit].hole++;
  }
  return Object.values(suitCounts).some((s) => s.total >= 5 && s.hole >= 1);
}

/** Check for backdoor flush draw (3 of same suit with at least 1 hole card) */
function hasBackdoorFD(holeCards: ParsedCard[], boardCards: ParsedCard[]): boolean {
  if (boardCards.length > 3) return false; // only on flop
  const suitCounts: Record<string, { total: number; hole: number }> = {};
  for (const c of [...holeCards, ...boardCards]) {
    if (!suitCounts[c.suit]) suitCounts[c.suit] = { total: 0, hole: 0 };
    suitCounts[c.suit].total++;
  }
  for (const c of holeCards) {
    if (suitCounts[c.suit]) suitCounts[c.suit].hole++;
  }
  return Object.values(suitCounts).some((s) => s.total === 3 && s.hole >= 1);
}

export type CategoryKey =
  | 'flush'
  | 'straight'
  | 'sets'
  | 'two_pair'
  | 'overpair'
  | 'top_pair'
  | 'pp_below_top'
  | 'middle_pair'
  | 'weak_pair'
  | 'ace_high'
  | 'no_made_hand'
  | 'flush_draw'
  | 'oesd'
  | 'gutshot'
  | 'backdoor_fd';

const CATEGORY_DEFINITIONS: Array<{ key: CategoryKey; name: string; nameZh: string }> = [
  { key: 'flush', name: 'Flush', nameZh: '\u540C\u82B1' },
  { key: 'straight', name: 'Straight', nameZh: '\u9806\u5B50' },
  { key: 'sets', name: 'Sets', nameZh: '\u6697\u4E09\u689D' },
  { key: 'two_pair', name: 'Two Pair', nameZh: '\u5169\u5C0D' },
  { key: 'overpair', name: 'Overpair', nameZh: '\u8D85\u5C0D' },
  { key: 'top_pair', name: 'Top Pair', nameZh: '\u9802\u5C0D' },
  { key: 'pp_below_top', name: 'PP < Top', nameZh: '\u53E3\u888B\u5C0D' },
  { key: 'middle_pair', name: 'Middle Pair', nameZh: '\u4E2D\u5C0D' },
  { key: 'weak_pair', name: 'Weak Pair', nameZh: '\u5F31\u5C0D' },
  { key: 'ace_high', name: 'Ace High', nameZh: 'A\u9AD8\u724C' },
  { key: 'no_made_hand', name: 'No Made Hand', nameZh: '\u6C92\u6709\u6210\u724C' },
  { key: 'flush_draw', name: 'Flush Draw', nameZh: '\u540C\u82B1\u807D\u724C' },
  { key: 'oesd', name: 'OESD', nameZh: '\u5169\u982D\u9806\u807D' },
  { key: 'gutshot', name: 'Gutshot', nameZh: '\u5361\u9806\u807D\u724C' },
  { key: 'backdoor_fd', name: 'Backdoor FD', nameZh: '\u5F8C\u9580\u540C\u82B1' },
];

/**
 * Categorize a combo against a known board.
 * Returns ALL matching categories (a hand can be both a pair and a draw).
 */
export function categorizeComboBoardAware(hand: string, boardCards: string[]): CategoryKey[] {
  const holeCards = parseHand(hand);
  const board = boardCards.map(parseCard);

  if (holeCards.length < 2 || board.length < 3) return ['no_made_hand'];

  const categories: CategoryKey[] = [];
  const allCards = [...holeCards, ...board];
  const allValues = allCards.map((c) => c.value);
  const holeValues = holeCards.map((c) => c.value);
  const boardValues = board.map((c) => c.value);
  const boardRanks = boardValues.sort((a, b) => b - a);
  const topBoardRank = boardRanks[0];
  const secondBoardRank = boardRanks[1];
  const isPocketPair = holeValues[0] === holeValues[1];

  // ---- Made hands (mutually exclusive for made hand category) ----

  // Flush
  const isFlush = hasFlush(holeCards, board);
  if (isFlush) categories.push('flush');

  // Straight
  const isStraight = hasStraight(allValues);
  if (isStraight && !isFlush) categories.push('straight');

  // Set (pocket pair matches a board card)
  if (isPocketPair && boardValues.includes(holeValues[0])) {
    categories.push('sets');
  }

  // Two pair (both hole cards pair with board cards, and it's not a set)
  if (!isPocketPair) {
    const h0PairsBoard = boardValues.includes(holeValues[0]);
    const h1PairsBoard = boardValues.includes(holeValues[1]);
    if (h0PairsBoard && h1PairsBoard) {
      categories.push('two_pair');
    } else if (h0PairsBoard || h1PairsBoard) {
      // Single pair with board
      const pairedValue = h0PairsBoard ? holeValues[0] : holeValues[1];
      if (pairedValue === topBoardRank) {
        categories.push('top_pair');
      } else if (pairedValue === secondBoardRank) {
        categories.push('middle_pair');
      } else {
        categories.push('weak_pair');
      }
    }
  }

  // Overpair (pocket pair above top board card)
  if (isPocketPair && holeValues[0] > topBoardRank && !boardValues.includes(holeValues[0])) {
    categories.push('overpair');
  }

  // Pocket pair below top card (not a set, not an overpair)
  if (isPocketPair && !boardValues.includes(holeValues[0]) && holeValues[0] <= topBoardRank) {
    if (holeValues[0] > secondBoardRank) {
      categories.push('pp_below_top');
    } else {
      categories.push('weak_pair');
    }
  }

  // Ace high (no pair, no straight, no flush, but has an ace)
  const hasMadeHand = categories.some((c) =>
    [
      'flush',
      'straight',
      'sets',
      'two_pair',
      'overpair',
      'top_pair',
      'pp_below_top',
      'middle_pair',
      'weak_pair',
    ].includes(c),
  );
  if (!hasMadeHand) {
    if (holeValues.includes(14)) {
      categories.push('ace_high');
    } else {
      categories.push('no_made_hand');
    }
  }

  // ---- Draws (can overlap with made hands) ----

  // Flush draw (4 to a flush)
  if (!isFlush && hasFlushDraw(holeCards, board)) {
    categories.push('flush_draw');
  }

  // OESD
  if (!isStraight && hasOESD(holeValues, boardValues)) {
    categories.push('oesd');
  }

  // Gutshot
  if (!isStraight && !hasOESD(holeValues, boardValues) && hasGutshot(holeValues, boardValues)) {
    categories.push('gutshot');
  }

  // Backdoor flush draw
  if (!isFlush && !hasFlushDraw(holeCards, board) && hasBackdoorFD(holeCards, board)) {
    categories.push('backdoor_fd');
  }

  return categories.length > 0 ? categories : ['no_made_hand'];
}

/**
 * Build category data for all combos with board-aware classification.
 * Each category includes the action distribution (how many combos of each action).
 */
export function categorizeAllCombosWithBoard(
  combos: GtoPlusCombo[],
  boardCards: string[],
  actions: string[],
): HandCategoryWithActions[] {
  const categoryData: Record<
    string,
    {
      combos: number;
      actionDist: Record<string, number>;
      hands: string[];
    }
  > = {};

  // Initialize all categories
  for (const def of CATEGORY_DEFINITIONS) {
    categoryData[def.key] = { combos: 0, actionDist: {}, hands: [] };
    for (const a of actions) {
      categoryData[def.key].actionDist[a] = 0;
    }
  }

  let totalCombos = 0;
  for (const combo of combos) {
    const cats =
      boardCards.length >= 3
        ? categorizeComboBoardAware(combo.hand, boardCards)
        : categorizeComboFallback(combo);

    totalCombos += combo.combos;

    for (const cat of cats) {
      const data = categoryData[cat];
      if (!data) continue;
      data.combos += combo.combos;
      data.hands.push(combo.hand);
      for (const a of actions) {
        data.actionDist[a] += (combo.frequencies[a] || 0) * combo.combos;
      }
    }
  }

  return CATEGORY_DEFINITIONS.map((def) => {
    const data = categoryData[def.key];
    return {
      name: def.name,
      nameZh: def.nameZh,
      key: def.key,
      combos: data.combos,
      percentage: totalCombos > 0 ? data.combos / totalCombos : 0,
      actionDistribution: data.actionDist,
      comboHands: data.hands,
    };
  }).filter((cat) => cat.combos > 0);
}

/**
 * Fallback categorizer when no board cards are available.
 * Uses equity heuristics like the original hand-categorizer.ts
 */
function categorizeComboFallback(combo: GtoPlusCombo): CategoryKey[] {
  const cards = parseHand(combo.hand);
  if (cards.length < 2) return ['no_made_hand'];

  const isPair = cards[0].value === cards[1].value;
  const equity = combo.equity;

  if (equity >= 90) return isPair ? ['sets'] : ['straight'];
  if (equity >= 80) return isPair ? ['overpair'] : ['two_pair'];
  if (equity >= 65)
    return isPair ? (cards[0].value >= 10 ? ['overpair'] : ['pp_below_top']) : ['top_pair'];
  if (equity >= 50) return isPair ? ['pp_below_top'] : ['middle_pair'];
  if (equity >= 35) {
    if (isPair) return ['weak_pair'];
    if (cards[0].suit === cards[1].suit) return ['flush_draw'];
    return ['gutshot'];
  }
  if (equity >= 25) {
    if (cards[0].value === 14 || cards[1].value === 14) return ['ace_high'];
    return ['gutshot'];
  }
  if (cards[0].value === 14 || cards[1].value === 14) return ['ace_high'];
  return ['no_made_hand'];
}

/**
 * Get the list of categories a specific hand belongs to.
 */
export function getCategoriesForHand(hand: string, boardCards: string[]): CategoryKey[] {
  return boardCards.length >= 3 ? categorizeComboBoardAware(hand, boardCards) : ['no_made_hand'];
}

export { CATEGORY_DEFINITIONS };
