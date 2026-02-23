// Runtime lookup service for querying solved CFR strategies.
// Loads JSONL files from disk and provides fast queries by info-set key.

import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { indexToCard, cardToIndex, indexToRank } from '../abstraction/card-index.js';
import { evaluateBestHand } from '@cardpilot/poker-evaluator';

export interface StrategyEntry {
  key: string;
  probs: number[];
}

export interface QueryResult {
  strategy: StrategyEntry | null;
  source: 'exact' | 'nearest_flop' | 'none';
  boardId: number;
  flopLabel: string;
}

interface FlopMeta {
  boardId: number;
  flopCards: [number, number, number];
  iterations: number;
  bucketCount: number;
  infoSets: number;
}

/**
 * Loads and indexes solved strategies for fast runtime queries.
 */
export class LookupService {
  private strategies = new Map<string, number[]>(); // key -> probs
  private flopMetas: FlopMeta[] = [];
  private bucketCount = 50;
  private loaded = false;

  /**
   * Load all JSONL files from a solve output directory.
   */
  load(dir: string): void {
    if (!existsSync(dir)) {
      throw new Error(`CFR output directory not found: ${dir}`);
    }

    const files = readdirSync(dir).filter(f => f.endsWith('.jsonl')).sort();
    let totalEntries = 0;

    for (const file of files) {
      const metaFile = file.replace('.jsonl', '.meta.json');
      const metaPath = join(dir, metaFile);

      if (existsSync(metaPath)) {
        const meta = JSON.parse(readFileSync(metaPath, 'utf-8')) as FlopMeta;
        this.flopMetas.push(meta);
        this.bucketCount = meta.bucketCount;
      }

      const content = readFileSync(join(dir, file), 'utf-8');
      for (const line of content.split('\n')) {
        if (!line.trim()) continue;
        const entry = JSON.parse(line) as StrategyEntry;
        this.strategies.set(entry.key, entry.probs);
        totalEntries++;
      }
    }

    this.loaded = true;
    console.log(`LookupService: loaded ${totalEntries} strategies from ${files.length} flops`);
  }

  get isLoaded(): boolean {
    return this.loaded;
  }

  get size(): number {
    return this.strategies.size;
  }

  /**
   * Direct lookup by info-set key.
   */
  getByKey(key: string): number[] | null {
    return this.strategies.get(key) ?? null;
  }

  /**
   * Query strategy for a specific game state.
   *
   * @param hand - Player's hole cards as card strings (e.g., ["As", "Kh"])
   * @param board - Community cards (3-5 cards as strings)
   * @param player - 0 = OOP, 1 = IP
   * @param historyKey - Encoded action history (e.g., "xbc" for check, bet, call)
   */
  query(
    hand: [string, string],
    board: string[],
    player: 0 | 1,
    historyKey: string,
  ): QueryResult {
    if (!this.loaded) {
      return { strategy: null, source: 'none', boardId: -1, flopLabel: '' };
    }

    const flopCards = board.slice(0, 3);
    const flopIndices = flopCards.map(cardToIndex) as [number, number, number];

    // Find exact board match (order-independent)
    const flopSet = new Set(flopIndices);
    const exactMatch = this.flopMetas.find(m => {
      const metaSet = new Set(m.flopCards);
      return flopSet.size === metaSet.size && [...flopSet].every(c => metaSet.has(c));
    });

    // Determine street from history
    const street = streetFromHistory(historyKey);
    const estimatedBucket = this.computeBucket(hand, board, player);

    if (exactMatch) {
      const result = this.findBestBucket(street, exactMatch.boardId, player, historyKey, estimatedBucket);
      if (result) {
        return {
          strategy: result,
          source: 'exact',
          boardId: exactMatch.boardId,
          flopLabel: flopCards.join(' '),
        };
      }
    }

    // Try nearest flop match
    const nearest = this.findNearestFlop(flopIndices);
    if (nearest) {
      const result = this.findBestBucket(street, nearest.boardId, player, historyKey, estimatedBucket);
      if (result) {
        return {
          strategy: result,
          source: 'nearest_flop',
          boardId: nearest.boardId,
          flopLabel: nearest.flopCards.map(indexToCard).join(' '),
        };
      }
    }

    return { strategy: null, source: 'none', boardId: -1, flopLabel: '' };
  }

  /**
   * Find the best matching bucket for a given info-set pattern.
   * Tries the estimated bucket first, then searches nearby buckets.
   */
  private findBestBucket(
    street: string,
    boardId: number,
    player: 0 | 1,
    historyKey: string,
    estimatedBucket: number,
  ): StrategyEntry | null {
    // Try exact bucket first
    const exactKey = `${street}|${boardId}|${player}|${historyKey}|${estimatedBucket}`;
    const exactProbs = this.strategies.get(exactKey);
    if (exactProbs) {
      return { key: exactKey, probs: exactProbs };
    }

    // Search nearby buckets (within ±5 range)
    const searchRadius = 5;
    for (let delta = 1; delta <= searchRadius; delta++) {
      for (const d of [delta, -delta]) {
        const bucket = estimatedBucket + d;
        if (bucket < 0 || bucket >= this.bucketCount) continue;
        const key = `${street}|${boardId}|${player}|${historyKey}|${bucket}`;
        const probs = this.strategies.get(key);
        if (probs) {
          return { key, probs };
        }
      }
    }

    // Wider search: any bucket for this pattern
    for (let b = 0; b < this.bucketCount; b++) {
      const key = `${street}|${boardId}|${player}|${historyKey}|${b}`;
      const probs = this.strategies.get(key);
      if (probs) {
        return { key, probs };
      }
    }

    return null;
  }

  /**
   * Compute the hand bucket for a given hand on a board.
   * Approximate mapping — may not exactly match the solver's range-percentile buckets.
   */
  private computeBucket(hand: [string, string], board: string[], _player: 0 | 1): number {
    // Evaluate hand strength on current board
    const allCards = [...hand, ...board.slice(0, 3)]; // use flop for bucketing (static abstraction)
    const eval_ = evaluateBestHand(allCards);

    // Map hand value to bucket using simple linear mapping.
    // Hand values from evaluator are roughly 1000-60000.
    // We normalize to [0, bucketCount-1].
    // A more accurate approach would replicate the solver's range-based bucketing,
    // but for lookups this linear approximation provides reasonable results.
    const minVal = 1000;
    const maxVal = 60000;
    const normalized = Math.max(0, Math.min(1, (eval_.value - minVal) / (maxVal - minVal)));
    return Math.min(this.bucketCount - 1, Math.floor(normalized * this.bucketCount));
  }

  /**
   * Find the nearest solved flop to the query flop.
   * Uses a texture similarity metric.
   */
  private findNearestFlop(flopCards: [number, number, number]): FlopMeta | null {
    if (this.flopMetas.length === 0) return null;

    const queryFeatures = flopFeatures(flopCards);
    let bestMeta: FlopMeta | null = null;
    let bestDist = Infinity;

    for (const meta of this.flopMetas) {
      const metaFeatures = flopFeatures(meta.flopCards);
      const dist = featureDistance(queryFeatures, metaFeatures);
      if (dist < bestDist) {
        bestDist = dist;
        bestMeta = meta;
      }
    }

    return bestMeta;
  }
}

// --- Helpers ---

function streetFromHistory(historyKey: string): string {
  const slashes = (historyKey.match(/\//g) || []).length;
  if (slashes >= 2) return 'R';
  if (slashes >= 1) return 'T';
  return 'F';
}

interface FlopFeatures {
  highRank: number;
  midRank: number;
  lowRank: number;
  suitCount: number;   // 1=monotone, 2=two-tone, 3=rainbow
  maxGap: number;
  totalSpread: number;
  paired: number;       // 0 or 1
}

function flopFeatures(cards: [number, number, number]): FlopFeatures {
  const ranks = cards.map(indexToRank).sort((a, b) => b - a);
  const suits = cards.map(c => c & 3);
  const suitCount = new Set(suits).size;
  const maxGap = Math.max(ranks[0] - ranks[1], ranks[1] - ranks[2]);
  const totalSpread = ranks[0] - ranks[2];
  const paired = (ranks[0] === ranks[1] || ranks[1] === ranks[2]) ? 1 : 0;

  return {
    highRank: ranks[0],
    midRank: ranks[1],
    lowRank: ranks[2],
    suitCount,
    maxGap,
    totalSpread,
    paired,
  };
}

function featureDistance(a: FlopFeatures, b: FlopFeatures): number {
  // Weighted Euclidean distance across texture dimensions
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
