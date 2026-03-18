const API_BASE = '/api/gto';

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${res.status}`);
  }
  return res.json();
}

// Tree configs
export function fetchTreeConfigs() {
  return fetchJson<
    Array<{
      name: string;
      label: string;
      stackLabel: string;
      iterations: number;
      buckets: number;
      numPlayers: number;
      startingPot: number;
      effectiveStack: number;
    }>
  >('/tree-configs');
}

export function fetchTreeConfig(name: string) {
  return fetchJson<{
    name: string;
    label: string;
    config: {
      startingPot: number;
      effectiveStack: number;
      betSizes: { flop: number[]; turn: number[]; river: number[] };
      raiseCapPerStreet: number;
      numPlayers?: number;
    };
  }>(`/tree-configs/${name}`);
}

// Preflop
export function fetchPreflopConfigs() {
  return fetchJson<{
    configs: string[];
    hasGtoWizardData: boolean;
    coverageByConfig: Record<string, 'exact' | 'solver'>;
  }>('/preflop/configs');
}

export function fetchPreflopSpots(config: string) {
  return fetchJson<{
    config: string;
    spots: Array<{
      spot: string;
      heroPosition: string;
      scenario: string;
      coverage: 'exact' | 'solver';
    }>;
  }>(`/preflop/spots/${config}`);
}

export function fetchPreflopRange(config: string, spot: string) {
  return fetchJson<{
    spot: string;
    format: string;
    coverage?: 'exact' | 'solver';
    heroPosition: string;
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
  }>(`/preflop/range/${config}/${encodeURIComponent(spot)}`);
}

// Strategy
export function fetchStrategyConfigs() {
  return fetchJson<{ configs: Array<{ name: string; flopCount: number }> }>('/strategy/configs');
}

export function fetchFlops(config: string) {
  return fetchJson<{
    config: string;
    count: number;
    flops: Array<{
      file: string;
      boardId: number;
      cards: string[];
      highCard: string;
      texture: string;
      pairing: string;
      connectivity: string;
    }>;
  }>(`/flops?config=${config}`);
}

export function fetchNearestFlop(cards: string, config?: string) {
  const params = new URLSearchParams({ cards });
  if (config) params.set('config', config);
  return fetchJson<{
    file: string;
    cards: string[];
    highCard: string;
    texture: string;
    pairing: string;
  }>(`/flops/nearest?${params}`);
}

export function fetchStrategyTree(config: string, flop: string, player?: string, history?: string) {
  const params = new URLSearchParams();
  if (player) params.set('player', player);
  if (history) params.set('history', history);
  const qs = params.toString() ? `?${params}` : '';
  return fetchJson<{
    config: string;
    flop: string;
    totalStrategies: number;
    filtered: number;
    strategies: Array<{ key: string; probs: number[] }>;
  }>(`/strategy/tree/${config}/${flop}${qs}`);
}

// Solver
export function startSolve(config: {
  configName: string;
  iterations: number;
  buckets: number;
  board: string[];
  oopRange: string[];
  ipRange: string[];
  treeConfig?: {
    startingPot: number;
    effectiveStack: number;
    betSizes: {
      flop: number[];
      turn: number[];
      river: number[];
      flopCbet?: number[];
      flopDonk?: number[];
      turnProbe?: number[];
      raiseMultipliers?: { flop?: number[]; turn?: number[]; river?: number[] };
    };
    raiseCapPerStreet: number;
    numPlayers?: number;
    rake?: { percentage: number; cap: number };
    smoothMode?: boolean;
    smoothGradation?: number;
    advancedConfig?: {
      oop: {
        noDonkBet: boolean;
        allInThresholdEnabled: boolean;
        allInThresholdPct: number;
        remainingBetAllIn: boolean;
        remainingBetPct: number;
      };
      ip: {
        noDonkBet: boolean;
        allInThresholdEnabled: boolean;
        allInThresholdPct: number;
        remainingBetAllIn: boolean;
        remainingBetPct: number;
      };
    };
    limitMode?: boolean;
    limitConfig?: {
      flopBet: number;
      flopCap: number;
      turnBet: number;
      turnCap: number;
      riverBet: number;
      riverCap: number;
    };
  };
}) {
  return fetchJson<{ jobId: string; status: string }>('/solve', {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

export function fetchSolveJob(jobId: string) {
  return fetchJson<{
    id: string;
    status: string;
    config: {
      configName: string;
      iterations: number;
      board?: string[];
      oopRange?: string[];
      ipRange?: string[];
    };
    progress: {
      completedFlops: number;
      totalFlops: number;
      currentIteration: number;
      totalIterations: number;
      exploitability: number;
      elapsed: number;
    };
  }>(`/solve/${jobId}`);
}

export function fetchSolveJobs() {
  return fetchJson<{
    jobs: Array<{ id: string; status: string; config: { configName: string }; createdAt: string }>;
  }>('/solve');
}

export function cancelSolve(jobId: string) {
  return fetchJson<{ cancelled: boolean }>(`/solve/${jobId}`, { method: 'DELETE' });
}

// Solver Grid (strategy browser integration)
export interface SolverGridResult {
  actions: string[];
  grid: Record<string, Record<string, number>>;
  context: GtoPlusContext;
  summary: GtoPlusSummary;
  player: number;
  history: string;
  childNodes: Array<{ action: string; history: string; player: number }>;
}

export function fetchSolverGrid(
  config: string,
  flop: string,
  player: number = 0,
  history: string = '',
) {
  const params = new URLSearchParams({ player: String(player), history });
  return fetchJson<SolverGridResult>(`/strategy/grid/${config}/${flop}?${params}`);
}

// GTO+ Import & Comparison
export interface GtoPlusSample {
  path: string;
  name: string;
}

export interface GtoPlusContext {
  pot: number;
  stack: number;
  toCall: number;
  odds: number;
  overallFreq: number;
}

export interface GtoPlusSummary {
  totalCombos: number;
  actionCombos: Record<string, number>;
  actionPercentages: Record<string, number>;
  overallEquity: number;
  overallEV: number;
}

export interface GtoPlusGridData {
  fileName: string;
  actions: string[];
  grid: Record<string, Record<string, number>>;
  context: GtoPlusContext;
  summary: GtoPlusSummary;
}

export interface GtoPlusCombo {
  hand: string;
  equity: number;
  combos: number;
  frequencies: Record<string, number>;
  evs: Record<string, number>;
  evTotal: number;
}

export interface StrategyComparison {
  accuracy: number;
  meanDeviation: number;
  maxDeviation: number;
  worstHand: string;
  perHand: Record<
    string,
    {
      handClass: string;
      gtoPlusFreqs: Record<string, number>;
      ezGtoFreqs: Record<string, number>;
      deviation: number;
    }
  >;
  perAction: Record<
    string,
    {
      meanDeviation: number;
      correlation: number;
    }
  >;
}

export function fetchGtoPlusSamples(dir?: string) {
  const params = dir ? `?dir=${encodeURIComponent(dir)}` : '';
  return fetchJson<{ directory: string; files: GtoPlusSample[] }>(`/gtoplus/samples${params}`);
}

export function fetchGtoPlusGrid(file: string) {
  return fetchJson<GtoPlusGridData>(`/gtoplus/grid?file=${encodeURIComponent(file)}`);
}

export function fetchGtoPlusCombos(file: string, hand?: string) {
  const params = new URLSearchParams({ file });
  if (hand) params.set('hand', hand);
  return fetchJson<{
    fileName: string;
    actions: string[];
    totalCombos: number;
    combos: GtoPlusCombo[];
  }>(`/gtoplus/combos?${params}`);
}

export interface GtoPlusFilePair {
  name: string;
  oopFile: string;
  ipFile: string;
}

export function fetchGtoPlusPaired(dir?: string) {
  const params = dir ? `?dir=${encodeURIComponent(dir)}` : '';
  return fetchJson<{ pairs: GtoPlusFilePair[]; unpaired: string[] }>(`/gtoplus/paired${params}`);
}

// Database API
export interface DatabaseSummary {
  id: string;
  name: string;
  flopCount: number;
  status: string;
  createdAt: string;
}

export interface DatabaseFull {
  id: string;
  name: string;
  createdAt: string;
  config: {
    treeConfigName: string;
    oopRange: string;
    ipRange: string;
    startingPot: number;
    effectiveStack: number;
    rake?: { percent: number; cap: number };
  };
  flops: DatabaseFlop[];
  status: 'idle' | 'solving' | 'complete';
}

export interface DatabaseFlop {
  id: string;
  cards: [string, string, string];
  weight: number;
  status: 'pending' | 'solving' | 'solved' | 'error' | 'ignored';
  solveProgress?: number;
  results?: {
    oopEquity: number;
    ipEquity: number;
    oopEV: number;
    ipEV: number;
    bettingFrequency: Record<string, number>;
    exploitability: number;
    iterations: number;
    solvedAt: string;
  };
}

export interface DatabaseReport {
  databaseId: string;
  databaseName: string;
  flopCount: number;
  solvedCount: number;
  averageOopEquity: number;
  averageIpEquity: number;
  averageOopEV: number;
  averageIpEV: number;
  averageBettingFreqs: Record<string, number>;
  perFlop: DatabaseFlop[];
}

export interface FlopSubsetInfo {
  name: string;
  description: string;
  count: number;
}

export function fetchDatabases() {
  return fetchJson<{ databases: DatabaseSummary[] }>('/database');
}

export function fetchDatabase(id: string) {
  return fetchJson<DatabaseFull>(`/database/${id}`);
}

export function createDatabase(name: string, config: DatabaseFull['config']) {
  return fetchJson<DatabaseFull>('/database', {
    method: 'POST',
    body: JSON.stringify({ name, config }),
  });
}

export function deleteDatabase(id: string) {
  return fetchJson<{ deleted: boolean }>(`/database/${id}`, { method: 'DELETE' });
}

export function addFlopsToDatabase(
  id: string,
  flops: Array<{ cards: [string, string, string]; weight?: number }>,
) {
  return fetchJson<DatabaseFull>(`/database/${id}/flops`, {
    method: 'POST',
    body: JSON.stringify({ flops }),
  });
}

export function addRandomFlopsToDatabase(id: string, count: number) {
  return fetchJson<DatabaseFull>(`/database/${id}/random-flops`, {
    method: 'POST',
    body: JSON.stringify({ count }),
  });
}

export function loadSubsetToDatabase(id: string, subsetName: string) {
  return fetchJson<DatabaseFull>(`/database/${id}/load-subset`, {
    method: 'POST',
    body: JSON.stringify({ subsetName }),
  });
}

export function toggleFlopIgnored(databaseId: string, flopId: string) {
  return fetchJson<DatabaseFull>(`/database/${databaseId}/flops/${flopId}/toggle-ignore`, {
    method: 'POST',
  });
}

export function deleteFlopFromDatabase(databaseId: string, flopId: string) {
  return fetchJson<DatabaseFull>(`/database/${databaseId}/flops/${flopId}`, {
    method: 'DELETE',
  });
}

export function fetchDatabaseReport(id: string) {
  return fetchJson<DatabaseReport>(`/database/${id}/report`);
}

export function fetchFlopSubsets() {
  return fetchJson<{ subsets: FlopSubsetInfo[] }>('/database/subsets');
}

export function solveDatabaseFlops(id: string) {
  return fetchJson<{ message: string; databaseId: string; pendingFlops: number }>(
    `/database/${id}/solve`,
    {
      method: 'POST',
    },
  );
}

export function compareWithGtoPlus(
  gtoPlusFile: string,
  ezGtoGrid: Record<string, Record<string, number>>,
  actions: string[],
) {
  return fetchJson<{
    fileName: string;
    context: GtoPlusContext;
    comparison: StrategyComparison;
  }>('/gtoplus/compare', {
    method: 'POST',
    body: JSON.stringify({ gtoPlusFile, ezGtoGrid, actions }),
  });
}

// ── Coaching API ──

export interface CoachingFeedback {
  gtoPolicy: Record<string, number>;
  qValues: Record<string, number>;
  deltaEV: number;
  severity: 'optimal' | 'minor' | 'moderate' | 'major' | 'blunder';
  bestAction: string;
  userActionEV: number;
  bestActionEV: number;
  potSize: number;
  interpolation?: { actions: Array<{ action: string; weight: number }> };
  interpolatedDeltaEV?: number;
  embedding?: number[];
}

export interface CoachingInferResult {
  policy: Record<string, number>;
  qValues: Record<string, number>;
  bestAction: string;
  bestActionEV: number;
  embedding: number[];
}

export interface HandReviewResult {
  decisions: Array<{
    street: string;
    history: string;
    userAction: string;
    feedback: CoachingFeedback;
  }>;
  handScore: number;
  totalEVLost: number;
}

export function inferCoaching(request: {
  holeCards: string[];
  boardCards?: string[];
  pot: number;
  stack: number;
  position: number | string;
  street?: number | string;
  facingBet?: number;
  actionHistory?: (number | string)[];
  legalMask?: number[];
}) {
  return fetchJson<CoachingInferResult>('/coaching/infer', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export function evaluateCoachingAction(request: {
  holeCards: string[];
  boardCards?: string[];
  pot: number;
  stack: number;
  position: number | string;
  street?: number | string;
  facingBet?: number;
  actionHistory?: (number | string)[];
  legalMask?: number[];
  userAction: string | number;
}) {
  return fetchJson<CoachingFeedback>('/coaching/realtime', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export function reviewCoachingHand(
  decisions: Array<{
    holeCards: string[];
    boardCards?: string[];
    pot: number;
    stack: number;
    position: number | string;
    street?: number | string;
    facingBet?: number;
    userAction: string | number;
  }>,
) {
  return fetchJson<HandReviewResult>('/coaching/realtime/hand', {
    method: 'POST',
    body: JSON.stringify({ decisions }),
  });
}

export function fetchCoachingModelStatus() {
  return fetchJson<{ loaded: boolean; provider?: string; modelPath?: string; error?: string }>(
    '/coaching/model/status',
  );
}

// Range vs Range
export interface RangeVsRangeResult {
  range1Equity: number;
  range2Equity: number;
  range1Combos: number;
  range2Combos: number;
  simulations: number;
  categories1: Array<{ category: string; count: number; percentage: number }>;
  categories2: Array<{ category: string; count: number; percentage: number }>;
  overlap: number;
  overlapHands: string[];
}

export function computeRangeVsRange(
  range1: string[],
  range2: string[],
  board?: string[],
  simulations?: number,
) {
  return fetchJson<RangeVsRangeResult>('/range-vs-range', {
    method: 'POST',
    body: JSON.stringify({ range1, range2, board, simulations }),
  });
}
