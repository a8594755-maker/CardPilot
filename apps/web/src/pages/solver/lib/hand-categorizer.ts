import type { GtoPlusCombo } from './api-client';

export interface HandCategory {
  name: string;
  key: string;
  combos: number;
  percentage: number;
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

function parseCard(card: string): { rank: string; suit: string; value: number } {
  return {
    rank: card[0],
    suit: card[1],
    value: RANK_VALUES[card[0]] || 0,
  };
}

function parseComboHand(hand: string): Array<{ rank: string; suit: string; value: number }> {
  const cards: Array<{ rank: string; suit: string; value: number }> = [];
  for (let i = 0; i < hand.length; i += 2) {
    cards.push(parseCard(hand.substring(i, i + 2)));
  }
  return cards;
}

/**
 * Categorize a single combo against a board into one of 13 GTO+ categories.
 * Since we don't have the board cards from the GTO+ data directly,
 * we infer from equity and hand structure.
 *
 * For now, this uses a heuristic approach based on equity ranges.
 * A more accurate version would take board cards and do full evaluation.
 */
export function categorizeCombo(combo: GtoPlusCombo): string {
  const cards = parseComboHand(combo.hand);
  if (cards.length < 2) return 'no_made_hand';

  const c1 = cards[0];
  const c2 = cards[1];
  const isPair = c1.value === c2.value;
  const equity = combo.equity;

  // High equity categories (made hands)
  if (equity >= 90) {
    if (isPair) return 'sets'; // Pocket pair with very high equity likely a set
    return 'straights'; // Very high equity non-pair likely straight+
  }

  if (equity >= 80) {
    if (isPair) return 'overpair';
    return 'two_pair';
  }

  if (equity >= 65) {
    if (isPair) {
      if (c1.value >= 10) return 'overpair';
      return 'pp_below_top';
    }
    return 'top_pair';
  }

  if (equity >= 50) {
    if (isPair) return 'pp_below_top';
    return 'middle_pair';
  }

  if (equity >= 35) {
    if (isPair) return 'weak_pair';
    // Check for draw potential by suit
    if (c1.suit === c2.suit) return 'backdoor_fd';
    const gap = Math.abs(c1.value - c2.value);
    if (gap <= 4 && gap >= 1) return 'gutshot';
    return 'weak_pair';
  }

  if (equity >= 25) {
    const gap = Math.abs(c1.value - c2.value);
    if (gap >= 1 && gap <= 3) return 'oesd';
    if (gap >= 1 && gap <= 4) return 'gutshot';
    if (c1.value === 14 || c2.value === 14) return 'ace_high';
    return 'gutshot';
  }

  if (equity >= 15) {
    if (c1.value === 14 || c2.value === 14) return 'ace_high';
    if (c1.suit === c2.suit) return 'backdoor_fd';
    return 'no_made_hand';
  }

  // Low equity
  if (c1.value === 14 || c2.value === 14) return 'ace_high';
  return 'no_made_hand';
}

const CATEGORY_DEFINITIONS: Array<{ key: string; name: string }> = [
  { key: 'straights', name: 'Straights' },
  { key: 'sets', name: 'Sets' },
  { key: 'two_pair', name: 'Two Pair' },
  { key: 'overpair', name: 'Overpair' },
  { key: 'top_pair', name: 'Top Pair' },
  { key: 'pp_below_top', name: 'PP < Top' },
  { key: 'middle_pair', name: 'Middle Pair' },
  { key: 'weak_pair', name: 'Weak Pair' },
  { key: 'ace_high', name: 'Ace High' },
  { key: 'no_made_hand', name: 'No Made Hand' },
  { key: 'oesd', name: 'OESD' },
  { key: 'gutshot', name: 'Gutshot' },
  { key: 'backdoor_fd', name: 'Backdoor FD' },
];

export function categorizeAllCombos(combos: GtoPlusCombo[]): HandCategory[] {
  const counts: Record<string, number> = {};
  for (const def of CATEGORY_DEFINITIONS) {
    counts[def.key] = 0;
  }

  let totalCombos = 0;
  for (const combo of combos) {
    const category = categorizeCombo(combo);
    counts[category] = (counts[category] || 0) + combo.combos;
    totalCombos += combo.combos;
  }

  return CATEGORY_DEFINITIONS.map((def) => ({
    name: def.name,
    key: def.key,
    combos: counts[def.key] || 0,
    percentage: totalCombos > 0 ? (counts[def.key] || 0) / totalCombos : 0,
  }));
}

export function computeEquityBuckets(combos: GtoPlusCombo[]): number[] {
  const buckets = [0, 0, 0, 0, 0]; // 0-20, 20-40, 40-60, 60-80, 80-100
  for (const c of combos) {
    const idx = Math.min(4, Math.floor(c.equity / 20));
    buckets[idx] += c.combos;
  }
  return buckets;
}
