import type {
  BotProfile,
  Mix,
  StrategyMix,
  LegalActions,
  TableState,
  PlayerActionType,
  RaiseSizingContext,
} from './types.js';
import type { AdaptiveAdjustments } from './session-stats.js';

// ===== Normalize mix so sum = 1 =====
function normalize(m: Mix): Mix {
  const sum = m.raise + m.call + m.fold;
  if (sum <= 0) return { raise: 0, call: 0, fold: 1 };
  return { raise: m.raise / sum, call: m.call / sum, fold: m.fold / sum };
}

// ===== Apply personality weights to base mix =====
function applyWeights(base: Mix, weights: Mix): Mix {
  return {
    raise: base.raise * weights.raise,
    call: base.call * weights.call,
    fold: base.fold * weights.fold,
  };
}

// ===== Apply preflop limp share =====
function applyLimpShare(m: Mix, limpShare: number): Mix {
  const shift = m.raise * limpShare;
  return {
    raise: m.raise - shift,
    call: m.call + shift,
    fold: m.fold,
  };
}

// ===== Sample action from mix =====
function sampleAction(m: Mix): 'raise' | 'call' | 'fold' {
  const r = Math.random();
  if (r < m.raise) return 'raise';
  if (r < m.raise + m.call) return 'call';
  return 'fold';
}

// ===== Pick highest probability action =====
function pickMaxAction(m: Mix): 'raise' | 'call' | 'fold' {
  if (m.raise >= m.call && m.raise >= m.fold) return 'raise';
  if (m.call >= m.fold) return 'call';
  return 'fold';
}

// ===== Resolve legality =====
function resolveWithLegality(
  action: 'raise' | 'call' | 'fold',
  legal: LegalActions,
): PlayerActionType {
  if (action === 'fold') {
    // Don't fold when checking is free
    if (legal.canCheck) return 'check';
    return 'fold';
  }
  if (action === 'call') {
    if (legal.canCall) return 'call';
    if (legal.canCheck) return 'check';
    return 'fold';
  }
  // action === 'raise'
  if (legal.canRaise) return 'raise';
  if (legal.canCall) return 'call';
  if (legal.canCheck) return 'check';
  return 'fold';
}

// ===== Detect if preflop is "unopened" =====
// Heuristic: toCall == 0 means no outstanding raise to face → treat as unopened
function isUnopened(state: TableState): boolean {
  if (state.street !== 'PREFLOP') return false;
  const la = state.legalActions;
  if (!la) return false;
  return la.callAmount === 0;
}

// ===== Map street string to lowercase =====
function mapStreet(s: string): 'preflop' | 'flop' | 'turn' | 'river' {
  const low = s.toLowerCase();
  if (low === 'preflop') return 'preflop';
  if (low === 'flop') return 'flop';
  if (low === 'turn') return 'turn';
  return 'river';
}

// ===== Quick hand strength evaluator (self-contained, no external deps) =====

const RANK_VALUES: Record<string, number> = {
  'A': 14, 'K': 13, 'Q': 12, 'J': 11, 'T': 10,
  '9': 9, '8': 8, '7': 7, '6': 6, '5': 5, '4': 4, '3': 3, '2': 2,
};

function rankValue(r: string): number {
  return RANK_VALUES[r] ?? 0;
}

/**
 * Quick hand strength score (0-1) for fallback decisions.
 * Preflop: rank-based heuristic.
 * Postflop: simplified made-hand classification.
 */
function quickHandStrength(
  holeCards: [string, string],
  board: string[],
  street: string,
): number {
  const r1 = rankValue(holeCards[0][0]);
  const r2 = rankValue(holeCards[1][0]);
  const suited = holeCards[0][1] === holeCards[1][1];
  const paired = holeCards[0][0] === holeCards[1][0];

  if (street === 'PREFLOP' || board.length === 0) {
    // Preflop heuristic
    let score = 0;
    if (paired) {
      // AA=1.0, KK=0.96, ..., 22=0.57
      score = 0.5 + (Math.max(r1, r2) / 14) * 0.5;
    } else {
      const high = Math.max(r1, r2);
      const low = Math.min(r1, r2);
      const gap = high - low;
      score = (high + low) / 28;
      if (suited) score += 0.06;
      if (gap <= 2) score += 0.04;
      if (gap >= 5) score -= 0.04;
    }
    return Math.max(0, Math.min(1, score));
  }

  // Postflop: check for made hands
  const boardRanks = board.map(c => c[0]);
  const boardSuits = board.map(c => c[1]);
  const heroR1 = holeCards[0][0];
  const heroR2 = holeCards[1][0];
  const heroS1 = holeCards[0][1];
  const heroS2 = holeCards[1][1];

  // Count hero rank matches on board
  const r1Matches = boardRanks.filter(r => r === heroR1).length;
  const r2Matches = boardRanks.filter(r => r === heroR2).length;

  // Set (pocket pair + one on board)
  if (paired && r1Matches >= 1) return 0.95;

  // Quads
  if (r1Matches >= 3 || r2Matches >= 3) return 0.98;

  // Trips (one hole card matches two board cards)
  if (r1Matches >= 2) return 0.88;
  if (r2Matches >= 2) return 0.88;

  // Two pair (both hole cards paired with board)
  if (r1Matches >= 1 && r2Matches >= 1) return 0.80;

  // Overpair (pocket pair higher than all board cards)
  if (paired) {
    const maxBoardRank = Math.max(...boardRanks.map(r => rankValue(r)));
    if (r1 > maxBoardRank) return 0.72;
    return 0.55; // underpair
  }

  // One pair with board
  if (r1Matches >= 1 || r2Matches >= 1) {
    const matchRank = r1Matches >= 1 ? heroR1 : heroR2;
    const sortedBoardRanks = [...boardRanks].sort((a, b) => rankValue(b) - rankValue(a));
    if (matchRank === sortedBoardRanks[0]) {
      // Top pair — kicker matters
      const kicker = r1Matches >= 1 ? heroR2 : heroR1;
      const kickerVal = rankValue(kicker);
      return 0.55 + (kickerVal / 14) * 0.15; // 0.55-0.70
    }
    if (sortedBoardRanks.length >= 2 && matchRank === sortedBoardRanks[1]) {
      return 0.45; // second pair
    }
    return 0.38; // bottom pair
  }

  // Flush draw check
  const s1BoardCount = boardSuits.filter(s => s === heroS1).length;
  const s2BoardCount = boardSuits.filter(s => s === heroS2).length;
  if (s1BoardCount >= 2 || s2BoardCount >= 2) {
    // Flush draw (4 to flush)
    if (suited && s1BoardCount >= 2) return 0.40;
    return 0.35;
  }

  // Straight draw (simplified: connected cards near board)
  const allRankValues = [r1, r2, ...boardRanks.map(r => rankValue(r))];
  const uniqueRanks = [...new Set(allRankValues)].sort((a, b) => a - b);
  let maxConsecutive = 1;
  let consecutive = 1;
  for (let i = 1; i < uniqueRanks.length; i++) {
    if (uniqueRanks[i] - uniqueRanks[i - 1] === 1) {
      consecutive++;
      maxConsecutive = Math.max(maxConsecutive, consecutive);
    } else {
      consecutive = 1;
    }
  }
  if (maxConsecutive >= 4) return 0.32; // open-ended straight draw
  if (maxConsecutive >= 3) return 0.25; // gutshot

  // High card
  const high = Math.max(r1, r2);
  return 0.08 + (high / 14) * 0.15;
}

// ===== Hand-strength-aware fallback policy =====
function fallbackMix(
  state: TableState,
  profile: BotProfile,
  holeCards: [string, string] | null,
): Mix {
  const la = state.legalActions;
  if (!la) return { raise: 0, call: 0, fold: 1 };

  const toCall = la.callAmount;
  const bb = state.bigBlind || 1;

  // If can check → check-heavy, with some raises for aggressive profiles
  if (la.canCheck) {
    const raiseChance = la.canRaise ? (profile.actionWeights.raise > 1.2 ? 0.20 : 0.05) : 0;
    return { raise: raiseChance, call: 0, fold: 0 };
  }

  // If we don't know our cards, use a slightly improved generic heuristic
  if (!holeCards) {
    if (toCall <= 3 * bb) {
      const raiseChance = la.canRaise ? 0.08 : 0;
      return { raise: raiseChance, call: 0.72, fold: 0.20 };
    }
    return { raise: 0.03, call: 0.30, fold: 0.67 };
  }

  // Hand-strength-aware fallback
  const strength = quickHandStrength(holeCards, state.board, state.street);
  const potOdds = toCall / (state.pot + toCall);

  // Monster hands (set+, two pair+): raise-heavy
  if (strength >= 0.75) {
    const raiseChance = la.canRaise ? 0.65 : 0;
    return { raise: raiseChance, call: 1 - raiseChance, fold: 0 };
  }

  // Strong hands (overpair, top pair good kicker): raise some, rarely fold
  if (strength >= 0.60) {
    const raiseChance = la.canRaise ? 0.35 : 0;
    return { raise: raiseChance, call: 0.55, fold: 0.10 };
  }

  // Decent hands (top pair, second pair): call-heavy, pot-odds-aware
  if (strength >= 0.45) {
    const raiseChance = la.canRaise ? 0.10 : 0;
    const foldChance = Math.max(0.05, potOdds * 0.8);
    return { raise: raiseChance, call: 1 - raiseChance - foldChance, fold: foldChance };
  }

  // Drawing hands (flush draw, OESD): call if pot odds favorable
  if (strength >= 0.30) {
    if (potOdds <= 0.35) {
      return { raise: 0.08, call: 0.57, fold: 0.35 };
    }
    return { raise: 0.03, call: 0.27, fold: 0.70 };
  }

  // Weak hands: fold more, but not as extreme as before
  if (toCall <= 2 * bb) {
    return { raise: 0.02, call: 0.35, fold: 0.63 };
  }
  return { raise: 0.01, call: 0.12, fold: 0.87 };
}

// ===== Main decision function =====
export interface DecisionResult {
  action: PlayerActionType;
  amount?: number;
  reasoning: string;
}

export function decide(
  state: TableState,
  profile: BotProfile,
  advice: StrategyMix | null,
  holeCards: [string, string] | null = null,
  adaptiveAdj?: AdaptiveAdjustments,
): DecisionResult {
  const la = state.legalActions;
  if (!la) {
    return { action: 'fold', reasoning: 'no legalActions available' };
  }

  // Step 1: base mix (from advice or fallback)
  let baseMix: Mix;
  let source: string;
  if (advice) {
    baseMix = { raise: advice.raise, call: advice.call, fold: advice.fold };
    source = 'advice';
  } else {
    baseMix = fallbackMix(state, profile, holeCards);
    source = holeCards ? 'fallback+hand' : 'fallback';
  }

  // Step 2: apply personality weights
  let m = applyWeights(baseMix, profile.actionWeights);
  m = normalize(m);

  // Step 2b: apply adaptive session adjustments
  if (adaptiveAdj) {
    m = {
      raise: m.raise * adaptiveAdj.raiseAdj,
      call: m.call * adaptiveAdj.callAdj,
      fold: m.fold * adaptiveAdj.foldAdj,
    };
    m = normalize(m);
  }

  // Step 3: preflop unopened limp share
  const limpShare = profile.unopenedLimpShare ?? 0;
  if (limpShare > 0 && isUnopened(state)) {
    m = applyLimpShare(m, limpShare);
    m = normalize(m);
  }

  // Step 4: choose action
  const rawAction = profile.stochastic ? sampleAction(m) : pickMaxAction(m);

  // Step 5: resolve legality
  const action = resolveWithLegality(rawAction, la);

  // Step 6: if raise, compute sizing
  let amount: number | undefined;
  if (action === 'raise' && la.canRaise) {
    const ctx: RaiseSizingContext = {
      street: mapStreet(state.street),
      bigBlind: state.bigBlind,
      pot: state.pot,
      toCall: la.callAmount,
      currentBet: state.currentBet,
      minRaiseTo: la.minRaise,
      maxRaiseTo: la.maxRaise,
    };
    const raiseTo = profile.chooseRaiseTo(ctx);
    amount = Math.max(la.minRaise, Math.min(la.maxRaise, Math.round(raiseTo)));
  }

  const strengthInfo = holeCards ? ` str=${quickHandStrength(holeCards, state.board, state.street).toFixed(2)}` : '';
  const reasoning =
    `src=${source}${strengthInfo} base=(R:${baseMix.raise.toFixed(2)} C:${baseMix.call.toFixed(2)} F:${baseMix.fold.toFixed(2)}) ` +
    `weighted=(R:${m.raise.toFixed(2)} C:${m.call.toFixed(2)} F:${m.fold.toFixed(2)}) ` +
    `raw=${rawAction} → ${action}${amount != null ? ` amt=${amount}` : ''}`;

  return { action, amount, reasoning };
}
