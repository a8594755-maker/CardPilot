import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { AdvicePayload } from "@cardpilot/shared-types";

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
  WHEEL_PLAYABILITY: "這手牌有 wheel 順子潛力，可玩性不錯。",
  BROADWAY_STRENGTH: "Broadway 組合在高牌面有不錯的命中率。",
  DEFEND_RANGE: "面對小尺寸 open，需要用部分 suited Ax 防守。",
  LOW_PLAYABILITY: "可玩性與實現權益都偏低，理論上以棄牌為主。"
};

const chartPath = resolveChartPath();
const chartRows: ChartRow[] = JSON.parse(readFileSync(chartPath, "utf-8"));

function resolveChartPath(): string {
  const fromEnv = process.env.CARDPILOT_CHART_PATH;
  if (fromEnv) return fromEnv;

  const localCwdPath = join(process.cwd(), "data", "preflop_charts.sample.json");
  try {
    readFileSync(localCwdPath, "utf-8");
    return localCwdPath;
  } catch {
    // fall through
  }

  const thisDir = fileURLToPath(new URL(".", import.meta.url));
  return join(thisDir, "../../../data/preflop_charts.sample.json");
}

export function buildSpotKey(params: {
  heroPos: string;
  villainPos: string;
  line: "unopened" | "facing_open";
  size: "open2.5x";
}): string {
  if (params.line === "unopened") {
    return `${params.heroPos}_vs_${params.villainPos}_unopened_${params.size}`;
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

  return {
    tableId: input.tableId,
    handId: input.handId,
    seat: input.seat,
    spotKey: `cash_6max_100bb_${spotKey}`,
    heroHand: input.heroHand,
    mix,
    tags,
    explanation
  };
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
