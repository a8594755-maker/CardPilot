// ===== Monte Carlo equity estimator (optimized for throughput) =====
// Zero-allocation inner loop: uses pre-allocated typed arrays and integer card encoding.

// Card encoding: 0-51 integer, rank = card % 13 (0=2..12=A), suit = card / 13 | 0
const FULL_DECK = new Uint8Array(52);
for (let i = 0; i < 52; i++) FULL_DECK[i] = i;

// String card → integer lookup (built once at module load)
const CARD_TO_INT: Record<string, number> = {};
const RANK_CHARS = '23456789TJQKA';
const SUIT_CHARS = 'cdhs';
for (let s = 0; s < 4; s++) {
  for (let r = 0; r < 13; r++) {
    CARD_TO_INT[RANK_CHARS[r] + SUIT_CHARS[s]] = s * 13 + r;
  }
}

// ===== Zero-alloc hand evaluator =====
// Uses pre-allocated workspace arrays (one set per evaluateHand call).
// rank value = card % 13 (0=deuce .. 12=ace), suit = card / 13 | 0

// Workspace: reused across evaluateHand calls (single-threaded so safe)
const _rc = new Uint8Array(13);     // rank counts
const _sc = [                        // suit-grouped ranks (4 suits × max 7 cards)
  new Uint8Array(7), new Uint8Array(7), new Uint8Array(7), new Uint8Array(7),
];
const _scLen = new Uint8Array(4);    // how many cards in each suit
const _sortBuf = new Uint8Array(13); // for sorting unique ranks

function evaluateHandFast(hand: Uint8Array, n: number): number {
  // Reset workspace
  _rc.fill(0);
  _scLen.fill(0);

  for (let i = 0; i < n; i++) {
    const card = hand[i];
    const rank = card % 13;
    const suit = (card / 13) | 0;
    _rc[rank]++;
    _sc[suit][_scLen[suit]++] = rank;
  }

  // Check flush (5+ of same suit)
  let flushSuit = -1;
  for (let s = 0; s < 4; s++) {
    if (_scLen[s] >= 5) { flushSuit = s; break; }
  }

  // Find straight from unique ranks (sorted desc)
  let uniqueCount = 0;
  for (let r = 12; r >= 0; r--) {
    if (_rc[r] > 0) _sortBuf[uniqueCount++] = r;
  }

  const straightHigh = findStraightFast(_sortBuf, uniqueCount);

  // Check straight flush
  if (flushSuit >= 0) {
    // Sort flush suit ranks descending into _sortBuf
    const fLen = _scLen[flushSuit];
    const fRanks = _sc[flushSuit];
    // Simple insertion sort (max 7 elements)
    let fUnique = 0;
    // Copy and sort desc
    for (let i = 0; i < fLen; i++) _sortBuf[i] = fRanks[i];
    for (let i = 1; i < fLen; i++) {
      const v = _sortBuf[i];
      let j = i - 1;
      while (j >= 0 && _sortBuf[j] < v) { _sortBuf[j + 1] = _sortBuf[j]; j--; }
      _sortBuf[j + 1] = v;
    }
    // Deduplicate (shouldn't have dupes in same suit, but be safe)
    fUnique = fLen;

    const sfHigh = findStraightFast(_sortBuf, fUnique);
    if (sfHigh >= 0) {
      return 8_000_000 + sfHigh;
    }
  }

  // Classify by rank counts — find top groups
  // We need: best count, its rank; second-best count, its rank; etc.
  let c1 = 0, r1 = 0; // best group
  let c2 = 0, r2 = 0; // second group
  let c3 = 0, r3 = 0; // third group (for kickers)

  for (let r = 12; r >= 0; r--) {
    const c = _rc[r];
    if (c === 0) continue;
    if (c > c1 || (c === c1 && r > r1)) {
      c3 = c2; r3 = r2;
      c2 = c1; r2 = r1;
      c1 = c; r1 = r;
    } else if (c > c2 || (c === c2 && r > r2)) {
      c3 = c2; r3 = r2;
      c2 = c; r2 = r;
    } else if (c > c3 || (c === c3 && r > r3)) {
      c3 = c; r3 = r;
    }
  }

  // Four of a kind
  if (c1 === 4) return 7_000_000 + r1 * 100 + r2;

  // Full house
  if (c1 >= 3 && c2 >= 2) return 6_000_000 + r1 * 100 + r2;

  // Flush
  if (flushSuit >= 0) {
    // _sortBuf already has flush ranks sorted desc from above
    const fLen = _scLen[flushSuit];
    return 5_000_000
      + _sortBuf[0] * 100_000
      + (_sortBuf[1] ?? 0) * 1000
      + (_sortBuf[2] ?? 0) * 100
      + (fLen > 3 ? _sortBuf[3] : 0) * 10
      + (fLen > 4 ? _sortBuf[4] : 0);
  }

  // Straight
  if (straightHigh >= 0) return 4_000_000 + straightHigh;

  // Three of a kind
  if (c1 === 3) return 3_000_000 + r1 * 10000 + r2 * 100 + r3;

  // Two pair
  if (c1 === 2 && c2 === 2) {
    const highPair = Math.max(r1, r2);
    const lowPair = Math.min(r1, r2);
    return 2_000_000 + highPair * 10000 + lowPair * 100 + r3;
  }

  // One pair
  if (c1 === 2) return 1_000_000 + r1 * 10000 + r2 * 100 + r3;

  // High card
  return r1 * 10000 + r2 * 100 + r3;
}

// Find highest straight from sorted-desc unique ranks, returns rank (0-12) or -1
function findStraightFast(sorted: Uint8Array, len: number): number {
  if (len < 5) return -1;

  // Check for 5 consecutive
  for (let i = 0; i <= len - 5; i++) {
    if (sorted[i] - sorted[i + 4] === 4) return sorted[i];
  }

  // Ace-low straight: A(12)-2(0)-3(1)-4(2)-5(3)
  if (sorted[0] === 12) {
    let hasWheel = true;
    for (const need of [0, 1, 2, 3]) {
      let found = false;
      for (let j = 0; j < len; j++) { if (sorted[j] === need) { found = true; break; } }
      if (!found) { hasWheel = false; break; }
    }
    if (hasWheel) return 3; // 5-high straight (rank 3 = "5")
  }

  return -1;
}

// ===== Main export =====

export interface MonteCarloResult {
  equity: number;
  iterations: number;
  timedOut: boolean;
}

// Pre-allocated buffers for the simulation loop (single-threaded)
const _availDeck = new Uint8Array(52);
const _heroHand = new Uint8Array(7);
const _oppHand = new Uint8Array(7);
const _boardInts = new Uint8Array(5);
const _seenMarks = new Uint8Array(52);
const _seenList = new Uint8Array(7);

export function estimateEquity(
  holeCards: [string, string],
  board: string[],
  numOpponents: number,
  iterations = 500,
  timeLimitMs = 80,
): MonteCarloResult {
  const startTime = Date.now();

  // Convert hole cards and board to integers
  const h0 = CARD_TO_INT[holeCards[0]];
  const h1 = CARD_TO_INT[holeCards[1]];
  const boardLen = board.length;
  for (let i = 0; i < boardLen; i++) _boardInts[i] = CARD_TO_INT[board[i]];
  const boardToDeal = 5 - boardLen;
  const cardsNeeded = boardToDeal + numOpponents * 2;

  // Build available deck (exclude seen cards)
  let seenCount = 0;
  if (_seenMarks[h0] === 0) { _seenMarks[h0] = 1; _seenList[seenCount++] = h0; }
  if (_seenMarks[h1] === 0) { _seenMarks[h1] = 1; _seenList[seenCount++] = h1; }
  for (let i = 0; i < boardLen; i++) {
    const b = _boardInts[i];
    if (_seenMarks[b] === 0) { _seenMarks[b] = 1; _seenList[seenCount++] = b; }
  }

  let availLen = 0;
  for (let i = 0; i < 52; i++) {
    if (_seenMarks[i] === 0) _availDeck[availLen++] = i;
  }
  for (let i = 0; i < seenCount; i++) _seenMarks[_seenList[i]] = 0;

  if (availLen < cardsNeeded) {
    return { equity: 0.5, iterations: 0, timedOut: false };
  }

  // Pre-fill hero hand with hole cards + known board
  _heroHand[0] = h0;
  _heroHand[1] = h1;
  for (let i = 0; i < boardLen; i++) _heroHand[2 + i] = _boardInts[i];

  let wins = 0;
  let ties = 0;
  let completed = 0;

  for (let iter = 0; iter < iterations; iter++) {
    // Time check every 50 iterations
    if (iter > 0 && iter % 50 === 0 && Date.now() - startTime > timeLimitMs) {
      return {
        equity: completed > 0 ? (wins + ties * 0.5) / completed : 0.5,
        iterations: completed,
        timedOut: true,
      };
    }

    // Partial Fisher-Yates shuffle (only first `cardsNeeded` positions)
    for (let i = 0; i < cardsNeeded; i++) {
      const j = i + ((Math.random() * (availLen - i)) | 0);
      const tmp = _availDeck[i];
      _availDeck[i] = _availDeck[j];
      _availDeck[j] = tmp;
    }

    let idx = 0;

    // Deal remaining board cards into hero hand
    for (let i = 0; i < boardToDeal; i++) {
      _heroHand[2 + boardLen + i] = _availDeck[idx++];
    }

    const heroScore = evaluateHandFast(_heroHand, 7);

    // Evaluate each opponent
    let heroWins = true;
    let heroTies = false;

    for (let opp = 0; opp < numOpponents; opp++) {
      // Opponent hand: 2 hole + 5 board (reuse board from heroHand[2..6])
      _oppHand[0] = _availDeck[idx++];
      _oppHand[1] = _availDeck[idx++];
      for (let i = 0; i < 5; i++) _oppHand[2 + i] = _heroHand[2 + i];

      const oppScore = evaluateHandFast(_oppHand, 7);

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
