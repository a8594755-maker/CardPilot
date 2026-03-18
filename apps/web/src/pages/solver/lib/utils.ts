import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format a number as a percentage string */
export function pct(value: number, decimals = 0): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

/** Poker card rank names */
export const RANKS = '23456789TJQKA';
export const RANK_NAMES: Record<string, string> = {
  '2': '2',
  '3': '3',
  '4': '4',
  '5': '5',
  '6': '6',
  '7': '7',
  '8': '8',
  '9': '9',
  T: '10',
  J: 'J',
  Q: 'Q',
  K: 'K',
  A: 'A',
};

/** Suit symbols */
export const SUIT_SYMBOLS: Record<string, string> = {
  s: '\u2660', // spade
  h: '\u2665', // heart
  d: '\u2666', // diamond
  c: '\u2663', // club
};

export const SUIT_COLORS: Record<string, string> = {
  s: '#1a1a2e',
  h: '#e74c3c',
  d: '#3498db',
  c: '#27ae60',
};

/** Generate 13x13 hand matrix labels */
export function getHandMatrixLabels(): string[][] {
  const ranks = 'AKQJT98765432';
  const matrix: string[][] = [];

  for (let row = 0; row < 13; row++) {
    const rowLabels: string[] = [];
    for (let col = 0; col < 13; col++) {
      if (row === col) {
        rowLabels.push(`${ranks[row]}${ranks[col]}`); // Pair
      } else if (row < col) {
        rowLabels.push(`${ranks[row]}${ranks[col]}s`); // Suited (above diagonal)
      } else {
        rowLabels.push(`${ranks[col]}${ranks[row]}o`); // Offsuit (below diagonal)
      }
    }
    matrix.push(rowLabels);
  }

  return matrix;
}

/** Interpolate between colors based on action frequencies */
export function getActionColor(actions: Record<string, number>): string {
  const fold = actions.fold ?? 0;
  const call = actions.call ?? 0;
  const raise = Object.entries(actions)
    .filter(([k]) => k !== 'fold' && k !== 'call')
    .reduce((sum, [, v]) => sum + v, 0);

  // RGB interpolation
  const r = Math.round(fold * 239 + call * 34 + raise * 59);
  const g = Math.round(fold * 68 + call * 197 + raise * 130);
  const b = Math.round(fold * 68 + call * 94 + raise * 246);

  return `rgb(${r}, ${g}, ${b})`;
}

/** Get action type color */
export const ACTION_COLORS: Record<string, string> = {
  fold: '#ef4444',
  call: '#22c55e',
  check: '#a3a3a3',
  raise: '#3b82f6',
  bet: '#f59e0b',
  allin: '#8b5cf6',
};

export function getActionTypeColor(action: string): string {
  if (action.startsWith('raise') || action.startsWith('3bet') || action.startsWith('4bet')) {
    return ACTION_COLORS.raise;
  }
  if (action.startsWith('bet')) return ACTION_COLORS.bet;
  return ACTION_COLORS[action] ?? ACTION_COLORS.raise;
}
