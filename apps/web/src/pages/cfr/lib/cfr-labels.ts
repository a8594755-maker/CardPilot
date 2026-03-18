// Action label and character generation for CFR strategy viewer.
// Ported from packages/cfr-solver/viewer/index.html lines 578-653.

export type Street = 'F' | 'T' | 'R';

// Default bet sizes per street (overridden by meta.betSizes if available)
let betSizesConfig = {
  flop: [0.33, 0.75],
  turn: [0.5, 1.0],
  river: [0.75, 1.5],
};

export function setBetSizesConfig(sizes: {
  flop: number[];
  turn: number[];
  river: number[];
}): void {
  betSizesConfig = sizes;
}

function streetSizesArray(street: Street): number[] {
  if (street === 'F') return betSizesConfig.flop;
  if (street === 'T') return betSizesConfig.turn;
  return betSizesConfig.river;
}

function pctLabel(frac: number): string {
  return Math.round(frac * 100) + '%';
}

/** Detect if current node is facing a bet/raise (last char is digit 1-9 or A). */
export function isFacing(historyKey: string): boolean {
  const last = (historyKey || '').split('/').pop() || '';
  if (last.length === 0) return false;
  const ch = last[last.length - 1];
  return '123456789A'.includes(ch);
}

/** Get human-readable labels for all actions at a node. */
export function getActionLabels(
  historyKey: string,
  numActions: number,
  street: Street = 'F',
): string[] {
  const facing = isFacing(historyKey);
  const sizes = streetSizesArray(street);

  if (facing) {
    const labels = ['Fold', 'Call'];
    const hasAllin = numActions > 2;
    const raiseCount = hasAllin ? numActions - 3 : numActions - 2;
    for (let i = 0; i < raiseCount; i++) {
      labels.push(sizes[i] ? `Raise ${pctLabel(sizes[i])}` : `Raise ${i + 1}`);
    }
    if (hasAllin) labels.push('All-in');
    return labels;
  } else {
    const labels = ['Check'];
    const hasAllin = numActions > 1;
    const betCount = hasAllin ? numActions - 2 : numActions - 1;
    for (let i = 0; i < betCount; i++) {
      labels.push(sizes[i] ? `Bet ${pctLabel(sizes[i])}` : `Bet ${i + 1}`);
    }
    if (hasAllin && numActions > 1) labels.push('All-in');
    return labels;
  }
}

/** Get CFR history key characters for each action. */
export function getActionChars(historyKey: string, numActions: number): string[] {
  const facing = isFacing(historyKey);

  if (facing) {
    const chars = ['f', 'c'];
    const hasAllin = numActions > 2;
    const raiseCount = hasAllin ? numActions - 3 : numActions - 2;
    for (let i = 0; i < raiseCount; i++) chars.push(String(i + 1));
    if (hasAllin) chars.push('A');
    return chars;
  } else {
    const chars = ['x'];
    const hasAllin = numActions > 1;
    const betCount = hasAllin ? numActions - 2 : numActions - 1;
    for (let i = 0; i < betCount; i++) chars.push(String(i + 1));
    if (hasAllin && numActions > 1) chars.push('A');
    return chars;
  }
}

/** Convert history key character to full label for breadcrumb. */
export function actionCharToFullLabel(ch: string): string {
  const map: Record<string, string> = { f: 'Fold', x: 'Check', c: 'Call', A: 'All-in' };
  if (map[ch]) return map[ch];
  // Digit = bet/raise size index
  if (/[1-9]/.test(ch)) return `Bet/Raise #${ch}`;
  return ch;
}

export const STREET_LABELS: Record<Street, string> = { F: 'Flop', T: 'Turn', R: 'River' };
export const PLAYER_LABELS = ['OOP (BB)', 'IP (BTN)'];
