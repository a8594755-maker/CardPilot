// Card utilities for poker evaluation

export type Card = string; // e.g., "Ah", "Ks"

export const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'];
export const SUITS = ['s', 'h', 'd', 'c'];
export const FULL_DECK: Card[] = RANKS.flatMap((rank) => SUITS.map((suit) => `${rank}${suit}`));

export interface CardDetails {
  rank: string;
  suit: string;
  rankValue: number; // 12 for A, 0 for 2
}

export function parseCard(card: Card): CardDetails {
  return {
    rank: card[0],
    suit: card[1],
    rankValue: RANKS.indexOf(card[0]),
  };
}

export function formatCard(rank: string, suit: string): Card {
  return `${rank}${suit}`;
}

export function isSuited(cards: [Card, Card]): boolean {
  return cards[0][1] === cards[1][1];
}

export function isPair(cards: [Card, Card]): boolean {
  return cards[0][0] === cards[1][0];
}

/**
 * Normalize hand representation.
 * "AhKh" -> "AKs"
 * "AhKd" -> "AKo"
 * "AhAd" -> "AA"
 */
export function normalizeHand(cards: [Card, Card]): string {
  const c1 = parseCard(cards[0]);
  const c2 = parseCard(cards[1]);

  if (c1.rank === c2.rank) {
    return `${c1.rank}${c2.rank}`;
  }

  const high = c1.rankValue <= c2.rankValue ? c1.rank : c2.rank;
  const low = c1.rankValue <= c2.rankValue ? c2.rank : c1.rank;
  const suited = c1.suit === c2.suit ? 's' : 'o';

  return `${high}${low}${suited}`;
}

/**
 * Create a shuffled deck, optionally using a deterministic seed.
 */
export function createShuffledDeck(seed?: string): Card[] {
  const deck = [...FULL_DECK];

  let seedValue = seed ? hashString(seed) : Date.now();

  for (let i = deck.length - 1; i > 0; i--) {
    seedValue = nextRandom(seedValue);
    const j = seedValue % (i + 1);
    [deck[i], deck[j]] = [deck[j], deck[i]];
  }

  return deck;
}

function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return Math.abs(hash);
}

function nextRandom(seed: number): number {
  return (seed * 1103515245 + 12345) & 0x7fffffff;
}

/**
 * Convert a card to pokersolver format.
 */
export function toSolverCard(card: Card): string {
  const suitMap: Record<string, string> = {
    s: 's',
    h: 'h',
    d: 'd',
    c: 'c',
  };

  return `${card[0]}${suitMap[card[1]] || card[1]}`;
}

export function toSolverCards(cards: Card[]): string[] {
  return cards.map(toSolverCard);
}
