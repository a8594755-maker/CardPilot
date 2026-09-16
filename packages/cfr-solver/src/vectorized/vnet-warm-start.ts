/**
 * VNet Warm-Start for CFR Solver — Per-Combo Version.
 *
 * Initializes ArrayStore strategySums with per-combo VNet predictions
 * before CFR begins. Each combo gets its own VNet inference with its
 * actual hole cards, producing a hand-specific initial strategy.
 *
 * This gives CFR a "warm start" from a good strategy instead of uniform,
 * reducing iterations needed to converge.
 */

import type { ArrayStore } from './array-store.js';
import type { FlatTree } from './flat-tree.js';
import type { ValidCombos } from './combo-utils.js';
import type { MLP } from '@cardpilot/fast-model';
import { indexToCard } from '../abstraction/card-index.js';

export interface WarmStartParams {
  store: ArrayStore;
  tree: FlatTree;
  board: number[];
  street: 'FLOP' | 'TURN' | 'RIVER';
  vnetModel: MLP;
  /** How much to weight VNet's initial strategy (default: 10). */
  initialWeight?: number;
  validCombos: ValidCombos;
  /** Dead combo mask: 1 = dead (card on board), 0 = live */
  blockerMatrix?: Uint8Array;
}

const RANK_VALUES: Record<string, number> = {
  '2': 2,
  '3': 3,
  '4': 4,
  '5': 5,
  '6': 6,
  '7': 7,
  '8': 8,
  '9': 9,
  T: 10,
  J: 11,
  Q: 12,
  K: 13,
  A: 14,
};
const SUIT_INDEX: Record<string, number> = { s: 0, h: 1, d: 2, c: 3 };

/**
 * Populate ArrayStore.strategySums with per-combo VNet predictions.
 *
 * For each node × each live combo:
 *   1. Encode 54-dim features with the combo's actual hole cards
 *   2. Run VNet inference → action probs + sizing probs
 *   3. Map VNet output to tree actions
 *   4. Write prob * weight into strategySums
 */
export function warmStartFromVNet(params: WarmStartParams): void {
  const {
    store,
    tree,
    board,
    street,
    vnetModel,
    initialWeight = 10,
    validCombos,
    blockerMatrix,
  } = params;

  const nc = validCombos.numCombos;
  const boardStrings = board.map(indexToCard);

  // Pre-encode board features (shared across all combos, 25 dims)
  const boardFeatures = encodeBoardFeatures(boardStrings);

  // Pre-encode street one-hot (3 dims)
  const streetFeatures = [
    street === 'FLOP' ? 1 : 0,
    street === 'TURN' ? 1 : 0,
    street === 'RIVER' ? 1 : 0,
  ];

  // Pre-compute hole card features for all combos (5 dims each)
  const comboHoleFeatures: number[][] = new Array(nc);
  for (let c = 0; c < nc; c++) {
    const [c1, c2] = validCombos.combos[c];
    comboHoleFeatures[c] = encodeHoleCards(c1, c2);
  }

  // Reusable 54-dim feature buffer
  const features = new Float64Array(54);

  for (let nodeId = 0; nodeId < tree.numNodes; nodeId++) {
    const numActions = tree.nodeNumActions[nodeId];
    if (numActions <= 1) continue;

    // Collect action labels
    const actionOffset = tree.nodeActionOffset[nodeId];
    const actionLabels: string[] = [];
    for (let a = 0; a < numActions; a++) {
      actionLabels.push(tree.nodeActionLabels[actionOffset + a]);
    }

    // Game state from tree
    const player = tree.nodePlayer[nodeId];
    const pot = tree.nodePot[nodeId];
    const s0 = tree.nodeStacks[nodeId * tree.numPlayers];
    const s1 = tree.nodeStacks[nodeId * tree.numPlayers + 1];
    const facingBet = actionLabels.some((l) => l === 'fold' || l === 'call');
    const toCall = facingBet ? Math.max(0, (player === 0 ? s0 : s1) - (player === 0 ? s1 : s0)) : 0;
    const isIP = player === 1;

    // Encode position/pot features (shared across combos, dims 33-53)
    const gameFeatures = encodeGameState(isIP, pot, toCall, Math.min(s0, s1), facingBet);

    // Pre-fill shared features into buffer
    // [0..4] = hole cards (per-combo)
    // [5..29] = board (shared)
    // [30..32] = street (shared)
    // [33..53] = game state (shared)
    for (let i = 0; i < 25; i++) features[5 + i] = boardFeatures[i];
    for (let i = 0; i < 3; i++) features[30 + i] = streetFeatures[i];
    for (let i = 0; i < gameFeatures.length; i++) features[33 + i] = gameFeatures[i];

    const base = store.nodeOffset[nodeId];

    // Per-combo VNet inference
    for (let c = 0; c < nc; c++) {
      if (blockerMatrix && blockerMatrix[c]) continue;

      // Set hole card features
      const hf = comboHoleFeatures[c];
      features[0] = hf[0];
      features[1] = hf[1];
      features[2] = hf[2];
      features[3] = hf[3];
      features[4] = hf[4];

      // VNet inference
      const prediction = vnetModel.predictFull(features as unknown as number[]);
      const { raise: raiseProb, call: callProb, fold: foldProb } = prediction.action;

      // Map to tree actions
      const treeProbs = mapToTreeActions(
        actionLabels,
        raiseProb,
        callProb,
        foldProb,
        prediction.sizing,
      );

      // Write per-combo strategy
      for (let a = 0; a < numActions; a++) {
        if (treeProbs[a] > 0) {
          store.strategySums[base + a * nc + c] = treeProbs[a] * initialWeight;
        }
      }
    }
  }
}

function encodeHoleCards(c1: number, c2: number): number[] {
  const s1 = indexToCard(c1);
  const s2 = indexToCard(c2);
  const r1 = RANK_VALUES[s1[0]] ?? 0;
  const r2 = RANK_VALUES[s2[0]] ?? 0;
  const suited = s1[1] === s2[1] ? 1 : 0;
  const paired = s1[0] === s2[0] ? 1 : 0;
  const gap = Math.abs(r1 - r2) / 12;
  return [r1 / 14, r2 / 14, suited, paired, gap];
}

function encodeBoardFeatures(boardStrings: string[]): number[] {
  const features: number[] = [];
  for (let i = 0; i < 5; i++) {
    if (i < boardStrings.length && boardStrings[i]) {
      const r = (RANK_VALUES[boardStrings[i][0]] ?? 0) / 14;
      const sIdx = SUIT_INDEX[boardStrings[i][1]] ?? 0;
      features.push(
        r,
        sIdx === 0 ? 1 : 0,
        sIdx === 1 ? 1 : 0,
        sIdx === 2 ? 1 : 0,
        sIdx === 3 ? 1 : 0,
      );
    } else {
      features.push(0, 0, 0, 0, 0);
    }
  }
  return features;
}

function encodeGameState(
  isIP: boolean,
  pot: number,
  toCall: number,
  effStack: number,
  facingBet: boolean,
): number[] {
  const potNorm = Math.min(pot / 100, 5);
  const toCallNorm = Math.min(toCall / 100, 5);
  const spr = pot > 0 ? Math.min(effStack / pot, 20) : 20;
  const potOdds = toCall > 0 ? toCall / (pot + toCall) : 0;

  // Position one-hot (7) — HU: BTN=index 4, BB=index 6
  const pos = [0, 0, 0, 0, 0, 0, 0];
  if (isIP) pos[4] = 1;
  else pos[6] = 1;

  return [
    ...pos, // 7 dims
    isIP ? 1 : 0, // 1 dim
    potNorm,
    toCallNorm,
    spr,
    potOdds, // 4 dims
    1 / 5,
    facingBet ? 1 : 0,
    0, // 3 dims (numVillains, facingBet, isAggressor)
    0,
    0,
    0,
    0,
    0,
    0, // 6 dims (betting history defaults)
  ]; // total: 21 dims → features[33..53]
}

/**
 * Map VNet action probs (raise/call/fold) + sizing to tree action labels.
 */
function mapToTreeActions(
  labels: string[],
  raiseProb: number,
  callProb: number,
  foldProb: number,
  sizing?: { third: number; half: number; twoThirds: number; pot: number; allIn: number },
): number[] {
  const probs = new Array(labels.length).fill(0);

  const betIndices: number[] = [];
  let allinIndex = -1;

  for (let i = 0; i < labels.length; i++) {
    const label = labels[i];
    if (label === 'fold') {
      probs[i] = foldProb;
    } else if (label === 'check' || label === 'call') {
      probs[i] = callProb;
    } else if (label === 'allin') {
      allinIndex = i;
    } else if (label.startsWith('bet_') || label.startsWith('raise_')) {
      betIndices.push(i);
    }
  }

  if (sizing && (betIndices.length > 0 || allinIndex >= 0)) {
    const sizingValues = [sizing.third, sizing.half, sizing.twoThirds, sizing.pot, sizing.allIn];
    const totalBetActions = betIndices.length + (allinIndex >= 0 ? 1 : 0);

    if (totalBetActions === 1) {
      const idx = betIndices[0] ?? allinIndex;
      probs[idx] = raiseProb;
    } else {
      const allinShare = sizing.allIn;
      const betShare = 1 - allinShare;

      if (allinIndex >= 0) {
        probs[allinIndex] = raiseProb * allinShare;
      }

      if (betIndices.length > 0 && betShare > 0) {
        const perBet = (raiseProb * betShare) / betIndices.length;
        for (const idx of betIndices) {
          probs[idx] = perBet;
        }
      }
    }
  } else {
    const allBetIndices = [...betIndices];
    if (allinIndex >= 0) allBetIndices.push(allinIndex);
    if (allBetIndices.length > 0) {
      const perBet = raiseProb / allBetIndices.length;
      for (const idx of allBetIndices) {
        probs[idx] = perBet;
      }
    }
  }

  // Normalize
  const sum = probs.reduce((a: number, b: number) => a + b, 0);
  if (sum > 0) {
    for (let i = 0; i < probs.length; i++) probs[i] /= sum;
  }

  return probs;
}
