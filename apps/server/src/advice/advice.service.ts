import { Injectable, Logger } from '@nestjs/common';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { 
  AdvicePayload, 
  StrategyMix, 
  AdviceContext, 
  AdviceExplanation,
  Position,
  PlayerActionType
} from '@cardpilot/shared-types';

interface ChartRow {
  format: string;
  spot: string;
  hand: string;
  frequency: StrategyMix;
  sizing?: string;
  tags: string[];
  explanation: {
    zh: string;
    en: string;
  };
}

const TAG_EXPLANATIONS: Record<string, { zh: string; en: string }> = {
  IP_ADVANTAGE: { 
    zh: "你在位置上有優勢，翻牌後更容易實現權益。", 
    en: "You have position advantage, easier to realize equity postflop." 
  },
  A_BLOCKER: { 
    zh: "A blocker 會降低對手拿到強 Ax 組合的機率。", 
    en: "A blocker reduces opponent's chance of having strong Ax hands." 
  },
  WHEEL_POTENTIAL: { 
    zh: "這手牌有 wheel 順子潛力（5-high straight），可玩性不錯。", 
    en: "This hand has wheel straight potential, good playability." 
  },
  BROADWAY_STRENGTH: { 
    zh: "Broadway 組合在高牌面有不錯的命中率。", 
    en: "Broadway combinations hit high card boards well." 
  },
  DEFEND_RANGE: { 
    zh: "面對小尺寸 open，需要用部分 suited Ax 防守。", 
    en: "Defend with some suited Ax against small open sizes." 
  },
  LOW_PLAYABILITY: { 
    zh: "可玩性與實現權益都偏低，理論上以棄牌為主。", 
    en: "Low playability and equity realization, mainly fold." 
  },
  PREMIUM_HAND: {
    zh: "這是頂級起手牌，應該為了價值積極下注。",
    en: "This is a premium starting hand, play aggressively for value."
  },
  OOP_DISADVANTAGE: {
    zh: "你處於位置劣勢，翻牌後較難控制底池。",
    en: "You are out of position, harder to control pot postflop."
  },
  SUITED_CONNECTOR: {
    zh: "同花連牌可玩性高，容易形成強牌。",
    en: "Suited connectors have high playability and strong hand potential."
  },
  SET_MINING: {
    zh: "小對子主要價值來自於擊中 set（三條）。",
    en: "Small pairs mainly rely on hitting a set for value."
  }
};

@Injectable()
export class AdviceService {
  private readonly logger = new Logger(AdviceService.name);
  private chartData: ChartRow[] = [];

  constructor() {
    this.loadChartData();
  }

  private loadChartData(): void {
    try {
      const __dirname = fileURLToPath(new URL('.', import.meta.url));
      const filePath = join(__dirname, 'data/preflop-charts.json');
      const content = readFileSync(filePath, 'utf-8');
      this.chartData = JSON.parse(content);
      this.logger.log(`Loaded ${this.chartData.length} preflop chart entries`);
    } catch (error) {
      this.logger.error('Failed to load preflop charts:', error);
      this.chartData = [];
    }
  }

  /**
   * 正規化手牌表示
   * "Ah5h" -> "A5s" (suited)
   * "Ah5d" -> "A5o" (offsuit)
   * "AhAd" -> "AA" (pair)
   */
  normalizeHand(holeCards: [string, string]): string {
    const [a, b] = holeCards;
    const rankA = a[0];
    const rankB = b[0];
    const suitA = a[1];
    const suitB = b[1];

    // Pair
    if (rankA === rankB) {
      return `${rankA}${rankB}`;
    }

    // Determine high and low cards
    const rankOrder = 'AKQJT98765432';
    const idxA = rankOrder.indexOf(rankA);
    const idxB = rankOrder.indexOf(rankB);
    
    const high = idxA <= idxB ? rankA : rankB;
    const low = idxA <= idxB ? rankB : rankA;
    const suited = suitA === suitB ? 's' : 'o';

    return `${high}${low}${suited}`;
  }

  /**
   * 建立 Spot Key
   * 格式: <position>[_vs_<vsPosition>[_<action>]]
   */
  buildSpotKey(params: {
    heroPosition: Position;
    vsPosition?: Position;
    actionHistory: string[];
    isUnopened: boolean;
  }): string {
    const { heroPosition, vsPosition, actionHistory, isUnopened } = params;

    // Open 情境（前面都棄牌）
    if (isUnopened) {
      return `${heroPosition}_open`;
    }

    // 需要對手位置
    if (!vsPosition) {
      return `${heroPosition}_defend`;
    }

    // 判斷是面對 open 還是 3bet
    const raiseCount = actionHistory.filter(a => 
      a.includes('raise') || a.includes('RAISE') || a.includes('3bet')
    ).length;

    if (raiseCount === 1) {
      return `${heroPosition}_vs_${vsPosition}_open`;
    } else if (raiseCount === 2) {
      return `${heroPosition}_vs_${vsPosition}_3bet`;
    } else if (raiseCount >= 3) {
      return `${heroPosition}_vs_${vsPosition}_4bet`;
    }

    return `${heroPosition}_vs_${vsPosition}`;
  }

  /**
   * 計算偏離程度
   * 0 = 完美符合 GTO，1 = 完全錯誤
   */
  calculateDeviation(
    gtoMix: StrategyMix,
    actualAction: PlayerActionType
  ): number {
    const actionKey = actualAction === 'all_in' ? 'raise' : actualAction;
    const actualProb = gtoMix[actionKey as keyof StrategyMix] || 0;
    
    // 如果 GTO 建議 0% 而你做了，就是完全錯誤
    // 如果 GTO 建議 100% 而你做了，就是完美
    return 1 - actualProb;
  }

  /**
   * 獲取 GTO 建議
   */
  getAdvice(params: {
    handId: string;
    heroHand: [string, string];
    heroPosition: Position;
    vsPosition?: Position;
    effectiveStack: number; // in bb
    potSize: number;
    toCall: number;
    actionHistory: string[];
    isUnopened: boolean;
  }): AdvicePayload {
    const normalizedHand = this.normalizeHand(params.heroHand);
    const spotKey = this.buildSpotKey({
      heroPosition: params.heroPosition,
      vsPosition: params.vsPosition,
      actionHistory: params.actionHistory,
      isUnopened: params.isUnopened
    });

    // 查表
    const entry = this.chartData.find(row => 
      row.format === '6max_100bb' &&
      row.spot === spotKey &&
      row.hand === normalizedHand
    );

    // 計算 pot odds
    const potOdds = params.toCall > 0 
      ? params.toCall / (params.potSize + params.toCall)
      : 0;

    const context: AdviceContext = {
      position: params.heroPosition,
      vsPosition: params.vsPosition,
      effectiveStack: params.effectiveStack,
      potOdds: Math.round(potOdds * 100) / 100,
      toCall: params.toCall
    };

    if (entry) {
      const explanation = this.generateExplanation(entry.tags, entry.explanation);
      
      return {
        handId: params.handId,
        spotKey: `6max_100bb_${spotKey}`,
        handCards: normalizedHand,
        strategy: entry.frequency,
        sizing: entry.sizing,
        explanation,
        context
      };
    }

    // Fallback: 使用簡單啟發式
    return this.getFallbackAdvice(params.handId, normalizedHand, spotKey, context);
  }

  private generateExplanation(
    tags: string[],
    entryExplanation: { zh: string; en: string }
  ): AdviceExplanation {
    const tagTexts = tags
      .map(tag => TAG_EXPLANATIONS[tag])
      .filter(Boolean)
      .map(t => t.zh);

    return {
      tags,
      shortText: entryExplanation.zh,
      details: tagTexts.join(' ')
    };
  }

  private getFallbackAdvice(
    handId: string,
    hand: string,
    spotKey: string,
    context: AdviceContext
  ): AdvicePayload {
    const rankA = hand[0];
    const rankB = hand[1];
    const suited = hand[2] === 's';
    const isPair = rankA === rankB;

    // 基本啟發式
    let strategy: StrategyMix;
    
    // 頂級對子
    if (isPair && 'AA KK QQ'.includes(hand)) {
      strategy = { raise: 0.95, call: 0.05, fold: 0 };
    }
    // 大對子
    else if (isPair && 'JJ TT'.includes(hand)) {
      strategy = { raise: 0.8, call: 0.15, fold: 0.05 };
    }
    // 小對子
    else if (isPair) {
      strategy = context.vsPosition 
        ? { raise: 0.05, call: 0.35, fold: 0.6 }
        : { raise: 0.3, call: 0, fold: 0.7 };
    }
    // AK
    else if (hand.includes('A') && hand.includes('K')) {
      strategy = { raise: 0.85, call: 0.1, fold: 0.05 };
    }
    // AQ, AJ suited
    else if (hand.includes('A') && suited) {
      strategy = { raise: 0.5, call: 0.3, fold: 0.2 };
    }
    // 同花連牌
    else if (suited && this.isConnected(hand)) {
      strategy = context.vsPosition
        ? { raise: 0.1, call: 0.5, fold: 0.4 }
        : { raise: 0.4, call: 0, fold: 0.6 };
    }
    // 其他 suited
    else if (suited) {
      strategy = { raise: 0.15, call: 0.25, fold: 0.6 };
    }
    // 其他 offsuit
    else {
      strategy = { raise: 0, call: 0.1, fold: 0.9 };
    }

    return {
      handId,
      spotKey: `6max_100bb_${spotKey}`,
      handCards: hand,
      strategy,
      sizing: strategy.raise > 0.3 ? '2.5x' : undefined,
      explanation: {
        tags: ['FALLBACK_STRATEGY'],
        shortText: '使用預設策略（未找到精確的 GTO 數據）',
        details: '這個情境還沒有精確的 GTO 數據，使用基本啟發式策略。'
      },
      context
    };
  }

  private isConnected(hand: string): boolean {
    const ranks = 'AKQJT98765432';
    const r1 = ranks.indexOf(hand[0]);
    const r2 = ranks.indexOf(hand[1]);
    return Math.abs(r1 - r2) <= 2;
  }
}
