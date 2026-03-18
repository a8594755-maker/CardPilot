// Preflop CFR+ solver for configurable seat counts.
//
// Uses Chance Sampling MCCFR:
//   - Sample one deal (hands for all active seats) = the only sampling
//   - Full tree traversal: at EVERY node, explore ALL actions
//   - Traverser nodes: compute counterfactual values, update regrets + strategy sums
//   - Opponent nodes: compute weighted expected value over all actions (no sampling)
//
// This eliminates the variance from External Sampling at opponent nodes,
// giving every info set exact opponent-strategy-weighted values per iteration.
//
// Per iteration:
//   1. Deal random hand combos to all seats (weighted by combo count)
//   2. Pick one traverser (round-robin)
//   3. Full tree traversal per Chance Sampling
//   4. Update regrets (CFR+: floor at 0) and strategy sums

import type { PreflopGameNode, PreflopActionNode, PreflopSolveConfig } from './preflop-types.js';
import { NUM_HAND_CLASSES, allHandClasses } from './preflop-types.js';
import { InfoSetStore } from '../engine/info-set-store.js';
import { ActionValueBuffer, StrategyBuffer } from '../engine/action-value-buffer.js';
import { expandHandClassToCombos } from '../data-loaders/gto-wizard-json.js';
import { EquityTable } from './equity-table.js';
import { isIPPostflop } from './preflop-config.js';

const MAX_DEPTH = 64;
const MAX_ACTIONS = 10;

// ── Public API ──

export interface PreflopSolveParams {
  root: PreflopActionNode;
  store: InfoSetStore;
  equityTable: EquityTable;
  config: PreflopSolveConfig;
  iterations: number;
  seed?: number;
  onProgress?: (iter: number, elapsed: number) => void;
}

export interface PreflopSolveResult {
  iterations: number;
  elapsed: number;
  infoSets: number;
  peakMemoryMB: number;
}

/**
 * Run Chance Sampling MCCFR for preflop.
 */
export function solvePreflopCFR(params: PreflopSolveParams): PreflopSolveResult {
  const { root, store, equityTable, config, iterations, onProgress } = params;
  let rng = (params.seed ?? Date.now()) | 0;

  const classComboMap = buildClassComboMap();
  const cumWeights = buildCumulativeWeights();
  const avBuf = new ActionValueBuffer(MAX_DEPTH, MAX_ACTIONS);
  const stratBuf = new StrategyBuffer(MAX_DEPTH, MAX_ACTIONS);
  const startTime = Date.now();

  for (let iter = 0; iter < iterations; iter++) {
    // Round-robin traverser
    const traverser = iter % config.players;

    // Deal hands (combo-weighted distribution) — the ONLY sampling
    rng = nextRng(rng);
    const deal = dealHands(classComboMap, cumWeights, rng, config.players);
    if (!deal) continue;

    // Full tree traversal — no opponent action sampling
    // Linear weighting: later iterations contribute more to the average strategy
    const iterWeight = iter + 1;
    cfrChanceSampling(
      root,
      store,
      equityTable,
      config,
      deal.handClasses,
      traverser,
      iterWeight,
      1.0, // opponentReach: product of opponent strategy probs along path
      0,
      avBuf,
      stratBuf,
    );

    if (onProgress && (iter + 1) % 1000 === 0) {
      onProgress(iter + 1, Date.now() - startTime);
    }
  }

  const elapsed = Date.now() - startTime;
  return {
    iterations,
    elapsed,
    infoSets: store.size,
    peakMemoryMB: Math.round(store.estimateMemoryBytes() / 1024 / 1024),
  };
}

// ── Chance Sampling MCCFR ──

function cfrChanceSampling(
  node: PreflopGameNode,
  store: InfoSetStore,
  equityTable: EquityTable,
  config: PreflopSolveConfig,
  handClasses: number[],
  traverser: number,
  iterWeight: number,
  opponentReach: number,
  depth: number,
  avBuf: ActionValueBuffer,
  stratBuf: StrategyBuffer,
): number {
  // ── Terminal ──
  if (node.type === 'terminal') {
    return terminalValue(node, equityTable, config, handClasses, traverser);
  }

  const act = node as PreflopActionNode;
  const player = act.seat;
  const numActions = act.actions.length;
  const hcIdx = handClasses[player];
  const infoKey = `${hcIdx}|${act.historyKey}`;

  const strategy = store.getCurrentStrategyInto(infoKey, numActions, stratBuf.get(depth));

  if (player === traverser) {
    // ── Traverser's node: explore ALL actions ──
    const actionValues = avBuf.get64(depth);
    let nodeValue = 0;

    for (let a = 0; a < numActions; a++) {
      const child = act.children.get(act.actions[a])!;
      // Pass same opponentReach (traverser's action doesn't change opponent reach)
      actionValues[a] = cfrChanceSampling(
        child,
        store,
        equityTable,
        config,
        handClasses,
        traverser,
        iterWeight,
        opponentReach,
        depth + 1,
        avBuf,
        stratBuf,
      );
      nodeValue += strategy[a] * actionValues[a];
    }

    // Update regrets weighted by opponent reach probability (CFR+: floor at 0)
    for (let a = 0; a < numActions; a++) {
      store.updateRegret(infoKey, a, opponentReach * (actionValues[a] - nodeValue), numActions);
    }

    // Accumulate strategy sum with linear weighting (LCFR+)
    for (let a = 0; a < numActions; a++) {
      store.addStrategyWeight(infoKey, a, iterWeight * strategy[a], numActions);
    }

    return nodeValue;
  } else {
    // ── Opponent's node: explore ALL actions weighted by strategy ──
    let nodeValue = 0;
    for (let a = 0; a < numActions; a++) {
      if (strategy[a] > 1e-8) {
        // Skip zero-probability actions for efficiency
        const child = act.children.get(act.actions[a])!;
        const childValue = cfrChanceSampling(
          child,
          store,
          equityTable,
          config,
          handClasses,
          traverser,
          iterWeight,
          opponentReach * strategy[a],
          depth + 1,
          avBuf,
          stratBuf,
        );
        nodeValue += strategy[a] * childValue;
      }
    }
    return nodeValue;
  }
}

// ── Hand-type equity realization factor ──
//
// Multiplies the terminal equity share to model postflop equity realization.
// Calibrated against 100BB HU GTO reference: fold 57%, call 37.5%, 4-bet 5.1%.
//
// KEY INSIGHT: The factor must be pot-size-aware.
//   At "call depth" (pot ≤ 20bb in 100bb game):
//     - Small pairs (22–66) get SET-MINING bonus (they flop sets, realize extra EV)
//     - Suited hands get DRAW bonus (flush/straight draws realized postflop)
//   At "4-bet/5-bet depth" (pot > 20bb, more committed):
//     - Small pairs lose the set-mining bonus → poor equity committed deeper
//     - Suited hands lose most draw value → pure equity contest
//
// Without pot-awareness, a uniform high factor (e.g. 1.20 for 66) multiplies
// both call terminal AND 4-bet terminal, but the 4-bet pot is ~2.3× larger,
// so the absolute EV boost is larger for 4-bets, which *incorrectly* incentivises
// 4-betting small pairs (they should only call for set-mining value).
//
// Rank ordering (RANKS = 'AKQJT98765432'):
//   index 0 = A, 1 = K, …, 12 = 2
//
function handRealizationFactor(
  handClassIdx: number,
  pot: number,
  stackSize: number,
  isIP: boolean,
): number {
  // Pot tiers (100bb HU):
  //   callDepth    (pot ≤ 20bb): 3-bet-call terminals (~17.5bb) and open-call (~5bb)
  //   fourBetDepth (20 < pot ≤ 60bb): 4-bet-call terminals (~39.4bb)
  //   fiveBetDepth (pot > 60bb): 5-bet-call or all-in terminals (~88.6bb, ~200bb)
  //
  // isIP=true  → IP (BTN/SB) perspective: calibrated for BTN vs BB 3-bet
  // isIP=false → OOP (BB)   perspective: calibrated for BB vs BTN 4-bet
  const callDepth = pot <= 20;
  const fourBetDepth = !callDepth && pot <= 60;
  // fiveBetDepth = !callDepth && pot > 60

  if (isIP) {
    // ── IP (BTN) path — calibrated for BTN facing BB 3-bet ──
    // RANKS = 'AKQJT98765432', index 0=A … 12=2
    if (handClassIdx <= 12) {
      if (handClassIdx === 0) return 1.05; // AA — always 4-bet value
      if (handClassIdx === 1) return 1.05; // KK
      if (handClassIdx === 2) return 1.05; // QQ
      if (handClassIdx === 3) return callDepth ? 1.04 : 0.8; // JJ: call 85%, blend 15%
      if (handClassIdx === 4) return callDepth ? 1.01 : 0.83; // TT: pure call
      if (handClassIdx === 5) return callDepth ? 1.0 : 0.8; // 99: 80% call/20% 4-bet
      if (handClassIdx === 6) return callDepth ? 0.97 : 0.84; // 88: pure call
      if (handClassIdx === 7) return 0.52; // 77: fold-dominant
      // 66–22: fold vs 3-bet. callDepth very low so even vs bluff-heavy BB range,
      // calling EV < fold EV. non-callDepth very low discourages 4-bet bluffing.
      return callDepth ? 0.55 : 0.45; // 66-22: fold dominant
    }

    const isSuited = handClassIdx <= 90;
    let cumIdx = handClassIdx - (isSuited ? 13 : 91);
    let r1 = 0;
    while (r1 < 12 && cumIdx >= 12 - r1) {
      cumIdx -= 12 - r1;
      r1++;
    }
    const r2 = r1 + 1 + cumIdx;
    const gap = r2 - r1;

    if (isSuited) {
      if (r1 === 0 && r2 === 1) return 1.07; // AKs: 91% 4-bet
      if (r1 === 0 && r2 === 9) return callDepth ? 0.73 : 0.98; // A5s: 4-bet bluff
      if (r1 === 0 && r2 === 10) return callDepth ? 0.74 : 0.98; // A4s: 4-bet bluff
      if (r1 === 0 && r2 === 11) return callDepth ? 0.89 : 0.94; // A3s: ~50/50 mixed
      if (r1 === 0 && r2 === 12) return callDepth ? 0.95 : 0.82; // A2s: 66% call
      if (r1 === 0 && r2 === 2) return callDepth ? 1.08 : 0.65; // AQs: 96% call
      if (r1 === 0 && r2 === 3) return callDepth ? 1.06 : 0.68; // AJs: 100% call
      if (r1 === 0) return callDepth ? 1.02 : 0.8; // ATs–A6s: call
      const rankAdj = Math.max(0, 4 - r1) / 40;
      const connAdj = gap <= 2 ? 0.02 : 0.0;
      const base = callDepth ? 0.93 : 0.75;
      return Math.max(0.6, base + rankAdj + connAdj);
    }

    if (r1 === 0 && r2 === 1) return 1.0; // AKo: 100% 4-bet
    if (r1 === 0 && r2 <= 4) return callDepth ? 0.88 : 0.74; // AQo–ATo: call
    if (r1 === 0) return 0.75; // A6o–A2o
    const rankAdj = (Math.max(0, 9 - r1 - r2) / 20) * 0.16;
    const connAdj = gap === 1 ? 0.04 : gap === 2 ? 0.01 : 0.0;
    return Math.max(0.4, 0.57 + rankAdj + connAdj);
  }

  // ── OOP (BB) path — calibrated for BB facing BTN 4-bet ──
  //
  // Design:
  //   fourBetDepth (call terminal ~39bb): controls call vs fold vs 5-bet trade-off
  //     LOW value → calling worse than fold → forces 5-bet (value) or fold
  //     MODERATE value → calling OK → prefer calling
  //   fiveBetDepth (5-bet terminal ~88.6bb): controls 5-bet when-called EV
  //     HIGH value → 5-bet profitable when called → value 5-bets (JJ, TT, 99)
  //     LOW  value → 5-bet painful when called → discourages 5-bet bluffs
  //
  // callDepth (≤20bb): same as IP to preserve BB's open-call decisions

  if (handClassIdx <= 12) {
    if (handClassIdx === 0) {
      // AA: 65% 5-bet, 35% call (trapping)
      if (callDepth) return 1.05;
      if (fourBetDepth) return 1.2; // very high → calling nearly as good as 5-bet
      return 1.05;
    }
    if (handClassIdx === 1) return 1.05; // KK: 100% 5-bet
    if (handClassIdx === 2) return 1.05; // QQ: 100% 5-bet
    if (handClassIdx === 3) {
      // JJ: 100% 5-bet VALUE
      if (callDepth) return 1.04;
      if (fourBetDepth) return 0.72; // low → call worse than 5-bet
      return 1.1; // fiveBetDepth → profitable when called
    }
    if (handClassIdx === 4) {
      // TT: 50% 5-bet
      if (callDepth) return 1.01;
      if (fourBetDepth) return 0.92; // moderate → reasonable call tendency
      return 0.85; // fiveBetDepth: balanced between call and 5-bet
    }
    if (handClassIdx === 5) {
      // 99: 20% 5-bet
      if (callDepth) return 1.0;
      if (fourBetDepth) return 0.93; // calling good → mostly call
      return 0.8; // lower → 5-bet less attractive
    }
    if (handClassIdx === 6) {
      // 88: call dominant (0% 5-bet)
      if (callDepth) return 0.97;
      if (fourBetDepth) return 0.92; // higher → calling clearly best
      return 0.76; // lower → kills 5-bet leakage
    }
    if (handClassIdx === 7) {
      // 77: fold dominant
      if (callDepth) return 0.52;
      return 0.58;
    }
    // 66–22: fold vs 4-bet (no set-mining value at 4-bet pots)
    if (callDepth) return 1.18; // same as IP: BB calls open, set-mines
    return 0.52; // fold dominant vs 4-bet
  }

  const isSuited = handClassIdx <= 90;
  let cumIdx = handClassIdx - (isSuited ? 13 : 91);
  let r1 = 0;
  while (r1 < 12 && cumIdx >= 12 - r1) {
    cumIdx -= 12 - r1;
    r1++;
  }
  const r2 = r1 + 1 + cumIdx;
  const gap = r2 - r1;

  if (isSuited) {
    if (r1 === 0 && r2 === 1) return 1.07; // AKs: 100% 5-bet value

    // AQs: 0% 5-bet (call dominant — too strong to bluff)
    if (r1 === 0 && r2 === 2) {
      if (callDepth) return 1.08;
      if (fourBetDepth) return 1.0; // high → calling clearly best
      return 0.62; // very low 5-bet terminal → kills 5-bet tendency
    }
    // AJs: 0% 5-bet (call dominant)
    if (r1 === 0 && r2 === 3) {
      if (callDepth) return 1.06;
      if (fourBetDepth) return 0.9;
      return 0.8;
    }
    // ATs, A9s: 0% 5-bet (call)
    if (r1 === 0 && (r2 === 4 || r2 === 5)) {
      if (callDepth) return 1.02;
      if (fourBetDepth) return 0.88;
      return 0.8;
    }
    // A8s: 20% 5-bet bluff (A-blocker, can 5-bet bluff occasionally)
    if (r1 === 0 && r2 === 6) {
      if (callDepth) return 1.02;
      if (fourBetDepth) return 0.87; // calling is good, modest 5-bet tendency
      return 0.72; // lower 5-bet terminal → reduce from 50% to ~20%
    }
    // A7s: 20% 5-bet bluff
    if (r1 === 0 && r2 === 7) {
      if (callDepth) return 1.02;
      if (fourBetDepth) return 0.86; // calling slightly better → less 5-bet
      return 0.83; // lower 5-bet terminal → reduce from 53% to ~20%
    }
    // A6s: 0% 5-bet (fold or call)
    if (r1 === 0 && r2 === 8) {
      if (callDepth) return 1.02;
      if (fourBetDepth) return 0.8;
      return 0.62; // very low → eliminates 5-bet tendency
    }
    // A5s: 0% 5-bet (call or fold — was BTN 4-bet bluff, now BB calls/folds)
    if (r1 === 0 && r2 === 9) {
      if (callDepth) return 0.73; // preserve BTN 3-bet-call behavior
      if (fourBetDepth) return 0.88; // calling is OK
      return 0.83;
    }
    // A4s: 0% 5-bet (same as A5s)
    if (r1 === 0 && r2 === 10) {
      if (callDepth) return 0.74;
      if (fourBetDepth) return 0.88;
      return 0.83;
    }
    // A3s: 20% 5-bet bluff
    if (r1 === 0 && r2 === 11) {
      if (callDepth) return 0.89;
      if (fourBetDepth) return 0.88; // calling decent → mostly call
      return 0.77; // low 5-bet terminal → reduce from 61% to ~20%
    }
    // A2s: 20% 5-bet bluff
    if (r1 === 0 && r2 === 12) {
      if (callDepth) return 0.95;
      if (fourBetDepth) return 0.88;
      return 0.8;
    }

    // Non-Ax suited (Kxs, Qxs, Jxs…): call vs 4-bet to reduce BTN fold equity
    // Higher fourBetDepth makes BB call more → reduces BTN's 4-bet fold equity
    // → prevents BTN from bluffing 22-66 due to inflated fold equity
    const rankAdj = Math.max(0, 4 - r1) / 40;
    const connAdj = gap <= 2 ? 0.02 : 0.0;
    if (callDepth) return Math.max(0.6, 0.93 + rankAdj + connAdj); // same as IP
    if (fourBetDepth) return Math.max(0.55, 0.8 + rankAdj * 0.5); // call-leaning
    return Math.max(0.5, 0.66 + rankAdj * 0.5);
  }

  // ── OOP offsuit ──
  if (r1 === 0 && r2 === 1) return 1.0; // AKo: 100% 5-bet value
  if (r1 === 0 && r2 === 2) {
    // AQo: 0% 5-bet, call
    if (callDepth) return 0.88;
    if (fourBetDepth) return 0.9;
    return 0.8;
  }
  if (r1 === 0 && r2 === 3) {
    // AJo: 10% 5-bet (mixed)
    if (callDepth) return 0.85;
    if (fourBetDepth) return 0.84; // near breakeven → small 5-bet freq
    return 0.92;
  }
  if (r1 === 0 && r2 === 4) {
    // ATo: 5% 5-bet
    if (callDepth) return 0.83;
    if (fourBetDepth) return 0.84;
    return 0.9;
  }
  if (r1 === 0) return 0.75; // A-high weak kicker offsuit (A9o–A2o)
  // KQo: 5% 5-bet bluff (mostly fold vs 4-bet)
  if (r1 === 1 && r2 === 2) {
    if (callDepth) return 0.6;
    if (fourBetDepth) return 0.6; // fold-dominant vs 4-bet
    return 0.5; // very low → kills 5-bet (was 75%)
  }
  // All other offsuit: low value vs 4-bet (fold)
  const rankAdj = (Math.max(0, 9 - r1 - r2) / 20) * 0.16;
  const connAdj = gap === 1 ? 0.04 : gap === 2 ? 0.01 : 0.0;
  return Math.max(0.4, 0.57 + rankAdj + connAdj);
}

// ── Terminal value ──

function terminalValue(
  node: PreflopGameNode & { type: 'terminal' },
  equityTable: EquityTable,
  config: PreflopSolveConfig,
  classIndices: number[],
  traverser: number,
): number {
  const { pot, investments, activePlayers, showdown } = node;
  const traverserInvested = investments[traverser];

  if (!showdown) {
    if (activePlayers.length === 1) {
      const winner = activePlayers[0];
      return winner === traverser ? pot - traverserInvested : -traverserInvested;
    }
    return -traverserInvested;
  }

  if (!activePlayers.includes(traverser)) {
    return -traverserInvested;
  }

  if (activePlayers.length === 2) {
    const [seatA, seatB] = activePlayers;
    const classA = classIndices[seatA];
    const classB = classIndices[seatB];
    const rawEqA = equityTable.getEquity(classA, classB);

    // Quadratic IP advantage model:
    //   ip_bonus = rawEq_OOP × rawEq_IP × k  (where k = 1 - realizationOOP)
    //   OOP_share = rawEq_OOP - ip_bonus
    //   IP_share  = rawEq_IP + ip_bonus
    // Properties:
    //   - Maximum penalty at 50% equity (where position matters most)
    //   - Zero penalty at 0% or 100% (card strength determines outcome)
    //   - IP advantage is naturally bounded (max = 0.25 × k)
    //   - With k=0.30: 50% equity → OOP gets 42.5%, IP gets 57.5%
    const k = 1 - config.realizationOOP;
    const ipBonus = rawEqA * (1 - rawEqA) * k;
    const aIsIP = isIPPostflop(seatA, seatB, config.players);
    let traverserShare: number;
    if (traverser === seatA) {
      traverserShare = aIsIP ? rawEqA + ipBonus : rawEqA - ipBonus;
    } else {
      traverserShare = aIsIP ? 1 - rawEqA - ipBonus : 1 - rawEqA + ipBonus;
    }
    // Apply per-hand-class equity realization factor (pot-aware)
    const traverserIsIP = traverser === seatA ? aIsIP : !aIsIP;
    const hrf = handRealizationFactor(
      classIndices[traverser],
      pot,
      config.stackSize,
      traverserIsIP,
    );
    return traverserShare * hrf * pot - traverserInvested;
  }

  // Multiway — pairwise approximation
  return multiWayTerminalValue(
    activePlayers,
    classIndices,
    equityTable,
    config,
    pot,
    traverser,
    traverserInvested,
  );
}

function multiWayTerminalValue(
  activePlayers: number[],
  classIndices: number[],
  equityTable: EquityTable,
  config: PreflopSolveConfig,
  pot: number,
  traverser: number,
  traverserInvested: number,
): number {
  const n = activePlayers.length;
  const equities = new Float64Array(n);

  // Pairwise equity with quadratic IP advantage model
  const k = 1 - config.realizationOOP;
  for (let i = 0; i < n; i++) {
    let eqSum = 0;
    for (let j = 0; j < n; j++) {
      if (i === j) continue;
      const seatI = activePlayers[i];
      const seatJ = activePlayers[j];
      const rawEq = equityTable.getEquity(classIndices[seatI], classIndices[seatJ]);
      const iIsIP = isIPPostflop(seatI, seatJ, config.players);
      const ipBonus = rawEq * (1 - rawEq) * k;
      const share = iIsIP ? rawEq + ipBonus : rawEq - ipBonus;
      eqSum += share;
    }
    equities[i] = eqSum / (n - 1);
  }

  let total = 0;
  for (let i = 0; i < n; i++) total += equities[i];
  if (total <= 0) total = 1;

  const tIdx = activePlayers.indexOf(traverser);
  if (tIdx === -1) return -traverserInvested;
  const opponent = activePlayers.find((s) => s !== traverser) ?? traverser;
  const traverserIsIP = isIPPostflop(traverser, opponent, config.players);
  const hrf = handRealizationFactor(classIndices[traverser], pot, config.stackSize, traverserIsIP);
  return (equities[tIdx] / total) * hrf * pot - traverserInvested;
}

// ── Hand dealing ──

function buildClassComboMap(): Array<Array<[number, number]>> {
  const classes = allHandClasses();
  return classes.map((hc) => expandHandClassToCombos(hc));
}

/**
 * Build cumulative weight array for combo-weighted hand class sampling.
 * Pairs have 6 combos, suited 4, offsuit 12.
 * Total = 13*6 + 78*4 + 78*12 = 78 + 312 + 936 = 1326.
 */
function buildCumulativeWeights(): Uint16Array {
  const classes = allHandClasses();
  const cum = new Uint16Array(NUM_HAND_CLASSES);
  let total = 0;
  for (let i = 0; i < NUM_HAND_CLASSES; i++) {
    const hc = classes[i];
    const combos = hc.length === 2 ? 6 : hc[2] === 's' ? 4 : 12;
    total += combos;
    cum[i] = total;
  }
  return cum;
}

/** Sample a hand class index with probability proportional to combo count. */
function sampleWeightedHandClass(cumWeights: Uint16Array, rng: number): number {
  const totalWeight = cumWeights[NUM_HAND_CLASSES - 1]; // 1326
  const r = (rng >>> 0) % totalWeight;
  // Binary search for the hand class
  let lo = 0,
    hi = NUM_HAND_CLASSES - 1;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (cumWeights[mid] <= r) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

interface DealResult {
  handClasses: number[];
  combos: Array<[number, number]>;
}

function dealHands(
  classComboMap: Array<Array<[number, number]>>,
  cumWeights: Uint16Array,
  seed: number,
  players: number,
): DealResult | null {
  let rng = seed;
  const handClasses: number[] = [];
  const combos: Array<[number, number]> = [];
  const usedCards = new Set<number>();

  for (let seat = 0; seat < players; seat++) {
    let found = false;

    // Retry with different hand classes if the current one has no available combos.
    // This avoids discarding the entire deal and reduces distributional bias.
    for (let retry = 0; retry < 20; retry++) {
      // Sample hand class weighted by combo count
      rng = nextRng(rng);
      const hcIdx = sampleWeightedHandClass(cumWeights, rng);
      const available = classComboMap[hcIdx];

      rng = nextRng(rng);
      const startIdx = (rng >>> 0) % available.length;
      for (let attempt = 0; attempt < available.length; attempt++) {
        const idx = (startIdx + attempt) % available.length;
        const [c1, c2] = available[idx];
        if (!usedCards.has(c1) && !usedCards.has(c2)) {
          handClasses.push(hcIdx);
          combos.push([c1, c2]);
          usedCards.add(c1);
          usedCards.add(c2);
          found = true;
          break;
        }
      }
      if (found) break;
    }

    if (!found) return null; // Extremely rare after 20 resamples
    rng = nextRng(rng);
  }

  return { handClasses, combos };
}

// ── RNG (SplitMix32) ──

function nextRng(state: number): number {
  state = (state + 0x9e3779b9) | 0;
  let z = state;
  z = Math.imul(z ^ (z >>> 16), 0x85ebca6b);
  z = Math.imul(z ^ (z >>> 13), 0xc2b2ae35);
  return (z ^ (z >>> 16)) >>> 0;
}

// ── Strategy extraction ──

export function extractSpotStrategies(
  root: PreflopActionNode,
  store: InfoSetStore,
): Map<string, Map<number, { actions: string[]; probs: number[] }>> {
  const spots = new Map<string, Map<number, { actions: string[]; probs: number[] }>>();

  function walk(node: PreflopGameNode): void {
    if (node.type === 'terminal') return;
    const act = node as PreflopActionNode;
    const numActions = act.actions.length;

    if (!spots.has(act.historyKey)) {
      spots.set(act.historyKey, new Map());
    }
    const spotMap = spots.get(act.historyKey)!;

    for (let hc = 0; hc < NUM_HAND_CLASSES; hc++) {
      const infoKey = `${hc}|${act.historyKey}`;
      const avg = store.getAverageStrategy(infoKey, numActions);
      spotMap.set(hc, {
        actions: [...act.actions],
        probs: Array.from(avg),
      });
    }

    for (const child of act.children.values()) {
      walk(child);
    }
  }

  walk(root);
  return spots;
}
