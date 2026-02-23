// Integer card encoding: 0-51
// Index = rank * 4 + suit
// rank: 0=2, 1=3, ..., 12=A
// suit: 0=c, 1=d, 2=h, 3=s

const RANK_CHARS = '23456789TJQKA';
const SUIT_CHARS = 'cdhs';

export function cardToIndex(card: string): number {
  const rank = RANK_CHARS.indexOf(card[0]);
  const suit = SUIT_CHARS.indexOf(card[1]);
  if (rank === -1 || suit === -1) throw new Error(`Invalid card: ${card}`);
  return rank * 4 + suit;
}

export function indexToCard(index: number): string {
  const rank = (index >> 2);  // Math.floor(index / 4)
  const suit = index & 3;     // index % 4
  return RANK_CHARS[rank] + SUIT_CHARS[suit];
}

export function indexToRank(index: number): number {
  return index >> 2;
}

export function indexToSuit(index: number): number {
  return index & 3;
}

/** Total number of cards in a deck */
export const DECK_SIZE = 52;

/** Number of unique 2-card combos */
export const NUM_COMBOS = 1326;

/**
 * Map a pair of card indices (c1 < c2) to a unique combo index 0..1325.
 * Uses triangular number formula.
 */
export function comboIndex(c1: number, c2: number): number {
  const lo = Math.min(c1, c2);
  const hi = Math.max(c1, c2);
  // index = hi*(hi-1)/2 + lo
  return (hi * (hi - 1)) / 2 + lo;
}

/**
 * Enumerate all 1326 2-card combos, excluding dead cards.
 * Returns array of [c1, c2] with c1 < c2.
 */
export function enumerateCombos(deadCards?: Set<number>): Array<[number, number]> {
  const combos: Array<[number, number]> = [];
  for (let c1 = 0; c1 < 52; c1++) {
    if (deadCards && deadCards.has(c1)) continue;
    for (let c2 = c1 + 1; c2 < 52; c2++) {
      if (deadCards && deadCards.has(c2)) continue;
      combos.push([c1, c2]);
    }
  }
  return combos;
}

/**
 * Create a full deck as array of indices [0..51].
 */
export function fullDeck(): number[] {
  return Array.from({ length: 52 }, (_, i) => i);
}

/**
 * Fisher-Yates shuffle (in-place) with a simple seeded PRNG.
 */
export function shuffleDeck(deck: number[], seed: number): number[] {
  let s = seed;
  for (let i = deck.length - 1; i > 0; i--) {
    s = (s * 1103515245 + 12345) & 0x7fffffff;
    const j = s % (i + 1);
    [deck[i], deck[j]] = [deck[j], deck[i]];
  }
  return deck;
}
