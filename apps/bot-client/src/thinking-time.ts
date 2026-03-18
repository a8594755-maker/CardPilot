// ===== Context-dependent thinking time =====
// Replaces flat delay with situational timing for human-like behavior

import type { BoardTexture } from './board-integration.js';
import type { RaiseContext } from './raise-context.js';

export interface ThinkingTimeInput {
  street: string;
  pot: number;
  bigBlind: number;
  toCall: number;
  handStrength: number | null;
  boardTexture: BoardTexture | null;
  raiseContext: RaiseContext;
  numPlayersInHand: number;
  isAllInDecision: boolean;
  baseDelay: number; // from CLI args (default 800ms)
}

export interface ThinkingTimeResult {
  delayMs: number;
  twoStage: boolean;
  firstStageMs: number;
  secondStageMs: number;
}

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

export function computeThinkingTime(input: ThinkingTimeInput): ThinkingTimeResult {
  const base = input.baseDelay;

  // Complexity multiplier starts at 1.0
  let complexity = 1.0;

  // Street: later streets = more thinking
  if (input.street === 'TURN') complexity += 0.2;
  if (input.street === 'RIVER') complexity += 0.3;

  // Pot size relative to standard stack (~100bb)
  const potRatio = input.pot / (100 * input.bigBlind);
  if (potRatio > 2) complexity += 0.3;
  if (potRatio > 5) complexity += 0.3;

  // Multiway: each extra player adds complexity
  if (input.numPlayersInHand > 2) {
    complexity += 0.15 * (input.numPlayersInHand - 2);
  }

  // Facing raise or all-in
  if (input.raiseContext.facingType !== 'unopened') {
    complexity += 0.2;
  }
  if (input.isAllInDecision) {
    complexity += 0.5;
  }

  // Hand strength ambiguity: medium hands are harder decisions
  if (input.handStrength != null) {
    const ambiguity = 1 - Math.abs(input.handStrength - 0.5) * 2;
    complexity += ambiguity * 0.3;
  }

  // Wet board = more to consider
  if (input.boardTexture && input.boardTexture.wetness > 0.6) {
    complexity += 0.15;
  }

  // 3bet/4bet decisions are more complex
  if (input.raiseContext.facingType === 'facing_3bet') complexity += 0.2;
  if (input.raiseContext.facingType === 'facing_4bet_plus') complexity += 0.3;

  // Snap fold: very weak hand facing big raise
  if (
    input.handStrength != null &&
    input.handStrength < 0.15 &&
    input.toCall > 5 * input.bigBlind
  ) {
    if (Math.random() < 0.6) {
      const snapDelay = 200 + Math.floor(Math.random() * 300);
      return {
        delayMs: snapDelay,
        twoStage: false,
        firstStageMs: snapDelay,
        secondStageMs: 0,
      };
    }
  }

  // Snap check: can check with weak hand
  if (input.handStrength != null && input.handStrength < 0.2 && input.toCall === 0) {
    if (Math.random() < 0.4) {
      const snapDelay = 300 + Math.floor(Math.random() * 400);
      return {
        delayMs: snapDelay,
        twoStage: false,
        firstStageMs: snapDelay,
        secondStageMs: 0,
      };
    }
  }

  // Final delay calculation
  const jitter = Math.random() * base * 0.3;
  let delay = base * complexity + jitter;
  delay = clamp(delay, 300, 8000);

  // Two-stage pause for complex decisions
  const twoStage = complexity > 1.5 && Math.random() < 0.3;
  let firstStageMs = delay;
  let secondStageMs = 0;

  if (twoStage) {
    firstStageMs = Math.floor(delay * 0.3);
    secondStageMs = Math.floor(delay * 0.7);
  }

  return {
    delayMs: Math.floor(delay),
    twoStage,
    firstStageMs,
    secondStageMs,
  };
}
