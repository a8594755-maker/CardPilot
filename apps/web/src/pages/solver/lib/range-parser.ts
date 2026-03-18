const RANKS = 'AKQJT98765432';
const ALL_HAND_CLASSES: string[] = [];

// Generate all 169 hand classes
for (let i = 0; i < 13; i++) {
  for (let j = 0; j < 13; j++) {
    if (i === j) {
      ALL_HAND_CLASSES.push(`${RANKS[i]}${RANKS[j]}`);
    } else if (i < j) {
      ALL_HAND_CLASSES.push(`${RANKS[i]}${RANKS[j]}s`);
    } else {
      ALL_HAND_CLASSES.push(`${RANKS[j]}${RANKS[i]}o`);
    }
  }
}

export { ALL_HAND_CLASSES };

/**
 * Parse a range string like "AA,AKs,AQs-A2s,KQo" into a set of hand classes.
 */
export function parseRange(rangeStr: string): Set<string> {
  const hands = new Set<string>();
  if (!rangeStr.trim()) return hands;

  const parts = rangeStr
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

  for (const part of parts) {
    if (part.includes('-')) {
      // Range notation: "AQs-A2s" or "TT-66"
      const [start, end] = part.split('-').map((s) => s.trim());
      expandRange(start, end, hands);
    } else if (part.endsWith('+')) {
      // Plus notation: "ATs+" means ATs, AJs, AQs, AKs
      expandPlus(part.slice(0, -1), hands);
    } else {
      // Single hand: "AA", "AKs", "AKo"
      if (ALL_HAND_CLASSES.includes(part)) {
        hands.add(part);
      }
    }
  }

  return hands;
}

/**
 * Convert a set of hand classes to a compact range string.
 */
export function handsToRange(hands: Set<string>): string {
  if (hands.size === 0) return '';

  // Group by type: pairs, suited, offsuit
  const pairs: string[] = [];
  const suited: Map<string, string[]> = new Map();
  const offsuit: Map<string, string[]> = new Map();

  for (const hand of hands) {
    if (hand.length === 2) {
      pairs.push(hand);
    } else if (hand.endsWith('s')) {
      const hi = hand[0];
      const lo = hand[1];
      if (!suited.has(hi)) suited.set(hi, []);
      suited.get(hi)!.push(lo);
    } else {
      const hi = hand[0];
      const lo = hand[1];
      if (!offsuit.has(hi)) offsuit.set(hi, []);
      offsuit.get(hi)!.push(lo);
    }
  }

  const parts: string[] = [];

  // Pairs - try to find consecutive ranges
  if (pairs.length > 0) {
    parts.push(...compressConsecutive(pairs, (p) => RANKS.indexOf(p[0])));
  }

  // Suited
  for (const [hi, lows] of suited) {
    const sorted = lows.sort((a, b) => RANKS.indexOf(a) - RANKS.indexOf(b));
    const compressed = compressSuitedRange(hi, sorted, 's');
    parts.push(...compressed);
  }

  // Offsuit
  for (const [hi, lows] of offsuit) {
    const sorted = lows.sort((a, b) => RANKS.indexOf(a) - RANKS.indexOf(b));
    const compressed = compressSuitedRange(hi, sorted, 'o');
    parts.push(...compressed);
  }

  return parts.join(',');
}

/**
 * Count total combos for a set of hands.
 * Pairs: 6 combos, Suited: 4 combos, Offsuit: 12 combos
 */
export function countCombos(hands: Set<string>): number {
  let count = 0;
  for (const hand of hands) {
    if (hand.length === 2)
      count += 6; // pair
    else if (hand.endsWith('s'))
      count += 4; // suited
    else count += 12; // offsuit
  }
  return count;
}

function expandRange(start: string, end: string, hands: Set<string>) {
  // Same type ranges: "AQs-A2s" or "TT-66"
  if (start.length === 2 && end.length === 2) {
    // Pair range
    const startIdx = RANKS.indexOf(start[0]);
    const endIdx = RANKS.indexOf(end[0]);
    const lo = Math.min(startIdx, endIdx);
    const hi = Math.max(startIdx, endIdx);
    for (let i = lo; i <= hi; i++) {
      hands.add(`${RANKS[i]}${RANKS[i]}`);
    }
  } else if (start.length === 3 && end.length === 3) {
    const suffix = start[2]; // 's' or 'o'
    if (start[0] === end[0]) {
      // Same high card: "AQs-A2s"
      const hi = start[0];
      const startIdx = RANKS.indexOf(start[1]);
      const endIdx = RANKS.indexOf(end[1]);
      const lo = Math.min(startIdx, endIdx);
      const top = Math.max(startIdx, endIdx);
      for (let i = lo; i <= top; i++) {
        if (RANKS[i] !== hi) {
          hands.add(`${hi}${RANKS[i]}${suffix}`);
        }
      }
    }
  }
}

function expandPlus(hand: string, hands: Set<string>) {
  if (hand.length === 2) {
    // Pair+: "TT+" means TT, JJ, QQ, KK, AA
    const idx = RANKS.indexOf(hand[0]);
    for (let i = 0; i <= idx; i++) {
      hands.add(`${RANKS[i]}${RANKS[i]}`);
    }
  } else if (hand.length === 3) {
    // Suited/offsuit+: "ATs+" means ATs, AJs, AQs, AKs
    const hi = hand[0];
    const lo = hand[1];
    const suffix = hand[2];
    const hiIdx = RANKS.indexOf(hi);
    const loIdx = RANKS.indexOf(lo);
    for (let i = hiIdx + 1; i <= loIdx; i++) {
      hands.add(`${hi}${RANKS[i]}${suffix}`);
    }
  }
}

function compressConsecutive(items: string[], getIndex: (item: string) => number): string[] {
  if (items.length === 0) return [];

  const sorted = [...items].sort((a, b) => getIndex(a) - getIndex(b));
  const result: string[] = [];
  let rangeStart = 0;

  for (let i = 1; i <= sorted.length; i++) {
    if (i === sorted.length || getIndex(sorted[i]) !== getIndex(sorted[i - 1]) + 1) {
      if (i - rangeStart >= 3) {
        result.push(`${sorted[rangeStart]}-${sorted[i - 1]}`);
      } else {
        for (let j = rangeStart; j < i; j++) {
          result.push(sorted[j]);
        }
      }
      rangeStart = i;
    }
  }

  return result;
}

function compressSuitedRange(hi: string, lows: string[], suffix: string): string[] {
  if (lows.length === 0) return [];

  const result: string[] = [];
  let rangeStart = 0;

  for (let i = 1; i <= lows.length; i++) {
    const prevIdx = RANKS.indexOf(lows[i - 1]);
    const currIdx = i < lows.length ? RANKS.indexOf(lows[i]) : -1;

    if (i === lows.length || currIdx !== prevIdx + 1) {
      if (i - rangeStart >= 3) {
        result.push(`${hi}${lows[rangeStart]}${suffix}-${hi}${lows[i - 1]}${suffix}`);
      } else {
        for (let j = rangeStart; j < i; j++) {
          result.push(`${hi}${lows[j]}${suffix}`);
        }
      }
      rangeStart = i;
    }
  }

  return result;
}
