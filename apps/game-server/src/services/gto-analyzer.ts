import { getPostflopAdvice, type AdvicePrecision, type PostflopContext } from "@cardpilot/advice-engine";
import type { Card } from "@cardpilot/poker-evaluator";
import type {
  HistoryGTOHandRecord,
  HistoryGTOAnalysis,
  HistoryGTOSpotAnalysis,
  StrategyMix,
} from "@cardpilot/shared-types";

const STREETS_ORDER = ["PREFLOP", "FLOP", "TURN", "RIVER"] as const;

interface DecisionPoint {
  street: "FLOP" | "TURN" | "RIVER";
  board: string[];
  pot: number;
  toCall: number;
  heroAction: string;
  heroAmount: number;
  effectiveStack: number;
  aggressor: "hero" | "villain" | "none";
  preflopAggressor: "hero" | "villain" | "none";
  heroInPosition: boolean;
  numVillains: number;
  villainPosition: string;
  actionHistory: Array<{ seat: number; street: string; type: string; amount: number }>;
}

/**
 * Reconstruct hero decision points from a completed hand record,
 * then run the advice engine on each one and score the hero's play.
 */
export async function analyzeHandGTO(
  handRecord: HistoryGTOHandRecord,
  precision: AdvicePrecision = "deep"
): Promise<HistoryGTOAnalysis> {
  const decisionPoints = extractDecisionPoints(handRecord);
  const spots: HistoryGTOSpotAnalysis[] = [];

  for (const dp of decisionPoints) {
    try {
      const context: PostflopContext = {
        tableId: "history-analysis",
        handId: `gto-${Date.now()}`,
        seat: handRecord.heroSeat,
        street: dp.street,
        heroHand: handRecord.heroCards as [Card, Card],
        board: dp.board as Card[],
        heroPosition: handRecord.heroPosition,
        villainPosition: dp.villainPosition,
        potSize: dp.pot,
        toCall: dp.toCall,
        effectiveStack: dp.effectiveStack,
        aggressor: dp.aggressor,
        preflopAggressor: dp.preflopAggressor,
        heroInPosition: dp.heroInPosition,
        numVillains: dp.numVillains,
        actionHistory: dp.actionHistory.map((a) => ({
          seat: a.seat,
          street: a.street as PostflopContext["street"],
          type: a.type as "fold" | "check" | "call" | "raise" | "all_in",
          amount: a.amount,
          at: 0,
        })),
        potType: inferPotType(dp.actionHistory),
      };

      const advice = await getPostflopAdvice(context, precision);

      const heroActionKey = mapActionToMixKey(dp.heroAction);
      const recommendedAction = advice.recommended ?? "call";
      const recommendedFreq = advice.mix[heroActionKey] ?? 0;
      const deviationScore = Math.round(Math.max(0, 1 - recommendedFreq) * 100);

      const alpha = advice.postflop?.alpha ?? 0;
      const mdf = advice.postflop?.mdf ?? 1;
      const equity = advice.math?.equityRequired ?? 0;

      const note = buildSpotNote(dp.heroAction, recommendedAction, recommendedFreq, advice.mix);

      spots.push({
        street: dp.street,
        board: dp.board,
        pot: dp.pot,
        heroAction: dp.heroAction,
        heroAmount: dp.heroAmount,
        recommended: {
          action: recommendedAction,
          mix: advice.mix,
        },
        deviationScore,
        alpha,
        mdf,
        equity,
        note,
      });
    } catch (err) {
      console.warn(`[gto-analyzer] Failed to analyze spot on ${dp.street}:`, (err as Error).message);
    }
  }

  const streetScores = computeStreetScores(spots);
  const overallScore = computeOverallScore(spots);

  return {
    overallScore,
    streetScores,
    spots,
    computedAt: Date.now(),
    precision,
  };
}

function extractDecisionPoints(hand: HistoryGTOHandRecord): DecisionPoint[] {
  const points: DecisionPoint[] = [];
  const heroSeat = hand.heroSeat;
  const bb = hand.bigBlind ?? 100;

  // Determine preflop aggressor
  const preflopRaises = hand.actions.filter(
    (a) => a.street.toUpperCase() === "PREFLOP" && (a.type === "raise" || a.type === "all_in")
  );
  const preflopAggressor: "hero" | "villain" | "none" =
    preflopRaises.length > 0
      ? preflopRaises[preflopRaises.length - 1].seat === heroSeat
        ? "hero"
        : "villain"
      : "none";

  // Determine villain position (last non-hero actor or fallback)
  const villainSeats = [...new Set(hand.actions.filter((a) => a.seat !== heroSeat).map((a) => a.seat))];
  const villainPosition = villainSeats.length > 0 ? guessPosition(villainSeats[0], hand.tableSize) : "CO";

  // Determine hero position order for IP/OOP
  const heroInPosition = isInPosition(hand.heroPosition);

  // Walk through streets and find hero actions
  for (const streetName of ["FLOP", "TURN", "RIVER"] as const) {
    const board = boardForStreet(hand.board, streetName);
    if (board.length === 0) continue;

    const streetActions = hand.actions.filter((a) => a.street.toUpperCase() === streetName);
    let pot = computePotBeforeStreet(hand.actions, streetName);
    let currentBet = 0;
    let streetAggressor: "hero" | "villain" | "none" = "none";

    for (const action of streetActions) {
      if (action.seat === heroSeat) {
        const toCall = Math.max(0, currentBet - streetCommittedBySeat(streetActions, heroSeat, action));
        const effectiveStack = Math.max(0, hand.stackSize - totalCommittedBySeat(hand.actions, heroSeat, action));

        points.push({
          street: streetName,
          board,
          pot,
          toCall,
          heroAction: action.type,
          heroAmount: action.amount,
          effectiveStack,
          aggressor: streetAggressor,
          preflopAggressor,
          heroInPosition,
          numVillains: Math.max(1, villainSeats.length),
          villainPosition,
          actionHistory: hand.actions.filter(
            (a) =>
              STREETS_ORDER.indexOf(a.street.toUpperCase() as typeof STREETS_ORDER[number]) <=
              STREETS_ORDER.indexOf(streetName)
          ),
        });
        break; // Only analyze first hero action per street for simplicity
      }

      // Track pot and current bet for non-hero actions
      if (action.type === "raise" || action.type === "all_in") {
        currentBet = action.amount;
        streetAggressor = "villain";
      } else if (action.type === "call") {
        // pot grows by the call amount
      } else if (action.type === "bet") {
        currentBet = action.amount;
        streetAggressor = "villain";
      }

      if (action.type !== "fold" && action.type !== "check") {
        pot += action.amount;
      }
    }
  }

  return points;
}

function boardForStreet(board: string[], street: "FLOP" | "TURN" | "RIVER"): string[] {
  if (street === "FLOP") return board.slice(0, 3);
  if (street === "TURN") return board.slice(0, 4);
  return board.slice(0, 5);
}

function computePotBeforeStreet(
  actions: HistoryGTOHandRecord["actions"],
  street: "FLOP" | "TURN" | "RIVER"
): number {
  const idx = STREETS_ORDER.indexOf(street);
  let pot = 0;
  for (const a of actions) {
    const aIdx = STREETS_ORDER.indexOf(a.street.toUpperCase() as typeof STREETS_ORDER[number]);
    if (aIdx >= idx) break;
    if (a.type !== "fold" && a.type !== "check") {
      pot += a.amount;
    }
  }
  return pot;
}

function streetCommittedBySeat(
  streetActions: HistoryGTOHandRecord["actions"],
  seat: number,
  beforeAction: HistoryGTOHandRecord["actions"][0]
): number {
  let committed = 0;
  for (const a of streetActions) {
    if (a === beforeAction) break;
    if (a.seat === seat && a.type !== "fold" && a.type !== "check") {
      committed += a.amount;
    }
  }
  return committed;
}

function totalCommittedBySeat(
  actions: HistoryGTOHandRecord["actions"],
  seat: number,
  beforeAction: HistoryGTOHandRecord["actions"][0]
): number {
  let committed = 0;
  for (const a of actions) {
    if (a === beforeAction) break;
    if (a.seat === seat && a.type !== "fold" && a.type !== "check") {
      committed += a.amount;
    }
  }
  return committed;
}

function inferPotType(actions: HistoryGTOHandRecord["actions"]): "SRP" | "3BP" | "4BP" {
  const preflopRaises = actions.filter(
    (a) => a.street.toUpperCase() === "PREFLOP" && (a.type === "raise" || a.type === "all_in")
  ).length;
  if (preflopRaises >= 3) return "4BP";
  if (preflopRaises === 2) return "3BP";
  return "SRP";
}

function mapActionToMixKey(action: string): keyof StrategyMix {
  if (action === "fold") return "fold";
  if (action === "call" || action === "check") return "call";
  return "raise";
}

function guessPosition(seat: number, tableSize: number): string {
  const positions6 = ["SB", "BB", "UTG", "MP", "CO", "BTN"];
  const positions9 = ["SB", "BB", "UTG", "UTG+1", "MP", "MP+1", "HJ", "CO", "BTN"];
  const positions = tableSize <= 6 ? positions6 : positions9;
  return positions[seat % positions.length] || "MP";
}

function isInPosition(position: string): boolean {
  return ["BTN", "CO", "HJ"].includes(position);
}

function buildSpotNote(
  heroAction: string,
  recommended: string,
  heroFreq: number,
  mix: StrategyMix
): string {
  if (heroFreq >= 0.5) {
    return `Good: ${heroAction} is within the recommended range (${Math.round(heroFreq * 100)}% frequency).`;
  }
  if (heroFreq >= 0.2) {
    return `Acceptable: ${heroAction} is a minor deviation. GTO prefers ${recommended} (${Math.round(mix[mapActionToMixKey(recommended)] * 100)}%).`;
  }
  return `Deviation: ${heroAction} is rarely recommended here (${Math.round(heroFreq * 100)}%). GTO strongly prefers ${recommended}.`;
}

function computeStreetScores(spots: HistoryGTOSpotAnalysis[]): {
  flop: number | null;
  turn: number | null;
  river: number | null;
} {
  const byStreet: Record<string, number[]> = { FLOP: [], TURN: [], RIVER: [] };
  for (const s of spots) {
    const key = s.street.toUpperCase();
    if (byStreet[key]) {
      byStreet[key].push(100 - s.deviationScore);
    }
  }
  return {
    flop: byStreet.FLOP.length > 0 ? avg(byStreet.FLOP) : null,
    turn: byStreet.TURN.length > 0 ? avg(byStreet.TURN) : null,
    river: byStreet.RIVER.length > 0 ? avg(byStreet.RIVER) : null,
  };
}

function computeOverallScore(spots: HistoryGTOSpotAnalysis[]): number {
  if (spots.length === 0) return 100;
  const scores = spots.map((s) => 100 - s.deviationScore);
  return Math.round(avg(scores));
}

function avg(arr: number[]): number {
  if (arr.length === 0) return 0;
  return arr.reduce((s, v) => s + v, 0) / arr.length;
}
