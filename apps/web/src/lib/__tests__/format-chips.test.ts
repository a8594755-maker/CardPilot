import { describe, it, expect } from 'vitest';
import { formatChips, formatDelta } from '../format-chips.js';

describe('formatChips', () => {
  it('chips mode: formats with locale separators', () => {
    const opts = { mode: 'chips' as const, bbSize: 10 };
    expect(formatChips(0, opts)).toBe('0');
    expect(formatChips(1500, opts)).toBe('1,500');
    expect(formatChips(100, opts)).toBe('100');
  });

  it('bb mode: 1 decimal for <10 BB', () => {
    const opts = { mode: 'bb' as const, bbSize: 100 };
    expect(formatChips(0, opts)).toBe('0 BB');
    expect(formatChips(100, opts)).toBe('1.0 BB');
    expect(formatChips(250, opts)).toBe('2.5 BB');
    expect(formatChips(750, opts)).toBe('7.5 BB');
    expect(formatChips(950, opts)).toBe('9.5 BB');
  });

  it('bb mode: 0 decimals for ≥10 BB (unless .5)', () => {
    const opts = { mode: 'bb' as const, bbSize: 100 };
    expect(formatChips(1000, opts)).toBe('10 BB');
    expect(formatChips(2000, opts)).toBe('20 BB');
    expect(formatChips(1050, opts)).toBe('10.5 BB');
    expect(formatChips(5000, opts)).toBe('50 BB');
  });

  it('bb mode: handles fractional BB values', () => {
    const opts = { mode: 'bb' as const, bbSize: 3 };
    // 7.5 / 3 = 2.5 BB → <10 → 1 decimal
    expect(formatChips(7.5, opts)).toBe('2.5 BB');
  });

  it('bb mode: handles bbSize=0 gracefully (falls back to 1)', () => {
    const opts = { mode: 'bb' as const, bbSize: 0 };
    // 100 / 1 = 100 BB → ≥10 → 0 decimals
    expect(formatChips(100, opts)).toBe('100 BB');
    // Small value: 5 / 1 = 5 BB → <10 → 1 decimal
    expect(formatChips(5, opts)).toBe('5.0 BB');
  });
});

describe('formatDelta', () => {
  it('positive delta shows +', () => {
    const opts = { mode: 'chips' as const, bbSize: 10 };
    expect(formatDelta(500, opts)).toBe('+500');
  });

  it('negative delta shows −', () => {
    const opts = { mode: 'chips' as const, bbSize: 10 };
    expect(formatDelta(-500, opts)).toBe('−500');
  });

  it('zero delta shows no sign', () => {
    const opts = { mode: 'chips' as const, bbSize: 10 };
    expect(formatDelta(0, opts)).toBe('0');
  });

  it('bb mode delta', () => {
    const opts = { mode: 'bb' as const, bbSize: 100 };
    expect(formatDelta(250, opts)).toBe('+2.5 BB');
    expect(formatDelta(-1000, opts)).toBe('−10 BB');
  });
});
