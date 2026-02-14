import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { AdvicePayload, PlayerActionType, StrategyMix } from "@cardpilot/shared-types";

type Mix = { raise: number; call: number; fold: number };

type ChartRow = {
  format: string;
  spot: string;
  hand: string;
  mix: Mix;
  notes: string[];
};

const EXPLANATIONS: Record<string, string> = {
  IP_ADVANTAGE: "你在位置上有優勢，翻牌後更容易實現權益。",
  A_BLOCKER: "A blocker 會降低對手拿到強 Ax 組合的機率。",
  K_BLOCKER: "K blocker 降低對手持有 KK/AK 的可能。",
  WHEEL_PLAYABILITY: "這手牌有 wheel 順子潛力，可玩性不錯。",
  SUITED_PLAYABILITY: "同花牌的後門花/順延展性使其更容易實現權益。",
  CONNECTED: "連牌結構使翻牌後的順子潛力更高。",
  BROADWAY_STRENGTH: "Broadway 組合在高牌面有不錯的命中率。",
  DEFEND_RANGE: "面對小尺寸 open，需要用足夠的牌防守以避免被過度偷盲。",
  FOLD_EQUITY: "位置優勢帶來的棄牌權益，使較弱的牌也值得進攻。",
  LOW_PLAYABILITY: "可玩性與實現權益都偏低，理論上以棄牌為主。",
  DOMINATION_RISK: "容易被更強的同類牌支配（domination），需要小心。",
  PAIR_VALUE: "口袋對子有固定的 set value，適合看翻牌。",
  PREMIUM_PAIR: "頂級口袋對子，是 preflop 最強手牌之一。"
};

const chartPath = resolveChartPath();
const chartRows: ChartRow[] = JSON.parse(readFileSync(chartPath, "utf-8"));
console.log(`[advice-engine] loaded ${chartRows.length} chart rows from ${chartPath}`);

function resolveChartPath(): string {
  const fromEnv = process.env.CARDPILOT_CHART_PATH;
  if (fromEnv) return fromEnv;

  // Try full chart first, then sample
  for (const filename of ["preflop_charts.json", "preflop_charts.sample.json"]) {
    const localCwdPath = join(process.cwd(), "data", filename);
    try {
      readFileSync(localCwdPath, "utf-8");
      return localCwdPath;
    } catch {
      // fall through
    }
  }

  const thisDir = fileURLToPath(new URL(".", import.meta.url));
  return join(thisDir, "../../../data/preflop_charts.json");
}

export function buildSpotKey(params: {
  heroPos: string;
  villainPos: string;
  line: "unopened" | "facing_open";
  size: "open2.5x";
}): string {
  if (params.line === "unopened") {
    return `${params.heroPos}_unopened_${params.size}`;
  }
  return `${params.heroPos}_vs_${params.villainPos}_facing_${params.size}`;
}

export function getPreflopAdvice(input: {
  tableId: string;
  handId: string;
  seat: number;
  heroPos: string;
  villainPos: string;
  line: "unopened" | "facing_open";
  heroHand: string;
}): AdvicePayload {
  const spotKey = buildSpotKey({
    heroPos: input.heroPos,
    villainPos: input.villainPos,
    line: input.line,
    size: "open2.5x"
  });

  const row = chartRows.find(
    (r) =>
      r.format === "cash_6max_100bb" &&
      r.spot === spotKey &&
      r.hand === input.heroHand
  );

  const mix: Mix = row?.mix ?? fallbackMix(input.heroHand, input.line);
  const tags = row?.notes ?? ["LOW_PLAYABILITY"];
  const explanation = tags.map((t) => EXPLANATIONS[t] ?? t).join(" ");

  // Randomized recommendation (§6.4)
  const rand = Math.random();
  const recommended = pickByMix(mix, rand);

  return {
    tableId: input.tableId,
    handId: input.handId,
    seat: input.seat,
    spotKey: `cash_6max_100bb_${spotKey}`,
    heroHand: input.heroHand,
    mix,
    tags,
    explanation,
    recommended,
    randomSeed: Math.round(rand * 100) / 100
  };
}

/**
 * Pick action by cumulative distribution of mix frequencies.
 * r ∈ [0,1) → action with matching probability band.
 */
function pickByMix(mix: Mix, r: number): "raise" | "call" | "fold" {
  if (r < mix.raise) return "raise";
  if (r < mix.raise + mix.call) return "call";
  return "fold";
}

/**
 * Calculate deviation score between player action and GTO mix.
 * 0 = perfect (chose the highest-frequency action), 1 = worst possible.
 */
export function calculateDeviation(
  mix: StrategyMix,
  playerAction: PlayerActionType
): number {
  const actionMap: Record<string, keyof StrategyMix> = {
    fold: "fold",
    check: "fold", // check ≈ passive / fold equivalent for preflop
    call: "call",
    raise: "raise",
    all_in: "raise"
  };

  const key = actionMap[playerAction] ?? "fold";
  const chosenFreq = mix[key];

  // Deviation = 1 − chosen_frequency
  // If GTO says raise 100% and you fold, deviation = 1.0
  // If GTO says raise 65% / fold 35% and you fold, deviation = 0.65
  return Math.round((1 - chosenFreq) * 10000) / 10000;
}

function fallbackMix(hand: string, line: "unopened" | "facing_open"): Mix {
  const rankA = hand[0];
  const rankB = hand[1];
  const suited = hand[2] === "s";

  if (line === "unopened") {
    if (rankA === "A" || (rankA === "K" && rankB !== "2")) {
      return { raise: 0.8, call: 0, fold: 0.2 };
    }
    if (suited) {
      return { raise: 0.35, call: 0.15, fold: 0.5 };
    }
  }

  if (line === "facing_open") {
    if (rankA === "A" && suited) {
      return { raise: 0.2, call: 0.6, fold: 0.2 };
    }
    if (suited) {
      return { raise: 0.08, call: 0.35, fold: 0.57 };
    }
  }

  return { raise: 0, call: 0.1, fold: 0.9 };
}
