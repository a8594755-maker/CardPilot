// Suit isomorphism for flop canonicalization
// Two flops are suit-isomorphic if they differ only in suit assignment.
// e.g., AsKsQs ≡ AhKhQh (both monotone AKQ)
//
// We canonicalize by always assigning suits in the order they first appear:
// First suit → 0, second suit → 1, etc.

import { indexToRank, indexToSuit } from './card-index.js';

/**
 * Compute a canonical form for a flop under suit isomorphism.
 * Returns a normalized representation where suits are renamed to 0,1,2,3
 * in order of first appearance.
 *
 * The canonical form is a string like "12-0,8-0,4-1" (rank-canonicalSuit pairs).
 */
export function canonicalFlop(cards: [number, number, number]): string {
  // Sort by rank descending, then by suit
  const sorted = [...cards].sort((a, b) => {
    const rd = indexToRank(b) - indexToRank(a);
    if (rd !== 0) return rd;
    return indexToSuit(a) - indexToSuit(b);
  });

  // Rename suits in order of first appearance
  const suitMap = new Map<number, number>();
  let nextSuit = 0;

  const canonical = sorted.map((c) => {
    const rank = indexToRank(c);
    const suit = indexToSuit(c);
    if (!suitMap.has(suit)) {
      suitMap.set(suit, nextSuit++);
    }
    return `${rank}-${suitMap.get(suit)!}`;
  });

  return canonical.join(',');
}

/**
 * Generate all suit-isomorphic unique flops.
 * Returns one representative per isomorphism class.
 */
export function enumerateIsomorphicFlops(): Array<{
  cards: [number, number, number];
  canonical: string;
}> {
  const seen = new Set<string>();
  const results: Array<{ cards: [number, number, number]; canonical: string }> = [];

  for (let c1 = 0; c1 < 52; c1++) {
    for (let c2 = c1 + 1; c2 < 52; c2++) {
      for (let c3 = c2 + 1; c3 < 52; c3++) {
        const cards: [number, number, number] = [c1, c2, c3];
        const canon = canonicalFlop(cards);
        if (!seen.has(canon)) {
          seen.add(canon);
          results.push({ cards, canonical: canon });
        }
      }
    }
  }

  return results;
}
