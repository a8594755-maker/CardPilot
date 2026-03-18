/**
 * Drill Generator
 *
 * Creates practice scenarios targeting a player's identified leaks.
 * Generates quiz-style decision points from the coaching dataset,
 * focused on the spots where the player makes the most mistakes.
 */

import type { LeakCluster } from './leak-detector.js';

// ── Types ──

export interface DrillConfig {
  /** Which leaks to focus on (from leak detector). */
  focusLeaks: LeakCluster[];
  /** Difficulty level. */
  difficulty: 'easy' | 'medium' | 'hard';
  /** Stack depth to practice. */
  stackDepth: 30 | 60 | 100 | 200;
  /** Number of scenarios to generate. */
  count: number;
}

export interface DrillScenario {
  /** Unique scenario ID. */
  id: string;
  /** Board cards (display format, e.g. "Ks Th 2d"). */
  board: string;
  /** Hole cards (display format, e.g. "Ac Qh"). */
  holeCards: string;
  /** Player position. */
  position: string;
  /** Pot size in BB. */
  pot: number;
  /** Effective stack in BB. */
  stack: number;
  /** Action history (human-readable). */
  actionHistory: string;
  /** Legal actions available. */
  legalActions: string[];
  /** GTO action probabilities (hidden until answered). */
  gtoPolicy: Record<string, number>;
  /** Per-action EV (hidden until answered). */
  qValues: Record<string, number>;
  /** Which leak this drill targets. */
  leakId: number;
  /** Difficulty tag. */
  difficulty: string;
}

export interface DrillResult {
  scenario: DrillScenario;
  /** User's chosen action. */
  userAction: string;
  /** Was the user's action the GTO-preferred action? */
  isCorrect: boolean;
  /** ΔEV of user's choice vs best. */
  deltaEV: number;
  /** Explanation text. */
  explanation: string;
}

// ── Drill evaluation ──

/**
 * Evaluate a user's answer to a drill scenario.
 */
export function evaluateDrill(scenario: DrillScenario, userAction: string): DrillResult {
  const qValues = scenario.qValues;
  const bestAction = Object.entries(qValues).reduce(
    (best, [action, ev]) => (ev > best.ev ? { action, ev } : best),
    { action: '', ev: -Infinity },
  ).action;

  const userEV = qValues[userAction] ?? 0;
  const bestEV = qValues[bestAction] ?? 0;
  const deltaEV = userEV - bestEV;

  // Consider "correct" if user picked the GTO-dominant action
  // or if ΔEV is within 1% of pot
  const isCorrect = userAction === bestAction || Math.abs(deltaEV) < scenario.pot * 0.01;

  // Generate explanation
  const gtoProb = scenario.gtoPolicy[bestAction] ?? 0;
  let explanation: string;

  if (isCorrect) {
    explanation = `Correct! ${bestAction} is the GTO play here (${(gtoProb * 100).toFixed(0)}% frequency).`;
  } else {
    const userProb = scenario.gtoPolicy[userAction] ?? 0;
    if (userProb > 0.05) {
      explanation =
        `${userAction} is part of the GTO mix (${(userProb * 100).toFixed(0)}%), ` +
        `but ${bestAction} is preferred (${(gtoProb * 100).toFixed(0)}%). ` +
        `ΔEV = ${deltaEV.toFixed(2)} BB.`;
    } else {
      explanation =
        `${userAction} is not part of the GTO strategy here. ` +
        `The optimal play is ${bestAction} (${(gtoProb * 100).toFixed(0)}%). ` +
        `ΔEV = ${deltaEV.toFixed(2)} BB.`;
    }
  }

  return {
    scenario,
    userAction,
    isCorrect,
    deltaEV,
    explanation,
  };
}

/**
 * Generate drill scenarios from a coaching dataset.
 *
 * In production, this would query the coaching dataset for scenarios
 * near each leak cluster's centroid. For now, returns placeholder
 * scenarios that would be populated from the solved data.
 *
 * @param config - Drill configuration
 * @returns Array of drill scenarios
 */
export function generateDrills(config: DrillConfig): DrillScenario[] {
  // This is a scaffold — actual implementation would:
  // 1. Load coaching dataset for the specified stack depth
  // 2. For each focus leak, find training samples nearest the centroid
  // 3. Convert to DrillScenario format
  // 4. Filter by difficulty:
  //    - easy: spots where GTO is >80% one action
  //    - medium: mixed spots (40-60% for top action)
  //    - hard: spots where mistake is subtle (<5% pot ΔEV)

  const scenarios: DrillScenario[] = [];

  for (let i = 0; i < config.count; i++) {
    const leak = config.focusLeaks[i % config.focusLeaks.length];
    if (!leak) continue;

    scenarios.push({
      id: `drill_${Date.now()}_${i}`,
      board: leak.examples[0]?.boardCards ?? 'Ks Th 2d',
      holeCards: leak.examples[0]?.holeCards ?? 'Ac Qh',
      position: 'BTN',
      pot: 10,
      stack: config.stackDepth - 5,
      actionHistory: '',
      legalActions: ['check', 'bet_33', 'bet_50', 'bet_75'],
      gtoPolicy: { check: 0.4, bet_33: 0.3, bet_50: 0.2, bet_75: 0.1 },
      qValues: { check: 2.5, bet_33: 2.8, bet_50: 2.3, bet_75: 1.9 },
      leakId: leak.id,
      difficulty: config.difficulty,
    });
  }

  return scenarios;
}
