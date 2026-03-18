// ===== Discrete raise sizing engine =====
// Selects from multiple candidates based on context scoring

import type { BoardTexture } from './board-integration.js';
import type { RaiseContext } from './raise-context.js';
import type { BotPersona } from './persona.js';

export type PostflopSizeCategory = 'third_pot' | 'half_pot' | 'two_thirds_pot' | 'pot' | 'overbet';
export type PreflopSizeCategory =
  | 'min_open'
  | 'standard_open'
  | 'large_open'
  | '3bet_small'
  | '3bet_large'
  | '4bet';

export interface SizingDecision {
  amount: number;
  category: string;
  reasoning: string;
}

export interface SizingInput {
  street: 'preflop' | 'flop' | 'turn' | 'river';
  pot: number;
  toCall: number;
  bigBlind: number;
  minRaiseTo: number;
  maxRaiseTo: number;
  handStrength: number;
  boardTexture: BoardTexture | null;
  raiseContext: RaiseContext;
  persona: BotPersona | null;
}

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

// ===== Preflop sizing =====
function choosePreflopSizing(input: SizingInput): SizingDecision {
  const { bigBlind: bb, raiseContext, persona, minRaiseTo, maxRaiseTo } = input;
  const heroPos = raiseContext.heroPosition ?? '';
  const personaAdj = persona ? persona.passiveAggressiveBias * 0.3 : 0;

  let target: number;
  let category: string;

  if (raiseContext.facingType === 'unopened' || raiseContext.facingType === 'facing_limp') {
    // Open sizing: position-dependent
    if (['UTG', 'UTG+1', 'MP', 'MP+1', 'HJ'].includes(heroPos)) {
      target = (2.5 + personaAdj) * bb;
      category = 'standard_open';
    } else if (['CO', 'BTN'].includes(heroPos)) {
      target = (2.2 + personaAdj) * bb;
      category = 'min_open';
    } else {
      // SB or BB (squeeze)
      target = (2.5 + personaAdj) * bb;
      category = 'standard_open';
    }

    // Add extra per limper
    if (raiseContext.facingType === 'facing_limp') {
      target += raiseContext.numCallers * bb;
      category = 'large_open';
    }
  } else if (raiseContext.facingType === 'facing_open') {
    // 3-bet sizing
    const openSize = raiseContext.raiseSize * bb;
    // IP: 3x the open, OOP: 3.5x the open
    const isIP = ['CO', 'BTN'].includes(heroPos);
    const multiplier = isIP ? 3.0 : 3.5;
    target = openSize * multiplier + personaAdj * bb;
    category = isIP ? '3bet_small' : '3bet_large';
  } else if (raiseContext.facingType === 'facing_3bet') {
    // 4-bet sizing: ~2.2-2.5x the 3bet
    const threeBetSize = raiseContext.raiseSize * bb;
    target = threeBetSize * (2.3 + personaAdj * 0.3);
    category = '4bet';
  } else {
    // facing 4bet+: just jam or make a standard raise
    target = raiseContext.raiseSize * bb * 2.2;
    category = '4bet';
  }

  const amount = clamp(Math.round(target), minRaiseTo, maxRaiseTo);
  return { amount, category, reasoning: `preflop ${category}` };
}

// ===== Postflop sizing =====
function choosePostflopSizing(input: SizingInput): SizingDecision {
  const { pot, toCall, handStrength, boardTexture, street, persona, minRaiseTo, maxRaiseTo } =
    input;

  // Candidate sizes
  const candidates: { category: PostflopSizeCategory; size: number; score: number }[] = [
    { category: 'third_pot', size: pot * 0.33, score: 0 },
    { category: 'half_pot', size: pot * 0.5, score: 0 },
    { category: 'two_thirds_pot', size: pot * 0.66, score: 0 },
    { category: 'pot', size: pot * 1.0, score: 0 },
    { category: 'overbet', size: pot * 1.5, score: 0 },
  ];

  const wetness = boardTexture?.wetness ?? 0.5;
  const isDry = wetness < 0.25;
  const isWet = wetness > 0.5;
  const isVeryWet = wetness > 0.75;

  // Board texture scoring
  if (isDry) {
    candidates[0].score += 2; // third_pot: small c-bet on dry
    candidates[1].score += 1; // half_pot: okay too
  } else if (isVeryWet) {
    candidates[2].score += 2; // two_thirds: protect equity
    candidates[3].score += 1; // pot: strong protection
  } else if (isWet) {
    candidates[2].score += 2; // two_thirds: standard on wet
    candidates[1].score += 1; // half_pot
  } else {
    // semi-wet
    candidates[1].score += 2; // half_pot
    candidates[2].score += 1; // two_thirds
  }

  // Hand strength scoring
  if (handStrength >= 0.85) {
    // Monster: go big for value
    candidates[3].score += 2; // pot
    if (street === 'river') {
      candidates[4].score += 1; // overbet on river with nuts
    }
    candidates[2].score += 1; // two_thirds
  } else if (handStrength >= 0.65) {
    // Strong: value bet medium-large
    candidates[2].score += 2; // two_thirds
    candidates[1].score += 1; // half_pot
  } else if (handStrength >= 0.45) {
    // Medium: thinner value or protection
    candidates[1].score += 2; // half_pot
    candidates[0].score += 1; // third_pot
  } else if (handStrength >= 0.3) {
    // Draw / semi-bluff: cheap
    candidates[0].score += 2; // third_pot (cheap semi-bluff)
    candidates[1].score += 1; // half_pot
  } else {
    // Air / bluff: polarized sizing
    candidates[3].score += 1; // pot (big bluff)
    candidates[0].score += 1; // third_pot (cheap bluff)
  }

  // Street scoring: larger on later streets
  if (street === 'turn') {
    candidates[2].score += 0.5;
    candidates[3].score += 0.3;
  }
  if (street === 'river') {
    candidates[3].score += 0.5;
    candidates[2].score += 0.3;
  }

  // Persona influence
  if (persona) {
    if (persona.passiveAggressiveBias > 0.2) {
      // Aggressive persona: shift toward larger sizes
      candidates[3].score += 0.5;
      candidates[2].score += 0.3;
    } else if (persona.passiveAggressiveBias < -0.2) {
      // Passive persona: shift toward smaller sizes
      candidates[0].score += 0.5;
      candidates[1].score += 0.3;
    }
  }

  // Pick highest-scoring candidate
  candidates.sort((a, b) => b.score - a.score);
  const best = candidates[0];

  // Convert size to raise-to amount
  const raiseTo = toCall + best.size;
  const amount = clamp(Math.round(raiseTo), minRaiseTo, maxRaiseTo);

  return {
    amount,
    category: best.category,
    reasoning: `${street} ${best.category} (score=${best.score.toFixed(1)}, wet=${wetness.toFixed(2)})`,
  };
}

// ===== Main sizing entry point =====
export function chooseSizing(input: SizingInput): SizingDecision {
  if (input.street === 'preflop') {
    return choosePreflopSizing(input);
  }
  return choosePostflopSizing(input);
}
