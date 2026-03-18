/**
 * Centralized chip/BB formatting utility.
 *
 * Rules:
 * - BB mode: 1 decimal for <10 BB, 0 decimals for ≥10 BB (unless .5)
 * - Chips mode: locale-formatted integer
 * - Always uses tabular-number CSS class externally (cp-num)
 */

export type ChipDisplayMode = 'chips' | 'bb';

export interface FormatChipsOptions {
  mode: ChipDisplayMode;
  bbSize: number;
}

/**
 * Format a chip amount for display.
 *
 * @param amount  Raw chip value
 * @param opts    Display mode + big blind size
 * @returns       Formatted string, e.g. "7.5 BB" or "1,500"
 */
export function formatChips(amount: number, opts: FormatChipsOptions): string {
  if (opts.mode === 'bb') {
    const bb = opts.bbSize || 1;
    const bbValue = amount / bb;
    if (bbValue === 0) return '0 BB';
    // <10 BB: always 1 decimal
    if (Math.abs(bbValue) < 10) {
      return `${bbValue.toFixed(1)} BB`;
    }
    // ≥10 BB: 0 decimals unless fractional .5
    const hasHalf = Math.abs(bbValue % 1) >= 0.25 && Math.abs(bbValue % 1) <= 0.75;
    return `${hasHalf ? bbValue.toFixed(1) : Math.round(bbValue)} BB`;
  }
  return amount.toLocaleString();
}

/**
 * Format a signed delta (e.g. +150 or −7.5 BB).
 */
export function formatDelta(amount: number, opts: FormatChipsOptions): string {
  const abs = Math.abs(amount);
  const str = formatChips(abs, opts);
  if (amount > 0) return `+${str}`;
  if (amount < 0) return `−${str}`;
  return str;
}

/**
 * React hook helper: returns a stable formatter function.
 * Usage: const fmt = useChipFormatter(displayBB, bigBlind);
 */
export function makeChipFormatter(displayBB: boolean, bigBlind: number) {
  const opts: FormatChipsOptions = {
    mode: displayBB ? 'bb' : 'chips',
    bbSize: bigBlind || 1,
  };
  return (amount: number) => formatChips(amount, opts);
}
