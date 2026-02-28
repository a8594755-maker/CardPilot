// Preflop CFR+ solver for 6-max poker.
//
// Uses Chance Sampling MCCFR:
//   - Sample one deal (hands for all 6 players) = the only sampling
//   - Full tree traversal: at EVERY node, explore ALL actions
//   - Traverser nodes: compute counterfactual values, update regrets + strategy sums
//   - Opponent nodes: compute weighted expected value over all actions (no sampling)
//
// This eliminates the variance from External Sampling at opponent nodes,
// giving every info set exact opponent-strategy-weighted values per iteration.
//
// Per iteration:
//   1. Deal random hand combos to 6 players (weighted by combo count)
//   2. Pick one traverser (round-robin)
//   3. Full tree traversal per Chance Sampling
//   4. Update regrets (CFR+: floor at 0) and strategy sums

import type { PreflopGameNode, PreflopActionNode, PreflopSolveConfig } from './preflop-types.js';
import { NUM_PLAYERS, NUM_HAND_CLASSES, allHandClasses } from './preflop-types.js';
import { InfoSetStore } from '../engine/info-set-store.js';
import { expandHandClassToCombos } from '../data-loaders/gto-wizard-json.js';
import { EquityTable } from './equity-table.js';
import { isIPPostflop } from './preflop-config.js';

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
  const startTime = Date.now();

  for (let iter = 0; iter < iterations; iter++) {
    // Round-robin traverser
    const traverser = iter % NUM_PLAYERS;

    // Deal hands (combo-weighted distribution) — the ONLY sampling
    rng = nextRng(rng);
    const deal = dealHands(classComboMap, cumWeights, rng);
    if (!deal) continue;

    // Full tree traversal — no opponent action sampling
    // Linear weighting: later iterations contribute more to the average strategy
    const iterWeight = iter + 1;
    cfrChanceSampling(
      root, store, equityTable, config,
      deal.handClasses,
      traverser,
      iterWeight,
      1.0, // opponentReach: product of opponent strategy probs along path
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

  const strategy = store.getCurrentStrategy(infoKey, numActions);

  if (player === traverser) {
    // ── Traverser's node: explore ALL actions ──
    const actionValues = new Float64Array(numActions);
    let nodeValue = 0;

    for (let a = 0; a < numActions; a++) {
      const child = act.children.get(act.actions[a])!;
      // Pass same opponentReach (traverser's action doesn't change opponent reach)
      actionValues[a] = cfrChanceSampling(
        child, store, equityTable, config,
        handClasses, traverser, iterWeight, opponentReach,
      );
      nodeValue += strategy[a] * actionValues[a];
    }

    // Update regrets weighted by opponent reach probability (CFR+: floor at 0)
    // This ensures deep nodes correctly weight by how often opponents reach them
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
    // Update opponentReach for each branch (multiply by action probability)
    let nodeValue = 0;
    for (let a = 0; a < numActions; a++) {
      if (strategy[a] > 1e-8) { // Skip zero-probability actions for efficiency
        const child = act.children.get(act.actions[a])!;
        const childValue = cfrChanceSampling(
          child, store, equityTable, config,
          handClasses, traverser, iterWeight,
          opponentReach * strategy[a], // accumulate opponent reach
        );
        nodeValue += strategy[a] * childValue;
      }
    }
    return nodeValue;
  }
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
      return winner === traverser ? (pot - traverserInvested) : -traverserInvested;
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
    const aIsIP = isIPPostflop(seatA, seatB);
    let traverserShare: number;
    if (traverser === seatA) {
      traverserShare = aIsIP ? rawEqA + ipBonus : rawEqA - ipBonus;
    } else {
      traverserShare = aIsIP ? (1 - rawEqA) - ipBonus : (1 - rawEqA) + ipBonus;
    }
    return traverserShare * pot - traverserInvested;
  }

  // Multiway — pairwise approximation
  return multiWayTerminalValue(activePlayers, classIndices, equityTable, config, pot, traverser, traverserInvested);
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
      const iIsIP = isIPPostflop(seatI, seatJ);
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
  return (equities[tIdx] / total) * pot - traverserInvested;
}

// ── Hand dealing ──

function buildClassComboMap(): Array<Array<[number, number]>> {
  const classes = allHandClasses();
  return classes.map(hc => expandHandClassToCombos(hc));
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
  let lo = 0, hi = NUM_HAND_CLASSES - 1;
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
): DealResult | null {
  let rng = seed;
  const handClasses: number[] = [];
  const combos: Array<[number, number]> = [];
  const usedCards = new Set<number>();

  for (let seat = 0; seat < NUM_PLAYERS; seat++) {
    // Sample hand class weighted by combo count
    rng = nextRng(rng);
    const hcIdx = sampleWeightedHandClass(cumWeights, rng);
    const available = classComboMap[hcIdx];
    let found = false;

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

    if (!found) return null;
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
