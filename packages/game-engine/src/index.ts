import { randomInt } from "node:crypto";
import { v4 as uuidv4 } from "uuid";
import pokersolver from "pokersolver";
import type {
  HandAction,
  HandActionType,
  DoubleBoardMode,
  GameType,
  LegalActions,
  PlayerActionType,
  PlayerStatus,
  RunoutPayout,
  SettlementResult,
  Street,
  TablePlayer,
  TableState,
} from "@cardpilot/shared-types";
import { getClockwiseSeatsFromButton as canonicalClockwiseSeats } from "@cardpilot/shared-types";

const RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"];
const SUITS = ["s", "h", "d", "c"];
const { Hand } = pokersolver as unknown as {
  Hand: {
    solve(cards: string[]): { descr: string; rank: number };
    winners(hands: Array<{ descr: string; rank: number }>): Array<{ descr: string; rank: number }>;
  };
};

const POSITION_LABELS_BY_COUNT: Record<number, readonly string[]> = {
  2: ["SB", "BB"],
  3: ["SB", "BB", "BTN"],
  4: ["SB", "BB", "UTG", "BTN"],
  5: ["SB", "BB", "UTG", "CO", "BTN"],
  6: ["SB", "BB", "UTG", "HJ", "CO", "BTN"],
};

type TableMode = 'COACH' | 'REVIEW' | 'CASUAL';

type MutableTableState = TableState & {
  pendingToAct: Set<number>;
  deck: string[];
  holeCards: Map<number, string[]>;
  holeCardCount: number;
  contributed: Map<number, number>;
  handStartStacks: Map<number, number>;
  pendingDeadBlinds: Map<number, number>;
  pendingDeadBlindActions: HandAction[];
  shownCards: Record<number, [string, string]>;
  /** Backward-compatible alias for shownCards. */
  shownHands: Record<number, [string, string]>;
  revealedHoles: Record<number, [string, string]>;
  muckedSeats: number[];
  showdownPhase: "none" | "decision";
  /** The currentBet value at which the last FULL bet/raise occurred. */
  lastReopenBet: number;
  /** Seats that have voluntarily acted since the most recent FULL raise level. */
  actedSinceLastFullRaise: Set<number>;
  ritVotes: Record<number, boolean | null>;
};

export class GameTable {
  private state: MutableTableState;
  private ante: number;
  private readonly rakeEnabled: boolean;
  private readonly rakePercent: number;
  private readonly rakeCap: number;
  private runItTwiceEnabled: boolean;
  private gameType: GameType;
  private bombPotEnabled: boolean;
  private bombPotFrequency: number;
  private doubleBoardMode: DoubleBoardMode;
  private handCounter = 0;
  private holeCardCount = 2;
  private isBombPotHand = false;
  private isDoubleBoardHand = false;
  private secondaryBoard: string[] = [];
  private doubleBoardPayouts: RunoutPayout[] | null = null;
  private pendingBlindLevel: { smallBlind: number; bigBlind: number; ante: number } | null = null;
  private consecutiveTimeouts = new Map<number, number>();
  private allInRunCount: 1 | 2 = 1;
  private runoutPending = false;
  private collectedFee = 0;
  private settlementResult: SettlementResult | null = null;
  private handInProgress = false;

  constructor(params: {
    tableId: string;
    smallBlind: number;
    bigBlind: number;
    mode?: TableMode;
    ante?: number;
    runItTwiceEnabled?: boolean;
    gameType?: GameType;
    bombPotEnabled?: boolean;
    bombPotFrequency?: number;
    doubleBoardMode?: DoubleBoardMode;
    rakeEnabled?: boolean;
    rakePercent?: number;
    rakeCap?: number;
  }) {
    this.ante = Math.max(0, params.ante ?? 0);
    this.runItTwiceEnabled = params.runItTwiceEnabled ?? false;
    this.gameType = params.gameType ?? "texas";
    this.bombPotEnabled = params.bombPotEnabled ?? false;
    this.bombPotFrequency = Math.max(0, Math.floor(params.bombPotFrequency ?? 0));
    this.doubleBoardMode = params.doubleBoardMode ?? "off";
    this.holeCardCount = this.gameType === "omaha" ? 4 : 2;
    this.rakePercent = Math.max(0, params.rakePercent ?? 0);
    this.rakeEnabled = params.rakeEnabled ?? this.rakePercent > 0;
    // rakeCap<=0 means uncapped rake
    this.rakeCap = params.rakeCap != null && params.rakeCap > 0
      ? params.rakeCap
      : Number.POSITIVE_INFINITY;

    this.state = {
      tableId: params.tableId,
      stateVersion: 0,
      smallBlind: params.smallBlind,
      bigBlind: params.bigBlind,
      ante: this.ante,
      buttonSeat: 1,
      street: "SHOWDOWN",
      board: [],
      pot: 0,
      currentBet: 0,
      minRaiseTo: params.bigBlind * 2,
      lastFullRaiseSize: params.bigBlind,
      lastFullBet: 0,
      actorSeat: null,
      handId: null,
      players: [],
      actions: [],
      legalActions: null,
      mode: params.mode ?? "COACH",
      gameType: this.gameType,
      isBombPotHand: false,
      isDoubleBoardHand: false,
      positions: {},
      shownCards: {},
      shownHands: {},
      revealedHoles: {},
      muckedSeats: [],
      showdownPhase: "none",
      ritVotes: {},
      runItTwiceEnabled: this.runItTwiceEnabled,
      nextBlindLevel: null,
      pendingToAct: new Set<number>(),
      deck: [],
      holeCardCount: this.holeCardCount,
      holeCards: new Map(),
      handStartStacks: new Map(),
      contributed: new Map(),
      pendingDeadBlinds: new Map(),
      pendingDeadBlindActions: [],
      lastReopenBet: 0,
      actedSinceLastFullRaise: new Set<number>()
    };
  }

  handleTimeout(seat: number): { state: TableState; action: PlayerActionType; autoSatOut: boolean } {
    if (this.state.handId === null) {
      throw new Error("no active hand");
    }

    if (this.state.street === "RUN_IT_TWICE_PROMPT") {
      const state = this.applyAction(seat, "vote_rit", undefined, false);
      const timeoutCount = (this.consecutiveTimeouts.get(seat) ?? 0) + 1;
      this.consecutiveTimeouts.set(seat, timeoutCount);
      const autoSatOut = this.applyTimeoutSitOutIfNeeded(seat, timeoutCount);
      return { state, action: "vote_rit", autoSatOut };
    }

    if (this.state.actorSeat !== seat) {
      throw new Error("not your turn");
    }

    const legal = this.computeLegalActions();
    if (!legal) {
      throw new Error("no legal actions for timeout");
    }

    const fallbackAction: PlayerActionType = legal.canCheck ? "check" : "fold";
    const state = this.applyAction(seat, fallbackAction);
    const timeoutCount = (this.consecutiveTimeouts.get(seat) ?? 0) + 1;
    this.consecutiveTimeouts.set(seat, timeoutCount);
    const autoSatOut = this.applyTimeoutSitOutIfNeeded(seat, timeoutCount);
    return { state, action: fallbackAction, autoSatOut };
  }

  getPublicState(): TableState {
    const {
      pendingToAct: _pending,
      deck: _deck,
      holeCards: _holes,
      contributed: _contrib,
      handStartStacks: _handStartStacks,
      pendingDeadBlinds: _pendingDeadBlinds,
      pendingDeadBlindActions: _pendingDeadBlindActions,
      lastReopenBet: _lastReopenBet,
      actedSinceLastFullRaise: _actedSinceLastFullRaise,
      ...rest
    } = this.state;
    // Compute legalActions for current actor
    const legal = this.computeLegalActions();
    const positions: Record<number, string> = {};
    if (this.state.handId) {
      for (const p of this.state.players) {
        if (p.inHand) positions[p.seat] = this.getPosition(p.seat);
      }
    }
    return { ...rest, legalActions: legal, positions };
  }

  configureVariantSettings(params: {
    runItTwiceEnabled?: boolean;
    gameType?: GameType;
    bombPotEnabled?: boolean;
    bombPotFrequency?: number;
    doubleBoardMode?: DoubleBoardMode;
  }): void {
    if (this.isHandActive()) {
      throw new Error("cannot update variant settings during an active hand");
    }
    if (typeof params.runItTwiceEnabled === "boolean") {
      this.runItTwiceEnabled = params.runItTwiceEnabled;
      this.state.runItTwiceEnabled = this.runItTwiceEnabled;
    }
    if (params.gameType) {
      this.gameType = params.gameType;
    }
    if (typeof params.bombPotEnabled === "boolean") {
      this.bombPotEnabled = params.bombPotEnabled;
    }
    if (typeof params.bombPotFrequency === "number") {
      this.bombPotFrequency = Math.max(0, Math.floor(params.bombPotFrequency));
    }
    if (params.doubleBoardMode) {
      this.doubleBoardMode = params.doubleBoardMode;
    }

    this.holeCardCount = this.gameType === "omaha" ? 4 : 2;
    this.state.gameType = this.gameType;
    this.state.holeCardCount = this.holeCardCount;
  }

  getHoleCards(seat: number): [string, string] | null {
    const cards = this.state.holeCards.get(seat);
    if (!cards || cards.length < 2) return null;
    return [cards[0], cards[1]];
  }

  getPrivateHoleCards(seat: number): string[] | null {
    const cards = this.state.holeCards.get(seat);
    return cards ? [...cards] : null;
  }

  isSeatFolded(seat: number): boolean {
    const player = this.state.players.find((p) => p.seat === seat);
    return player?.folded ?? false;
  }

  getShowdownContenderSeats(): number[] {
    return this.state.players
      .filter((p) => p.inHand && !p.folded && this.state.holeCards.has(p.seat))
      .map((p) => p.seat)
      .sort((a, b) => a - b);
  }

  revealPublicHand(seat: number): boolean {
    const cards = this.state.holeCards.get(seat);
    if (!cards) return false;
    this.state.shownCards[seat] = [cards[0], cards[1]];
    this.state.shownHands[seat] = [cards[0], cards[1]];
    this.state.revealedHoles[seat] = [cards[0], cards[1]];
    this.state.muckedSeats = this.state.muckedSeats.filter((s) => s !== seat);
    return true;
  }

  muckPublicHand(seat: number): boolean {
    if (!this.state.holeCards.has(seat)) return false;
    if (this.state.shownCards[seat]) {
      const next = { ...this.state.shownCards };
      delete next[seat];
      this.state.shownCards = next;
    }
    if (this.state.shownHands[seat]) {
      const next = { ...this.state.shownHands };
      delete next[seat];
      this.state.shownHands = next;
    }
    if (this.state.revealedHoles[seat]) {
      const next = { ...this.state.revealedHoles };
      delete next[seat];
      this.state.revealedHoles = next;
    }
    if (!this.state.muckedSeats.includes(seat)) {
      this.state.muckedSeats = [...this.state.muckedSeats, seat].sort((a, b) => a - b);
    }
    return true;
  }

  finalizeShowdownReveals(params?: { autoMuckLosingHands?: boolean }): void {
    if (this.state.showdownPhase !== "decision") return;
    const winners = new Set((this.state.winners ?? []).map((w) => w.seat));
    const contenders = this.getShowdownContenderSeats();
    const autoMuckLosingHands = params?.autoMuckLosingHands ?? true;

    for (const seat of winners) {
      this.revealPublicHand(seat);
    }

    if (autoMuckLosingHands) {
      for (const seat of contenders) {
        if (winners.has(seat)) continue;
        if (this.state.revealedHoles[seat]) continue;
        this.muckPublicHand(seat);
      }
    }

    this.state.showdownPhase = "none";
  }

  addPlayer(player: { seat: number; userId: string; name: string; stack: number; status?: PlayerStatus; isNewPlayer?: boolean }): void {
    if (this.state.players.some((p) => p.seat === player.seat)) {
      throw new Error("seat already occupied");
    }
    if (player.stack <= 0) {
      throw new Error("stack must be greater than 0");
    }
    this.state.players.push({
      seat: player.seat,
      userId: player.userId,
      name: player.name,
      stack: player.stack,
      inHand: false,
      folded: false,
      allIn: false,
      streetCommitted: 0,
      status: player.status ?? 'active',
      isNewPlayer: player.isNewPlayer ?? false,
    });
    this.consecutiveTimeouts.set(player.seat, 0);
    this.state.players.sort((a, b) => a.seat - b.seat);
  }

  addStack(seat: number, amount: number): void {
    const player = this.state.players.find((p) => p.seat === seat);
    if (!player) throw new Error("player not found");
    player.stack += amount;
  }

  removePlayer(seat: number): void {
    const pendingDeadBlind = this.state.pendingDeadBlinds.get(seat) ?? 0;
    if (pendingDeadBlind > 0 && !this.isHandActive()) {
      this.state.pot = Math.max(0, this.state.pot - pendingDeadBlind);
    }
    this.state.players = this.state.players.filter((p) => p.seat !== seat);
    this.state.pendingToAct.delete(seat);
    this.state.actedSinceLastFullRaise.delete(seat);
    this.state.pendingDeadBlinds.delete(seat);
    this.state.pendingDeadBlindActions = this.state.pendingDeadBlindActions.filter((action) => action.seat !== seat);
    this.state.holeCards.delete(seat);
    this.consecutiveTimeouts.delete(seat);
  }

  startHand(): { handId: string } {
    if (this.isHandActive()) {
      throw new Error("hand already active");
    }

    if (this.pendingBlindLevel) {
      this.state.smallBlind = this.pendingBlindLevel.smallBlind;
      this.state.bigBlind = this.pendingBlindLevel.bigBlind;
      this.ante = this.pendingBlindLevel.ante;
      this.state.ante = this.pendingBlindLevel.ante;
      this.pendingBlindLevel = null;
      this.state.nextBlindLevel = null;
    }

    const seated = this.state.players.filter(
      (p) => p.stack > 0 && p.status === 'active'
    );
    if (seated.length < 2) {
      throw new Error("need at least 2 players with chips");
    }

    const handId = uuidv4();
    const pendingDeadBlinds = new Map(this.state.pendingDeadBlinds);
    const pendingDeadBlindActions = [...this.state.pendingDeadBlindActions];
    this.state.pendingDeadBlinds.clear();
    this.state.pendingDeadBlindActions = [];

    this.state.handId = handId;
    this.state.street = "PREFLOP";
    this.handInProgress = true;
    this.state.board = [];
    this.state.actions = [...pendingDeadBlindActions];
    this.state.pot = 0;
    this.state.currentBet = this.state.bigBlind;
    this.state.minRaiseTo = this.state.bigBlind * 2;
    this.state.lastFullRaiseSize = this.state.bigBlind;
    this.state.lastFullBet = this.state.bigBlind;
    this.state.lastReopenBet = this.state.bigBlind;
    this.state.actedSinceLastFullRaise = new Set<number>();
    this.state.pendingToAct = new Set<number>();
    this.state.holeCards.clear();
    this.state.contributed.clear();
    this.state.handStartStacks.clear();
    this.state.deck = shuffledDeck();
    this.state.winners = undefined;
    this.state.runoutBoards = undefined;
    this.state.runoutPayouts = undefined;
    this.state.ritVotes = {};
    this.state.shownCards = {};
    this.state.shownHands = {};
    this.state.revealedHoles = {};
    this.state.muckedSeats = [];
    this.state.showdownPhase = "none";
    this.allInRunCount = 1;
    this.runoutPending = false;
    this.collectedFee = 0;
    this.settlementResult = null;
    this.secondaryBoard = [];
    this.doubleBoardPayouts = null;

    this.handCounter += 1;
    this.holeCardCount = this.gameType === "omaha" ? 4 : 2;
    this.isBombPotHand = this.shouldDealBombPotHand();
    this.isDoubleBoardHand = this.doubleBoardMode === "always"
      || (this.doubleBoardMode === "bomb_pot" && this.isBombPotHand);
    this.state.gameType = this.gameType;
    this.state.holeCardCount = this.holeCardCount;
    this.state.isBombPotHand = this.isBombPotHand;
    this.state.isDoubleBoardHand = this.isDoubleBoardHand;

    const sortedSeats = seated.map((p) => p.seat).sort((a, b) => a - b);
    this.state.buttonSeat = nextSeatCircular(this.state.buttonSeat, sortedSeats);

    for (const player of this.state.players) {
      const active = sortedSeats.includes(player.seat);
      this.state.handStartStacks.set(player.seat, player.stack);
      player.inHand = active;
      player.folded = !active;
      player.allIn = false;
      player.streetCommitted = 0;
      this.state.contributed.set(player.seat, 0);
      // Mark new players as no longer new after being dealt in
      if (active && player.isNewPlayer) {
        player.isNewPlayer = false;
      }
    }

    for (const [seat, amount] of pendingDeadBlinds.entries()) {
      if (amount <= 0) continue;
      this.state.pot += amount;
      this.state.contributed.set(seat, (this.state.contributed.get(seat) ?? 0) + amount);
    }

    if (this.isBombPotHand) {
      const bombAnte = Math.max(this.state.bigBlind, this.ante > 0 ? this.ante : this.state.bigBlind);
      for (const seat of sortedSeats) {
        const commit = this.commitForcedChips(seat, bombAnte, { countToStreet: false });
        if (commit > 0) {
          this.logAction({ seat, street: "PREFLOP", type: "ante", amount: commit, at: Date.now() });
        }
      }
    } else if (this.ante > 0) {
      for (const seat of sortedSeats) {
        this.collectAnte(seat);
      }
    }

    for (const seat of sortedSeats) {
      const cards: string[] = [];
      for (let i = 0; i < this.holeCardCount; i += 1) {
        cards.push(this.drawCard());
      }
      this.state.holeCards.set(seat, cards);
    }

    if (this.isBombPotHand) {
      this.state.street = "FLOP";
      this.dealStreetBoardCards("FLOP");
      this.state.currentBet = 0;
      this.state.minRaiseTo = this.state.bigBlind;
      this.state.lastFullRaiseSize = this.state.bigBlind;
      this.state.lastFullBet = 0;
      this.state.lastReopenBet = 0;
      this.state.actedSinceLastFullRaise = new Set<number>();
      for (const player of this.state.players) {
        player.streetCommitted = 0;
      }
      this.state.pendingToAct = new Set(
        this.activePlayers()
          .filter((p) => !p.allIn)
          .map((p) => p.seat)
      );
      this.state.actorSeat = this.nextActorFrom(this.state.buttonSeat);
      return { handId };
    }

    // Determine blind seats — HU is a special case (button = SB)
    const isHeadsUp = sortedSeats.length === 2;
    let sbSeat: number;
    let bbSeat: number;
    if (isHeadsUp) {
      sbSeat = this.state.buttonSeat;
      bbSeat = sortedSeats.find((s) => s !== sbSeat)!;
    } else {
      // Multi-way: SB = first after button (index 0), BB = second (index 1)
      sbSeat = this.getRelativeSeat(0);
      bbSeat = this.getRelativeSeat(1);
    }
    this.commitBlind(sbSeat, this.state.smallBlind, "post_sb");
    this.commitBlind(bbSeat, this.state.bigBlind, "post_bb");

    this.state.pendingToAct = new Set(
      this.activePlayers()
        .filter((p) => !p.allIn)
        .map((p) => p.seat)
    );
    // First to act preflop: next pending player after BB
    // Multi-way: finds UTG; HU: wraps to SB/button
    this.state.actorSeat = this.nextActorFrom(bbSeat);

    return { handId };
  }

  setAllInRunCount(count: 1 | 2): void {
    this.allInRunCount = count;
  }

  updateBlindStructure(smallBlind: number, bigBlind: number, ante: number): void {
    if (smallBlind <= 0 || bigBlind <= 0) {
      throw new Error("blinds must be greater than 0");
    }
    if (smallBlind >= bigBlind) {
      throw new Error("small blind must be less than big blind");
    }
    if (ante < 0) {
      throw new Error("ante cannot be negative");
    }

    const next = { smallBlind, bigBlind, ante };
    this.pendingBlindLevel = next;
    this.state.nextBlindLevel = next;
  }

  getAllInRunCount(): 1 | 2 {
    return this.allInRunCount;
  }

  applyAction(seat: number, action: PlayerActionType, amount?: number, ritVote?: boolean): TableState {
    if (action === "vote_rit") {
      return this.applyRitVote(seat, ritVote);
    }

    if (this.state.handId === null || this.state.actorSeat === null) {
      throw new Error("no active hand");
    }
    if (this.state.street === "RUN_IT_TWICE_PROMPT") {
      throw new Error("waiting for run-it-twice votes");
    }
    if (this.state.actorSeat !== seat) {
      throw new Error("not your turn");
    }

    const player = this.playerBySeat(seat);
    if (!player.inHand || player.folded || player.allIn) {
      throw new Error("player cannot act");
    }

    this.consecutiveTimeouts.set(seat, 0);

    const toCall = Math.max(0, this.state.currentBet - player.streetCommitted);
    const pendingBeforeAction = new Set(this.state.pendingToAct);
    let actionAmount = 0;

    // Validate action legality
    if (action === "check" && toCall > 0) {
      throw new Error("cannot check when facing a bet");
    }
    if (action === "call" && toCall === 0) {
      throw new Error("nothing to call");
    }
    if (action === "raise") {
      if (amount === undefined) {
        throw new Error("raise amount required");
      }
      if (amount < this.state.minRaiseTo && amount < player.stack + player.streetCommitted) {
        throw new Error(`raise must be at least ${this.state.minRaiseTo}`);
      }
      if (amount <= this.state.currentBet) {
        throw new Error("raise must increase current bet");
      }
      const needed = amount - player.streetCommitted;
      if (needed > player.stack) {
        throw new Error("insufficient chips for raise");
      }
    }
    if (action === "all_in") {
      // all_in is always legal if player has chips
      if (player.stack <= 0) {
        throw new Error("no chips to go all-in");
      }
    }

    // Apply action
    if (action === "fold") {
      player.folded = true;
      player.inHand = false;
      this.markActedSinceLastFullRaise(seat);
    } else if (action === "check") {
      // no chip movement
      this.markActedSinceLastFullRaise(seat);
    } else if (action === "call") {
      const commit = Math.min(toCall, player.stack);
      player.stack -= commit;
      player.streetCommitted += commit;
      this.state.pot += commit;
      actionAmount = commit;
      if (player.stack === 0) player.allIn = true;
      this.markActedSinceLastFullRaise(seat);
    } else if (action === "raise") {
      const raiseTo = amount as number;
      const previousBet = this.state.currentBet;
      const previousMinRaiseTo = this.state.minRaiseTo;
      const commit = raiseTo - player.streetCommitted;
      player.stack -= commit;
      player.streetCommitted = raiseTo;
      this.state.pot += commit;
      actionAmount = commit;
      const raiseIncrement = raiseTo - previousBet;
      const minRaiseIncrement = previousMinRaiseTo - previousBet;
      const isFullRaise = raiseIncrement >= minRaiseIncrement;
      this.state.currentBet = raiseTo;
      if (player.stack === 0) player.allIn = true;

      if (isFullRaise) {
        this.state.lastFullRaiseSize = raiseIncrement;
        this.state.lastFullBet = raiseTo;
        this.state.lastReopenBet = raiseTo;
        this.state.minRaiseTo = raiseTo + raiseIncrement;
        this.state.actedSinceLastFullRaise = new Set<number>([seat]);
        this.state.pendingToAct = new Set(
          this.activePlayers()
            .filter((p) => p.seat !== seat && !p.allIn)
            .map((p) => p.seat)
        );
      } else {
        // Short all-in raise via "raise": not a full raise, so no reopen reset.
        this.markActedSinceLastFullRaise(seat);
        this.state.minRaiseTo = this.state.currentBet + this.state.lastFullRaiseSize;
        this.state.pendingToAct = this.pendingSeatsAfterIncompleteRaise(
          seat,
          previousBet,
          pendingBeforeAction
        );
      }
    } else if (action === "all_in") {
      const previousBet = this.state.currentBet;
      const previousMinRaiseTo = this.state.minRaiseTo;
      const commit = player.stack;
      const newTotal = player.streetCommitted + commit;
      player.stack = 0;
      player.streetCommitted = newTotal;
      this.state.pot += commit;
      actionAmount = commit;
      player.allIn = true;

      if (newTotal > previousBet) {
        const raiseSize = newTotal - previousBet;
        const minRaiseIncrement = previousMinRaiseTo - previousBet;
        const isFullRaise = raiseSize >= minRaiseIncrement;

        this.state.currentBet = newTotal;

        if (isFullRaise) {
          // Full raise: establish a new reopen level.
          this.state.lastFullRaiseSize = raiseSize;
          this.state.lastFullBet = newTotal;
          this.state.lastReopenBet = newTotal;
          this.state.minRaiseTo = newTotal + raiseSize;
          this.state.actedSinceLastFullRaise = new Set<number>([seat]);
          this.state.pendingToAct = new Set(
            this.activePlayers()
              .filter((p) => p.seat !== seat && !p.allIn)
              .map((p) => p.seat)
          );
        } else {
          // Incomplete all-in raise: no reopen reset.
          this.markActedSinceLastFullRaise(seat);
          this.state.minRaiseTo = this.state.currentBet + this.state.lastFullRaiseSize;
          this.state.pendingToAct = this.pendingSeatsAfterIncompleteRaise(
            seat,
            previousBet,
            pendingBeforeAction
          );
        }
      } else {
        this.markActedSinceLastFullRaise(seat);
      }
    }

    if (actionAmount > 0) {
      this.state.contributed.set(seat, (this.state.contributed.get(seat) ?? 0) + actionAmount);
    }

    this.logAction({
      seat,
      street: this.state.street,
      type: action,
      amount: actionAmount,
      at: Date.now()
    });

    this.state.pendingToAct.delete(seat);

    const remaining = this.activePlayers();
    if (remaining.length <= 1) {
      this.finishNoShowdown();
      return this.getPublicState();
    }

    // Check if all remaining active players are all-in (no more betting possible)
    const canStillAct = remaining.filter((p) => !p.allIn);
    if (canStillAct.length <= 1 && this.state.pendingToAct.size === 0) {
      this.state.actorSeat = null;
      this.state.pendingToAct.clear();
      if (this.shouldPromptRunItTwice()) {
        this.enterRunItTwicePrompt();
      } else {
        this.runoutPending = true;
      }
      return this.getPublicState();
    }

    if (this.state.pendingToAct.size === 0) {
      this.advanceStreetOrShowdown();
      return this.getPublicState();
    }

    const next = this.nextActorFrom(seat);
    this.state.actorSeat = next;
    return this.getPublicState();
  }

  getHeroHandCode(seat: number): string {
    const cards = this.state.holeCards.get(seat);
    if (!cards || cards.length < 2) return "72o";
    const [a, b] = cards;
    const [ra, sa] = [a[0], a[1]];
    const [rb, sb] = [b[0], b[1]];

    const aIdx = RANKS.indexOf(ra);
    const bIdx = RANKS.indexOf(rb);
    const high = aIdx <= bIdx ? ra : rb;
    const low = aIdx <= bIdx ? rb : ra;
    if (high === low) return `${high}${low}`;
    const suited = sa === sb ? "s" : "o";
    return `${high}${low}${suited}`;
  }

  getPosition(seat: number): string {
    const activeSeats = this.activePlayers().map((p) => p.seat).sort((a, b) => a - b);
    const order = orderedFromButton(this.state.buttonSeat, activeSeats);
    const labelOrder = POSITION_LABELS_BY_COUNT[order.length];
    if (!labelOrder) return "UNKNOWN";
    const idx = order.indexOf(seat);
    return idx >= 0 ? labelOrder[idx] : "UNKNOWN";
  }

  isHandActive(): boolean {
    return this.handInProgress
      && this.state.handId !== null
      && (
        this.state.actorSeat !== null
        || this.runoutPending
        || this.state.street === "RUN_IT_TWICE_PROMPT"
        || this.state.showdownPhase === "decision"
      );
  }

  /** Called by the server after finalizeHandEnd to cleanly mark the hand as done.
   *  This prevents any stale handId from blocking the next startHand(). */
  clearHand(): void {
    this.handInProgress = false;
    this.state.handId = null;
  }

  /** Toggle a player's sit-out status. Cannot toggle during an active hand for that player. */
  toggleSitOut(seat: number): PlayerStatus {
    const player = this.playerBySeat(seat);
    if (player.inHand) {
      throw new Error("Cannot change sit-out status during an active hand");
    }
    player.status = player.status === 'active' ? 'sitting_out' : 'active';
    return player.status;
  }

  /** Set a player's status directly (used by server for auto sit-out on timeout). */
  setPlayerStatus(seat: number, status: PlayerStatus): void {
    const player = this.playerBySeat(seat);
    player.status = status;
  }

  /** Post a dead blind to allow a new player to enter the game immediately.
   *  Policy: dead blind is forced and non-live. It is added to the next hand's pot,
   *  does NOT count toward streetCommitted, and does NOT grant blind option rights. */
  postDeadBlind(seat: number): void {
    const player = this.playerBySeat(seat);
    if (this.isHandActive()) {
      throw new Error("Cannot post dead blind during an active hand");
    }
    const amount = Math.min(player.stack, this.state.bigBlind);
    if (amount <= 0) throw new Error("No chips to post");
    player.stack -= amount;
    this.state.pendingDeadBlinds.set(seat, (this.state.pendingDeadBlinds.get(seat) ?? 0) + amount);
    this.state.pendingDeadBlindActions.push({
      seat,
      street: "PREFLOP",
      type: "post_dead_blind" as HandActionType,
      amount,
      at: Date.now(),
    });
    // Keep conservation visible between hands.
    this.state.pot += amount;
    player.status = 'active';
    player.isNewPlayer = false;
    this.consecutiveTimeouts.set(seat, 0);
  }

  /** Replace the deck after startHand() for deterministic testing.
   *  Cards are popped from end, so last element is dealt first. */
  setDeckForTesting(deck: string[]): void {
    this.state.deck = [...deck];
  }

  /** Expose hole cards for testing (read-only snapshot). */
  getAllHoleCards(): Map<number, string[]> {
    const copy = new Map<number, string[]>();
    for (const [seat, cards] of this.state.holeCards.entries()) {
      copy.set(seat, [...cards]);
    }
    return copy;
  }

  /** Expose contributions for testing (read-only snapshot). */
  getContributions(): Map<number, number> {
    return new Map(this.state.contributed);
  }

  getMode(): TableMode {
    return this.state.mode;
  }

  setMode(mode: TableMode): void {
    this.state.mode = mode;
  }

  private computeLegalActions(): LegalActions | null {
    if (this.state.actorSeat == null || !this.state.handId) return null;

    const player = this.state.players.find((p) => p.seat === this.state.actorSeat);
    if (!player || !player.inHand || player.folded || player.allIn) return null;

    const toCall = Math.max(0, this.state.currentBet - player.streetCommitted);
    const canCheck = toCall === 0;
    const canCall = toCall > 0;
    const callAmount = Math.min(toCall, player.stack);

    const maxRaise = player.stack + player.streetCommitted;
    const hasActedSinceLastFullRaise = this.state.actedSinceLastFullRaise.has(player.seat);
    const raiseIncrementFaced = Math.max(0, this.state.currentBet - player.streetCommitted);
    const fullRaiseFaced = raiseIncrementFaced >= this.state.lastFullRaiseSize;
    const raiseBlockedByIncompleteAllIn = hasActedSinceLastFullRaise
      && raiseIncrementFaced > 0
      && !fullRaiseFaced;
    const canRaise = maxRaise > this.state.currentBet && !raiseBlockedByIncompleteAllIn;
    const minRaise = Math.min(this.state.minRaiseTo, maxRaise);

    return {
      canFold: true,
      canCheck,
      canCall,
      callAmount,
      canRaise,
      minRaise,
      maxRaise
    };
  }

  private advanceStreetOrShowdown(): void {
    if (this.state.street === "PREFLOP") {
      this.state.street = "FLOP";
      this.dealStreetBoardCards("FLOP");
      this.prepareNextStreet();
      return;
    }
    if (this.state.street === "FLOP") {
      this.state.street = "TURN";
      this.dealStreetBoardCards("TURN");
      this.prepareNextStreet();
      return;
    }
    if (this.state.street === "TURN") {
      this.state.street = "RIVER";
      this.dealStreetBoardCards("RIVER");
      this.prepareNextStreet();
      return;
    }

    this.state.street = "SHOWDOWN";
    this.showdown();
  }

  private runOutBoardTwice(): void {
    if (this.isDoubleBoardHand) {
      this.allInRunCount = 1;
      this.runOutBoard();
      return;
    }

    const contenders = this.activePlayers();
    if (contenders.length < 2) {
      while (this.state.board.length < 5) {
        if (this.state.board.length === 0) {
          this.state.board.push(this.drawCard(), this.drawCard(), this.drawCard());
          this.state.street = "FLOP";
        } else if (this.state.board.length === 3) {
          this.state.board.push(this.drawCard());
          this.state.street = "TURN";
        } else if (this.state.board.length === 4) {
          this.state.board.push(this.drawCard());
          this.state.street = "RIVER";
        }
      }
      this.state.street = "SHOWDOWN";
      this.showdown();
      return;
    }

    const baseBoard = [...this.state.board];
    const firstBoard = this.completeRunoutBoard(baseBoard);
    const secondBoard = this.completeRunoutBoard(baseBoard);

    const payoutsRun1 = new Map<number, { amount: number; handName?: string }>();
    const payoutsRun2 = new Map<number, { amount: number; handName?: string }>();
    const sidePots = this.buildSidePots(contenders);
    const {
      sidePots: distributableSidePots,
      collectedFee,
    } = this.applyRakeToSidePots(sidePots);
    this.collectedFee = collectedFee;
    const solvedFirst = this.solveContenders(contenders, firstBoard);
    const solvedSecond = this.solveContenders(contenders, secondBoard);

    for (const sidePot of distributableSidePots) {
      // Run-it-twice odd-chip policy: Run 1 gets ceil, Run 2 gets floor.
      const run1Amount = Math.ceil(sidePot.amount / 2);
      const run2Amount = Math.floor(sidePot.amount / 2);
      this.distributeSolvedPot(run1Amount, solvedFirst, sidePot.eligibleSeats, payoutsRun1);
      this.distributeSolvedPot(run2Amount, solvedSecond, sidePot.eligibleSeats, payoutsRun2);
    }

    const payouts = this.mergePayoutMaps(payoutsRun1, payoutsRun2);
    // Store both boards for client visualization
    this.state.runoutBoards = [firstBoard, secondBoard];
    this.state.runoutPayouts = [
      { run: 1, board: firstBoard, winners: this.mapPayoutsToWinners(payoutsRun1) },
      { run: 2, board: secondBoard, winners: this.mapPayoutsToWinners(payoutsRun2) },
    ];
    this.state.board = secondBoard;
    this.state.street = "SHOWDOWN";
    this.state.winners = this.mapPayoutsToWinners(payouts);
    this.state.pot = 0;
    this.state.actorSeat = null;
    this.state.pendingToAct.clear();
    this.revealShowdownHands(this.mandatoryShowdownSeats(contenders));
    this.applyShowdownVisibilityPolicy(contenders);
    this.settlementResult = this.createSettlementResult(true);
    this.allInRunCount = 1;
  }

  private completeRunoutBoard(baseBoard: string[]): string[] {
    const board = [...baseBoard];
    while (board.length < 5) {
      board.push(this.drawCard());
    }
    return board;
  }

  private solveContenders(contenders: TablePlayer[], board: string[]): Array<{ seat: number; hand: { descr: string; rank: number } }> {
    return contenders.map((p) => {
      const cards = this.state.holeCards.get(p.seat) ?? ["2c", "7d"];
      const hand = this.solveBestHand(cards, board);
      return { seat: p.seat, hand };
    });
  }

  private solveBestHand(holeCards: string[], board: string[]): { descr: string; rank: number } {
    if (this.gameType === "omaha" && holeCards.length >= 4 && board.length >= 3) {
      let best: { descr: string; rank: number } | null = null;
      const holeCombos = combinations(holeCards, 2);
      const boardCombos = combinations(board, 3);
      for (const holeCombo of holeCombos) {
        for (const boardCombo of boardCombos) {
          const candidate = Hand.solve(toSolverCards([...holeCombo, ...boardCombo]));
          if (!best || this.isSolverHandBetter(candidate, best)) {
            best = candidate;
          }
        }
      }
      if (best) return best;
    }

    const fallbackCards = [...holeCards.slice(0, 2), ...board];
    return Hand.solve(toSolverCards(fallbackCards));
  }

  private isSolverHandBetter(candidate: { descr: string; rank: number }, current: { descr: string; rank: number }): boolean {
    const winners = Hand.winners([candidate, current]);
    const candidateWins = winners.some((winner) => winner.descr === candidate.descr && winner.rank === candidate.rank);
    const currentWins = winners.some((winner) => winner.descr === current.descr && winner.rank === current.rank);
    return candidateWins && !currentWins;
  }

  private resolveWinnerSeats(
    solved: Array<{ seat: number; hand: { descr: string; rank: number } }>,
    eligibleSeats: number[]
  ): number[] {
    const eligible = solved.filter((s) => eligibleSeats.includes(s.seat));
    if (eligible.length === 0) return [];
    const winners = Hand.winners(eligible.map((s) => s.hand));
    return eligible
      .filter((s) => winners.some((w: { descr: string; rank: number }) => w.descr === s.hand.descr && w.rank === s.hand.rank))
      .map((s) => s.seat);
  }

  private distributeSolvedPot(
    potAmount: number,
    solved: Array<{ seat: number; hand: { descr: string; rank: number } }>,
    eligibleSeats: number[],
    payouts: Map<number, { amount: number; handName?: string }>
  ): void {
    if (potAmount <= 0) return;
    const winnerSeats = this.resolveWinnerSeats(solved, eligibleSeats);
    if (winnerSeats.length === 0) return;

    const share = Math.floor(potAmount / winnerSeats.length);
    let remainder = potAmount - share * winnerSeats.length;

    // Odd-chip rule: start from the seat immediately left of button, then clockwise.
    const sortedWinners = this.sortSeatsClockwiseFromButtonLeft(winnerSeats);

    for (const seat of sortedWinners) {
      const player = this.playerBySeat(seat);
      const amt = share + (remainder > 0 ? 1 : 0);
      player.stack += amt;
      if (remainder > 0) remainder -= 1;

      const solvedEntry = solved.find((s) => s.seat === seat);
      const existing = payouts.get(seat);
      payouts.set(seat, {
        amount: (existing?.amount ?? 0) + amt,
        handName: existing?.handName ?? solvedEntry?.hand.descr,
      });
    }
  }

  private buildSidePots(contenders: TablePlayer[]): Array<{ amount: number; eligibleSeats: number[] }> {
    const contributors = this.state.players
      .map((p) => ({ seat: p.seat, contributed: this.state.contributed.get(p.seat) ?? 0 }))
      .filter((c) => c.contributed > 0)
      .sort((a, b) => a.contributed - b.contributed);

    if (contributors.length === 0) return [];

    const levels = [...new Set(contributors.map((c) => c.contributed).filter((v) => v > 0))].sort((a, b) => a - b);
    const sidePots: Array<{ amount: number; eligibleSeats: number[] }> = [];

    let prevLevel = 0;
    for (const level of levels) {
      const participants = contributors.filter((c) => c.contributed >= level);
      const potAmount = (level - prevLevel) * participants.length;
      const eligibleSeats = contenders
        .filter((p) => (this.state.contributed.get(p.seat) ?? 0) >= level)
        .map((p) => p.seat);

      if (potAmount > 0 && eligibleSeats.length > 0) {
        sidePots.push({ amount: potAmount, eligibleSeats });
      }
      prevLevel = level;
    }

    return sidePots;
  }

  /** Deal remaining community cards when all players are all-in */
  private runOutBoard(): void {
    if (this.allInRunCount === 2 && !this.isDoubleBoardHand) {
      this.runOutBoardTwice();
      return;
    }

    // Deal all remaining cards at once (will be revealed step by step by server)
    while (this.state.board.length < 5) {
      if (this.state.board.length === 0) {
        this.dealStreetBoardCards("FLOP");
        this.state.street = "FLOP";
      } else if (this.state.board.length === 3) {
        this.dealStreetBoardCards("TURN");
        this.state.street = "TURN";
      } else if (this.state.board.length === 4) {
        this.dealStreetBoardCards("RIVER");
        this.state.street = "RIVER";
      }
    }
    this.state.street = "SHOWDOWN";
    this.showdown();
  }

  /** Abort the current hand: return all bets to players, reset state.
   *  Used when idle timeout triggers a mid-hand reset. */
  abortHand(): void {
    if (!this.state.handId) return;
    // Return all committed chips to each player based on tracked contribution deltas.
    for (const p of this.state.players) {
      p.stack += this.state.contributed.get(p.seat) ?? 0;
      p.inHand = false;
      p.folded = false;
      p.allIn = false;
      p.streetCommitted = 0;
      this.state.contributed.set(p.seat, 0);
    }
    this.state.handId = null;
    this.handInProgress = false;
    this.state.street = "SHOWDOWN";
    this.state.board = [];
    this.state.pot = 0;
    this.state.currentBet = 0;
    this.state.lastFullRaiseSize = this.state.bigBlind;
    this.state.lastFullBet = 0;
    this.state.lastReopenBet = 0;
    this.state.actedSinceLastFullRaise = new Set<number>();
    this.state.actorSeat = null;
    this.state.actions = [];
    this.state.winners = undefined;
    this.state.runoutBoards = undefined;
    this.state.runoutPayouts = undefined;
    this.state.shownCards = {};
    this.state.shownHands = {};
    this.state.revealedHoles = {};
    this.state.muckedSeats = [];
    this.state.showdownPhase = "none";
    this.state.pendingToAct.clear();
    this.state.holeCards.clear();
    this.state.contributed.clear();
    this.state.pendingDeadBlinds.clear();
    this.state.pendingDeadBlindActions = [];
    this.state.handStartStacks.clear();
    this.runoutPending = false;
    this.collectedFee = 0;
    this.settlementResult = null;
    this.secondaryBoard = [];
    this.doubleBoardPayouts = null;
    this.isBombPotHand = false;
    this.isDoubleBoardHand = false;
    this.state.isBombPotHand = false;
    this.state.isDoubleBoardHand = false;
  }

  /** True when applyAction detected an all-in runout situation */
  isRunoutPending(): boolean {
    return this.runoutPending;
  }

  /** Check if EVERY active player is all-in (for run-count prompt eligibility) */
  isEveryoneAllIn(): boolean {
    const remaining = this.activePlayers();
    return remaining.length >= 2 && remaining.every((p) => p.allIn);
  }

  /** Execute the full runout (used for run-it-twice which isn't sequential) */
  performRunout(): void {
    this.runoutPending = false;
    this.runOutBoard();
  }

  /** Get the next street to reveal in sequential runout */
  getNextRevealStreet(): Street | null {
    if (this.state.board.length === 0) return "FLOP";
    if (this.state.board.length === 3) return "TURN";
    if (this.state.board.length === 4) return "RIVER";
    if (this.state.board.length === 5) return "SHOWDOWN";
    return null;
  }

  /** Reveal next street cards (for sequential all-in runout) */
  revealNextStreet(): { street: Street; newCards: string[] } | null {
    const nextStreet = this.getNextRevealStreet();
    if (!nextStreet) return null;

    const newCards: string[] = [];
    if (nextStreet === "FLOP" && this.state.board.length === 0) {
      newCards.push(...this.dealStreetBoardCards("FLOP"));
      this.state.street = "FLOP";
    } else if (nextStreet === "TURN" && this.state.board.length === 3) {
      newCards.push(...this.dealStreetBoardCards("TURN"));
      this.state.street = "TURN";
    } else if (nextStreet === "RIVER" && this.state.board.length === 4) {
      newCards.push(...this.dealStreetBoardCards("RIVER"));
      this.state.street = "RIVER";
    } else if (nextStreet === "SHOWDOWN" && this.state.board.length === 5) {
      this.state.street = "SHOWDOWN";
      this.showdown();
      return { street: "SHOWDOWN", newCards: [] };
    }

    return { street: nextStreet, newCards };
  }

  private prepareNextStreet(): void {
    this.state.currentBet = 0;
    this.state.minRaiseTo = this.state.bigBlind;
    this.state.lastFullRaiseSize = this.state.bigBlind;
    this.state.lastFullBet = 0;
    this.state.lastReopenBet = 0;
    this.state.actedSinceLastFullRaise = new Set<number>();
    for (const p of this.state.players) {
      p.streetCommitted = 0;
    }
    this.state.pendingToAct = new Set(
      this.activePlayers()
        .filter((p) => !p.allIn)
        .map((p) => p.seat)
    );

    // Post-flop: first active player clockwise of button
    const first = this.nextActorFrom(this.state.buttonSeat);
    this.state.actorSeat = first;

    // If only one or zero players can act (rest are all-in), signal runout
    if (this.state.pendingToAct.size <= 1 && this.activePlayers().filter(p => !p.allIn).length <= 1) {
      if (this.state.pendingToAct.size === 0) {
        this.state.actorSeat = null;
        this.state.pendingToAct.clear();
        if (this.shouldPromptRunItTwice()) {
          this.enterRunItTwicePrompt();
        } else {
          this.runoutPending = true;
        }
      }
    }
  }

  private showdown(): void {
    const contenders = this.activePlayers();

    if (this.isDoubleBoardHand && this.secondaryBoard.length === 5) {
      this.showdownDoubleBoard(contenders);
      return;
    }

    const board = this.state.board;
    const solved = this.solveContenders(contenders, board);
    const sidePots = this.buildSidePots(contenders);
    const {
      sidePots: distributableSidePots,
      collectedFee,
    } = this.applyRakeToSidePots(sidePots);
    this.collectedFee = collectedFee;
    const payouts = new Map<number, { amount: number; handName?: string }>();

    if (distributableSidePots.length > 0) {
      for (const sidePot of distributableSidePots) {
        this.distributeSolvedPot(sidePot.amount, solved, sidePot.eligibleSeats, payouts);
      }
    }

    this.state.winners = [...payouts.entries()]
      .map(([seat, v]) => ({ seat, amount: v.amount, handName: v.handName }))
      .sort((a, b) => a.seat - b.seat);
    this.doubleBoardPayouts = null;
    this.state.runoutPayouts = undefined;
    this.state.pot = 0;
    this.state.actorSeat = null;
    this.state.pendingToAct.clear();
    this.revealShowdownHands(this.mandatoryShowdownSeats(contenders));
    this.applyShowdownVisibilityPolicy(contenders);
    this.settlementResult = this.createSettlementResult(true);
  }

  private showdownDoubleBoard(contenders: TablePlayer[]): void {
    const boardPrimary = [...this.state.board];
    const boardSecondary = [...this.secondaryBoard];
    const solvedPrimary = this.solveContenders(contenders, boardPrimary);
    const solvedSecondary = this.solveContenders(contenders, boardSecondary);
    const sidePots = this.buildSidePots(contenders);
    const {
      sidePots: distributableSidePots,
      collectedFee,
    } = this.applyRakeToSidePots(sidePots);
    this.collectedFee = collectedFee;

    const payoutsPrimary = new Map<number, { amount: number; handName?: string }>();
    const payoutsSecondary = new Map<number, { amount: number; handName?: string }>();
    for (const sidePot of distributableSidePots) {
      const boardAAmount = Math.ceil(sidePot.amount / 2);
      const boardBAmount = Math.floor(sidePot.amount / 2);
      this.distributeSolvedPot(boardAAmount, solvedPrimary, sidePot.eligibleSeats, payoutsPrimary);
      this.distributeSolvedPot(boardBAmount, solvedSecondary, sidePot.eligibleSeats, payoutsSecondary);
    }

    const mergedPayouts = this.mergePayoutMaps(payoutsPrimary, payoutsSecondary);
    this.doubleBoardPayouts = [
      { run: 1, board: boardPrimary, winners: this.mapPayoutsToWinners(payoutsPrimary) },
      { run: 2, board: boardSecondary, winners: this.mapPayoutsToWinners(payoutsSecondary) },
    ];

    this.state.winners = this.mapPayoutsToWinners(mergedPayouts);
    this.state.runoutPayouts = undefined;
    this.state.runoutBoards = undefined;
    this.state.pot = 0;
    this.state.actorSeat = null;
    this.state.pendingToAct.clear();
    this.revealShowdownHands(this.mandatoryShowdownSeats(contenders));
    this.applyShowdownVisibilityPolicy(contenders);
    this.settlementResult = this.createSettlementResult(true);
  }

  private finishNoShowdown(): void {
    const winner = this.activePlayers()[0];
    const won = this.state.pot;
    winner.stack += won;
    this.state.winners = [{ seat: winner.seat, amount: won }];
    this.state.runoutPayouts = undefined;
    this.state.ritVotes = {};
    this.state.shownCards = {};
    this.state.shownHands = {};
    this.state.pot = 0;
    this.state.street = "SHOWDOWN";
    this.state.actorSeat = null;
    this.state.pendingToAct.clear();
    this.state.showdownPhase = "none";
    this.state.muckedSeats = [];
    this.collectedFee = 0;
    this.settlementResult = this.createSettlementResult(false);
  }

  private commitBlind(seat: number, amount: number, type: "post_sb" | "post_bb") {
    const commit = this.commitForcedChips(seat, amount, { countToStreet: true });
    this.logAction({ seat, street: "PREFLOP", type, amount: commit, at: Date.now() });
  }

  private collectAnte(seat: number): void {
    const commit = this.commitForcedChips(seat, this.ante, { countToStreet: false });
    if (commit > 0) {
      this.logAction({ seat, street: "PREFLOP", type: "ante", amount: commit, at: Date.now() });
    }
  }

  private commitForcedChips(seat: number, amount: number, opts: { countToStreet: boolean }): number {
    const player = this.playerBySeat(seat);
    const commit = Math.min(player.stack, amount);
    if (commit <= 0) return 0;

    player.stack -= commit;
    if (opts.countToStreet) {
      player.streetCommitted += commit;
    }
    this.state.pot += commit;
    this.state.contributed.set(seat, (this.state.contributed.get(seat) ?? 0) + commit);
    if (player.stack === 0) {
      player.allIn = true;
    }
    return commit;
  }

  private markActedSinceLastFullRaise(seat: number): void {
    this.state.actedSinceLastFullRaise.add(seat);
  }

  private pendingSeatsAfterIncompleteRaise(
    excludingSeat: number,
    previousBet: number,
    pendingBeforeAction: ReadonlySet<number>
  ): Set<number> {
    const pending = new Set<number>();
    for (const player of this.activePlayers()) {
      if (player.seat === excludingSeat || player.allIn) continue;
      const needsToMatchNewBet = player.streetCommitted < this.state.currentBet;
      const hadActionPendingAtPreviousLevel = pendingBeforeAction.has(player.seat);
      const hadMatchedPreviousBet = player.streetCommitted === previousBet;
      if (needsToMatchNewBet || (hadActionPendingAtPreviousLevel && !hadMatchedPreviousBet)) {
        pending.add(player.seat);
      }
    }
    return pending;
  }

  private mandatoryShowdownSeats(contenders: TablePlayer[]): number[] {
    const required = new Set<number>();
    for (const winner of this.state.winners ?? []) {
      required.add(winner.seat);
    }
    if (this.didRiverEndWithCall()) {
      for (const contender of contenders) {
        required.add(contender.seat);
      }
    }
    return this.sortSeatsClockwiseFromButtonLeft([...required]);
  }

  private sortSeatsClockwiseFromButtonLeft(seats: number[]): number[] {
    if (seats.length <= 1) return [...seats];
    const tableSeats = this.state.players.map((player) => player.seat).sort((a, b) => a - b);
    const clockwiseFromButtonLeft = orderedFromButton(this.state.buttonSeat, tableSeats);
    const indexBySeat = new Map<number, number>();
    clockwiseFromButtonLeft.forEach((seat, index) => indexBySeat.set(seat, index));
    return [...seats].sort(
      (a, b) => (indexBySeat.get(a) ?? Number.MAX_SAFE_INTEGER) - (indexBySeat.get(b) ?? Number.MAX_SAFE_INTEGER)
    );
  }

  private revealShowdownHands(seats: number[]): void {
    for (const seat of seats) {
      const cards = this.state.holeCards.get(seat);
      if (!cards) continue;
      this.state.shownCards[seat] = [cards[0], cards[1]];
      this.state.shownHands[seat] = [cards[0], cards[1]];
      this.state.revealedHoles[seat] = [cards[0], cards[1]];
      this.state.muckedSeats = this.state.muckedSeats.filter((s) => s !== seat);
    }
  }

  private applyShowdownVisibilityPolicy(contenders: TablePlayer[]): void {
    const contenderSeats = contenders.map((player) => player.seat);
    if (contenderSeats.length < 2) {
      this.state.showdownPhase = "none";
      this.state.muckedSeats = [];
      return;
    }

    const calledShowdown = this.didRiverEndWithCall();
    const mustForceReveal = calledShowdown;
    if (mustForceReveal) {
      this.revealShowdownHands(contenderSeats);
      this.state.showdownPhase = "none";
      this.state.muckedSeats = [];
      return;
    }

    this.enterShowdownDecisionState(contenderSeats);
  }

  private didRiverEndWithCall(): boolean {
    for (let i = this.state.actions.length - 1; i >= 0; i -= 1) {
      const action = this.state.actions[i];
      if (action.street !== "RIVER") continue;
      return action.type === "call";
    }
    return false;
  }

  private applyRakeToSidePots(
    sidePots: Array<{ amount: number; eligibleSeats: number[] }>
  ): { sidePots: Array<{ amount: number; eligibleSeats: number[] }>; collectedFee: number } {
    const grossPot = this.state.pot;
    const fee = this.calculateRake(grossPot);
    const netPot = Math.max(0, grossPot - fee);
    this.state.pot = netPot;

    if (fee <= 0) {
      return {
        sidePots: sidePots.map((sidePot) => ({ amount: sidePot.amount, eligibleSeats: [...sidePot.eligibleSeats] })),
        collectedFee: 0,
      };
    }

    const adjusted = sidePots.map((sidePot) => ({ amount: sidePot.amount, eligibleSeats: [...sidePot.eligibleSeats] }));
    let remainingFee = fee;
    for (const sidePot of adjusted) {
      if (remainingFee <= 0) break;
      const deduction = Math.min(sidePot.amount, remainingFee);
      sidePot.amount -= deduction;
      remainingFee -= deduction;
    }

    return {
      sidePots: adjusted.filter((sidePot) => sidePot.amount > 0),
      collectedFee: fee - remainingFee,
    };
  }

  private calculateRake(totalPot: number): number {
    if (!this.rakeEnabled || totalPot <= 0 || this.rakePercent <= 0) return 0;
    const uncapped = Math.floor((totalPot * this.rakePercent) / 100);
    if (uncapped <= 0) return 0;
    return Math.min(uncapped, this.rakeCap);
  }

  private playerBySeat(seat: number): TablePlayer {
    const player = this.state.players.find((p) => p.seat === seat);
    if (!player) throw new Error(`seat ${seat} not found`);
    return player;
  }

  private activePlayers(): TablePlayer[] {
    return this.state.players.filter((p) => p.inHand && !p.folded);
  }

  private drawCard(): string {
    const card = this.state.deck.pop();
    if (!card) throw new Error("deck exhausted");
    return card;
  }

  private getRelativeSeat(offsetFromButton: number): number {
    const activeSeats = this.state.players.filter((p) => p.inHand).map((p) => p.seat).sort((a, b) => a - b);
    const ordered = orderedFromButton(this.state.buttonSeat, activeSeats);
    return ordered[offsetFromButton % ordered.length];
  }

  private nextActorFrom(seat: number): number | null {
    const activeSeats = this.activePlayers()
      .filter((p) => !p.allIn)
      .map((p) => p.seat)
      .sort((a, b) => a - b);

    if (activeSeats.length === 0) return null;

    for (let i = 1; i <= activeSeats.length; i += 1) {
      const candidate = nextSeatCircular(seat, activeSeats, i);
      if (this.state.pendingToAct.has(candidate)) {
        return candidate;
      }
    }
    return null;
  }

  private logAction(action: HandAction): void {
    this.state.actions.push(action);
  }

  private shouldPromptRunItTwice(): boolean {
    if (this.state.board.length >= 5) return false;
    if (this.state.street === "RIVER" || this.state.street === "SHOWDOWN") return false;
    if (this.isDoubleBoardHand) return false;
    return this.runItTwiceEnabled && this.isEveryoneAllIn();
  }

  private shouldDealBombPotHand(): boolean {
    if (!this.bombPotEnabled) return false;
    if (this.bombPotFrequency <= 0) return false;
    return this.handCounter % this.bombPotFrequency === 0;
  }

  private dealStreetBoardCards(street: "FLOP" | "TURN" | "RIVER"): string[] {
    if (street === "FLOP") {
      const dealt = [this.drawCard(), this.drawCard(), this.drawCard()];
      this.state.board.push(...dealt);
      if (this.isDoubleBoardHand) {
        this.secondaryBoard.push(this.drawCard(), this.drawCard(), this.drawCard());
      }
      return dealt;
    }

    const card = this.drawCard();
    this.state.board.push(card);
    if (this.isDoubleBoardHand) {
      this.secondaryBoard.push(this.drawCard());
    }
    return [card];
  }

  private enterRunItTwicePrompt(): void {
    const contenders = this.activePlayers().map((p) => p.seat);
    this.state.street = "RUN_IT_TWICE_PROMPT";
    this.state.ritVotes = {};
    for (const seat of contenders) {
      this.state.ritVotes[seat] = null;
    }
    this.state.actorSeat = null;
    this.state.pendingToAct.clear();
    this.runoutPending = false;
  }

  private applyRitVote(seat: number, ritVote?: boolean): TableState {
    if (this.state.handId === null) {
      throw new Error("no active hand");
    }
    if (this.state.street !== "RUN_IT_TWICE_PROMPT") {
      throw new Error("run-it-twice vote not expected");
    }
    if (typeof ritVote !== "boolean") {
      throw new Error("run-it-twice vote required");
    }

    const contender = this.activePlayers().some((p) => p.seat === seat);
    if (!contender) {
      throw new Error("seat is not eligible to vote");
    }

    this.state.ritVotes[seat] = ritVote;
    this.logAction({
      seat,
      street: "RUN_IT_TWICE_PROMPT",
      type: "vote_rit",
      amount: 0,
      at: Date.now(),
    });

    const votes = Object.values(this.state.ritVotes);
    const anyNo = votes.some((v) => v === false);
    const allYes = votes.length > 0 && votes.every((v) => v === true);

    if (!anyNo && !allYes) {
      return this.getPublicState();
    }

    this.state.ritVotes = {};
    this.allInRunCount = allYes ? 2 : 1;
    this.runoutPending = false;
    this.runOutBoard();
    return this.getPublicState();
  }

  private applyTimeoutSitOutIfNeeded(seat: number, timeoutCount: number): boolean {
    if (timeoutCount < 2) return false;
    const player = this.playerBySeat(seat);
    player.status = "sitting_out";
    return true;
  }

  private enterShowdownDecisionState(contenderSeats: number[]): void {
    if (contenderSeats.length < 2) {
      this.state.showdownPhase = "none";
      this.state.muckedSeats = [];
      return;
    }

    this.state.showdownPhase = "decision";
    this.state.muckedSeats = [];
  }

  getSettlementResult(): SettlementResult | null {
    return this.settlementResult;
  }

  private mapPayoutsToWinners(payouts: Map<number, { amount: number; handName?: string }>): Array<{ seat: number; amount: number; handName?: string }> {
    return [...payouts.entries()]
      .map(([seat, payout]) => ({ seat, amount: payout.amount, handName: payout.handName }))
      .sort((a, b) => a.seat - b.seat);
  }

  private mergePayoutMaps(
    map1: Map<number, { amount: number; handName?: string }>,
    map2: Map<number, { amount: number; handName?: string }>
  ): Map<number, { amount: number; handName?: string }> {
    const merged = new Map<number, { amount: number; handName?: string }>();

    for (const [seat, payout] of map1.entries()) {
      merged.set(seat, { ...payout });
    }
    for (const [seat, payout] of map2.entries()) {
      const existing = merged.get(seat);
      merged.set(seat, {
        amount: (existing?.amount ?? 0) + payout.amount,
        handName: existing?.handName ?? payout.handName,
      });
    }

    return merged;
  }

  private buildPotLayers(): Array<{ label: string; amount: number; eligibleSeats: number[] }> {
    const contenders = this.state.players.filter((p) => p.inHand && !p.folded);
    const contendersForPots = contenders.length > 0
      ? contenders
      : this.state.players.filter((p) => (this.state.contributed.get(p.seat) ?? 0) > 0);

    const sidePots = this.buildSidePots(contendersForPots);
    if (sidePots.length > 0) {
      return sidePots.map((sidePot, index) => ({
        label: index === 0 ? "Main Pot" : `Side Pot ${index}`,
        amount: sidePot.amount,
        eligibleSeats: [...sidePot.eligibleSeats],
      }));
    }

    const total = [...this.state.contributed.values()].reduce((sum, amount) => sum + amount, 0);
    if (total <= 0) return [];
    return [{
      label: "Main Pot",
      amount: total,
      eligibleSeats: [...new Set((this.state.winners ?? []).map((winner) => winner.seat))],
    }];
  }

  private createSettlementResult(showdown: boolean): SettlementResult {
    const contributions: Record<number, number> = {};
    for (const player of this.state.players) {
      contributions[player.seat] = this.state.contributed.get(player.seat) ?? 0;
    }

    const totalPot = Object.values(contributions).reduce((sum, amount) => sum + amount, 0);
    const collectedFee = this.collectedFee;
    const runCount = this.state.runoutPayouts?.length === 2 ? 2 : 1;
    const winnersByRun = runCount === 2
      ? this.state.runoutPayouts!.map((run) => ({ run: run.run, board: [...run.board], winners: [...run.winners] }))
      : [{
          run: 1 as const,
          board: [...this.state.board],
          winners: [...(this.state.winners ?? [])],
        }];
    const boards = runCount === 2
      ? [...(this.state.runoutBoards ?? [])]
      : this.doubleBoardPayouts && this.doubleBoardPayouts.length === 2
        ? this.doubleBoardPayouts.map((run) => [...run.board])
        : [[...this.state.board]];

    const payoutsBySeat: Record<number, number> = {};
    for (const winner of this.state.winners ?? []) {
      payoutsBySeat[winner.seat] = (payoutsBySeat[winner.seat] ?? 0) + winner.amount;
    }
    const totalPaid = Object.values(payoutsBySeat).reduce((sum, amount) => sum + amount, 0);

    // Conservation invariant: totalPaid + collectedFee must equal totalPot.
    if (totalPaid + collectedFee !== totalPot) {
      console.error(
        `[CONSERVATION VIOLATION] totalPaid+collectedFee=${totalPaid + collectedFee} != totalPot=${totalPot}, ` +
        `handId=${this.state.handId}, winners=${JSON.stringify(this.state.winners)}, ` +
        `contributions=${JSON.stringify(Object.fromEntries(this.state.contributed))}`
      );
    }

    // Conservation invariant with rake: sum(stacks_after) + collectedFee == sum(stacks_before)
    const sumStacksAfter = this.state.players.reduce((s, p) => s + p.stack, 0);
    const sumStacksBefore = [...this.state.handStartStacks.values()].reduce((s, v) => s + v, 0);
    if (sumStacksAfter + collectedFee !== sumStacksBefore) {
      console.error(
        `[CONSERVATION VIOLATION] sumStacksAfter+collectedFee=${sumStacksAfter + collectedFee} != sumStacksBefore=${sumStacksBefore}, ` +
        `handId=${this.state.handId}`
      );
    }

    const payoutsBySeatByRun = runCount === 2
      ? winnersByRun.map((run) => {
          const bySeat: Record<number, number> = {};
          for (const winner of run.winners) {
            bySeat[winner.seat] = (bySeat[winner.seat] ?? 0) + winner.amount;
          }
          return bySeat;
        })
      : undefined;

    const ledger = this.state.players
      .map((player) => {
        const startStack = this.state.handStartStacks.get(player.seat) ?? player.stack;
        const invested = contributions[player.seat] ?? 0;
        const endStack = player.stack;
        const won = Math.max(0, endStack - startStack + invested);
        const net = endStack - startStack;
        return {
          seat: player.seat,
          playerName: player.name,
          startStack,
          invested,
          won,
          endStack,
          net,
        };
      })
      .sort((a, b) => a.seat - b.seat);

    return {
      handId: this.state.handId ?? "",
      totalPot,
      rake: collectedFee,
      collectedFee,
      totalPaid,
      runCount,
      boards,
      potLayers: this.buildPotLayers(),
      winnersByRun,
      doubleBoardPayouts: this.doubleBoardPayouts
        ? this.doubleBoardPayouts.map((run) => ({ run: run.run, board: [...run.board], winners: [...run.winners] }))
        : undefined,
      payoutsBySeat,
      payoutsBySeatByRun,
      ledger,
      contributions,
      showdown,
      buttonSeat: this.state.buttonSeat,
      timestamp: Date.now(),
    };
  }
}

function shuffledDeck(): string[] {
  const deck: string[] = [];
  for (const r of RANKS) {
    for (const s of SUITS) {
      deck.push(`${r}${s}`);
    }
  }
  for (let i = deck.length - 1; i > 0; i -= 1) {
    const j = randomInt(i + 1);
    [deck[i], deck[j]] = [deck[j], deck[i]];
  }
  return deck;
}

function nextSeatCircular(currentSeat: number, orderedSeats: number[], offset = 1): number {
  const idx = orderedSeats.findIndex((s) => s > currentSeat);
  const firstIdx = idx === -1 ? 0 : idx;
  const normalized = (firstIdx + offset - 1) % orderedSeats.length;
  return orderedSeats[normalized];
}

function orderedFromButton(buttonSeat: number, seats: number[]): number[] {
  return canonicalClockwiseSeats(buttonSeat, seats);
}

function combinations<T>(items: readonly T[], choose: number): T[][] {
  if (choose <= 0 || choose > items.length) return [];
  if (choose === 1) return items.map((item) => [item]);
  const result: T[][] = [];
  const walk = (start: number, path: T[]): void => {
    if (path.length === choose) {
      result.push([...path]);
      return;
    }
    for (let i = start; i <= items.length - (choose - path.length); i += 1) {
      path.push(items[i]);
      walk(i + 1, path);
      path.pop();
    }
  };
  walk(0, []);
  return result;
}

function toSolverCards(cards: string[]): string[] {
  return cards.map((c) => `${c[0]}${solverSuit(c[1])}`);
}

function solverSuit(suit: string): string {
  if (suit === "s") return "s";
  if (suit === "h") return "h";
  if (suit === "d") return "d";
  return "c";
}
