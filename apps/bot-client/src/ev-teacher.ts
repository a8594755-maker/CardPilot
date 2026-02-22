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

// Training mode uses higher MC budget for accuracy
const TRAIN_MC_ITERATIONS = 1000;
const TRAIN_MC_TIME_LIMIT = 200; // ms

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

  // Get equity via Monte Carlo (higher budget for training accuracy)
  const mcResult = estimateEquity(
    holeCards,
    board,
    Math.max(numOpponents, 1),
    TRAIN_MC_ITERATIONS,
    TRAIN_MC_TIME_LIMIT,
  );
  const equity = mcResult.equity;

  // EV(fold) = 0 (baseline)
  const evFold = 0;

  // EV(call)
  const evCall = computeCallEv(equity, pot, callAmount);

  // Compute EV for each sizing bucket
  const bb = bigBlind || 1;
  const isPreflop = street.toUpperCase() === 'PREFLOP';
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
