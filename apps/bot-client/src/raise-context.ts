// ===== Raise context analysis =====
// Parses action history to extract raise type, position, sizing, multiway, SPR

import type { TableState } from './types.js';

export interface RaiseContext {
  raiserSeat: number | null;
  raiserPosition: string | null;
  raiseSize: number; // in big blinds
  raiseSizeCategory: 'min' | 'small' | 'standard' | 'large' | 'overbet' | 'allin';
  numCallers: number; // callers of the raise before us
  isMultiway: boolean; // numCallers >= 2
  effectiveStack: number; // min(our stack, raiser stack) in bb
  spr: number; // stack-to-pot ratio after calling
  is3bet: boolean;
  facingType: 'unopened' | 'facing_open' | 'facing_3bet' | 'facing_4bet_plus' | 'facing_limp';
  heroPosition: string | null;
}

function categorizeSizeBB(sizeBB: number, isAllin: boolean): RaiseContext['raiseSizeCategory'] {
  if (isAllin) return 'allin';
  if (sizeBB <= 2.1) return 'min';
  if (sizeBB <= 2.5) return 'small';
  if (sizeBB <= 3.5) return 'standard';
  if (sizeBB <= 5.0) return 'large';
  return 'overbet';
}

export function analyzeRaiseContext(state: TableState, mySeat: number): RaiseContext {
  const bb = state.bigBlind || 1;
  const currentStreet = state.street;

  // Filter actions for current street
  const streetActions = state.actions.filter((a) => a.street === currentStreet);

  // Count raises and identify raiser
  let raiseCount = 0;
  let lastRaiserSeat: number | null = null;
  let lastRaiseAmount = 0;
  let lastRaiseIsAllin = false;
  let limpCount = 0;
  let callersAfterLastRaise = 0;

  for (const a of streetActions) {
    if (a.seat === mySeat) continue; // skip our own actions

    if (a.type === 'raise' || a.type === 'all_in') {
      raiseCount++;
      lastRaiserSeat = a.seat;
      lastRaiseAmount = a.amount;
      lastRaiseIsAllin = a.type === 'all_in';
      callersAfterLastRaise = 0; // reset callers count
    } else if (a.type === 'call') {
      if (raiseCount > 0) {
        callersAfterLastRaise++;
      } else {
        limpCount++; // call with no raise = limp (preflop)
      }
    }
  }

  // Determine facing type
  let facingType: RaiseContext['facingType'];
  if (raiseCount === 0) {
    facingType = limpCount > 0 ? 'facing_limp' : 'unopened';
  } else if (raiseCount === 1) {
    facingType = 'facing_open';
  } else if (raiseCount === 2) {
    facingType = 'facing_3bet';
  } else {
    facingType = 'facing_4bet_plus';
  }

  // Raise size in bb
  const raiseSize = lastRaiseAmount / bb;

  // Raiser position
  const raiserPosition = lastRaiserSeat != null ? (state.positions[lastRaiserSeat] ?? null) : null;

  // Hero position
  const heroPosition = state.positions[mySeat] ?? null;

  // Effective stack
  const myPlayer = state.players.find((p) => p.seat === mySeat);
  const raiserPlayer =
    lastRaiserSeat != null ? state.players.find((p) => p.seat === lastRaiserSeat) : null;
  const myStack = myPlayer?.stack ?? 0;
  const raiserStack = raiserPlayer?.stack ?? myStack;
  const effectiveStack = Math.min(myStack, raiserStack) / bb;

  // SPR: effective stack / (pot + call amount) after calling
  const callAmount = state.legalActions?.callAmount ?? 0;
  const potAfterCall = state.pot + callAmount;
  const spr = potAfterCall > 0 ? (effectiveStack * bb - callAmount) / potAfterCall : 999;

  return {
    raiserSeat: lastRaiserSeat,
    raiserPosition,
    raiseSize,
    raiseSizeCategory:
      lastRaiserSeat != null ? categorizeSizeBB(raiseSize, lastRaiseIsAllin) : 'min',
    numCallers: callersAfterLastRaise,
    isMultiway: callersAfterLastRaise >= 2,
    effectiveStack,
    spr: Math.max(0, spr),
    is3bet: raiseCount >= 2,
    facingType,
    heroPosition,
  };
}
