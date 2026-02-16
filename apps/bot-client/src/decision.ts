import type {
  BotProfile,
  Mix,
  StrategyMix,
  LegalActions,
  TableState,
  PlayerActionType,
  RaiseSizingContext,
} from './types.js';

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

// ===== Fallback policy when no advice_payload =====
function fallbackMix(state: TableState, profile: BotProfile): Mix {
  const la = state.legalActions;
  if (!la) return { raise: 0, call: 0, fold: 1 };

  const toCall = la.callAmount;
  const bb = state.bigBlind || 1;

  // If can check → check-heavy
  if (la.canCheck) {
    // Aggressive personas may sprinkle in raises
    const raiseChance = la.canRaise ? (profile.actionWeights.raise > 1.2 ? 0.20 : 0.05) : 0;
    return { raise: raiseChance, call: 0, fold: 0 };
  }

  // Small call (≤ 3bb) → mostly call
  if (toCall <= 3 * bb) {
    const raiseChance = la.canRaise ? (profile.actionWeights.raise > 1.2 ? 0.15 : 0.05) : 0;
    return { raise: raiseChance, call: 0.80, fold: 0.20 - raiseChance };
  }

  // Large call → mostly fold
  const raiseChance = la.canRaise ? (profile.actionWeights.raise > 1.2 ? 0.10 : 0.02) : 0;
  return { raise: raiseChance, call: 0.25, fold: 0.75 - raiseChance };
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
    baseMix = fallbackMix(state, profile);
    source = 'fallback';
  }

  // Step 2: apply personality weights
  let m = applyWeights(baseMix, profile.actionWeights);
  m = normalize(m);

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

  const reasoning =
    `src=${source} base=(R:${baseMix.raise.toFixed(2)} C:${baseMix.call.toFixed(2)} F:${baseMix.fold.toFixed(2)}) ` +
    `weighted=(R:${m.raise.toFixed(2)} C:${m.call.toFixed(2)} F:${m.fold.toFixed(2)}) ` +
    `raw=${rawAction} → ${action}${amount != null ? ` amt=${amount}` : ''}`;

  return { action, amount, reasoning };
}
