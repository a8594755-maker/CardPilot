// ===== Session statistics tracking for adaptive bot learning =====

export interface SessionStats {
  handsPlayed: number;
  handsWon: number;
  handsFolded: number;
  totalRaises: number;
  totalCalls: number;
  totalFolds: number;
  foldToRaiseCount: number;
  facingRaiseCount: number;
  showdownsReached: number;
  netChips: number;
  lastNResults: number[]; // last 20 hand results (+/-)
}

export function createSessionStats(): SessionStats {
  return {
    handsPlayed: 0,
    handsWon: 0,
    handsFolded: 0,
    totalRaises: 0,
    totalCalls: 0,
    totalFolds: 0,
    foldToRaiseCount: 0,
    facingRaiseCount: 0,
    showdownsReached: 0,
    netChips: 0,
    lastNResults: [],
  };
}

export function recordAction(
  stats: SessionStats,
  action: string,
  facingRaise: boolean,
): void {
  if (action === 'raise' || action === 'all_in') stats.totalRaises++;
  else if (action === 'call') stats.totalCalls++;
  else if (action === 'fold') {
    stats.totalFolds++;
    stats.handsFolded++;
    if (facingRaise) stats.foldToRaiseCount++;
  } else if (action === 'check') {
    stats.totalCalls++;
  }

  if (facingRaise) stats.facingRaiseCount++;
}

export function recordHandResult(stats: SessionStats, net: number, won: boolean): void {
  stats.handsPlayed++;
  if (won) stats.handsWon++;
  stats.netChips += net;
  stats.lastNResults.push(net);
  if (stats.lastNResults.length > 20) stats.lastNResults.shift();
}

export interface AdaptiveAdjustments {
  raiseAdj: number;
  callAdj: number;
  foldAdj: number;
}

/**
 * Compute adjustment multipliers for action weights.
 * Each value in [0.85, 1.15] — small nudges, not dramatic shifts.
 */
export function computeAdaptiveAdjustments(stats: SessionStats): AdaptiveAdjustments {
  if (stats.handsPlayed < 10) {
    return { raiseAdj: 1.0, callAdj: 1.0, foldAdj: 1.0 };
  }

  let raiseAdj = 1.0;
  let callAdj = 1.0;
  let foldAdj = 1.0;

  // If folding to raises too much (>60%), reduce fold weight, increase call/raise
  const foldToRaiseRate = stats.facingRaiseCount > 0
    ? stats.foldToRaiseCount / stats.facingRaiseCount
    : 0;

  if (foldToRaiseRate > 0.60) {
    foldAdj -= 0.08;
    callAdj += 0.05;
    raiseAdj += 0.03;
  } else if (foldToRaiseRate < 0.30) {
    foldAdj += 0.04;
    callAdj -= 0.02;
  }

  // If on a losing streak (last 5 hands all negative), tighten up
  const recentResults = stats.lastNResults.slice(-5);
  if (recentResults.length >= 5 && recentResults.every(r => r < 0)) {
    foldAdj += 0.05;
    raiseAdj -= 0.03;
  }

  // If winning a lot, become slightly more aggressive
  const winRate = stats.handsWon / stats.handsPlayed;
  if (winRate > 0.35 && stats.handsPlayed > 20) {
    raiseAdj += 0.04;
  }

  const clamp = (v: number) => Math.max(0.85, Math.min(1.15, v));
  return {
    raiseAdj: clamp(raiseAdj),
    callAdj: clamp(callAdj),
    foldAdj: clamp(foldAdj),
  };
}
