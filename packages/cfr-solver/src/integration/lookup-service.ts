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
  version?: string;
  keyFormat?: string;
}

/**
 * Loads and indexes solved strategies for fast runtime queries.
 */
export class LookupService {
  private strategies = new Map<string, number[]>(); // key -> probs
  private flopMetas: FlopMeta[] = [];
  private bucketCount = 50;
  private loaded = false;
  private keyFormatV2 = false;

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
        if (meta.keyFormat === 'v2' || meta.version === 'v2') {
          this.keyFormatV2 = true;
        }
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
    const estimatedBuckets = this.computeBucketV2(hand, board, player);

    if (exactMatch) {
      const result = this.findBestBucketV2(street, exactMatch.boardId, player, historyKey, estimatedBuckets);
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
      const result = this.findBestBucketV2(street, nearest.boardId, player, historyKey, estimatedBuckets);
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
   * Build a V2 bucket key suffix for the given street.
   */
  private buildBucketSuffix(
    street: string,
    buckets: { flop: number; turn: number; river: number },
  ): string {
    if (!this.keyFormatV2) {
      // V1 fallback: single bucket per street
      if (street === 'T') return `${buckets.turn}`;
      if (street === 'R') return `${buckets.river}`;
      return `${buckets.flop}`;
    }
    // V2: per-street bucket IDs
    if (street === 'T') return `${buckets.flop}-${buckets.turn}`;
    if (street === 'R') return `${buckets.flop}-${buckets.turn}-${buckets.river}`;
    return `${buckets.flop}`;
  }

  /**
   * Find the best matching bucket for a V2 info-set key.
   */
  private findBestBucketV2(
    street: string,
    boardId: number,
    player: 0 | 1,
    historyKey: string,
    estimatedBuckets: { flop: number; turn: number; river: number },
  ): StrategyEntry | null {
    // Try exact bucket combination first
    const suffix = this.buildBucketSuffix(street, estimatedBuckets);
    const exactKey = `${street}|${boardId}|${player}|${historyKey}|${suffix}`;
    const exactProbs = this.strategies.get(exactKey);
    if (exactProbs) {
      return { key: exactKey, probs: exactProbs };
    }

    // For V2, search nearby primary bucket (the last bucket component)
    const searchRadius = 5;
    const primaryBucket = street === 'R' ? estimatedBuckets.river
      : street === 'T' ? estimatedBuckets.turn
      : estimatedBuckets.flop;

    for (let delta = 1; delta <= searchRadius; delta++) {
      for (const d of [delta, -delta]) {
        const bucket = primaryBucket + d;
        if (bucket < 0 || bucket >= this.bucketCount) continue;
        const adjusted = { ...estimatedBuckets };
        if (street === 'R') adjusted.river = bucket;
        else if (street === 'T') adjusted.turn = bucket;
        else adjusted.flop = bucket;
        const adjustedSuffix = this.buildBucketSuffix(street, adjusted);
        const key = `${street}|${boardId}|${player}|${historyKey}|${adjustedSuffix}`;
        const probs = this.strategies.get(key);
        if (probs) {
          return { key, probs };
        }
      }
    }

    // Wider search: scan all stored keys with matching prefix
    const prefix = `${street}|${boardId}|${player}|${historyKey}|`;
    for (const [key, probs] of this.strategies) {
      if (key.startsWith(prefix)) {
        return { key, probs };
      }
    }

    return null;
  }

  /**
   * Compute per-street hand buckets for a given hand on a board (V2).
   * Uses approximate linear mapping from hand evaluation value.
   */
  private computeBucketV2(
    hand: [string, string],
    board: string[],
    _player: 0 | 1,
  ): { flop: number; turn: number; river: number } {
    const minVal = 1000;
    const maxVal = 60000;
    const toBucket = (cards: string[]) => {
      const eval_ = evaluateBestHand(cards);
      const normalized = Math.max(0, Math.min(1, (eval_.value - minVal) / (maxVal - minVal)));
      return Math.min(this.bucketCount - 1, Math.floor(normalized * this.bucketCount));
    };

    const flopBucket = toBucket([...hand, ...board.slice(0, 3)]);
    const turnBucket = board.length >= 4
      ? toBucket([...hand, ...board.slice(0, 4)])
      : flopBucket;
    const riverBucket = board.length >= 5
      ? toBucket([...hand, ...board])
      : turnBucket;

    return { flop: flopBucket, turn: turnBucket, river: riverBucket };
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
