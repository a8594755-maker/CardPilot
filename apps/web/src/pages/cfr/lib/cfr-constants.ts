// Card and hand class constants for the CFR strategy viewer.

export const RANKS = '23456789TJQKA';
export const RANK_ORDER = 'AKQJT98765432'; // descending for matrix display
export const SUITS = 'cdhs';
export const SUIT_SYMBOLS: Record<string, string> = {
  c: '\u2663',
  d: '\u2666',
  h: '\u2665',
  s: '\u2660',
};
export const SUIT_COLORS: Record<string, string> = {
  c: 'text-green-400',
  d: 'text-blue-400',
  h: 'text-red-400',
  s: 'text-slate-300',
};

// 13x13 hand class matrix: row=first rank, col=second rank
// Upper-right = suited, lower-left = offsuit, diagonal = pairs
export const ALL_HAND_CLASSES: string[] = [];
for (let r = 0; r < 13; r++) {
  for (let c = 0; c < 13; c++) {
    if (r === c) ALL_HAND_CLASSES.push(RANK_ORDER[r] + RANK_ORDER[c]);
    else if (c > r) ALL_HAND_CLASSES.push(RANK_ORDER[r] + RANK_ORDER[c] + 's');
    else ALL_HAND_CLASSES.push(RANK_ORDER[c] + RANK_ORDER[r] + 'o');
  }
}

export function cardLabel(index: number): string {
  const rank = Math.floor(index / 4);
  const suit = index % 4;
  return `${RANKS[rank]}${SUIT_SYMBOLS[SUITS[suit]]}`;
}

export function cardRankSuit(index: number): { rank: string; suit: string } {
  return { rank: RANKS[Math.floor(index / 4)], suit: SUITS[index % 4] };
}

export function cardColorClass(index: number): string {
  return SUIT_COLORS[SUITS[index % 4]] ?? 'text-white';
}
