type Rank = '2' | '3' | '4' | '5' | '6' | '7' | '8' | '9' | 'T' | 'J' | 'Q' | 'K' | 'A';

type ParsedCard = {
  rank: Rank;
  suit: string;
  value: number;
};

const RANK_VALUE: Record<Rank, number> = {
  '2': 2,
  '3': 3,
  '4': 4,
  '5': 5,
  '6': 6,
  '7': 7,
  '8': 8,
  '9': 9,
  T: 10,
  J: 11,
  Q: 12,
  K: 13,
  A: 14,
};

const RANK_NAME: Record<number, string> = {
  2: 'Twos',
  3: 'Threes',
  4: 'Fours',
  5: 'Fives',
  6: 'Sixes',
  7: 'Sevens',
  8: 'Eights',
  9: 'Nines',
  10: 'Tens',
  11: 'Jacks',
  12: 'Queens',
  13: 'Kings',
  14: 'Aces',
};

const RANK_NAME_SINGULAR: Record<number, string> = {
  2: 'Two',
  3: 'Three',
  4: 'Four',
  5: 'Five',
  6: 'Six',
  7: 'Seven',
  8: 'Eight',
  9: 'Nine',
  10: 'Ten',
  11: 'Jack',
  12: 'Queen',
  13: 'King',
  14: 'Ace',
};

function rankLabel(v: number): string {
  return RANK_NAME[v] ?? String(v);
}

function rankSingular(v: number): string {
  return RANK_NAME_SINGULAR[v] ?? String(v);
}

function parseCard(card: string): ParsedCard | null {
  if (typeof card !== 'string' || card.length < 2) return null;
  const rank = card[0] as Rank;
  const suit = card[1];
  if (!(rank in RANK_VALUE)) return null;
  return { rank, suit, value: RANK_VALUE[rank] };
}

function countByRank(cards: ParsedCard[]): Map<number, number> {
  const counts = new Map<number, number>();
  for (const card of cards) {
    counts.set(card.value, (counts.get(card.value) ?? 0) + 1);
  }
  return counts;
}

function findStraightHigh(values: number[]): number | null {
  const uniq = [...new Set(values)].sort((a, b) => b - a);
  const withWheel = uniq.includes(14) ? [...uniq, 1] : uniq;
  const sorted = [...new Set(withWheel)].sort((a, b) => b - a);
  for (let i = 0; i <= sorted.length - 5; i++) {
    if (sorted[i] - sorted[i + 4] === 4) return sorted[i];
  }
  return null;
}

function getFlushSuit(cards: ParsedCard[]): string | null {
  const suitCounts = new Map<string, number>();
  for (const card of cards) {
    suitCounts.set(card.suit, (suitCounts.get(card.suit) ?? 0) + 1);
  }
  for (const [suit, count] of suitCounts) {
    if (count >= 5) return suit;
  }
  return null;
}

function hasFlushDraw(cards: ParsedCard[]): boolean {
  const suitCounts = new Map<string, number>();
  for (const card of cards) {
    suitCounts.set(card.suit, (suitCounts.get(card.suit) ?? 0) + 1);
  }
  return [...suitCounts.values()].some((count) => count === 4);
}

function straightDrawLabel(
  values: number[],
): 'Open-ended straight draw' | 'Gutshot straight draw' | null {
  const uniq = [...new Set(values)].sort((a, b) => a - b);
  const allValues = uniq.includes(14) ? [1, ...uniq] : uniq;
  const set = new Set(allValues);

  let hasOpenEnded = false;
  let hasGutshot = false;

  for (let start = 1; start <= 10; start += 1) {
    const seq = [start, start + 1, start + 2, start + 3, start + 4];
    const hits = seq.filter((v) => set.has(v));
    if (hits.length !== 4) continue;

    const missing = seq.find((v) => !set.has(v));
    if (missing == null) continue;
    if (missing === seq[0] || missing === seq[4]) {
      hasOpenEnded = true;
    } else {
      hasGutshot = true;
    }
  }

  if (hasOpenEnded) return 'Open-ended straight draw';
  if (hasGutshot) return 'Gutshot straight draw';
  return null;
}

/**
 * Returns a human-readable description of the best made hand.
 * Examples: "Set of Queens", "Two Pair (Aces and Tens)", "Flush (King-high)",
 *           "Straight (Ten-high)", "Full House (Jacks full of Fours)"
 */
export function describeHandStrength(holeCards: string[], boardCards: string[]): string {
  const parsedHole = holeCards.map(parseCard).filter((c): c is ParsedCard => c !== null);
  const parsedBoard = boardCards.map(parseCard).filter((c): c is ParsedCard => c !== null);
  const all = [...parsedHole, ...parsedBoard];

  if (parsedHole.length < 2) return 'No hand data';
  if (parsedBoard.length === 0) return 'No board yet';

  const values = all.map((c) => c.value);
  const rankCountMap = countByRank(all);
  const rankCounts = [...rankCountMap.values()].sort((a, b) => b - a);
  const holeValues = new Set(parsedHole.map((c) => c.value));

  const flushSuit = getFlushSuit(all);
  const straightHigh = findStraightHigh(values);

  // Straight Flush / Royal Flush
  if (flushSuit && straightHigh !== null) {
    const flushCards = all.filter((c) => c.suit === flushSuit);
    const sfHigh = findStraightHigh(flushCards.map((c) => c.value));
    if (sfHigh !== null) {
      if (sfHigh === 14) return 'Royal Flush';
      return `Straight Flush (${rankSingular(sfHigh)}-high)`;
    }
  }

  // Four of a Kind
  if (rankCounts[0] === 4) {
    const quadRank = [...rankCountMap.entries()].find(([, c]) => c === 4)![0];
    return `Four of a Kind (${rankLabel(quadRank)})`;
  }

  // Full House
  if (rankCounts[0] === 3 && rankCounts[1] >= 2) {
    const trips = [...rankCountMap.entries()].filter(([, c]) => c >= 3).sort((a, b) => b[0] - a[0]);
    const pairs = [...rankCountMap.entries()]
      .filter(([r, c]) => c >= 2 && r !== trips[0][0])
      .sort((a, b) => b[0] - a[0]);
    if (trips.length > 0 && pairs.length > 0) {
      return `Full House (${rankLabel(trips[0][0])} full of ${rankLabel(pairs[0][0])})`;
    }
    return 'Full House';
  }

  // Flush
  if (flushSuit) {
    const flushCards = all.filter((c) => c.suit === flushSuit).sort((a, b) => b.value - a.value);
    return `Flush (${rankSingular(flushCards[0].value)}-high)`;
  }

  // Straight
  if (straightHigh !== null) {
    return `Straight (${rankSingular(straightHigh)}-high)`;
  }

  // Three of a Kind / Set / Trips
  if (rankCounts[0] === 3) {
    const tripRank = [...rankCountMap.entries()].find(([, c]) => c === 3)![0];
    const isSet = parsedHole.filter((c) => c.value === tripRank).length === 2;
    if (isSet) return `Set of ${rankLabel(tripRank)}`;
    return `Trips (${rankLabel(tripRank)})`;
  }

  // Two Pair
  if (rankCounts[0] === 2 && rankCounts[1] === 2) {
    const pairs = [...rankCountMap.entries()]
      .filter(([, c]) => c === 2)
      .sort((a, b) => b[0] - a[0]);
    if (pairs.length >= 2) {
      return `Two Pair (${rankLabel(pairs[0][0])} and ${rankLabel(pairs[1][0])})`;
    }
    return 'Two Pair';
  }

  // One Pair
  if (rankCounts[0] === 2) {
    const pairRank = [...rankCountMap.entries()].find(([, c]) => c === 2)![0];
    const boardValues = parsedBoard.map((c) => c.value);
    const boardTop = Math.max(...boardValues);
    const isPocket = parsedHole.filter((c) => c.value === pairRank).length === 2;
    if (isPocket) return `Pocket ${rankLabel(pairRank)}`;
    if (pairRank === boardTop && holeValues.has(pairRank))
      return `Top Pair (${rankLabel(pairRank)})`;
    // Check if it's middle or bottom pair
    const boardRanks = [...new Set(boardValues)].sort((a, b) => b - a);
    if (
      holeValues.has(pairRank) &&
      boardRanks.length >= 2 &&
      pairRank === boardRanks[boardRanks.length - 1]
    ) {
      return `Bottom Pair (${rankLabel(pairRank)})`;
    }
    if (holeValues.has(pairRank)) return `Pair of ${rankLabel(pairRank)}`;
    return `Pair of ${rankLabel(pairRank)}`;
  }

  // Draws (only pre-river)
  if (parsedBoard.length < 5) {
    const drawParts: string[] = [];
    if (hasFlushDraw(all)) drawParts.push('Flush draw');
    const straightDraw = straightDrawLabel(values);
    if (straightDraw) drawParts.push(straightDraw);
    if (drawParts.length > 0) return drawParts.join(' + ');
  }

  // High card
  const highCard = Math.max(...parsedHole.map((c) => c.value));
  return `High Card (${rankSingular(highCard)})`;
}
