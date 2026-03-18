// Preflop all-in equity table: 169×169 hand class matchups
//
// Fast Monte Carlo approach: for each class pair, repeatedly sample
// a random combo pair + random board, evaluate, and average.
// This avoids the expensive nested combo enumeration.

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { indexToCard } from '../abstraction/card-index.js';
import { evaluateBestHand, compareHands } from '@cardpilot/poker-evaluator';
import { expandHandClassToCombos } from '../data-loaders/gto-wizard-json.js';
import { NUM_HAND_CLASSES, allHandClasses } from './preflop-types.js';

// ── EquityTable class ──

export class EquityTable {
  private data: Float32Array;

  private constructor(data: Float32Array) {
    if (data.length !== NUM_HAND_CLASSES * NUM_HAND_CLASSES) {
      throw new Error(
        `Invalid equity table size: ${data.length}, expected ${NUM_HAND_CLASSES * NUM_HAND_CLASSES}`,
      );
    }
    this.data = data;
  }

  getEquity(classIndexA: number, classIndexB: number): number {
    return this.data[classIndexA * NUM_HAND_CLASSES + classIndexB];
  }

  getEquityWithRealization(
    classIndexA: number,
    classIndexB: number,
    aIsIP: boolean,
    realizationIP: number,
    realizationOOP: number,
  ): number {
    const rawEquity = this.getEquity(classIndexA, classIndexB);
    // Bayesian realization model: each player's equity is scaled by their
    // realization factor, then normalized. This correctly penalizes OOP
    // for both strong and weak hands (no phantom boost for weak OOP hands).
    const factorA = aIsIP ? realizationIP : realizationOOP;
    const factorB = aIsIP ? realizationOOP : realizationIP;
    const adjA = rawEquity * factorA;
    const adjB = (1 - rawEquity) * factorB;
    const total = adjA + adjB;
    if (total <= 0) return 0.5;
    return adjA / total;
  }

  static load(path: string): EquityTable {
    if (!existsSync(path)) {
      throw new Error(`Equity table not found: ${path}. Run 'preflop-solve equity' first.`);
    }
    const buf = readFileSync(path);
    const magic = buf.toString('utf-8', 0, 4);
    if (magic !== 'EQ01') {
      throw new Error(`Invalid equity table magic: ${magic}`);
    }
    const size = buf.readUInt32LE(4);
    if (size !== NUM_HAND_CLASSES) {
      throw new Error(`Equity table size mismatch: ${size} vs ${NUM_HAND_CLASSES}`);
    }
    const floats = new Float32Array(
      buf.buffer,
      buf.byteOffset + 8,
      NUM_HAND_CLASSES * NUM_HAND_CLASSES,
    );
    return new EquityTable(Float32Array.from(floats));
  }

  save(path: string): void {
    const header = Buffer.alloc(8);
    header.write('EQ01', 0, 4, 'utf-8');
    header.writeUInt32LE(NUM_HAND_CLASSES, 4);
    const body = Buffer.from(this.data.buffer, this.data.byteOffset, this.data.byteLength);
    writeFileSync(path, Buffer.concat([header, body]));
  }

  static fromData(data: Float32Array): EquityTable {
    return new EquityTable(data);
  }

  getRawData(): Float32Array {
    return this.data;
  }
}

// ── Fast RNG (SplitMix32) ──

let _rng = Date.now() | 0;
function fastRng(): number {
  _rng = (_rng + 0x9e3779b9) | 0;
  let z = _rng;
  z = Math.imul(z ^ (z >>> 16), 0x85ebca6b);
  z = Math.imul(z ^ (z >>> 13), 0xc2b2ae35);
  return (z ^ (z >>> 16)) >>> 0;
}
function seedRng(s: number): void {
  _rng = s | 0;
}

// ── Fast Monte Carlo equity computation ──

/**
 * Compute equity for class pair by sampling random combo pairs + boards.
 * Much faster than enumerating all combos × all boards.
 *
 * @param classIdxA Hand class index for player A (0-168)
 * @param classIdxB Hand class index for player B (0-168)
 * @param combosA Pre-expanded combos for class A
 * @param combosB Pre-expanded combos for class B
 * @param samples Number of Monte Carlo samples
 */
function computeClassEquityMC(
  combosA: Array<[number, number]>,
  combosB: Array<[number, number]>,
  samples: number,
): number {
  let wins = 0;
  let ties = 0;
  let total = 0;

  for (let s = 0; s < samples; s++) {
    // Pick random combo from A
    const aIdx = fastRng() % combosA.length;
    const [a1, a2] = combosA[aIdx];

    // Pick random combo from B (must not conflict)
    let bIdx = fastRng() % combosB.length;
    let attempts = 0;
    while (attempts < combosB.length) {
      const [b1, b2] = combosB[bIdx];
      if (b1 !== a1 && b1 !== a2 && b2 !== a1 && b2 !== a2) break;
      bIdx = (bIdx + 1) % combosB.length;
      attempts++;
    }
    if (attempts >= combosB.length) continue; // Can't find non-conflicting combo (same ranks)

    const [b1, b2] = combosB[bIdx];

    // Sample 5 board cards (no conflicts)
    const dead = [a1, a2, b1, b2];
    const board = sampleBoard(dead);
    if (!board) continue;

    // Evaluate
    const cardA1 = indexToCard(a1);
    const cardA2 = indexToCard(a2);
    const cardB1 = indexToCard(b1);
    const cardB2 = indexToCard(b2);
    const boardCards = board.map(indexToCard);

    const evalA = evaluateBestHand([cardA1, cardA2, ...boardCards]);
    const evalB = evaluateBestHand([cardB1, cardB2, ...boardCards]);
    const cmp = compareHands(evalA, evalB);

    if (cmp > 0) wins++;
    else if (cmp === 0) ties++;
    total++;
  }

  if (total === 0) return 0.5;
  return (wins + ties * 0.5) / total;
}

function sampleBoard(dead: number[]): number[] | null {
  // Build available cards
  const avail: number[] = [];
  const deadSet = new Set(dead);
  for (let i = 0; i < 52; i++) {
    if (!deadSet.has(i)) avail.push(i);
  }

  if (avail.length < 5) return null;

  // Fisher-Yates partial shuffle for 5 cards
  for (let i = 0; i < 5; i++) {
    const j = i + (fastRng() % (avail.length - i));
    [avail[i], avail[j]] = [avail[j], avail[i]];
  }

  return [avail[0], avail[1], avail[2], avail[3], avail[4]];
}

// ── Full table computation ──

/**
 * Compute the full 169×169 equity table using fast Monte Carlo.
 *
 * @param samplesPerPair Number of Monte Carlo samples per class pair
 * @param startPair Starting pair index (for distributed computation)
 * @param endPair Ending pair index (exclusive)
 * @param onProgress Progress callback
 */
export function computeFullEquityTable(
  startPair = 0,
  endPair?: number,
  samplesPerPair = 5000,
  onProgress?: (completed: number, total: number) => void,
): Float32Array {
  const classes = allHandClasses();
  const data = new Float32Array(NUM_HAND_CLASSES * NUM_HAND_CLASSES);

  // Pre-expand all hand class combos
  const allCombos: Array<Array<[number, number]>> = [];
  for (const hc of classes) {
    allCombos.push(expandHandClassToCombos(hc));
  }

  // Fill diagonal with 0.5
  for (let i = 0; i < NUM_HAND_CLASSES; i++) {
    data[i * NUM_HAND_CLASSES + i] = 0.5;
  }

  const totalPairs = (NUM_HAND_CLASSES * (NUM_HAND_CLASSES - 1)) / 2;
  const end = endPair ?? totalPairs;

  seedRng(42); // Deterministic

  let pairIdx = 0;
  let completed = 0;

  for (let i = 0; i < NUM_HAND_CLASSES; i++) {
    for (let j = i + 1; j < NUM_HAND_CLASSES; j++) {
      if (pairIdx >= startPair && pairIdx < end) {
        const eq = computeClassEquityMC(allCombos[i], allCombos[j], samplesPerPair);
        data[i * NUM_HAND_CLASSES + j] = eq;
        data[j * NUM_HAND_CLASSES + i] = 1 - eq;

        completed++;
        if (onProgress && completed % 200 === 0) {
          onProgress(completed, end - startPair);
        }
      }
      pairIdx++;
    }
  }

  if (onProgress) onProgress(completed, end - startPair);
  return data;
}
