#!/usr/bin/env tsx
/**
 * Coaching Dataset Generator
 *
 * Converts solved CFR strategies (JSONL + meta.json) into training data
 * for the coaching neural network.
 *
 * Uses .meta.json nodes map for action labels, pot, stacks — avoiding the
 * action-count mismatch bug in inferActionsFromHistory().
 *
 * Key format in JSONL: "street|boardId|player|historyKey|handClass"
 *   - Hand-class lines: 5 parts (e.g. "F|13|0||AKs")
 *   - Aggregate lines: 4 parts (e.g. "F|13|0|") — skipped
 *
 * Usage:
 *   npx tsx packages/cfr-solver/src/scripts/coaching-dataset.ts \
 *     --cfr-dir data/cfr/coach_hu_srp_100bb/ \
 *     --output data/coaching/hu_srp_100bb/ \
 *     --config coach_hu_srp_100bb \
 *     --max-flops 200
 */

import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { parseArgs } from 'node:util';

import {
  COACHING_NUM_ACTIONS,
  actionToIndex,
  HISTORY_TOKEN_VOCAB,
  MAX_HISTORY_LENGTH,
} from '../integration/action-translation.js';
import { getTreeConfig, type TreeConfigName } from '../tree/tree-config.js';
import type { TreeConfig } from '../types.js';
import { replayHistory } from './cfr-to-training-data.js';

// ══════════════════════════════════════════════
//   COACHING TRAINING SAMPLE SCHEMA
// ══════════════════════════════════════════════

export interface CoachingTrainingSample {
  // === Input Features ===
  hole: [number, number]; // card indices 0-51
  board: number[]; // 3-5 card indices
  position: number; // 0=OOP, 1=IP (postflop)
  street: number; // 0=flop, 1=turn, 2=river
  pot: number; // in BB
  stack: number; // effective stack in BB
  spr: number; // stack-to-pot ratio
  facingBet: number; // 0 if opening action, else bet level in BB
  actionHistory: number[]; // token IDs, max len 30
  legalMask: number[]; // 16-dim (1=legal, 0=illegal)

  // === Targets ===
  policy: number[]; // 16-dim, CFR average strategy (0 for illegal)
  qValues: number[]; // 16-dim, per-action EV in BB (NaN for illegal)
  stateValue: number; // weighted avg of Q-values by policy

  // === Metadata ===
  spotId: string; // e.g. "coach_hu_srp_100bb"
  flopId: number; // board ID (hash of flop card indices)
  weight: number; // reach probability (for sampling)
}

// ══════════════════════════════════════════════
//   META DATA TYPES (from .meta.json)
// ══════════════════════════════════════════════

interface MetaNode {
  player: number;
  actions: string[];
  pot: number;
  stacks: number[];
}

interface FlopMetaV3 {
  version: string;
  configName: string;
  boardId: number;
  flopCards: number[];
  iterations: number;
  bucketCount: number;
  infoSets: number;
  elapsedMs: number;
  timestamp: string;
  nodes: Record<string, MetaNode>;
}

// ══════════════════════════════════════════════
//   HAND CLASS → HOLE CARDS
// ══════════════════════════════════════════════

const RANKS_STR = '23456789TJQKA';

/**
 * Convert a hand class string (e.g. "AKs", "32o", "AA") to representative
 * hole card indices, avoiding dead cards (board).
 *
 * Card index = rank * 4 + suit, where rank 0=2..12=A, suit 0=c,1=d,2=h,3=s
 */
function handClassToCombo(handClass: string, deadCards: Set<number>): [number, number] | null {
  if (handClass.length === 2) {
    // Pair: "AA", "KK", etc.
    const rank = RANKS_STR.indexOf(handClass[0]);
    if (rank < 0) return null;
    const cards: number[] = [];
    for (let s = 0; s < 4; s++) {
      const card = rank * 4 + s;
      if (!deadCards.has(card)) cards.push(card);
      if (cards.length === 2) break;
    }
    return cards.length >= 2 ? [cards[0], cards[1]] : null;
  }

  if (handClass.length === 3) {
    const highRank = RANKS_STR.indexOf(handClass[0]);
    const lowRank = RANKS_STR.indexOf(handClass[1]);
    if (highRank < 0 || lowRank < 0) return null;

    if (handClass[2] === 's') {
      // Suited: same suit for both cards
      for (let s = 0; s < 4; s++) {
        const c1 = highRank * 4 + s;
        const c2 = lowRank * 4 + s;
        if (!deadCards.has(c1) && !deadCards.has(c2)) return [c1, c2];
      }
      return null;
    } else {
      // Offsuit: different suits
      for (let s1 = 0; s1 < 4; s1++) {
        for (let s2 = 0; s2 < 4; s2++) {
          if (s1 === s2) continue;
          const c1 = highRank * 4 + s1;
          const c2 = lowRank * 4 + s2;
          if (!deadCards.has(c1) && !deadCards.has(c2)) return [c1, c2];
        }
      }
      return null;
    }
  }

  return null;
}

// ══════════════════════════════════════════════
//   HISTORY KEY → TOKEN SEQUENCE
// ══════════════════════════════════════════════

/**
 * Convert a historyKey string (e.g. "x1c/x2") to a token sequence.
 */
function historyKeyToTokens(historyKey: string, _config: TreeConfig): number[] {
  const tokens: number[] = [];
  let facingBet = false;

  for (const char of historyKey) {
    if (char === '/') {
      tokens.push(HISTORY_TOKEN_VOCAB.street_sep);
      facingBet = false;
      continue;
    }

    switch (char) {
      case 'x':
        tokens.push(HISTORY_TOKEN_VOCAB.check);
        break;
      case 'c':
        tokens.push(HISTORY_TOKEN_VOCAB.call);
        facingBet = false;
        break;
      case 'f':
        tokens.push(HISTORY_TOKEN_VOCAB.fold);
        break;
      case 'A':
        tokens.push(facingBet ? HISTORY_TOKEN_VOCAB.raise_allin : HISTORY_TOKEN_VOCAB.bet_allin);
        facingBet = true;
        break;
      default: {
        const sizeIdx = parseInt(char, 10) - 1;
        if (isNaN(sizeIdx) || sizeIdx < 0) break;

        if (facingBet) {
          const raiseKey = `raise_${sizeIdx}` as keyof typeof HISTORY_TOKEN_VOCAB;
          tokens.push(HISTORY_TOKEN_VOCAB[raiseKey] ?? HISTORY_TOKEN_VOCAB.raise_0);
        } else {
          const betKey = `bet_${sizeIdx}` as keyof typeof HISTORY_TOKEN_VOCAB;
          tokens.push(HISTORY_TOKEN_VOCAB[betKey] ?? HISTORY_TOKEN_VOCAB.bet_0);
        }
        facingBet = true;
        break;
      }
    }

    if (tokens.length >= MAX_HISTORY_LENGTH) break;
  }

  // Pad to MAX_HISTORY_LENGTH
  while (tokens.length < MAX_HISTORY_LENGTH) {
    tokens.push(HISTORY_TOKEN_VOCAB.PAD);
  }

  return tokens;
}

// ══════════════════════════════════════════════
//   CFR PROBS → 16-DIM POLICY VECTOR
// ══════════════════════════════════════════════

/**
 * Convert CFR action probabilities to the 16-dim coaching policy vector.
 * Maps each CFR action to its canonical index.
 */
function toPolicyVector(
  actions: string[],
  probs: number[],
): { policy: number[]; legalMask: number[] } {
  const policy = new Array(COACHING_NUM_ACTIONS).fill(0);
  const legalMask = new Array(COACHING_NUM_ACTIONS).fill(0);

  for (let i = 0; i < actions.length; i++) {
    const idx = actionToIndex(actions[i]);
    if (idx >= 0) {
      policy[idx] = probs[i] ?? 0;
      legalMask[idx] = 1;
    }
  }

  // Normalize policy (should already sum to ~1, but ensure)
  const sum = policy.reduce((a: number, b: number) => a + b, 0);
  if (sum > 0) {
    for (let i = 0; i < policy.length; i++) {
      policy[i] /= sum;
    }
  }

  return { policy, legalMask };
}

// ══════════════════════════════════════════════
//   SAMPLE CREATION
// ══════════════════════════════════════════════

/**
 * Create a coaching training sample from a solved info-set.
 * Uses meta node for action labels (fixes action count mismatch).
 */
function createSampleFromMeta(
  historyKey: string,
  handClass: string,
  probs: number[],
  metaNode: MetaNode,
  boardCards: number[],
  configName: string,
  flopId: number,
  config: TreeConfig,
  deadCards: Set<number>,
  actionEVs?: number[],
): CoachingTrainingSample | null {
  // Use meta actions (THE FIX — no more inferActionsFromHistory)
  const actions = metaNode.actions;
  if (actions.length !== probs.length) return null;

  // Convert hand class to representative hole cards
  const hole = handClassToCombo(handClass, deadCards);
  if (!hole) return null;

  const { policy, legalMask } = toPolicyVector(actions, probs);
  const tokens = historyKeyToTokens(historyKey, config);

  // Use replayHistory for facingBet (reliable for this)
  const state = replayHistory(historyKey, config);

  // Use meta node's pot and stacks (ground truth from tree builder)
  const pot = metaNode.pot;
  const effectiveStack = Math.min(metaNode.stacks[0], metaNode.stacks[1]);

  // Map per-action Q-values (in chips) to 16-dim coaching vector (in BB)
  const qValues = new Array(COACHING_NUM_ACTIONS).fill(NaN);
  if (actionEVs && actionEVs.length === actions.length) {
    for (let i = 0; i < actions.length; i++) {
      const idx = actionToIndex(actions[i]);
      if (idx >= 0) {
        qValues[idx] = actionEVs[i]; // already in chips (= BB for 100bb game)
      }
    }
  }

  // State value = weighted average of Q-values by policy
  let stateValue = 0;
  if (actionEVs && actionEVs.length === actions.length) {
    for (let i = 0; i < COACHING_NUM_ACTIONS; i++) {
      if (isFinite(qValues[i])) {
        stateValue += policy[i] * qValues[i];
      }
    }
  }

  return {
    hole,
    board: boardCards,
    position: metaNode.player,
    street: 0, // flop only (single-street tree)
    pot,
    stack: effectiveStack,
    spr: pot > 0 ? effectiveStack / pot : 0,
    facingBet: state.facingBet,
    actionHistory: tokens,
    legalMask,
    policy,
    qValues,
    stateValue,
    spotId: configName,
    flopId,
    weight: 1.0,
  };
}

// ══════════════════════════════════════════════
//   CLI ENTRY POINT
// ══════════════════════════════════════════════

async function main() {
  const { values } = parseArgs({
    options: {
      'cfr-dir': { type: 'string' },
      output: { type: 'string' },
      config: { type: 'string' },
      'max-flops': { type: 'string', default: '0' },
    },
  });

  const cfrDir = resolve(values['cfr-dir'] ?? '');
  const outputDir = resolve(values['output'] ?? 'data/coaching/output');
  const configName = (values['config'] ?? 'coach_hu_srp_100bb') as TreeConfigName;
  const maxFlops = parseInt(values['max-flops'] ?? '0', 10);

  if (!existsSync(cfrDir)) {
    console.error(`CFR directory not found: ${cfrDir}`);
    process.exit(1);
  }

  mkdirSync(outputDir, { recursive: true });

  const config = getTreeConfig(configName);
  console.log(`Config: ${configName}`);
  console.log(`CFR dir: ${cfrDir}`);
  console.log(`Output: ${outputDir}`);

  // Scan for meta.json files (each has a companion .jsonl)
  const metaFiles = readdirSync(cfrDir)
    .filter((f) => f.endsWith('.meta.json'))
    .sort();
  const flopFiles = maxFlops > 0 ? metaFiles.slice(0, maxFlops) : metaFiles;

  console.log(`Found ${metaFiles.length} solved flops, processing ${flopFiles.length}`);

  let totalSamples = 0;
  let totalSkipped = 0;
  let flopCount = 0;

  for (const metaFile of flopFiles) {
    const metaPath = join(cfrDir, metaFile);
    const jsonlFile = metaFile.replace('.meta.json', '.jsonl');
    const jsonlPath = join(cfrDir, jsonlFile);

    if (!existsSync(jsonlPath)) {
      console.warn(`  Missing JSONL for ${metaFile}, skipping`);
      continue;
    }

    // Load meta data
    const meta: FlopMetaV3 = JSON.parse(readFileSync(metaPath, 'utf-8'));
    const boardCards = meta.flopCards;
    const deadCards = new Set(boardCards);

    // Process JSONL lines
    const lines = readFileSync(jsonlPath, 'utf-8').trim().split('\n');
    const samples: CoachingTrainingSample[] = [];
    let skipped = 0;

    for (const line of lines) {
      if (!line.trim()) continue;

      try {
        const entry = JSON.parse(line);
        const parts = (entry.key as string).split('|');

        // Skip aggregate lines (no hand class — parts[4] is undefined or empty)
        if (parts.length < 5 || !parts[4]) {
          continue;
        }

        const historyKey = parts[3];
        const handClass = parts[4];

        // Look up meta node for this history key
        const metaNode = meta.nodes[historyKey];
        if (!metaNode) {
          skipped++;
          continue;
        }

        const sample = createSampleFromMeta(
          historyKey,
          handClass,
          entry.probs,
          metaNode,
          boardCards,
          configName,
          meta.boardId,
          config,
          deadCards,
          entry.actionEVs, // per-action Q-values (if available)
        );

        if (sample) {
          samples.push(sample);
        } else {
          skipped++;
        }
      } catch {
        skipped++;
      }
    }

    if (samples.length > 0) {
      const outPath = join(outputDir, jsonlFile);
      const outLines = samples.map((s) => JSON.stringify(s)).join('\n');
      writeFileSync(outPath, outLines + '\n');
    }

    totalSamples += samples.length;
    totalSkipped += skipped;
    flopCount++;

    if (flopCount % 100 === 0 || flopCount === flopFiles.length) {
      console.log(
        `  ${flopCount}/${flopFiles.length} flops, ${totalSamples} samples, ${totalSkipped} skipped`,
      );
    }
  }

  console.log(
    `\nDone. ${flopCount} flops → ${totalSamples} coaching training samples (${totalSkipped} skipped).`,
  );
}

// Only run if executed directly
const isMain = process.argv[1]?.includes('coaching-dataset');
if (isMain) {
  main().catch((err) => {
    console.error('Fatal error:', err);
    process.exit(1);
  });
}

export { historyKeyToTokens, toPolicyVector, createSampleFromMeta, handClassToCombo };
