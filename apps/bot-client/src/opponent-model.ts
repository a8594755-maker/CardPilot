// ===== Per-opponent stat tracking and adjustment =====

import type { HandAction, TableState } from './types.js';

export interface OpponentStats {
  seatId: number;
  handsObserved: number;

  // Preflop
  vpipCount: number;         // voluntarily put in pot
  vpipOpportunities: number;
  pfrCount: number;          // preflop raise
  pfrOpportunities: number;

  // Postflop
  cbetMade: number;
  cbetOpportunities: number;
  foldToCbetCount: number;
  foldToCbetFacing: number;

  // General
  foldToRaiseCount: number;
  facingRaiseCount: number;
  totalBetsAndRaises: number;
  totalCallsAndChecks: number;
}

export interface OpponentProfile {
  vpip: number;            // 0-1
  pfr: number;             // 0-1
  foldToCbet: number;      // 0-1
  foldToRaise: number;     // 0-1
  aggression: number;      // 0-1
  isKnown: boolean;        // handsObserved > threshold
}

export interface OpponentAdjustment {
  raiseAdj: number;
  callAdj: number;
  foldAdj: number;
}

const KNOWN_THRESHOLD = 15;

function createOpponentStats(seat: number): OpponentStats {
  return {
    seatId: seat,
    handsObserved: 0,
    vpipCount: 0,
    vpipOpportunities: 0,
    pfrCount: 0,
    pfrOpportunities: 0,
    cbetMade: 0,
    cbetOpportunities: 0,
    foldToCbetCount: 0,
    foldToCbetFacing: 0,
    foldToRaiseCount: 0,
    facingRaiseCount: 0,
    totalBetsAndRaises: 0,
    totalCallsAndChecks: 0,
  };
}

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

export class OpponentTracker {
  private stats = new Map<number, OpponentStats>();
  private processedActions = new Set<string>(); // deduplicate
  private lastHandId: string | null = null;
  private preflopRaiserSeat: number | null = null;

  // Called when a new hand starts — tracks VPIP/PFR opportunities
  observeHandStart(state: TableState): void {
    if (!state.handId || state.handId === this.lastHandId) return;
    this.lastHandId = state.handId;
    this.preflopRaiserSeat = null;
    this.processedActions.clear();

    // Each player in hand has a VPIP and PFR opportunity
    for (const p of state.players) {
      if (!p.inHand || p.folded) continue;
      const s = this.getOrCreate(p.seat);
      s.handsObserved++;
      s.vpipOpportunities++;
      s.pfrOpportunities++;
    }
  }

  // Called for each action observed
  observeAction(action: HandAction, state: TableState, mySeat: number): void {
    if (action.seat === mySeat) return; // don't track self

    // Deduplicate
    const key = `${state.handId}:${action.street}:${action.seat}:${action.type}:${action.amount}:${action.at}`;
    if (this.processedActions.has(key)) return;
    this.processedActions.add(key);

    const s = this.getOrCreate(action.seat);

    // Track action type
    if (action.type === 'raise' || action.type === 'all_in') {
      s.totalBetsAndRaises++;
    } else if (action.type === 'call' || action.type === 'check') {
      s.totalCallsAndChecks++;
    }

    // Preflop stats
    if (action.street === 'PREFLOP') {
      if (action.type === 'raise' || action.type === 'all_in') {
        s.pfrCount++;
        s.vpipCount++;
        if (!this.preflopRaiserSeat) {
          this.preflopRaiserSeat = action.seat;
        }
      } else if (action.type === 'call') {
        s.vpipCount++;
      }
    }

    // Postflop: c-bet tracking
    if (action.street === 'FLOP' && this.preflopRaiserSeat != null) {
      if (action.seat === this.preflopRaiserSeat) {
        // Preflop raiser acting on flop
        s.cbetOpportunities++;
        if (action.type === 'raise' || action.type === 'all_in') {
          s.cbetMade++;
        }
      }
    }

    // Fold tracking
    if (action.type === 'fold') {
      s.totalCallsAndChecks++; // fold counts toward passive actions
      // Check if facing a raise
      const streetActions = state.actions.filter(
        a => a.street === action.street && a.at < action.at,
      );
      const facingRaise = streetActions.some(
        a => (a.type === 'raise' || a.type === 'all_in') && a.seat !== action.seat,
      );
      if (facingRaise) {
        s.facingRaiseCount++;
        s.foldToRaiseCount++;
      }
      // Check if fold to c-bet
      if (action.street === 'FLOP' && this.preflopRaiserSeat != null && this.preflopRaiserSeat !== action.seat) {
        const pfRaiserBet = streetActions.some(
          a => a.seat === this.preflopRaiserSeat && (a.type === 'raise' || a.type === 'all_in'),
        );
        if (pfRaiserBet) {
          s.foldToCbetFacing++;
          s.foldToCbetCount++;
        }
      }
    }

    // Call/raise facing a raise
    if ((action.type === 'call' || action.type === 'raise') && action.street !== 'PREFLOP') {
      const streetActions = state.actions.filter(
        a => a.street === action.street && a.at < action.at,
      );
      const facingRaise = streetActions.some(
        a => (a.type === 'raise' || a.type === 'all_in') && a.seat !== action.seat,
      );
      if (facingRaise) {
        s.facingRaiseCount++;
        // Not folded → did not fold to raise (only increment facingRaiseCount)
      }
    }
  }

  // Get computed profile for an opponent
  getProfile(seat: number): OpponentProfile {
    const s = this.stats.get(seat);
    if (!s || s.handsObserved < 3) {
      return { vpip: 0.5, pfr: 0.2, foldToCbet: 0.5, foldToRaise: 0.5, aggression: 0.5, isKnown: false };
    }

    const vpip = s.vpipOpportunities > 0 ? s.vpipCount / s.vpipOpportunities : 0.5;
    const pfr = s.pfrOpportunities > 0 ? s.pfrCount / s.pfrOpportunities : 0.2;
    const foldToCbet = s.foldToCbetFacing > 0 ? s.foldToCbetCount / s.foldToCbetFacing : 0.5;
    const foldToRaise = s.facingRaiseCount > 0 ? s.foldToRaiseCount / s.facingRaiseCount : 0.5;
    const totalActions = s.totalBetsAndRaises + s.totalCallsAndChecks;
    const aggression = totalActions > 0 ? s.totalBetsAndRaises / totalActions : 0.5;

    return {
      vpip,
      pfr,
      foldToCbet,
      foldToRaise,
      aggression,
      isKnown: s.handsObserved >= KNOWN_THRESHOLD,
    };
  }

  // Compute mix adjustment for facing a specific opponent
  computeAdjustment(
    seat: number,
    situation: 'facing_raise' | 'facing_cbet' | 'general',
  ): OpponentAdjustment {
    const profile = this.getProfile(seat);
    if (!profile.isKnown) {
      return { raiseAdj: 1.0, callAdj: 1.0, foldAdj: 1.0 };
    }

    let raiseAdj = 1.0;
    let callAdj = 1.0;
    let foldAdj = 1.0;

    if (situation === 'facing_raise') {
      // Tight raiser: their raises are strong → fold more
      if (profile.pfr < 0.10) {
        foldAdj += 0.08;
      }
      // Loose raiser: their raises are wider → call/raise more
      if (profile.pfr > 0.25) {
        callAdj += 0.06;
        raiseAdj += 0.04;
      }
    }

    if (situation === 'facing_cbet') {
      // They fold to raises often → bluff raise more
      if (profile.foldToCbet > 0.65) {
        raiseAdj += 0.10;
      }
      // They rarely fold to c-bets → don't bluff as much
      if (profile.foldToCbet < 0.35) {
        foldAdj += 0.05;
        raiseAdj -= 0.05;
      }
    }

    if (situation === 'general') {
      // Passive opponent: their bets mean strength → fold more
      if (profile.aggression < 0.3) {
        foldAdj += 0.06;
      }
      // Aggressive opponent: they bluff more → call more
      if (profile.aggression > 0.6) {
        callAdj += 0.05;
      }
    }

    return {
      raiseAdj: clamp(raiseAdj, 0.85, 1.15),
      callAdj: clamp(callAdj, 0.85, 1.15),
      foldAdj: clamp(foldAdj, 0.85, 1.15),
    };
  }

  private getOrCreate(seat: number): OpponentStats {
    let s = this.stats.get(seat);
    if (!s) {
      s = createOpponentStats(seat);
      this.stats.set(seat, s);
    }
    return s;
  }
}
