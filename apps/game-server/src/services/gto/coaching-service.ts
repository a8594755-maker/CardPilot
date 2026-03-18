/**
 * Coaching Service
 *
 * Evaluates player decisions against GTO and provides ΔEV feedback.
 * Uses the coaching neural network (ONNX) for real-time inference.
 */

import type { CoachingOracle, CoachingInput, CoachingInference } from '@cardpilot/cfr-solver';

// ── Types ──

export type Severity = 'optimal' | 'minor' | 'moderate' | 'major' | 'blunder';

export interface CoachingFeedback {
  /** GTO action probabilities (action name → probability). */
  gtoPolicy: Record<string, number>;
  /** Per-action EV in BB. */
  qValues: Record<string, number>;
  /** EV difference: user action EV - best action EV (negative = mistake). */
  deltaEV: number;
  /** How bad the mistake is. */
  severity: Severity;
  /** Best action according to GTO. */
  bestAction: string;
  /** User's action EV in BB. */
  userActionEV: number;
  /** Best action EV in BB. */
  bestActionEV: number;
  /** Pot size for context. */
  potSize: number;
}

export interface HandReview {
  /** One feedback entry per decision point in the hand. */
  decisions: Array<{
    street: string;
    history: string;
    userAction: string;
    feedback: CoachingFeedback;
  }>;
  /** Overall hand quality (average |ΔEV| as % of pot). */
  handScore: number;
  /** Total EV lost across all decisions (in BB). */
  totalEVLost: number;
}

// ── Action names ──

const ACTION_NAMES = [
  'fold',
  'check',
  'call',
  'bet_25',
  'bet_33',
  'bet_50',
  'bet_75',
  'bet_100',
  'bet_150',
  'raise_25',
  'raise_33',
  'raise_50',
  'raise_75',
  'raise_100',
  'raise_150',
  'allin',
];

// ── Severity classification ──

function classifySeverity(deltaEV: number, potSize: number): Severity {
  const pctPot = Math.abs(deltaEV) / Math.max(potSize, 0.01);
  if (pctPot < 0.01) return 'optimal';
  if (pctPot < 0.05) return 'minor';
  if (pctPot < 0.15) return 'moderate';
  if (pctPot < 0.3) return 'major';
  return 'blunder';
}

// ── Core evaluation ──

export function evaluateDecision(
  inference: CoachingInference,
  userActionIndex: number,
  legalMask: number[],
  potSize: number,
): CoachingFeedback {
  const policy = inference.policy;
  const qValues = inference.qValues;

  // Build named maps
  const gtoPolicy: Record<string, number> = {};
  const qValueMap: Record<string, number> = {};
  let bestActionIdx = -1;
  let bestActionEV = -Infinity;

  for (let i = 0; i < ACTION_NAMES.length; i++) {
    if (legalMask[i] > 0) {
      gtoPolicy[ACTION_NAMES[i]] = policy[i];
      // Q-values from model are normalized by /10, scale back to BB
      qValueMap[ACTION_NAMES[i]] = qValues[i] * 10;
      if (qValues[i] > bestActionEV) {
        bestActionEV = qValues[i];
        bestActionIdx = i;
      }
    }
  }

  const userActionEV = (legalMask[userActionIndex] > 0 ? qValues[userActionIndex] : 0) * 10;
  const bestEV = bestActionEV * 10;
  const deltaEV = userActionEV - bestEV;

  return {
    gtoPolicy,
    qValues: qValueMap,
    deltaEV,
    severity: classifySeverity(deltaEV, potSize),
    bestAction: bestActionIdx >= 0 ? ACTION_NAMES[bestActionIdx] : 'unknown',
    userActionEV,
    bestActionEV: bestEV,
    potSize,
  };
}

/**
 * Evaluate a single decision point.
 *
 * @param oracle - The coaching model
 * @param input - Game state features
 * @param userActionIndex - Index of the user's chosen action (0-15)
 * @returns Coaching feedback with ΔEV and severity
 */
export async function evaluateWithOracle(
  oracle: CoachingOracle,
  input: CoachingInput,
  userActionIndex: number,
): Promise<CoachingFeedback> {
  const inference = await oracle.infer(input);
  return evaluateDecision(inference, userActionIndex, input.legalMask, input.pot);
}

/**
 * Review a complete hand history.
 *
 * @param oracle - The coaching model
 * @param decisions - Array of (input, userAction) pairs for each decision in the hand
 * @returns Hand review with per-decision feedback and overall score
 */
export async function reviewHand(
  oracle: CoachingOracle,
  decisions: Array<{
    input: CoachingInput;
    userActionIndex: number;
    street: string;
    history: string;
    userAction: string;
  }>,
): Promise<HandReview> {
  const inputs = decisions.map((d) => d.input);
  const inferences = await oracle.inferBatch(inputs);

  const feedbacks = decisions.map((d, i) => ({
    street: d.street,
    history: d.history,
    userAction: d.userAction,
    feedback: evaluateDecision(inferences[i], d.userActionIndex, d.input.legalMask, d.input.pot),
  }));

  const totalEVLost = feedbacks.reduce(
    (sum, f) => sum + Math.abs(Math.min(0, f.feedback.deltaEV)),
    0,
  );
  const avgPctPot =
    feedbacks.length > 0
      ? feedbacks.reduce(
          (sum, f) => sum + Math.abs(f.feedback.deltaEV) / Math.max(f.feedback.potSize, 0.01),
          0,
        ) / feedbacks.length
      : 0;

  // Hand score: 100 = perfect, 0 = all blunders
  const handScore = Math.max(0, Math.min(100, 100 * (1 - avgPctPot)));

  return {
    decisions: feedbacks,
    handScore,
    totalEVLost,
  };
}
