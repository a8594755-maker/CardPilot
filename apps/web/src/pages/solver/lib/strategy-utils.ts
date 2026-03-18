export function getActionColor(action: string): string {
  const lower = action.toLowerCase();
  if (lower === 'fold') return '#ef4444';
  if (lower === 'call') return '#22c55e';
  if (lower === 'check') return '#9ca3af';
  if (lower === 'allin' || lower === 'jam') return '#8b5cf6';
  if (lower.startsWith('raise') || lower.startsWith('3bet') || lower.startsWith('4bet'))
    return '#3b82f6';
  if (lower.startsWith('bet')) return '#f59e0b';
  return '#06b6d4';
}

const ACTION_LABELS_ZH: Record<string, string> = {
  fold: '\u68C4\u724C',
  call: '\u8DDF\u6CE8',
  check: '\u904E\u724C',
  allin: '\u5168\u4E0B',
  jam: '\u5168\u4E0B',
};

export function formatActionLabel(action: string, locale: 'zh' | 'en' = 'zh'): string {
  if (!action) return action;
  const lower = action.toLowerCase();

  if (locale === 'zh') {
    if (ACTION_LABELS_ZH[lower]) return ACTION_LABELS_ZH[lower];
    if (lower.startsWith('raise') || lower.startsWith('3bet') || lower.startsWith('4bet')) {
      const size = action.includes('_') ? action.split('_')[1] : '';
      return size ? `\u52A0\u6CE8 ${size}` : '\u52A0\u6CE8';
    }
    if (lower.startsWith('bet')) {
      const size = action.includes('_') ? action.split('_')[1] : '';
      return size ? `\u4E0B\u6CE8 ${size}` : '\u4E0B\u6CE8';
    }
  }

  if (action.includes('_')) {
    const [type, size] = action.split('_');
    if (size) return `${capitalize(type)} ${size}`;
  }
  return capitalize(action);
}

export function formatPercent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function bytesToReadable(value: number): string {
  if (value <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let current = value;
  let idx = 0;
  while (current >= 1024 && idx < units.length - 1) {
    current /= 1024;
    idx += 1;
  }
  const decimals = current >= 10 || idx === 0 ? 0 : 1;
  return `${current.toFixed(decimals)} ${units[idx]}`;
}

function capitalize(text: string): string {
  return text.length > 0 ? `${text[0].toUpperCase()}${text.slice(1)}` : text;
}
