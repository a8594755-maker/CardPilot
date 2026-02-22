// ===== Monte Carlo equity estimator =====
// Self-contained, zero-dependency equity estimation via random simulation.
// Used as a more accurate replacement for quickHandStrength() in fallback decisions.

const RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A'] as const;
const SUITS = ['c', 'd', 'h', 's'] as const;

const RANK_VAL: Record<string, number> = {
  '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
  '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14,
};

// Build full 52-card deck
function buildDeck(): string[] {
  const deck: string[] = [];
  for (const r of RANKS) {
    for (const s of SUITS) {
      deck.push(r + s);
    }
  }
  return deck;
}

// Remove known cards from deck
function removeSeen(deck: string[], seen: string[]): string[] {
  const seenSet = new Set(seen);
  return deck.filter(c => !seenSet.has(c));
}

// Fisher-Yates partial shuffle — only shuffle the first `n` elements
function partialShuffle(arr: string[], n: number): void {
  for (let i = 0; i < n && i < arr.length - 1; i++) {
    const j = i + Math.floor(Math.random() * (arr.length - i));
    const tmp = arr[i];
    arr[i] = arr[j];
    arr[j] = tmp;
  }
}

// ===== Simplified 7-card hand evaluator =====
// Returns a numeric score where higher = better hand.
// Categories: 8=SF, 7=quads, 6=full house, 5=flush, 4=straight, 3=trips, 2=two pair, 1=pair, 0=high

function evaluateHand(cards: string[]): number {
  // Count ranks and suits
  const rankCounts = new Map<number, number>();
  const suitCounts = new Map<string, number[]>(); // suit -> list of rank values

  for (const card of cards) {
    const rv = RANK_VAL[card[0]];
    const suit = card[1];
    rankCounts.set(rv, (rankCounts.get(rv) ?? 0) + 1);
    const list = suitCounts.get(suit);
    if (list) list.push(rv);
    else suitCounts.set(suit, [rv]);
  }

  // Check flush (5+ of same suit)
  let flushRanks: number[] | null = null;
  for (const [, ranks] of suitCounts) {
    if (ranks.length >= 5) {
      flushRanks = ranks.sort((a, b) => b - a);
      break;
    }
  }

  // Check straight from all unique rank values
  const allRanks = [...rankCounts.keys()].sort((a, b) => b - a);
  const straightHigh = findStraightHigh(allRanks);

  // Check straight flush
  if (flushRanks) {
    const sfHigh = findStraightHigh(flushRanks);
    if (sfHigh > 0) {
      return 8 * 1_000_000 + sfHigh;
    }
  }

  // Classify by rank counts
  const groups = [...rankCounts.entries()].sort((a, b) => {
    if (b[1] !== a[1]) return b[1] - a[1]; // most frequent first
    return b[0] - a[0]; // then by rank
  });

  const counts = groups.map(g => g[1]);
  const vals = groups.map(g => g[0]);

  // Four of a kind
  if (counts[0] === 4) {
    return 7 * 1_000_000 + vals[0] * 100 + vals[1];
  }

  // Full house (3 + 2 or 3 + 3)
  if (counts[0] === 3 && counts.length >= 2 && counts[1] >= 2) {
    return 6 * 1_000_000 + vals[0] * 100 + vals[1];
  }

  // Flush
  if (flushRanks) {
    return 5 * 1_000_000 + flushKicker(flushRanks);
  }

  // Straight
  if (straightHigh > 0) {
    return 4 * 1_000_000 + straightHigh;
  }

  // Three of a kind
  if (counts[0] === 3) {
    return 3 * 1_000_000 + vals[0] * 10000 + vals[1] * 100 + vals[2];
  }

  // Two pair
  if (counts[0] === 2 && counts.length >= 2 && counts[1] === 2) {
    const highPair = Math.max(vals[0], vals[1]);
    const lowPair = Math.min(vals[0], vals[1]);
    const kick = vals.find(v => v !== highPair && v !== lowPair) ?? 0;
    return 2 * 1_000_000 + highPair * 10000 + lowPair * 100 + kick;
  }

  // One pair
  if (counts[0] === 2) {
    return 1 * 1_000_000 + vals[0] * 10000 + vals[1] * 100 + (vals[2] ?? 0);
  }

  // High card
  return vals[0] * 10000 + (vals[1] ?? 0) * 100 + (vals[2] ?? 0);
}

// Find the highest card of a 5-card straight, or 0 if no straight.
// Handles ace-low straight (A-2-3-4-5).
function findStraightHigh(sortedDesc: number[]): number {
  const unique = [...new Set(sortedDesc)].sort((a, b) => b - a);
  if (unique.length < 5) return 0;

  let run = 1;
  for (let i = 1; i < unique.length; i++) {
    if (unique[i - 1] - unique[i] === 1) {
      run++;
      if (run >= 5) return unique[i - 1 + 1 - 5 + 1]; // highest of the run... wait
    } else {
      run = 1;
    }
  }

  // Re-check properly: find 5 consecutive
  for (let i = 0; i <= unique.length - 5; i++) {
    if (unique[i] - unique[i + 4] === 4) {
      return unique[i]; // highest card of the straight
    }
  }

  // Ace-low straight: A-2-3-4-5
  if (unique.includes(14) && unique.includes(2) && unique.includes(3) && unique.includes(4) && unique.includes(5)) {
    return 5; // 5-high straight
  }

  return 0;
}

function flushKicker(sortedDesc: number[]): number {
  // Encode top 5 cards
  return (sortedDesc[0] ?? 0) * 100_000
    + (sortedDesc[1] ?? 0) * 1000
    + (sortedDesc[2] ?? 0) * 100
    + (sortedDesc[3] ?? 0) * 10
    + (sortedDesc[4] ?? 0);
}

// ===== Main export =====

export interface MonteCarloResult {
  equity: number;        // 0-1, estimated win probability
  iterations: number;    // how many simulations completed
  timedOut: boolean;     // true if hit time limit before all iterations
}

/**
 * Estimate hand equity via Monte Carlo simulation.
 * @param holeCards Hero's hole cards [e.g. "Ah", "Ks"]
 * @param board Community cards dealt so far
 * @param numOpponents Number of active opponents
 * @param iterations Max simulation iterations (default 500)
 * @param timeLimitMs Max time in ms (default 80ms)
 */
export function estimateEquity(
  holeCards: [string, string],
  board: string[],
  numOpponents: number,
  iterations = 500,
  timeLimitMs = 80,
): MonteCarloResult {
  const startTime = Date.now();
  const fullDeck = buildDeck();
  const seen = [...holeCards, ...board];
  const available = removeSeen(fullDeck, seen);
  const boardToDeal = 5 - board.length;
  const cardsNeeded = boardToDeal + numOpponents * 2;

  // Not enough cards for even one simulation
  if (available.length < cardsNeeded) {
    return { equity: 0.5, iterations: 0, timedOut: false };
  }

  let wins = 0;
  let ties = 0;
  let completed = 0;

  // Reuse array for shuffling (avoid allocation per iteration)
  const deck = [...available];

  for (let i = 0; i < iterations; i++) {
    // Time check every 50 iterations to amortize Date.now() cost
    if (i > 0 && i % 50 === 0 && Date.now() - startTime > timeLimitMs) {
      return {
        equity: completed > 0 ? (wins + ties * 0.5) / completed : 0.5,
        iterations: completed,
        timedOut: true,
      };
    }

    // Partial shuffle — only need `cardsNeeded` random cards from top
    partialShuffle(deck, cardsNeeded);

    let idx = 0;

    // Deal remaining board cards
    const runoutBoard = board.length < 5
      ? [...board, ...deck.slice(idx, idx + boardToDeal)]
      : board;
    idx += boardToDeal;

    // Evaluate hero hand
    const heroCards = [...holeCards, ...runoutBoard];
    const heroScore = evaluateHand(heroCards);

    // Evaluate each opponent
    let heroWins = true;
    let heroTies = false;

    for (let opp = 0; opp < numOpponents; opp++) {
      const oppHole = [deck[idx], deck[idx + 1]];
      idx += 2;

      const oppCards = [...oppHole, ...runoutBoard];
      const oppScore = evaluateHand(oppCards);

      if (oppScore > heroScore) {
        heroWins = false;
        heroTies = false;
        break;
      }
      if (oppScore === heroScore) {
        heroTies = true;
        heroWins = false;
      }
    }

    if (heroWins) wins++;
    else if (heroTies) ties++;
    completed++;
  }

  return {
    equity: completed > 0 ? (wins + ties * 0.5) / completed : 0.5,
    iterations: completed,
    timedOut: false,
  };
}
