// ===== Board texture integration adapter =====
// Wraps @cardpilot/poker-evaluator board texture analysis for bot decisions

import { analyzeBoardTexture, type BoardTexture } from '@cardpilot/poker-evaluator';
import type { HandAction } from './types.js';

export type { BoardTexture };

// ===== Get board texture (null if <3 cards) =====
export function getBoardTexture(board: string[]): BoardTexture | null {
  if (board.length < 3) return null;
  try {
    return analyzeBoardTexture(board);
  } catch {
    return null;
  }
}

export interface BoardTextureAdjustment {
  raiseAdj: number;
  callAdj: number;
  foldAdj: number;
  recommendedBetSize: 'small' | 'medium' | 'large' | 'overbet';
}

// ===== Compute mix adjustment based on board texture =====
export function computeBoardTextureAdjustment(
  texture: BoardTexture,
  isAggressor: boolean,
  handStrength: number,
  street: string,
): BoardTextureAdjustment {
  let raiseAdj = 1.0;
  let callAdj = 1.0;
  let foldAdj = 1.0;
  let recommendedBetSize: BoardTextureAdjustment['recommendedBetSize'] = 'medium';

  if (isAggressor) {
    // C-bet / continuation aggression adjustments
    switch (texture.category) {
      case 'dry':
        raiseAdj = 1.15; // c-bet more on dry boards
        recommendedBetSize = 'small'; // 1/3 pot
        break;
      case 'semi-wet':
        raiseAdj = 1.0;
        recommendedBetSize = 'medium'; // 2/3 pot
        break;
      case 'wet':
        raiseAdj = 0.85; // c-bet less on wet boards
        foldAdj = 0.90;  // when we check, don't fold easily
        recommendedBetSize = 'large'; // pot
        break;
      case 'very-wet':
        raiseAdj = 0.70; // check more
        foldAdj = 0.85;
        recommendedBetSize = 'large';
        break;
    }

    // Monotone boards: extra caution even as aggressor
    if (texture.isMonotone) {
      raiseAdj *= 0.85;
    }

    // Paired boards: slightly more aggression (fewer strong combos out there)
    if (texture.isPaired && !texture.isTrips) {
      raiseAdj *= 1.08;
    }

    // Strong hands on any texture: always bet
    if (handStrength >= 0.75) {
      raiseAdj = Math.max(raiseAdj, 1.10);
    }
  } else {
    // Defending against bets
    // On wet boards, we have more equity from draws → call/raise more
    if (texture.wetness > 0.5) {
      callAdj = 1.10;
      raiseAdj = 1.05;
    }

    // Dry boards as defender: aggressor likely has it → fold a bit more
    if (texture.category === 'dry' && handStrength < 0.45) {
      foldAdj = 1.08;
    }

    // Turn and river: tighten defense on scary boards
    if ((street === 'TURN' || street === 'RIVER') && texture.wetness > 0.6) {
      foldAdj = 1.05;
    }

    recommendedBetSize = texture.category === 'dry' ? 'small' : 'medium';
  }

  return { raiseAdj, callAdj, foldAdj, recommendedBetSize };
}

// ===== Simplified Minimum Defense Frequency =====
export function computeSimplifiedMDF(potSize: number, raiseSize: number): number {
  if (raiseSize <= 0) return 1.0;
  return 1 - raiseSize / (potSize + raiseSize);
}

// ===== Detect if bot was the aggressor on previous street =====
export function detectAggressor(
  actions: HandAction[],
  mySeat: number,
  currentStreet: string,
): boolean {
  // Map current street to the previous one
  const streetOrder = ['PREFLOP', 'FLOP', 'TURN', 'RIVER'];
  const currentIdx = streetOrder.indexOf(currentStreet);
  if (currentIdx <= 0) return false; // preflop: no previous street

  const prevStreet = streetOrder[currentIdx - 1];

  // Check if bot made the last aggressive action on the previous street
  const prevStreetActions = actions.filter(a => a.street === prevStreet);
  const lastAggressive = [...prevStreetActions]
    .reverse()
    .find(a => a.type === 'raise' || a.type === 'all_in');

  return lastAggressive?.seat === mySeat;
}
