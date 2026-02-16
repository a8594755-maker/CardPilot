/**
 * Line Recognition Module
 *
 * Parses a full action sequence and tags poker "line types" for dashboards,
 * filters, scenario sharing, and GTO audit categorization.
 *
 * Recognized line types:
 *   CBET           – Preflop aggressor bets on flop
 *   DELAYED_CBET   – PFA checks flop, bets turn
 *   BARREL         – PFA bets consecutive streets (double/triple barrel)
 *   PROBE          – Non-PFA bets into PFA after PFA checks
 *   DONK_BET       – OOP player bets into PFA before PFA acts
 *   CHECK_RAISE    – Check then raise on the same street
 *   XR_TURN        – Check-raise specifically on the turn
 *   XR_RIVER       – Check-raise specifically on the river
 *   FLOAT_BET      – Call flop in position, bet turn when checked to
 *   OVERBET        – Bet > pot
 *   LIMP           – Preflop open-limp (call BB without raising)
 *   SQUEEZE        – 3bet after open + cold call
 *   COLD_4BET      – 4bet without having previously entered the pot
 *   THREE_BET      – Re-raise over an open raise preflop
 *   FOUR_BET_PLUS  – 4bet or higher preflop
 *   CHECK_BACK     – IP player checks back when checked to
 *   LEAD_RIVER     – OOP player leads river after checking prior streets
 */

import type { HandAction, Street } from "@cardpilot/shared-types";

// ── Public types ──

export type LineTag =
  | "CBET"
  | "DELAYED_CBET"
  | "BARREL"
  | "DOUBLE_BARREL"
  | "TRIPLE_BARREL"
  | "PROBE"
  | "DONK_BET"
  | "CHECK_RAISE"
  | "XR_TURN"
  | "XR_RIVER"
  | "FLOAT_BET"
  | "OVERBET"
  | "LIMP"
  | "SQUEEZE"
  | "THREE_BET"
  | "FOUR_BET_PLUS"
  | "COLD_4BET"
  | "CHECK_BACK"
  | "LEAD_RIVER";

export type PotType = "SRP" | "3BP" | "4BP" | "LIMPED";

export interface LineRecognitionResult {
  lineTags: LineTag[];
  potType: PotType;
  preflopAggressorSeat: number | null;
}

// ── Core API ──

/**
 * Analyze a complete action timeline and return all recognized line tags.
 *
 * @param actions       – Full action timeline for the hand (sorted by time).
 * @param heroSeat      – The seat of the hero (for hero-specific tags).
 * @param buttonSeat    – The seat of the button (for positional inference).
 * @param playerSeats   – All active seats in the hand.
 * @param bigBlind      – Big blind amount (for sizing classification).
 */
export function recognizeLines(input: {
  actions: HandAction[];
  heroSeat: number;
  buttonSeat: number;
  playerSeats: number[];
  bigBlind: number;
}): LineRecognitionResult {
  const { actions, heroSeat, buttonSeat, playerSeats, bigBlind } = input;

  const tags = new Set<LineTag>();

  const pfaResult = detectPreflopAggressor(actions);
  const pfaSeat = pfaResult.seat;
  const potType = pfaResult.potType;

  // ── Preflop line tags ──
  const preflopActions = filterStreet(actions, "PREFLOP");
  detectPreflopLines(preflopActions, heroSeat, bigBlind, tags);

  // ── Postflop line tags (per-street) ──
  for (const street of ["FLOP", "TURN", "RIVER"] as const) {
    const streetActions = filterStreet(actions, street);
    if (streetActions.length === 0) continue;

    detectPostflopLines({
      streetActions,
      allActions: actions,
      heroSeat,
      pfaSeat,
      street,
      bigBlind,
      buttonSeat,
      playerSeats,
      tags,
    });
  }

  // ── Multi-street patterns ──
  detectMultiStreetPatterns(actions, heroSeat, pfaSeat, tags);

  return {
    lineTags: [...tags],
    potType,
    preflopAggressorSeat: pfaSeat,
  };
}

// ── Preflop aggressor detection ──

interface PfaDetection {
  seat: number | null;
  potType: PotType;
}

export function detectPreflopAggressor(actions: HandAction[]): PfaDetection {
  const preflopActions = filterStreet(actions, "PREFLOP");
  const raises = preflopActions.filter(
    (a) => a.type === "raise" || a.type === "all_in"
  );

  if (raises.length === 0) {
    // Check if there were only calls (limped pot)
    const calls = preflopActions.filter((a) => a.type === "call");
    if (calls.length > 0) {
      return { seat: null, potType: "LIMPED" };
    }
    return { seat: null, potType: "SRP" };
  }

  const lastRaiser = raises[raises.length - 1];

  let potType: PotType;
  if (raises.length >= 3) {
    potType = "4BP";
  } else if (raises.length === 2) {
    potType = "3BP";
  } else {
    potType = "SRP";
  }

  return { seat: lastRaiser.seat, potType };
}

// ── Preflop lines ──

function detectPreflopLines(
  preflopActions: HandAction[],
  heroSeat: number,
  bigBlind: number,
  tags: Set<LineTag>
): void {
  const heroActions = preflopActions.filter((a) => a.seat === heroSeat);
  const allRaises = preflopActions.filter(
    (a) => a.type === "raise" || a.type === "all_in"
  );

  // Limp detection: hero calls without raising preflop and no raise before hero's action
  for (const action of heroActions) {
    if (action.type === "call") {
      const priorRaises = allRaises.filter((r) => r.at < action.at);
      if (priorRaises.length === 0) {
        tags.add("LIMP");
        break;
      }
    }
  }

  // 3bet / 4bet+ / squeeze detection
  const heroRaises = heroActions.filter(
    (a) => a.type === "raise" || a.type === "all_in"
  );

  for (const heroRaise of heroRaises) {
    const priorRaisesAll = allRaises.filter(
      (r) => r.at < heroRaise.at
    );
    const priorRaisesOther = priorRaisesAll.filter(
      (r) => r.seat !== heroSeat
    );

    if (priorRaisesAll.length === 1) {
      // Check for squeeze: open + cold call + hero 3bet
      const openRaise = priorRaisesAll[0];
      const coldCalls = preflopActions.filter(
        (a) =>
          a.type === "call" &&
          a.seat !== heroSeat &&
          a.at > openRaise.at &&
          a.at < heroRaise.at
      );
      if (coldCalls.length > 0) {
        tags.add("SQUEEZE");
      } else {
        tags.add("THREE_BET");
      }
    } else if (priorRaisesAll.length >= 2) {
      tags.add("FOUR_BET_PLUS");

      // Cold 4bet: hero's first aggressive preflop action and there are already 2+ raises from others
      const heroPriorActions = preflopActions.filter(
        (a) => a.seat === heroSeat && a.at < heroRaise.at
      );
      const heroPriorAggressive = heroPriorActions.filter(
        (a) => a.type === "raise" || a.type === "all_in"
      );
      if (heroPriorAggressive.length === 0) {
        tags.add("COLD_4BET");
      }
    }
  }
}

// ── Postflop lines ──

function detectPostflopLines(input: {
  streetActions: HandAction[];
  allActions: HandAction[];
  heroSeat: number;
  pfaSeat: number | null;
  street: "FLOP" | "TURN" | "RIVER";
  bigBlind: number;
  buttonSeat: number;
  playerSeats: number[];
  tags: Set<LineTag>;
}): void {
  const {
    streetActions,
    allActions,
    heroSeat,
    pfaSeat,
    street,
    bigBlind,
    tags,
  } = input;

  const heroActions = streetActions.filter((a) => a.seat === heroSeat);
  const heroIsPfa = pfaSeat !== null && heroSeat === pfaSeat;

  // ── C-bet ──
  if (heroIsPfa && street === "FLOP") {
    const heroBets = heroActions.filter(
      (a) => a.type === "raise" || a.type === "all_in"
    );
    if (heroBets.length > 0) {
      tags.add("CBET");
    }
  }

  // ── Delayed C-bet: PFA checks flop, bets turn ──
  if (heroIsPfa && street === "TURN") {
    const flopActions = filterStreet(allActions, "FLOP");
    const heroFlopActions = flopActions.filter((a) => a.seat === heroSeat);
    const heroFlopChecks = heroFlopActions.filter((a) => a.type === "check");
    const heroFlopBets = heroFlopActions.filter(
      (a) => a.type === "raise" || a.type === "all_in"
    );

    if (heroFlopChecks.length > 0 && heroFlopBets.length === 0) {
      const heroTurnBets = heroActions.filter(
        (a) => a.type === "raise" || a.type === "all_in"
      );
      if (heroTurnBets.length > 0) {
        tags.add("DELAYED_CBET");
      }
    }
  }

  // ── Donk bet: Non-PFA bets before PFA acts on this street ──
  if (!heroIsPfa && pfaSeat !== null) {
    const heroBets = heroActions.filter(
      (a) => a.type === "raise" || a.type === "all_in"
    );
    for (const heroBet of heroBets) {
      const pfaActedBefore = streetActions.some(
        (a) =>
          a.seat === pfaSeat &&
          a.at < heroBet.at &&
          (a.type === "raise" || a.type === "all_in" || a.type === "check" || a.type === "call")
      );
      if (!pfaActedBefore) {
        tags.add("DONK_BET");
        break;
      }
    }
  }

  // ── Probe bet: Non-PFA bets after PFA checks on the SAME street ──
  if (!heroIsPfa && pfaSeat !== null) {
    const pfaChecksThisStreet = streetActions.filter(
      (a) => a.seat === pfaSeat && a.type === "check"
    );
    if (pfaChecksThisStreet.length > 0) {
      const heroBets = heroActions.filter(
        (a) =>
          a.type === "raise" || a.type === "all_in"
      );
      for (const heroBet of heroBets) {
        if (pfaChecksThisStreet.some((c) => c.at < heroBet.at)) {
          tags.add("PROBE");
          break;
        }
      }
    }
  }

  // ── Check-raise ──
  detectCheckRaise(streetActions, heroSeat, street, tags);

  // ── Float bet: Hero calls flop in position, bets turn when checked to ──
  if (street === "TURN" && !heroIsPfa) {
    const flopActions = filterStreet(allActions, "FLOP");
    const heroFlopCalls = flopActions.filter(
      (a) => a.seat === heroSeat && a.type === "call"
    );
    if (heroFlopCalls.length > 0) {
      // Check if opponent checked turn before hero bet
      const nonHeroTurnChecks = streetActions.filter(
        (a) => a.seat !== heroSeat && a.type === "check"
      );
      const heroTurnBets = heroActions.filter(
        (a) => a.type === "raise" || a.type === "all_in"
      );
      if (
        nonHeroTurnChecks.length > 0 &&
        heroTurnBets.length > 0 &&
        nonHeroTurnChecks.some((c) => c.at < heroTurnBets[0].at)
      ) {
        tags.add("FLOAT_BET");
      }
    }
  }

  // ── Check back: Hero checks when checked to (IP) ──
  const heroChecks = heroActions.filter((a) => a.type === "check");
  if (heroChecks.length > 0) {
    for (const heroCheck of heroChecks) {
      const otherCheckedBefore = streetActions.some(
        (a) => a.seat !== heroSeat && a.type === "check" && a.at < heroCheck.at
      );
      if (otherCheckedBefore) {
        tags.add("CHECK_BACK");
        break;
      }
    }
  }

  // ── Overbet: Hero bets > pot ──
  for (const action of heroActions) {
    if (
      (action.type === "raise" || action.type === "all_in") &&
      action.amount > 0
    ) {
      // Estimate pot at point of bet (rough: sum of all prior amounts)
      const priorPot = estimatePotAtAction(allActions, action);
      if (priorPot > 0 && action.amount > priorPot) {
        tags.add("OVERBET");
        break;
      }
    }
  }

  // ── Lead river: OOP non-PFA leads river after checking prior streets ──
  if (street === "RIVER" && !heroIsPfa) {
    const heroRiverBets = heroActions.filter(
      (a) => a.type === "raise" || a.type === "all_in"
    );
    if (heroRiverBets.length > 0) {
      const flopActions = filterStreet(allActions, "FLOP");
      const turnActions = filterStreet(allActions, "TURN");
      const heroFlopChecks = flopActions.filter(
        (a) => a.seat === heroSeat && a.type === "check"
      );
      const heroTurnChecks = turnActions.filter(
        (a) => a.seat === heroSeat && a.type === "check"
      );
      const heroFlopBets = flopActions.filter(
        (a) =>
          a.seat === heroSeat &&
          (a.type === "raise" || a.type === "all_in")
      );
      const heroTurnBets = turnActions.filter(
        (a) =>
          a.seat === heroSeat &&
          (a.type === "raise" || a.type === "all_in")
      );
      if (
        heroFlopChecks.length > 0 &&
        heroFlopBets.length === 0 &&
        (turnActions.length === 0 ||
          (heroTurnChecks.length > 0 && heroTurnBets.length === 0))
      ) {
        tags.add("LEAD_RIVER");
      }
    }
  }
}

// ── Multi-street barrel detection ──

function detectMultiStreetPatterns(
  allActions: HandAction[],
  heroSeat: number,
  pfaSeat: number | null,
  tags: Set<LineTag>
): void {
  if (pfaSeat === null || heroSeat !== pfaSeat) return;

  const streetsBet: string[] = [];

  for (const street of ["FLOP", "TURN", "RIVER"] as const) {
    const streetActions = filterStreet(allActions, street);
    const heroBets = streetActions.filter(
      (a) =>
        a.seat === heroSeat &&
        (a.type === "raise" || a.type === "all_in")
    );
    if (heroBets.length > 0) {
      streetsBet.push(street);
    } else {
      break; // Barrel requires consecutive streets
    }
  }

  if (streetsBet.length >= 2) {
    tags.add("BARREL");
  }
  if (streetsBet.length === 2) {
    tags.add("DOUBLE_BARREL");
  }
  if (streetsBet.length >= 3) {
    tags.add("TRIPLE_BARREL");
  }
}

// ── Check-raise detection ──

function detectCheckRaise(
  streetActions: HandAction[],
  heroSeat: number,
  street: "FLOP" | "TURN" | "RIVER",
  tags: Set<LineTag>
): void {
  const heroActions = streetActions.filter((a) => a.seat === heroSeat);
  const heroChecks = heroActions.filter((a) => a.type === "check");
  const heroRaises = heroActions.filter(
    (a) => a.type === "raise" || a.type === "all_in"
  );

  if (heroChecks.length === 0 || heroRaises.length === 0) return;

  // Hero must check first, then raise after someone else bets
  for (const check of heroChecks) {
    for (const raise of heroRaises) {
      if (raise.at <= check.at) continue;
      // Check that an opponent bet between hero's check and raise
      const opponentBet = streetActions.some(
        (a) =>
          a.seat !== heroSeat &&
          (a.type === "raise" || a.type === "all_in") &&
          a.at > check.at &&
          a.at < raise.at
      );
      if (opponentBet) {
        tags.add("CHECK_RAISE");
        if (street === "TURN") tags.add("XR_TURN");
        if (street === "RIVER") tags.add("XR_RIVER");
        return;
      }
    }
  }
}

// ── Helpers ──

function filterStreet(actions: HandAction[], street: Street): HandAction[] {
  return actions.filter((a) => a.street === street);
}

function estimatePotAtAction(
  allActions: HandAction[],
  targetAction: HandAction
): number {
  let pot = 0;
  for (const action of allActions) {
    if (action.at >= targetAction.at) break;
    if (action.amount > 0) {
      pot += action.amount;
    }
  }
  return pot;
}

// ── Convenience: classify a spot type from line tags ──

export type SpotType =
  | "SRP"
  | "3BP"
  | "4BP"
  | "LIMPED"
  | "SQUEEZE_POT";

export function classifySpotType(result: LineRecognitionResult): SpotType {
  if (result.lineTags.includes("SQUEEZE")) return "SQUEEZE_POT";
  return result.potType === "LIMPED" ? "LIMPED" : result.potType;
}

// ── Convenience: classify action deviation type ──

export type ActionDeviationType =
  | "OVERFOLD"
  | "UNDERFOLD"
  | "OVERBLUFF"
  | "UNDERBLUFF"
  | "OVERCALL"
  | "UNDERCALL"
  | "CORRECT";

export function classifyActionDeviation(input: {
  gtoMix: { raise: number; call: number; fold: number };
  actualAction: "raise" | "call" | "fold";
  threshold?: number;
}): ActionDeviationType {
  const { gtoMix, actualAction, threshold = 0.15 } = input;
  const best = Math.max(gtoMix.raise, gtoMix.call, gtoMix.fold);
  const chosen = gtoMix[actualAction];

  if (Math.abs(chosen - best) < threshold) return "CORRECT";

  if (actualAction === "fold") {
    return gtoMix.fold < threshold ? "OVERFOLD" : "CORRECT";
  }
  if (actualAction === "call") {
    if (gtoMix.call < threshold && gtoMix.fold > 0.4) return "OVERCALL";
    if (gtoMix.call > 0.5 && gtoMix.call > gtoMix.raise) return "CORRECT";
    return "UNDERCALL";
  }
  if (actualAction === "raise") {
    if (gtoMix.raise < threshold && gtoMix.fold > 0.3) return "OVERBLUFF";
    if (gtoMix.raise < threshold) return "UNDERBLUFF";
    return "CORRECT";
  }

  return "CORRECT";
}
