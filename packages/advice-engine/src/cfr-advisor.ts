// CFR strategy advisor — bridges solved CFR data into the PostflopEngine.
//
// Supports multiple configs (SRP + 3bet) with separate binary readers.
// Uses BinaryStrategyReader for O(log n) lookups, combined with flop
// metadata for board matching.

import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import {
  BinaryStrategyReader,
  buildTree,
  V1_TREE_CONFIG,
  PIPELINE_3BET_CONFIG,
  getTreeConfig,
  type TreeConfigName,
} from '@cardpilot/cfr-solver';
import type { Action, GameNode, TreeConfig } from '@cardpilot/cfr-solver';
import type { PostflopFrequency } from '@cardpilot/shared-types';
import type { PostflopContext } from './postflop-engine.js';
import { classifyHandOnBoard } from '@cardpilot/poker-evaluator';
import { downloadBuffer, downloadJson } from './s3-client.js';

// Bet size midpoints for classifying observed bets as small/big (V1 2-size tree)
const BET_THRESHOLDS: Record<string, number> = {
  FLOP: (0.33 + 0.75) / 2, // 0.54
  TURN: (0.5 + 1.0) / 2, // 0.75
  RIVER: (0.75 + 1.5) / 2, // 1.125
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

type PotType = 'SRP' | '3BP' | '4BP';

/** Per-config CFR data bundle. */
interface CfrConfigData {
  reader: BinaryStrategyReader;
  flopMetas: FlopMeta[];
  actionIndex: Map<string, Action[]>;
  treeConfig: TreeConfig;
  bucketCount: number;
}

export class CfrAdvisor {
  private configs = new Map<PotType, CfrConfigData>();

  /** Load CFR data for a specific pot type. */
  load(binaryPath: string, metaDir?: string, potType: PotType = 'SRP'): boolean {
    try {
      const binPath =
        binaryPath.endsWith('.gz') || binaryPath.endsWith('.bin')
          ? binaryPath
          : join(binaryPath, 'v1_hu_srp_50bb.bin.gz');

      if (!existsSync(binPath)) {
        console.warn(`[cfr-advisor] binary file not found: ${binPath}`);
        return false;
      }

      const reader = new BinaryStrategyReader(binPath);
      const treeConfig = potType === '3BP' ? PIPELINE_3BET_CONFIG : V1_TREE_CONFIG;
      const bucketCount = reader.bucketCount || (potType === '3BP' ? 100 : 50);

      // Build action index from tree
      const actionIndex = new Map<string, Action[]>();
      const root = buildTree(treeConfig);
      const walk = (node: GameNode) => {
        if (node.type === 'terminal') return;
        actionIndex.set(node.historyKey, [...node.actions]);
        for (const child of node.children.values()) walk(child);
      };
      walk(root);

      // Load flop metadata
      const flopMetas: FlopMeta[] = [];
      const mDir = metaDir ?? binaryPath.replace(/\.bin(\.gz)?$/, '');
      if (existsSync(mDir)) {
        const metaFiles = readdirSync(mDir)
          .filter((f) => f.endsWith('.meta.json'))
          .sort();
        for (const file of metaFiles) {
          try {
            const meta = JSON.parse(readFileSync(join(mDir, file), 'utf-8'));
            flopMetas.push({ boardId: meta.boardId, flopCards: meta.flopCards });
          } catch {
            /* skip corrupted meta files */
          }
        }
      }

      this.configs.set(potType, { reader, flopMetas, actionIndex, treeConfig, bucketCount });
      console.log(
        `[cfr-advisor] loaded ${potType}: ${reader.entryCount} entries, ${flopMetas.length} flop metas, ${bucketCount} buckets`,
      );
      return true;
    } catch (e) {
      console.warn(`[cfr-advisor] Failed to load ${potType}: ${(e as Error).message}`);
      return false;
    }
  }

  get isLoaded(): boolean {
    return this.configs.size > 0;
  }

  /** Load CFR data using a tree config name from the registry. */
  loadByConfigName(binaryPath: string, configName: TreeConfigName, metaDir?: string): boolean {
    try {
      if (!existsSync(binaryPath)) {
        console.warn(`[cfr-advisor] binary file not found: ${binaryPath}`);
        return false;
      }

      const reader = new BinaryStrategyReader(binaryPath);
      const treeConfig = getTreeConfig(configName);
      const bucketCount = reader.bucketCount || 100;

      const actionIndex = new Map<string, Action[]>();
      const root = buildTree(treeConfig);
      const walk = (node: GameNode) => {
        if (node.type === 'terminal') return;
        actionIndex.set(node.historyKey, [...node.actions]);
        for (const child of node.children.values()) walk(child);
      };
      walk(root);

      const flopMetas: FlopMeta[] = [];
      const mDir = metaDir ?? binaryPath.replace(/\.bin(\.gz)?$/, '');
      if (existsSync(mDir)) {
        const metaFiles = readdirSync(mDir)
          .filter((f) => f.endsWith('.meta.json'))
          .sort();
        for (const file of metaFiles) {
          try {
            const meta = JSON.parse(readFileSync(join(mDir, file), 'utf-8'));
            flopMetas.push({ boardId: meta.boardId, flopCards: meta.flopCards });
          } catch {
            /* skip corrupted meta files */
          }
        }
      }

      // Derive pot type from config name
      const potType: PotType = configName.includes('3b') ? '3BP' : 'SRP';
      this.configs.set(potType, { reader, flopMetas, actionIndex, treeConfig, bucketCount });
      console.log(
        `[cfr-advisor] loaded ${configName} as ${potType}: ${reader.entryCount} entries, ${flopMetas.length} flop metas`,
      );
      return true;
    } catch (e) {
      console.warn(`[cfr-advisor] Failed to load ${configName}: ${(e as Error).message}`);
      return false;
    }
  }

  /** Load CFR data from S3 (iDrive e2). */
  async loadFromS3(
    binaryKey: string,
    metaIndexKey: string,
    potType: PotType = 'SRP',
  ): Promise<boolean> {
    try {
      console.log(`[cfr-advisor] downloading ${potType} binary from S3: ${binaryKey}`);
      const buf = await downloadBuffer(binaryKey);
      if (!buf) {
        console.warn(`[cfr-advisor] S3 binary not found: ${binaryKey}`);
        return false;
      }

      const reader = new BinaryStrategyReader(buf);
      const treeConfig = potType === '3BP' ? PIPELINE_3BET_CONFIG : V1_TREE_CONFIG;
      const bucketCount = reader.bucketCount || (potType === '3BP' ? 100 : 50);

      // Build action index from tree
      const actionIndex = new Map<string, Action[]>();
      const root = buildTree(treeConfig);
      const walk = (node: GameNode) => {
        if (node.type === 'terminal') return;
        actionIndex.set(node.historyKey, [...node.actions]);
        for (const child of node.children.values()) walk(child);
      };
      walk(root);

      // Download flop metadata index from S3
      const flopMetas: FlopMeta[] = [];
      const metaIndex =
        await downloadJson<Array<{ boardId: number; flopCards: [number, number, number] }>>(
          metaIndexKey,
        );
      if (metaIndex && Array.isArray(metaIndex)) {
        for (const meta of metaIndex) {
          flopMetas.push({ boardId: meta.boardId, flopCards: meta.flopCards });
        }
      }

      this.configs.set(potType, { reader, flopMetas, actionIndex, treeConfig, bucketCount });
      console.log(
        `[cfr-advisor] loaded ${potType} from S3: ${reader.entryCount} entries, ${flopMetas.length} flop metas, ${bucketCount} buckets`,
      );
      return true;
    } catch (e) {
      console.warn(`[cfr-advisor] Failed to load ${potType} from S3: ${(e as Error).message}`);
      return false;
    }
  }

  /** Get list of loaded pot types. */
  get loadedPotTypes(): PotType[] {
    return [...this.configs.keys()];
  }

  /**
   * Query CFR strategy for a given postflop context.
   * Returns null if CFR data is unavailable or the context doesn't match.
   */
  query(context: PostflopContext): CfrQueryResult | null {
    if (this.configs.size === 0) return null;
    if (context.numVillains !== 1) return null;

    const potType: PotType = context.potType ?? 'SRP';
    const config = this.configs.get(potType);
    if (!config) return null;

    const player: 0 | 1 = context.heroInPosition ? 1 : 0;
    const historyKey = this.buildHistoryKey(context, config);
    if (historyKey === null) return null;

    const actions = config.actionIndex.get(historyKey);
    if (!actions) return null;

    // Find matching board
    const boardMatch = this.findBoard(context.board, config.flopMetas);
    if (!boardMatch) return null;

    // Estimate hand bucket
    const bucket = this.estimateBucket(context, config.bucketCount);
    const streetChar = context.street === 'FLOP' ? 'F' : context.street === 'TURN' ? 'T' : 'R';

    // Try exact bucket, then nearby, then wider
    let probs: number[] | null = null;
    const source: 'cfr_exact' | 'cfr_nearest' = boardMatch.exact ? 'cfr_exact' : 'cfr_nearest';

    const bucketsToTry = [bucket];
    for (let d = 1; d <= 5; d++) {
      if (bucket + d < config.bucketCount) bucketsToTry.push(bucket + d);
      if (bucket - d >= 0) bucketsToTry.push(bucket - d);
    }

    for (const b of bucketsToTry) {
      const key = `${streetChar}|${boardMatch.boardId}|${player}|${historyKey}|${b}`;
      probs = config.reader.lookup(key);
      if (probs) break;
    }

    // If still no match, try all buckets
    if (!probs) {
      for (let b = 0; b < config.bucketCount; b++) {
        const key = `${streetChar}|${boardMatch.boardId}|${player}|${historyKey}|${b}`;
        probs = config.reader.lookup(key);
        if (probs) break;
      }
    }

    if (!probs || probs.length !== actions.length) return null;

    const frequency = this.mapToFrequency(actions, probs);
    if (!frequency) return null;

    return { frequency, source, confidence: source === 'cfr_exact' ? 0.85 : 0.65 };
  }

  /** Find the matching board (exact or nearest texture). */
  private findBoard(
    board: string[],
    flopMetas: FlopMeta[],
  ): { boardId: number; exact: boolean } | null {
    if (flopMetas.length === 0) return null;

    const flopCards = board.slice(0, 3);
    const flopIndices = flopCards.map(cardToIndex);

    // Exact match (order-independent)
    const flopSet = new Set(flopIndices);
    const exact = flopMetas.find((m) => {
      const s = new Set(m.flopCards);
      return s.size === flopSet.size && [...flopSet].every((c) => s.has(c));
    });
    if (exact) return { boardId: exact.boardId, exact: true };

    // Nearest flop by texture features
    const queryFeats = flopFeatures(flopIndices);
    let bestId = 0;
    let bestDist = Infinity;
    for (const meta of flopMetas) {
      const dist = featureDistance(queryFeats, flopFeatures(meta.flopCards));
      if (dist < bestDist) {
        bestDist = dist;
        bestId = meta.boardId;
      }
    }
    return { boardId: bestId, exact: false };
  }

  /** Estimate the hand bucket using hand classification. */
  private estimateBucket(context: PostflopContext, bucketCount: number): number {
    const handClass = classifyHandOnBoard(context.heroHand, context.board);
    const maxBucket = bucketCount - 1;
    if (handClass.type === 'made_hand') {
      if (handClass.strength === 'strong')
        return Math.floor(maxBucket * 0.8 + Math.random() * maxBucket * 0.2);
      if (handClass.strength === 'medium')
        return Math.floor(maxBucket * 0.4 + Math.random() * maxBucket * 0.3);
      return Math.floor(maxBucket * 0.15 + Math.random() * maxBucket * 0.25);
    }
    if (handClass.type === 'draw')
      return Math.floor(maxBucket * 0.3 + Math.random() * maxBucket * 0.3);
    return Math.floor(Math.random() * maxBucket * 0.2);
  }

  /**
   * Convert game-server action history into a CFR history key string.
   */
  private buildHistoryKey(context: PostflopContext, config: CfrConfigData): string | null {
    if (!context.actionHistory || context.actionHistory.length === 0) return '';

    const postflopActions = context.actionHistory.filter(
      (a) => a.street === 'FLOP' || a.street === 'TURN' || a.street === 'RIVER',
    );

    let history = '';
    let currentStreet: string | null = null;
    let runningPot = config.treeConfig.startingPot;

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
          // For single-size configs, always map to '1' (bet_0)
          if (config.treeConfig.betSizes.flop.length === 1) {
            history += '1';
          } else {
            history += fraction <= threshold ? '1' : '2';
          }
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
   * Actions are named bet_0, bet_1, raise_0, raise_1, etc.
   */
  private mapToFrequency(actions: Action[], probs: number[]): PostflopFrequency | null {
    let check = 0;
    let betSmall = 0;
    let betBig = 0;

    for (let i = 0; i < actions.length; i++) {
      const p = probs[i];
      const a = actions[i];
      if (a === 'check' || a === 'call') {
        check += p;
      } else if (a === 'bet_0' || a === 'raise_0' || a === 'bet_small' || a === 'raise_small') {
        betSmall += p;
      } else if (a === 'bet_1' || a === 'raise_1' || a === 'bet_big' || a === 'raise_big') {
        betBig += p;
      } else if (a === 'allin') {
        betBig += p;
      }
      // fold is intentionally excluded — it's implicit (1 - sum)
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
  const suits = cards.map((c) => c & 3);
  const suitCount = new Set(suits).size;
  const maxGap = Math.max(ranks[0] - ranks[1], ranks[1] - ranks[2]);
  const totalSpread = ranks[0] - ranks[2];
  const paired = ranks[0] === ranks[1] || ranks[1] === ranks[2] ? 1 : 0;
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
