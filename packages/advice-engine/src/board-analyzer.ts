import type { Card } from "@cardpilot/poker-evaluator";
import type { BoardTextureProfile } from "@cardpilot/shared-types";

const RANK_ORDER = "23456789TJQKA";

type TextureBucket = "DRY_TEXTURE" | "NEUTRAL_TEXTURE" | "WET_TEXTURE";

type ParsedCard = {
  rank: string;
  suit: string;
  value: number;
};

export class BoardAnalyzer {
  static analyze(board: Card[]): BoardTextureProfile {
    if (board.length < 3) {
      throw new Error("BoardAnalyzer requires at least a flop (3 cards).");
    }

    const cards = board.map((card) => parseCard(card));
    const rankCounts = this.buildRankCounts(cards);
    const suitCounts = this.buildSuitCounts(cards);
    const values = uniqueSortedValues(cards);
    const highCardCount = cards.filter((card) => card.value >= 10).length;

    const isPaired = Object.values(rankCounts).some((count) => count >= 2);
    const maxSuitCount = Math.max(...Object.values(suitCounts));
    const isMonotone = maxSuitCount >= 3;
    const flushDrawPresent = maxSuitCount >= 2 && board.length <= 4;
    const isConnected = isConnectedValues(values);
    const isDisconnected = !isConnected && largestGap(values) >= 4;
    const isHighCardHeavy = highCardCount >= 2;

    const wetnessScore = this.computeWetnessScore({
      isMonotone,
      flushDrawPresent,
      isConnected,
      isDisconnected,
      isPaired,
      isHighCardHeavy
    });
    const wetness = wetnessFromScore(wetnessScore);

    const labels: string[] = [];
    if (isMonotone) labels.push("monotone");
    if (isPaired) labels.push("paired");
    if (flushDrawPresent) labels.push("flush_draw_present");
    if (isConnected) labels.push("connected");
    if (isDisconnected) labels.push("disconnected");
    if (isHighCardHeavy) labels.push("high_card_heavy");
    labels.push(wetness);

    return {
      isPaired,
      isMonotone,
      hasFlushDraw: flushDrawPresent,
      isConnected,
      isDisconnected,
      isHighCardHeavy,
      wetness,
      labels
    };
  }

  static isPaired(board: Card[]): boolean {
    return this.analyze(board).isPaired;
  }

  static hasFlushDraw(board: Card[]): boolean {
    return this.analyze(board).hasFlushDraw;
  }

  static isStraightConnected(board: Card[]): boolean {
    return this.analyze(board).isConnected;
  }

  static isDisconnected(board: Card[]): boolean {
    return this.analyze(board).isDisconnected;
  }

  static isHighCardHeavy(board: Card[]): boolean {
    return this.analyze(board).isHighCardHeavy;
  }

  static toTextureBucket(texture: BoardTextureProfile): TextureBucket {
    if (texture.wetness === "wet") return "WET_TEXTURE";
    if (texture.wetness === "dry") return "DRY_TEXTURE";
    return "NEUTRAL_TEXTURE";
  }

  static describe(texture: BoardTextureProfile): string {
    const parts: string[] = [];
    if (texture.isMonotone) {
      parts.push("monotone board");
    } else if (texture.hasFlushDraw) {
      parts.push("flush-draw texture");
    }

    if (texture.isPaired) parts.push("paired board");
    if (texture.isConnected) parts.push("straight-connected structure");
    if (texture.isDisconnected) parts.push("disconnected structure");
    if (texture.isHighCardHeavy) parts.push("high-card-heavy runout");

    const textureText = texture.wetness === "wet"
      ? "wet texture"
      : texture.wetness === "dry"
        ? "dry texture"
        : "neutral texture";

    if (parts.length === 0) return textureText;
    return `${parts.join(", ")} (${textureText})`;
  }

  private static buildRankCounts(cards: ParsedCard[]): Record<string, number> {
    const counts: Record<string, number> = {};
    for (const card of cards) {
      counts[card.rank] = (counts[card.rank] ?? 0) + 1;
    }
    return counts;
  }

  private static buildSuitCounts(cards: ParsedCard[]): Record<string, number> {
    const counts: Record<string, number> = {};
    for (const card of cards) {
      counts[card.suit] = (counts[card.suit] ?? 0) + 1;
    }
    return counts;
  }

  private static computeWetnessScore(input: {
    isMonotone: boolean;
    flushDrawPresent: boolean;
    isConnected: boolean;
    isDisconnected: boolean;
    isPaired: boolean;
    isHighCardHeavy: boolean;
  }): number {
    let score = 0;
    if (input.isMonotone) score += 2;
    if (input.flushDrawPresent) score += 1;
    if (input.isConnected) score += 2;
    if (input.isDisconnected) score -= 2;
    if (input.isPaired) score -= 1;
    if (input.isHighCardHeavy) score += 1;
    return score;
  }
}

export function analyzeBoardTexture(board: Card[]): BoardTextureProfile {
  return BoardAnalyzer.analyze(board);
}

export function hasFlushDraw(board: Card[]): boolean {
  return BoardAnalyzer.hasFlushDraw(board);
}

export function isStraightConnected(board: Card[]): boolean {
  return BoardAnalyzer.isStraightConnected(board);
}

export function isPairedBoard(board: Card[]): boolean {
  return BoardAnalyzer.isPaired(board);
}

export function isDisconnectedBoard(board: Card[]): boolean {
  return BoardAnalyzer.isDisconnected(board);
}

export function isHighCardHeavyBoard(board: Card[]): boolean {
  return BoardAnalyzer.isHighCardHeavy(board);
}

function parseCard(card: Card): ParsedCard {
  const rank = card[0]?.toUpperCase();
  const suit = card[1]?.toLowerCase();
  const rankIdx = RANK_ORDER.indexOf(rank);

  if (rankIdx < 0 || !suit) {
    throw new Error(`Invalid card "${card}"`);
  }

  return {
    rank,
    suit,
    value: rankIdx + 2
  };
}

function uniqueSortedValues(cards: ParsedCard[]): number[] {
  const values = new Set<number>();
  for (const card of cards) {
    values.add(card.value);
    if (card.value === 14) {
      values.add(1); // Wheel support (A2345)
    }
  }
  return [...values].sort((a, b) => a - b);
}

function isConnectedValues(values: number[]): boolean {
  if (values.length < 2) return false;

  let bestRun = 1;
  let currentRun = 1;
  for (let i = 1; i < values.length; i++) {
    if (values[i] === values[i - 1] + 1) {
      currentRun += 1;
      bestRun = Math.max(bestRun, currentRun);
    } else {
      currentRun = 1;
    }
  }

  return bestRun >= 3;
}

function largestGap(values: number[]): number {
  if (values.length < 2) return 0;
  let maxGap = 0;
  for (let i = 1; i < values.length; i++) {
    maxGap = Math.max(maxGap, values[i] - values[i - 1]);
  }
  return maxGap;
}

function wetnessFromScore(score: number): BoardTextureProfile["wetness"] {
  if (score >= 3) return "wet";
  if (score <= 0) return "dry";
  return "neutral";
}
