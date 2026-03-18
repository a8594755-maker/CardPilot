/** Flop database - stores multiple trees (same config, different flops) */
export interface FlopDatabase {
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
  flops: FlopEntry[];
  status: 'idle' | 'solving' | 'complete';
}

/** Individual flop entry in a database */
export interface FlopEntry {
  id: string;
  cards: [string, string, string];
  weight: number; // for weighted subsets
  status: 'pending' | 'solving' | 'solved' | 'error' | 'ignored';
  solveProgress?: number;
  results?: FlopResults;
}

/** Results for a solved flop */
export interface FlopResults {
  oopEquity: number;
  ipEquity: number;
  oopEV: number;
  ipEV: number;
  bettingFrequency: Record<string, number>; // action -> frequency
  exploitability: number;
  iterations: number;
  solvedAt: string;
}

/** Aggregate report across all solved flops */
export interface AggregateReport {
  databaseId: string;
  databaseName: string;
  flopCount: number;
  solvedCount: number;
  averageOopEquity: number;
  averageIpEquity: number;
  averageOopEV: number;
  averageIpEV: number;
  averageBettingFreqs: Record<string, number>;
  perFlop: Array<FlopEntry & { results: FlopResults }>;
}

/** Flop texture classification */
export interface FlopTexture {
  paired: boolean;
  monotone: boolean;
  twoTone: boolean;
  rainbow: boolean;
  connected: boolean;
  disconnected: boolean;
  highCard: string;
  hasAce: boolean;
  hasBroadway: boolean;
}

/** Predefined flop subset */
export interface FlopSubset {
  name: string;
  description: string;
  count: number;
  flops: Array<{ cards: [string, string, string]; weight: number }>;
}

/** Database solve progress event */
export interface DatabaseSolveProgress {
  databaseId: string;
  completedFlops: number;
  totalFlops: number;
  currentFlop: string;
  overallProgress: number;
}
