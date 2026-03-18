// Context-aware bet sizing presets for CardPilot

export type BetPreset = { label: string; pctOfPot: number };

export type BoardTexture = 'dry' | 'wet' | 'neutral';

export type Street = 'PREFLOP' | 'FLOP' | 'TURN' | 'RIVER' | 'SHOWDOWN';

/**
 * Compute Stack-to-Pot Ratio
 */
export function computeSPR(stack: number, pot: number): number {
  if (pot <= 0) return Infinity;
  return stack / pot;
}

/**
 * Analyze board texture from community cards.
 * Cards are 2-char strings like "Ah", "Ks", "Td".
 */
export function analyzeBoard(board: string[]): BoardTexture {
  if (board.length < 3) return 'neutral';

  const suits = board.map((c) => c[1]);
  const ranks = board.map((c) => rankToNum(c[0]));

  // Flush draw: 2+ of same suit
  const suitCounts = new Map<string, number>();
  for (const s of suits) suitCounts.set(s, (suitCounts.get(s) ?? 0) + 1);
  const maxSuitCount = Math.max(...suitCounts.values());
  const hasFlushDraw = maxSuitCount >= 2;
  const hasFlush = maxSuitCount >= 3;

  // Straight draw: check connectedness
  const sorted = [...new Set(ranks)].sort((a, b) => a - b);
  let maxConnected = 1;
  let current = 1;
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] - sorted[i - 1] <= 2) {
      current++;
      maxConnected = Math.max(maxConnected, current);
    } else {
      current = 1;
    }
  }
  const hasStraightDraw = maxConnected >= 3;

  if (hasFlush || (hasFlushDraw && hasStraightDraw)) return 'wet';
  if (!hasFlushDraw && !hasStraightDraw) return 'dry';
  return 'neutral';
}

/**
 * Get suggested bet sizing presets based on game context.
 */
export function getSuggestedPresets(params: {
  street: Street;
  pot: number;
  heroStack: number;
  board: string[];
  numPlayers: number;
}): BetPreset[] {
  const { street, pot, heroStack, board, numPlayers } = params;
  const spr = computeSPR(heroStack, pot);
  const texture = analyzeBoard(board);
  const multiway = numPlayers >= 3;

  // Low SPR: push toward all-in
  if (spr < 2 && street !== 'PREFLOP') {
    return [
      { label: '50%', pctOfPot: 50 },
      { label: 'Pot', pctOfPot: 100 },
      { label: 'All-In', pctOfPot: Math.round((heroStack / pot) * 100) },
    ];
  }

  if (street === 'FLOP') {
    if (multiway) {
      return [
        { label: '25%', pctOfPot: 25 },
        { label: '33%', pctOfPot: 33 },
        { label: '50%', pctOfPot: 50 },
      ];
    }
    if (texture === 'dry') {
      return [
        { label: '25%', pctOfPot: 25 },
        { label: '33%', pctOfPot: 33 },
        { label: '75%', pctOfPot: 75 },
      ];
    }
    if (texture === 'wet') {
      return [
        { label: '50%', pctOfPot: 50 },
        { label: '75%', pctOfPot: 75 },
        { label: 'Pot', pctOfPot: 100 },
      ];
    }
    return [
      { label: '33%', pctOfPot: 33 },
      { label: '66%', pctOfPot: 66 },
      { label: 'Pot', pctOfPot: 100 },
    ];
  }

  if (street === 'TURN') {
    if (multiway) {
      return [
        { label: '33%', pctOfPot: 33 },
        { label: '50%', pctOfPot: 50 },
        { label: '75%', pctOfPot: 75 },
      ];
    }
    if (texture === 'dry') {
      return [
        { label: '33%', pctOfPot: 33 },
        { label: '50%', pctOfPot: 50 },
        { label: '75%', pctOfPot: 75 },
      ];
    }
    return [
      { label: '50%', pctOfPot: 50 },
      { label: '75%', pctOfPot: 75 },
      { label: '125%', pctOfPot: 125 },
    ];
  }

  if (street === 'RIVER') {
    if (spr < 3) {
      return [
        { label: '50%', pctOfPot: 50 },
        { label: 'Pot', pctOfPot: 100 },
        { label: 'All-In', pctOfPot: Math.round((heroStack / pot) * 100) },
      ];
    }
    return [
      { label: '50%', pctOfPot: 50 },
      { label: '75%', pctOfPot: 75 },
      { label: 'Pot', pctOfPot: 100 },
    ];
  }

  // PREFLOP / SHOWDOWN fallback
  return [
    { label: '1/3', pctOfPot: 33 },
    { label: '1/2', pctOfPot: 50 },
    { label: 'Pot', pctOfPot: 100 },
  ];
}

/**
 * Convert user custom presets (% of pot) into BetPreset array
 */
export function userPresetsToButtons(presets: [number, number, number]): BetPreset[] {
  return presets.map((pct) => ({ label: `${pct}%`, pctOfPot: pct }));
}

function rankToNum(r: string): number {
  const map: Record<string, number> = {
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
  return map[r] ?? 0;
}
