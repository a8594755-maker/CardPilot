// Preflop solution data loader.
// Fetches static JSON from /data/preflop/solutions/<config>/<spot>.json
// Caches in memory for instant scenario switching.

export interface SpotSolution {
  spot: string;
  format: string;
  heroPosition: string;
  villainPosition?: string;
  scenario: string;
  potSize: number;
  actions: string[];
  grid: Record<string, Record<string, number>>;
  summary: {
    totalCombos: number;
    rangeSize: number;
    actionFrequencies: Record<string, number>;
  };
  metadata: {
    iterations: number;
    exploitability: number;
    solveDate: string;
    solver: string;
  };
}

export interface SolutionIndex {
  format: string;
  configs: string[];
  spots: Array<{
    file: string;
    spot: string;
    heroPosition: string;
    scenario: string;
  }>;
  solveDate: string;
}

export type ScenarioType = 'RFI' | 'facing_open' | 'facing_3bet' | 'facing_4bet';
export type Position = 'UTG' | 'HJ' | 'CO' | 'BTN' | 'SB' | 'BB';

export const POSITIONS: Position[] = ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB'];

export const SCENARIO_LABELS: Record<ScenarioType, string> = {
  RFI: 'Raise First In',
  facing_open: 'Facing Open',
  facing_3bet: 'Facing 3-Bet',
  facing_4bet: 'Facing 4-Bet',
};

// 13×13 hand grid layout
export const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'] as const;

export function handClassAt(row: number, col: number): string {
  const r1 = RANKS[row];
  const r2 = RANKS[col];
  if (row === col) return `${r1}${r2}`;       // pair
  if (row < col) return `${r1}${r2}s`;        // suited (above diagonal)
  return `${r2}${r1}o`;                        // offsuit (below diagonal)
}

export function handClassType(hc: string): 'pair' | 'suited' | 'offsuit' {
  if (hc.length === 2) return 'pair';
  return hc[2] === 's' ? 'suited' : 'offsuit';
}

// ── Cache ──

const indexCache = new Map<string, SolutionIndex>();
const spotCache = new Map<string, SpotSolution>();

function basePath(config: string): string {
  return `/data/preflop/solutions/${config}`;
}

export async function loadIndex(config: string): Promise<SolutionIndex> {
  const cached = indexCache.get(config);
  if (cached) return cached;

  const resp = await fetch(`${basePath(config)}/index.json`);
  if (!resp.ok) throw new Error(`Failed to load index for ${config}: ${resp.status}`);
  const data = await resp.json() as SolutionIndex;
  indexCache.set(config, data);
  return data;
}

export async function loadSpot(config: string, spotName: string): Promise<SpotSolution> {
  const key = `${config}/${spotName}`;
  const cached = spotCache.get(key);
  if (cached) return cached;

  const resp = await fetch(`${basePath(config)}/${spotName}.json`);
  if (!resp.ok) throw new Error(`Failed to load spot ${spotName}: ${resp.status}`);
  const data = await resp.json() as SpotSolution;
  spotCache.set(key, data);
  return data;
}

export function clearCache(): void {
  indexCache.clear();
  spotCache.clear();
}

// ── Helpers ──

export function getSpotsForPosition(index: SolutionIndex, pos: Position): SolutionIndex['spots'] {
  return index.spots.filter(s => s.heroPosition === pos);
}

export function getSpotsForScenario(index: SolutionIndex, scenario: ScenarioType): SolutionIndex['spots'] {
  return index.spots.filter(s => s.scenario === scenario);
}

export function getAvailableScenarios(index: SolutionIndex, pos: Position): ScenarioType[] {
  const scenarios = new Set<ScenarioType>();
  for (const spot of index.spots) {
    if (spot.heroPosition === pos) {
      scenarios.add(spot.scenario as ScenarioType);
    }
  }
  return Array.from(scenarios);
}

// Action color mapping
export const ACTION_COLORS: Record<string, string> = {
  fold: '#6b7280',     // gray
  check: '#6b7280',
  call: '#22c55e',     // green
  'open_2.5': '#ef4444', // red
  'open_2': '#ef4444',
  '3bet': '#f59e0b',   // amber
  '4bet': '#f97316',   // orange
  '5bet': '#ec4899',   // pink
  allin: '#ec4899',
};

export function getActionColor(action: string): string {
  if (action === 'fold') return ACTION_COLORS.fold;
  if (action === 'check') return ACTION_COLORS.check;
  if (action === 'call') return ACTION_COLORS.call;
  if (action.startsWith('open')) return ACTION_COLORS['open_2.5'];
  if (action.includes('3bet') || action.startsWith('3bet')) return ACTION_COLORS['3bet'];
  if (action.includes('4bet') || action.startsWith('4bet')) return ACTION_COLORS['4bet'];
  if (action.includes('5bet') || action.includes('allin')) return ACTION_COLORS.allin;
  // Default: raise-like = red
  return '#ef4444';
}

export function getActionLabel(action: string): string {
  if (action === 'fold') return 'Fold';
  if (action === 'check') return 'Check';
  if (action === 'call') return 'Call';
  if (action.startsWith('open')) return 'Open';
  if (action.includes('3bet')) return '3-Bet';
  if (action.includes('4bet')) return '4-Bet';
  if (action.includes('5bet') || action.includes('allin')) return 'All-In';
  return action;
}

// Blend action colors for a hand class cell
export function blendActionColors(freqs: Record<string, number>): string {
  let r = 0, g = 0, b = 0;
  for (const [action, freq] of Object.entries(freqs)) {
    if (freq <= 0) continue;
    const hex = getActionColor(action);
    const cr = parseInt(hex.slice(1, 3), 16);
    const cg = parseInt(hex.slice(3, 5), 16);
    const cb = parseInt(hex.slice(5, 7), 16);
    r += cr * freq;
    g += cg * freq;
    b += cb * freq;
  }
  return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`;
}

// Get the dominant (most frequent) action for a hand class
export function dominantAction(freqs: Record<string, number>): { action: string; freq: number } {
  let best = '';
  let bestFreq = -1;
  for (const [action, freq] of Object.entries(freqs)) {
    if (freq > bestFreq) {
      best = action;
      bestFreq = freq;
    }
  }
  return { action: best, freq: bestFreq };
}
