import type { GtoPlusCombo } from './api-client';

/**
 * Export strategy data to CSV format.
 */
export function strategyToCSV(combos: GtoPlusCombo[], actions: string[]): string {
  const headers = [
    'Hand',
    'Equity',
    'Combos',
    ...actions.map((a) => `${a}_freq`),
    ...actions.map((a) => `${a}_ev`),
    'EV_Total',
  ];
  const rows = combos.map((c) => [
    c.hand,
    c.equity.toFixed(4),
    c.combos.toFixed(6),
    ...actions.map((a) => (c.frequencies[a] || 0).toFixed(6)),
    ...actions.map((a) => (c.evs[a] ?? 0).toFixed(6)),
    c.evTotal.toFixed(6),
  ]);

  return [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
}

/**
 * Export strategy data to readable text format.
 */
export function strategyToText(combos: GtoPlusCombo[], actions: string[]): string {
  const lines: string[] = [];
  lines.push(`Hands: ${combos.length}`);
  lines.push(`Actions: ${actions.join(', ')}`);
  lines.push('');

  const padHand = 6;
  const padNum = 8;

  // Header
  const header = [
    'Hand'.padEnd(padHand),
    'Equity'.padStart(padNum),
    'Combos'.padStart(padNum),
    ...actions.map((a) => a.padStart(padNum)),
    'EV'.padStart(padNum),
  ].join(' ');
  lines.push(header);
  lines.push('-'.repeat(header.length));

  for (const c of combos) {
    const row = [
      c.hand.padEnd(padHand),
      c.equity.toFixed(1).padStart(padNum),
      c.combos.toFixed(3).padStart(padNum),
      ...actions.map((a) => ((c.frequencies[a] || 0) * 100).toFixed(1).padStart(padNum)),
      c.evTotal.toFixed(3).padStart(padNum),
    ].join(' ');
    lines.push(row);
  }

  return lines.join('\n');
}

/**
 * Copy strategy grid to clipboard as a serialized JSON string.
 */
export async function copyStrategyToClipboard(
  grid: Record<string, Record<string, number>>,
  actions: string[],
): Promise<void> {
  const data = JSON.stringify({ grid, actions });
  await navigator.clipboard.writeText(data);
}

/**
 * Parse a strategy from clipboard text.
 */
export function parseStrategyFromClipboard(
  text: string,
): { grid: Record<string, Record<string, number>>; actions: string[] } | null {
  try {
    const data = JSON.parse(text);
    if (data.grid && data.actions) return data;
    return null;
  } catch {
    return null;
  }
}

/**
 * Download data as a file.
 */
export function downloadFile(content: string, filename: string, type = 'text/csv'): void {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
