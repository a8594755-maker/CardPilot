// Heuristic EV estimation at street transition boundaries.
//
// When solving a single street (e.g., Flop-only), the tree has "transition"
// terminal nodes where the next street would begin. We need to estimate
// the EV at these points without solving the full Turn/River tree.
//
// The simplest approach: EV ≈ equity × pot
// Each player's equity is their probability of winning at showdown
// given the current board and both players' weighted reach probabilities.

import { evaluateHandBoard } from '@cardpilot/poker-evaluator';

/**
 * Estimate EV at a street transition for all combos.
 *
 * Uses equity-based approximation:
 * For each of traverser's combos, compute equity against opponent's
 * reach-weighted range, then EV ≈ (equity - 0.5) × pot
 *
 * This is a rough approximation but sufficient for the Flop tree
 * to converge to reasonable strategies. The Turn/River will be
 * resolved exactly via subgame solving.
 *
 * @param combos - valid combos on this board
 * @param board - current board cards (3 for flop transition, 4 for turn transition)
 * @param pot - pot size at transition
 * @param oopReach - OOP reach probs (length = numCombos)
 * @param ipReach - IP reach probs (length = numCombos)
 * @param blockerMatrix - blocker matrix
 * @param numCombos - number of valid combos
 * @param traverser - 0 (OOP) or 1 (IP)
 * @param playerStacks - remaining stacks at transition
 * @param outEV - output EV vector (length = numCombos)
 */
export function estimateTransitionEV(
  combos: Array<[number, number]>,
  board: number[],
  pot: number,
  oopReach: Float32Array,
  ipReach: Float32Array,
  blockerMatrix: Uint8Array,
  numCombos: number,
  traverser: number,
  playerStacks: number[],
  outEV: Float32Array,
): void {
  // Use the current board for evaluation (no future cards sampled)
  // This is an equity approximation — how often does each combo win
  // against the opponent's weighted range right now?

  // Pre-evaluate all hand values on current board
  const handValues = new Float64Array(numCombos);
  for (let i = 0; i < numCombos; i++) {
    handValues[i] = evaluateHandBoard(combos[i][0], combos[i][1], board);
  }

  const opponentReach = traverser === 0 ? ipReach : oopReach;
  const numPlayers = playerStacks.length;
  const totalChips = pot + playerStacks.reduce((a, b) => a + b, 0);
  const startTotal = totalChips / numPlayers;
  const traverserStack = playerStacks[traverser];

  for (let i = 0; i < numCombos; i++) {
    let wins = 0;
    let losses = 0;
    let ties = 0;

    for (let j = 0; j < numCombos; j++) {
      if (blockerMatrix[i * numCombos + j]) continue;
      const oppR = opponentReach[j];
      if (oppR === 0) continue;

      if (handValues[i] > handValues[j]) {
        wins += oppR;
      } else if (handValues[i] < handValues[j]) {
        losses += oppR;
      } else {
        ties += oppR;
      }
    }

    const total = wins + losses + ties;
    if (total === 0) {
      outEV[i] = 0;
      continue;
    }

    // Equity = (wins + ties/2) / total

    // EV = equity × pot_won - (1-equity) × pot_lost
    // Simplified: EV relative to starting total
    const winPayoff = traverserStack + pot - startTotal;
    const losePayoff = traverserStack - startTotal;
    const tiePayoff = traverserStack + pot / 2 - startTotal;

    outEV[i] = wins * winPayoff + losses * losePayoff + ties * tiePayoff;
  }
}

/**
 * More accurate transition EV using Monte Carlo sampling of future cards.
 *
 * Instead of evaluating on the current board only, sample N possible
 * future runouts and average the equity. This is more expensive but
 * gives better boundary conditions for the Flop tree.
 *
 * @param numSamples - how many future cards to sample (default 10)
 */
export function estimateTransitionEVMonteCarlo(
  combos: Array<[number, number]>,
  board: number[],
  pot: number,
  oopReach: Float32Array,
  ipReach: Float32Array,
  blockerMatrix: Uint8Array,
  numCombos: number,
  traverser: number,
  playerStacks: number[],
  outEV: Float32Array,
  numSamples: number = 10,
): void {
  outEV.fill(0);

  // Determine how many cards remain to be dealt
  const cardsNeeded = 5 - board.length; // flop→2, turn→1, river→0
  if (cardsNeeded === 0) {
    // Already at river — use exact evaluation
    estimateTransitionEV(
      combos,
      board,
      pot,
      oopReach,
      ipReach,
      blockerMatrix,
      numCombos,
      traverser,
      playerStacks,
      outEV,
    );
    return;
  }

  // Build available cards
  const dead = new Uint8Array(52);
  for (const c of board) dead[c] = 1;
  const available: number[] = [];
  for (let c = 0; c < 52; c++) {
    if (!dead[c]) available.push(c);
  }

  const tempEV = new Float32Array(numCombos);
  const fullBoard = [...board, ...Array(cardsNeeded).fill(0)];

  let rng = 42;
  for (let s = 0; s < numSamples; s++) {
    // Sample future cards
    const sampled = sampleCards(available, cardsNeeded, rng);
    rng = nextRng(rng);

    for (let k = 0; k < cardsNeeded; k++) {
      fullBoard[board.length + k] = sampled[k];
    }

    tempEV.fill(0);
    estimateTransitionEV(
      combos,
      fullBoard,
      pot,
      oopReach,
      ipReach,
      blockerMatrix,
      numCombos,
      traverser,
      playerStacks,
      tempEV,
    );

    for (let i = 0; i < numCombos; i++) {
      outEV[i] += tempEV[i];
    }
  }

  // Average
  const invN = 1 / numSamples;
  for (let i = 0; i < numCombos; i++) {
    outEV[i] *= invN;
  }
}

function sampleCards(available: number[], count: number, seed: number): number[] {
  // Fisher-Yates partial shuffle
  const arr = [...available];
  let s = seed;
  for (let i = 0; i < count && i < arr.length; i++) {
    s = nextRng(s);
    const j = i + (s % (arr.length - i));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr.slice(0, count);
}

function nextRng(state: number): number {
  return (state * 1103515245 + 12345) & 0x7fffffff;
}
