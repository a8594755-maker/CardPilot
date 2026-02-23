// CFR strategy advisor — bridges solved CFR data into the PostflopEngine.
//
// Uses the BinaryStrategyReader (90MB gzip) for O(log n) lookups, combined
// with flop metadata for board matching. Falls back to JSONL LookupService
// for small datasets.

import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import {
  BinaryStrategyReader,
  buildTree,
  V1_TREE_CONFIG,
} from '@cardpilot/cfr-solver';
import type { Action, GameNode } from '@cardpilot/cfr-solver';
import type { PostflopFrequency } from '@cardpilot/shared-types';
import type { PostflopContext } from './postflop-engine.js';
import { classifyHandOnBoard } from '@cardpilot/poker-evaluator';

// V1 bet size midpoints for classifying observed bets as small/big
const BET_THRESHOLDS: Record<string, number> = {
  FLOP: (0.33 + 0.75) / 2,   // 0.54
  TURN: (0.50 + 1.00) / 2,   // 0.75
  RIVER: (0.75 + 1.50) / 2,  // 1.125
};

interface FlopMeta {
  boardId: number;
  flopCards: [number, number, number];
}

export interface CfrQueryResult {
  frequency: PostflopFrequency;
  source: 'cfr_exact' | 'cfr_nearest';
  confidence: number;
}

export class CfrAdvisor {
  private reader: BinaryStrategyReader | null = null;
  private flopMetas: FlopMeta[] = [];
  private actionIndex = new Map<string, Action[]>();
  private loaded = false;

  constructor() {
    this.buildActionIndex();
  }

  /** Build history→actions index from the V1 tree. */
  private buildActionIndex(): void {
    const root = buildTree(V1_TREE_CONFIG);
    const walk = (node: GameNode) => {
      if (node.type === 'terminal') return;
      this.actionIndex.set(node.historyKey, [...node.actions]);
      for (const child of node.children.values()) walk(child);
    };
    walk(root);
  }

  /**
   * Load CFR data. Accepts:
   *   - A .bin.gz or .bin binary file path
   *   - A directory containing the binary + meta files, or just meta files
   */
  load(binaryPath: string, metaDir?: string): boolean {
    try {
      // Load binary reader
      const binPath = binaryPath.endsWith('.gz') || binaryPath.endsWith('.bin')
        ? binaryPath
        : join(binaryPath, 'v1_hu_srp_50bb.bin.gz');

      if (!existsSync(binPath)) {
        console.warn(`[cfr-advisor] binary file not found: ${binPath}`);
        return false;
      }

      this.reader = new BinaryStrategyReader(binPath);

      // Load flop metadata from JSONL directory (tiny files, ~200 × 200 bytes)
      const mDir = metaDir ?? binaryPath.replace(/\.bin(\.gz)?$/, '');
      if (existsSync(mDir)) {
        const metaFiles = readdirSync(mDir).filter(f => f.endsWith('.meta.json')).sort();
        for (const file of metaFiles) {
          const meta = JSON.parse(readFileSync(join(mDir, file), 'utf-8'));
          this.flopMetas.push({ boardId: meta.boardId, flopCards: meta.flopCards });
        }
      }

      this.loaded = true;
      console.log(`[cfr-advisor] loaded binary: ${this.reader.entryCount} entries, ${this.flopMetas.length} flop metas`);
      return true;
    } catch (e) {
      console.warn(`[cfr-advisor] Failed to load: ${(e as Error).message}`);
      return false;
    }
  }

  get isLoaded(): boolean {
    return this.loaded;
  }

  /**
   * Query CFR strategy for a given postflop context.
   * Returns null if CFR data is unavailable or the context doesn't match.
   */
  query(context: PostflopContext): CfrQueryResult | null {
    if (!this.loaded || !this.reader) return null;
    // Only support HU SRP
    if (context.numVillains !== 1) return null;
    if (context.potType && context.potType !== 'SRP') return null;

    const player: 0 | 1 = context.heroInPosition ? 1 : 0;
    const historyKey = this.buildHistoryKey(context);
    if (historyKey === null) return null;

    const actions = this.actionIndex.get(historyKey);
    if (!actions) return null;

    // Find matching board
    const boardMatch = this.findBoard(context.board);
    if (!boardMatch) return null;

    // Estimate hand bucket
    const bucket = this.estimateBucket(context);
    const streetChar = context.street === 'FLOP' ? 'F' : context.street === 'TURN' ? 'T' : 'R';

    // Try exact bucket, then nearby, then any
    let probs: number[] | null = null;
    let source: 'cfr_exact' | 'cfr_nearest' = boardMatch.exact ? 'cfr_exact' : 'cfr_nearest';

    // Try estimated bucket first, then ±5, then wider
    const bucketsToTry = [bucket];
    for (let d = 1; d <= 5; d++) {
      if (bucket + d < 50) bucketsToTry.push(bucket + d);
      if (bucket - d >= 0) bucketsToTry.push(bucket - d);
    }

    for (const b of bucketsToTry) {
      const key = `${streetChar}|${boardMatch.boardId}|${player}|${historyKey}|${b}`;
      probs = this.reader.lookup(key);
      if (probs) break;
    }

    // If still no match, try all buckets
    if (!probs) {
      for (let b = 0; b < 50; b++) {
        const key = `${streetChar}|${boardMatch.boardId}|${player}|${historyKey}|${b}`;
        probs = this.reader.lookup(key);
        if (probs) break;
      }
    }

    if (!probs || probs.length !== actions.length) return null;

    const frequency = this.mapToFrequency(actions, probs);
    if (!frequency) return null;

    return { frequency, source, confidence: source === 'cfr_exact' ? 0.85 : 0.65 };
  }

  /** Find the matching board (exact or nearest texture). */
  private findBoard(board: string[]): { boardId: number; exact: boolean } | null {
    if (this.flopMetas.length === 0) return null;

    const flopCards = board.slice(0, 3);
    const flopIndices = flopCards.map(cardToIndex);

    // Exact match (order-independent)
    const flopSet = new Set(flopIndices);
    const exact = this.flopMetas.find(m => {
      const s = new Set(m.flopCards);
      return s.size === flopSet.size && [...flopSet].every(c => s.has(c));
    });
    if (exact) return { boardId: exact.boardId, exact: true };

    // Nearest flop by texture features
    const queryFeats = flopFeatures(flopIndices);
    let bestId = 0;
    let bestDist = Infinity;
    for (const meta of this.flopMetas) {
      const dist = featureDistance(queryFeats, flopFeatures(meta.flopCards));
      if (dist < bestDist) {
        bestDist = dist;
        bestId = meta.boardId;
      }
    }
    return { boardId: bestId, exact: false };
  }

  /** Estimate the hand bucket using hand classification. */
  private estimateBucket(context: PostflopContext): number {
    const handClass = classifyHandOnBoard(context.heroHand, context.board);
    // Map hand strength to a bucket (0-49)
    if (handClass.type === 'made_hand') {
      if (handClass.strength === 'strong') return 40 + Math.floor(Math.random() * 10);
      if (handClass.strength === 'medium') return 20 + Math.floor(Math.random() * 15);
      return 8 + Math.floor(Math.random() * 12);
    }
    if (handClass.type === 'draw') return 15 + Math.floor(Math.random() * 15);
    return Math.floor(Math.random() * 10);
  }

  /**
   * Convert game-server action history into a CFR history key string.
   * Returns null if the history can't be mapped to V1 tree.
   */
  private buildHistoryKey(context: PostflopContext): string | null {
    if (!context.actionHistory || context.actionHistory.length === 0) return '';

    const postflopActions = context.actionHistory.filter(
      a => a.street === 'FLOP' || a.street === 'TURN' || a.street === 'RIVER'
    );

    let history = '';
    let currentStreet: string | null = null;
    let runningPot = V1_TREE_CONFIG.startingPot;

    for (const action of postflopActions) {
      if (currentStreet !== null && action.street !== currentStreet) {
        history += '/';
      }
      currentStreet = action.street;

      switch (action.type) {
        case 'check':
          history += 'x';
          break;
        case 'call':
          history += 'c';
          runningPot += action.amount;
          break;
        case 'fold':
          history += 'f';
          break;
        case 'all_in':
          history += 'A';
          runningPot += action.amount;
          break;
        case 'raise': {
          const fraction = runningPot > 0 ? action.amount / runningPot : 1;
          const threshold = BET_THRESHOLDS[action.street] ?? 0.75;
          history += fraction <= threshold ? 'a' : 'b';
          runningPot += action.amount;
          break;
        }
        default:
          break;
      }
    }

    return history;
  }

  /**
   * Map CFR action probs to PostflopFrequency.
   * When facing a bet, fold is excluded so sum < 1 (fold is implicit).
   */
  private mapToFrequency(actions: Action[], probs: number[]): PostflopFrequency | null {
    let check = 0;
    let betSmall = 0;
    let betBig = 0;

    for (let i = 0; i < actions.length; i++) {
      const p = probs[i];
      switch (actions[i]) {
        case 'check':
        case 'call':
          check += p;
          break;
        case 'bet_small':
        case 'raise_small':
          betSmall += p;
          break;
        case 'bet_big':
        case 'raise_big':
          betBig += p;
          break;
        case 'allin':
          betBig += p;
          break;
        case 'fold':
          // Intentionally excluded — fold is implicit (1 - sum)
          break;
      }
    }

    const sum = check + betSmall + betBig;
    if (sum < 0.01) return null;

    // Don't normalize: when facing a bet, sum < 1 and the gap is fold
    return { check, betSmall, betBig };
  }
}

// --- Card conversion helpers ---

function cardToIndex(card: string): number {
  const rankStr = card[0];
  const suitStr = card[1];
  const ranks = '23456789TJQKA';
  const suits = 'cdhs';
  const rank = ranks.indexOf(rankStr.toUpperCase());
  const suit = suits.indexOf(suitStr.toLowerCase());
  if (rank < 0 || suit < 0) return -1;
  return rank * 4 + suit;
}

function indexToRank(index: number): number {
  return Math.floor(index / 4);
}

// --- Flop texture features ---

interface FlopFeats {
  highRank: number;
  midRank: number;
  lowRank: number;
  suitCount: number;
  maxGap: number;
  totalSpread: number;
  paired: number;
}

function flopFeatures(cards: number[]): FlopFeats {
  const ranks = cards.map(indexToRank).sort((a, b) => b - a);
  const suits = cards.map(c => c & 3);
  const suitCount = new Set(suits).size;
  const maxGap = Math.max(ranks[0] - ranks[1], ranks[1] - ranks[2]);
  const totalSpread = ranks[0] - ranks[2];
  const paired = (ranks[0] === ranks[1] || ranks[1] === ranks[2]) ? 1 : 0;
  return { highRank: ranks[0], midRank: ranks[1], lowRank: ranks[2], suitCount, maxGap, totalSpread, paired };
}

function featureDistance(a: FlopFeats, b: FlopFeats): number {
  return (
    3 * Math.abs(a.highRank - b.highRank) +
    2 * Math.abs(a.midRank - b.midRank) +
    1 * Math.abs(a.lowRank - b.lowRank) +
    5 * Math.abs(a.suitCount - b.suitCount) +
    2 * Math.abs(a.maxGap - b.maxGap) +
    1 * Math.abs(a.totalSpread - b.totalSpread) +
    4 * Math.abs(a.paired - b.paired)
  );
}
