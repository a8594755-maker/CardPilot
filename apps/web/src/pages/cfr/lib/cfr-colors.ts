// Action color mapping and blending for CFR strategy viewer.
// Ported from packages/cfr-solver/viewer/index.html lines 656-686, 1303-1333.

// Pre-computed lookup tables — replaces per-call regex tests
function extractKey(label: string): string {
  const first = label.split(/[\s(]/)[0].toLowerCase();
  return first === 'all-in' || first === 'all' ? 'allin' : first;
}

const COLOR_MAP: Record<string, string> = {
  fold: 'var(--cp-fold-color, #64748b)',
  check: 'var(--cp-check-color, #22c55e)',
  call: 'var(--cp-call-color, #38bdf8)',
  allin: 'var(--cp-allin-color, #f97316)',
  bet: 'var(--cp-bet-0-color, #fbbf24)',
  raise: 'var(--cp-raise-0-color, #e879f9)',
};

const BTN_CLASS_MAP: Record<string, string> = {
  fold: 'border-slate-500 text-slate-400',
  check: 'border-emerald-500 text-emerald-400',
  call: 'border-sky-400 text-sky-400',
  allin: 'border-orange-500 text-orange-400',
  bet: 'border-amber-500 text-amber-400',
  raise: 'border-fuchsia-400 text-fuchsia-400',
};

const BG_CLASS_MAP: Record<string, string> = {
  fold: 'bg-slate-500',
  check: 'bg-emerald-500',
  call: 'bg-emerald-500',
  allin: 'bg-orange-500',
  bet: 'bg-amber-500',
  raise: 'bg-fuchsia-400',
};

/** Get CSS color for an action label. */
export function getActionColor(label: string): string {
  return COLOR_MAP[extractKey(label)] ?? '#888';
}

/** Get Tailwind class for action button border. */
export function getActionBtnClass(label: string): string {
  return BTN_CLASS_MAP[extractKey(label)] ?? 'border-slate-600 text-slate-400';
}

/** Get Tailwind background class for action. */
export function getActionBgClass(label: string): string {
  return BG_CLASS_MAP[extractKey(label)] ?? 'bg-slate-600';
}

// RGB values for action blending
const ACTION_RGB: Record<string, [number, number, number]> = {
  fold: [100, 116, 139],
  check: [34, 197, 94],
  call: [56, 189, 248],
  bet: [251, 191, 36],
  raise: [232, 121, 249],
  allin: [239, 68, 68],
};

const AGG_KEYS = new Set(['bet', 'raise', 'allin']);

/** Blend action colors into a single background color (GTO Wizard style). */
export function blendActionColors(probs: number[], labels: string[]): string {
  let r = 0, g = 0, b = 0;
  for (let i = 0; i < probs.length; i++) {
    const rgb = ACTION_RGB[extractKey(labels[i])] || [128, 128, 128];
    r += rgb[0] * probs[i];
    g += rgb[1] * probs[i];
    b += rgb[2] * probs[i];
  }
  return `rgb(${Math.round(r)},${Math.round(g)},${Math.round(b)})`;
}

/** Compute aggression frequency (bet + raise + allin). */
export function computeAggression(probs: number[], labels: string[]): number {
  let agg = 0;
  for (let i = 0; i < probs.length; i++) {
    if (AGG_KEYS.has(extractKey(labels[i]))) agg += probs[i];
  }
  return agg;
}
