/**
 * EV-aware teacher for V2 training pipeline.
 *
 * Computes approximate Expected Value for each action (fold/call/raise)
 * and for each raise sizing bucket, then converts to probability
 * distributions via softmax for use as training labels.
 *
 * This replaces the GTO advice engine mix as the teacher signal,
 * producing labels that incorporate pot odds, fold equity, and bet sizing.
 */

import { estimateEquity } from './monte-carlo.js';

// ── Sizing buckets (fractions of pot) ──

export const SIZING_BUCKETS = [0.33, 0.50, 0.66, 1.00] as const;
export const SIZING_BUCKET_NAMES = ['third', 'half', 'twoThirds', 'pot', 'allIn'] as const;
export const NUM_SIZING_BUCKETS = 5; // 4 pot fractions + all-in

// ── Configuration ──

const DEFAULT_ACTION_TEMP = parseFloat(process.env.EV_ACTION_TEMP ?? '0.5');
const DEFAULT_SIZING_TEMP = parseFloat(process.env.EV_SIZING_TEMP ?? '0.3');

// Training mode: low MC budget for speed — approximate equity is fine for labels
export type EvTeacherQualityProfile = 'high' | 'normal' | 'low';

const QUALITY_PRESETS: Record<EvTeacherQualityProfile, { iterations: number; timeLimitMs: number }> = {
  high: { iterations: 96, timeLimitMs: 12 },
  normal: { iterations: 64, timeLimitMs: 8 },
  low: { iterations: 32, timeLimitMs: 4 },
};

let currentQuality: EvTeacherQualityProfile =
  (process.env.EV_QUALITY_PROFILE as EvTeacherQualityProfile) || 'normal';
if (!(currentQuality in QUALITY_PRESETS)) currentQuality = 'normal';

let runtimeMcIterations = parseInt(
  process.env.EV_TRAIN_MC_ITERS ?? String(QUALITY_PRESETS[currentQuality].iterations),
  10,
);
let runtimeMcTimeLimitMs = parseInt(
  process.env.EV_TRAIN_MC_MS ?? String(QUALITY_PRESETS[currentQuality].timeLimitMs),
  10,
);

function sanitizeMcBudget(): void {
  runtimeMcIterations = Math.max(8, Math.min(400, runtimeMcIterations | 0));
  runtimeMcTimeLimitMs = Math.max(1, Math.min(100, runtimeMcTimeLimitMs | 0));
}
sanitizeMcBudget();

export function setEvTeacherQualityProfile(profile: EvTeacherQualityProfile): void {
  if (!QUALITY_PRESETS[profile]) return;
  currentQuality = profile;
  runtimeMcIterations = QUALITY_PRESETS[profile].iterations;
  runtimeMcTimeLimitMs = QUALITY_PRESETS[profile].timeLimitMs;
  sanitizeMcBudget();
}

export function setEvTeacherMcBudget(iterations: number, timeLimitMs: number): void {
  runtimeMcIterations = iterations;
  runtimeMcTimeLimitMs = timeLimitMs;
  sanitizeMcBudget();
}

export function getEvTeacherQualityState(): {
  profile: EvTeacherQualityProfile;
  iterations: number;
  timeLimitMs: number;
} {
  return {
    profile: currentQuality,
    iterations: runtimeMcIterations,
    timeLimitMs: runtimeMcTimeLimitMs,
  };
}

// ── Preflop equity lookup (avoids MC for ~50% of decisions) ──
// Key: canonical hand string (e.g., "AKs", "QTo", "77")
// Values: precomputed equity vs 1 random opponent (approximations from poker tables)

const PREFLOP_EQUITY: Record<string, number> = {};

// Build canonical hand key from two cards
function canonicalHand(c1: string, c2: string): string {
  const r1 = c1[0], r2 = c2[0], s1 = c1[1], s2 = c2[1];
  const ORDER = '23456789TJQKA';
  const i1 = ORDER.indexOf(r1), i2 = ORDER.indexOf(r2);
  const high = i1 >= i2 ? r1 : r2;
  const low = i1 >= i2 ? r2 : r1;
  if (r1 === r2) return `${high}${low}`;
  return s1 === s2 ? `${high}${low}s` : `${high}${low}o`;
}

// Precomputed equities vs 1 opponent (from standard poker equity tables)
// Pairs
const PAIR_EQ: Record<string, number> = {
  AA: 0.852, KK: 0.824, QQ: 0.799, JJ: 0.775, TT: 0.750,
  '99': 0.720, '88': 0.691, '77': 0.661, '66': 0.631, '55': 0.602,
  '44': 0.572, '33': 0.543, '22': 0.513,
};
// Suited hands (approx)
const SUITED_EQ: Record<string, number> = {
  AKs: 0.670, AQs: 0.660, AJs: 0.650, ATs: 0.640, A9s: 0.610, A8s: 0.600, A7s: 0.590, A6s: 0.580, A5s: 0.590, A4s: 0.580, A3s: 0.570, A2s: 0.560,
  KQs: 0.640, KJs: 0.630, KTs: 0.620, K9s: 0.590, K8s: 0.570, K7s: 0.560, K6s: 0.550, K5s: 0.540, K4s: 0.530, K3s: 0.520, K2s: 0.510,
  QJs: 0.610, QTs: 0.600, Q9s: 0.580, Q8s: 0.560, Q7s: 0.530, Q6s: 0.530, Q5s: 0.520, Q4s: 0.510, Q3s: 0.500, Q2s: 0.490,
  JTs: 0.580, J9s: 0.570, J8s: 0.550, J7s: 0.520, J6s: 0.500, J5s: 0.490, J4s: 0.480, J3s: 0.470, J2s: 0.460,
  T9s: 0.560, T8s: 0.540, T7s: 0.520, T6s: 0.490, T5s: 0.470, T4s: 0.460, T3s: 0.450, T2s: 0.440,
  '98s': 0.540, '97s': 0.510, '96s': 0.490, '95s': 0.470, '94s': 0.440, '93s': 0.430, '92s': 0.420,
  '87s': 0.520, '86s': 0.500, '85s': 0.470, '84s': 0.440, '83s': 0.420, '82s': 0.410,
  '76s': 0.500, '75s': 0.480, '74s': 0.450, '73s': 0.420, '72s': 0.400,
  '65s': 0.490, '64s': 0.460, '63s': 0.430, '62s': 0.410,
  '54s': 0.470, '53s': 0.440, '52s': 0.420,
  '43s': 0.440, '42s': 0.410,
  '32s': 0.420,
};
// Offsuit hands (approx, ~3-4% less than suited)
const OFFSUIT_EQ: Record<string, number> = {
  AKo: 0.650, AQo: 0.640, AJo: 0.630, ATo: 0.620, A9o: 0.580, A8o: 0.570, A7o: 0.560, A6o: 0.550, A5o: 0.560, A4o: 0.550, A3o: 0.540, A2o: 0.530,
  KQo: 0.620, KJo: 0.610, KTo: 0.600, K9o: 0.560, K8o: 0.540, K7o: 0.530, K6o: 0.520, K5o: 0.510, K4o: 0.500, K3o: 0.490, K2o: 0.480,
  QJo: 0.590, QTo: 0.580, Q9o: 0.550, Q8o: 0.530, Q7o: 0.500, Q6o: 0.490, Q5o: 0.480, Q4o: 0.470, Q3o: 0.460, Q2o: 0.450,
  JTo: 0.560, J9o: 0.540, J8o: 0.520, J7o: 0.490, J6o: 0.470, J5o: 0.450, J4o: 0.440, J3o: 0.430, J2o: 0.420,
  T9o: 0.530, T8o: 0.510, T7o: 0.490, T6o: 0.460, T5o: 0.430, T4o: 0.420, T3o: 0.410, T2o: 0.400,
  '98o': 0.510, '97o': 0.480, '96o': 0.460, '95o': 0.430, '94o': 0.410, '93o': 0.390, '92o': 0.380,
  '87o': 0.490, '86o': 0.460, '85o': 0.440, '84o': 0.410, '83o': 0.380, '82o': 0.370,
  '76o': 0.470, '75o': 0.440, '74o': 0.410, '73o': 0.390, '72o': 0.360,
  '65o': 0.460, '64o': 0.430, '63o': 0.400, '62o': 0.370,
  '54o': 0.440, '53o': 0.410, '52o': 0.380,
  '43o': 0.400, '42o': 0.380,
  '32o': 0.370,
};

// Merge all into lookup
Object.assign(PREFLOP_EQUITY, PAIR_EQ, SUITED_EQ, OFFSUIT_EQ);

/** Get preflop equity from lookup, or fallback to MC */
function getPreflopEquity(
  holeCards: [string, string],
  numOpponents: number,
): number {
  const key = canonicalHand(holeCards[0], holeCards[1]);
  const eq1v1 = PREFLOP_EQUITY[key];
  if (eq1v1 === undefined) return 0.5; // shouldn't happen

  // Approximate multi-way: eq_multiway ≈ eq^(0.8*N) for N opponents
  // (simplified — equity degrades against more opponents)
  if (numOpponents <= 1) return eq1v1;
  return Math.pow(eq1v1, 0.85 * numOpponents / 1);
}

// ── Types ──

export interface EvTeacherInput {
  holeCards: [string, string];
  board: string[];
  street: string;
  pot: number;
  callAmount: number;
  numOpponents: number;
  minRaise: number;
  maxRaise: number;
  bigBlind: number;
}

export interface EvTeacherOutput {
  actionMix: [number, number, number]; // [raise, call, fold]
  sizingMix: [number, number, number, number, number]; // [33%, 50%, 66%, 100%, allIn]
  equity: number;
  evs: { fold: number; call: number; raise: number };
}

// ── Fold equity estimation ──

/**
 * Estimate fold equity based on bet-size-to-pot ratio.
 * Larger bets generate more fold equity; multiple opponents reduce it.
 */
function estimateFoldEquity(betSize: number, pot: number, numOpponents: number): number {
  if (pot <= 0 || betSize <= 0) return 0;

  const betToPot = betSize / pot;
  let base: number;
  if (betToPot >= 2.0) base = 0.70;
  else if (betToPot >= 1.0) base = 0.55;
  else if (betToPot >= 0.66) base = 0.45;
  else if (betToPot >= 0.33) base = 0.35;
  else base = 0.20;

  // Each additional opponent reduces fold equity multiplicatively
  const foldEq = Math.pow(base, numOpponents);
  return Math.max(0, Math.min(0.90, foldEq));
}

// ── Softmax ──

function softmax(values: number[], temperature: number): number[] {
  const temp = Math.max(temperature, 0.01); // prevent division by zero
  const scaled = values.map(v => v / temp);
  const maxVal = Math.max(...scaled);
  const exps = scaled.map(v => Math.exp(v - maxVal));
  const sum = exps.reduce((a, b) => a + b, 0);
  return exps.map(e => e / sum);
}

// ── EV calculations ──

function computeCallEv(equity: number, pot: number, callAmount: number): number {
  if (callAmount <= 0) {
    // Can check: EV(check) = equity * pot (simplified; we continue to see cards)
    return equity * pot * 0.5; // discount since pot isn't won yet on non-river streets
  }
  // EV(call) = equity * pot - (1-equity) * callAmount
  return equity * pot - (1 - equity) * callAmount;
}

function computeRaiseEv(
  equity: number,
  pot: number,
  callAmount: number,
  raiseAmount: number,
  numOpponents: number,
): number {
  const betSize = raiseAmount - callAmount; // net new chips we're putting in beyond call
  const foldEq = estimateFoldEquity(betSize, pot, numOpponents);

  // EV(raise) = foldEq * pot + (1-foldEq) * [equity * (pot + raiseAmt + callAmt) - raiseAmt]
  const evWhenCalled = equity * (pot + raiseAmount + callAmount) - raiseAmount;
  return foldEq * pot + (1 - foldEq) * evWhenCalled;
}

// ── Main export ──

/**
 * Compute EV-based training labels for a given game state.
 * Returns softmax-converted probability distributions for both
 * action selection (fold/call/raise) and raise sizing (5 buckets).
 */
export function computeEvLabels(
  input: EvTeacherInput,
  actionTemp: number = DEFAULT_ACTION_TEMP,
  sizingTemp: number = DEFAULT_SIZING_TEMP,
): EvTeacherOutput {
  const { holeCards, board, street, pot, callAmount, numOpponents, minRaise, maxRaise, bigBlind } = input;

  // Preflop: use lookup table (zero CPU cost), postflop: use MC
  const isPreflop_ = street.toUpperCase() === 'PREFLOP';
  let equity: number;
  if (isPreflop_ && board.length === 0) {
    equity = getPreflopEquity(holeCards, Math.max(numOpponents, 1));
  } else {
    const mcResult = estimateEquity(
      holeCards,
      board,
      Math.max(numOpponents, 1),
      runtimeMcIterations,
      runtimeMcTimeLimitMs,
    );
    equity = mcResult.equity;
  }

  // EV(fold) = 0 (baseline)
  const evFold = 0;

  // EV(call)
  const evCall = computeCallEv(equity, pot, callAmount);

  // Compute EV for each sizing bucket
  const bb = bigBlind || 1;
  const isPreflop = isPreflop_;
  const sizingEvs: number[] = [];

  for (const frac of SIZING_BUCKETS) {
    let raiseAmt: number;
    if (isPreflop) {
      // Preflop: bucket fractions map to BB multiples (2.5bb, 3bb, 4bb, 5bb)
      const bbMult = frac <= 0.33 ? 2.5 : frac <= 0.50 ? 3.0 : frac <= 0.66 ? 4.0 : 5.0;
      raiseAmt = bbMult * bb;
    } else {
      // Postflop: fraction of pot
      raiseAmt = callAmount + pot * frac;
    }
    raiseAmt = Math.max(minRaise, Math.min(maxRaise, Math.round(raiseAmt)));
    sizingEvs.push(computeRaiseEv(equity, pot, callAmount, raiseAmt, numOpponents));
  }

  // All-in bucket
  const allInEv = computeRaiseEv(equity, pot, callAmount, maxRaise, numOpponents);
  sizingEvs.push(allInEv);

  // EV(raise) = best among sizing buckets
  const evRaise = Math.max(...sizingEvs);

  // Convert to probability distributions via softmax
  const actionProbs = softmax([evRaise, evCall, evFold], actionTemp);
  const sizingProbs = softmax(sizingEvs, sizingTemp);

  return {
    actionMix: [actionProbs[0], actionProbs[1], actionProbs[2]] as [number, number, number],
    sizingMix: [sizingProbs[0], sizingProbs[1], sizingProbs[2], sizingProbs[3], sizingProbs[4]] as [number, number, number, number, number],
    equity,
    evs: { fold: evFold, call: evCall, raise: evRaise },
  };
}
