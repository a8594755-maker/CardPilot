import { useState, useCallback } from 'react';
import { useSolverConfig } from '../../stores/solver-config';

/**
 * Bet size code field supporting R/M/B notation:
 * - R: Ratio to pot (e.g. R33 = 33% pot, R75 = 75% pot)
 * - M: Multiplier raise (e.g. M2 = 2x raise, M3 = 3x raise)
 * - B: Fixed bet amount (e.g. B50 = bet 50 chips)
 *
 * Comma-separated per street. Streets separated by semicolons.
 * Example: "R33,R75,R150;R50,R100;R67,R150"
 */

function parseBetSizeCode(code: string): { flop: number[]; turn: number[]; river: number[] } {
  const streets = code.split(';').map((s) => s.trim());
  const parse = (str: string): number[] => {
    if (!str) return [];
    return str
      .split(',')
      .map((part) => {
        const trimmed = part.trim().toUpperCase();
        if (trimmed.startsWith('R')) {
          return parseFloat(trimmed.slice(1)) / 100;
        } else if (trimmed.startsWith('M')) {
          // Multiplier raise - convert to pot fraction approximation
          const mult = parseFloat(trimmed.slice(1));
          return mult; // stored as multiplier
        } else if (trimmed.startsWith('B')) {
          // Fixed bet - stored as negative (convention for absolute amounts)
          return -parseFloat(trimmed.slice(1));
        } else {
          // Bare number = percentage
          const num = parseFloat(trimmed);
          return isNaN(num) ? 0 : num / 100;
        }
      })
      .filter((n) => !isNaN(n) && n !== 0);
  };

  return {
    flop: parse(streets[0] || ''),
    turn: parse(streets[1] || streets[0] || ''),
    river: parse(streets[2] || streets[1] || streets[0] || ''),
  };
}

function betSizesToCode(sizes: { flop: number[]; turn: number[]; river: number[] }): string {
  const encode = (arr: number[]): string =>
    arr
      .map((v) => {
        if (v < 0) return `B${Math.abs(v)}`;
        if (v > 5) return `M${v}`;
        return `R${Math.round(v * 100)}`;
      })
      .join(',');

  const f = encode(sizes.flop);
  const t = encode(sizes.turn);
  const r = encode(sizes.river);

  if (f === t && t === r) return f;
  if (t === r) return `${f};${t}`;
  return `${f};${t};${r}`;
}

export function BetSizeCodeField() {
  const { betSizeCode, setBetSizeCode, setBetSizes, betSizes } = useSolverConfig();
  const [codeInput, setCodeInput] = useState(betSizeCode || betSizesToCode(betSizes));
  const [error, setError] = useState('');

  const applyCode = useCallback(() => {
    try {
      const parsed = parseBetSizeCode(codeInput);
      if (parsed.flop.length === 0 && parsed.turn.length === 0 && parsed.river.length === 0) {
        setError('No valid sizes parsed');
        return;
      }
      setBetSizeCode(codeInput);
      setBetSizes(parsed);
      setError('');
    } catch {
      setError('Invalid code format');
    }
  }, [codeInput, setBetSizeCode, setBetSizes]);

  return (
    <div className="space-y-2">
      <label className="text-xs text-muted-foreground block">
        Bet Size Code (R = % pot, M = multiplier, B = fixed)
      </label>
      <div className="flex gap-2">
        <input
          value={codeInput}
          onChange={(e) => setCodeInput(e.target.value)}
          placeholder="R33,R75,R150;R50,R100;R67"
          className="flex-1 px-3 py-1.5 bg-secondary border border-border rounded text-sm font-mono"
          onKeyDown={(e) => e.key === 'Enter' && applyCode()}
        />
        <button
          onClick={applyCode}
          className="px-3 py-1.5 text-xs bg-primary text-primary-foreground rounded hover:bg-primary/90"
        >
          Apply
        </button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <p className="text-[10px] text-muted-foreground">
        Separate streets with semicolons. E.g. "R33,R75;R50,R100;R67,R150"
      </p>
    </div>
  );
}
