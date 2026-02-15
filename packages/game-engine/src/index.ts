import { randomInt } from "node:crypto";
import { v4 as uuidv4 } from "uuid";
import pokersolver from "pokersolver";
import type { HandAction, LegalActions, PlayerActionType, Street, TablePlayer, TableState } from "@cardpilot/shared-types";

const RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"];
const SUITS = ["s", "h", "d", "c"];
const { Hand } = pokersolver as unknown as {
  Hand: {
    solve(cards: string[]): { descr: string; rank: number };
    winners(hands: Array<{ descr: string; rank: number }>): Array<{ descr: string; rank: number }>;
  };
};

const POSITIONS_6MAX = ["SB", "BB", "UTG", "HJ", "CO", "BTN"] as const;
const POSITIONS_HU = ["SB", "BB"] as const;

type TableMode = 'COACH' | 'REVIEW' | 'CASUAL';

type MutableTableState = TableState & {
  pendingToAct: Set<number>;
  deck: string[];
  holeCards: Map<number, [string, string]>;
  contributed: Map<number, number>;
};

export class GameTable {
  private state: MutableTableState;
  private allInRunCount: 1 | 2 = 1;
  private runoutPending = false;

  constructor(params: { tableId: string; smallBlind: number; bigBlind: number; mode?: TableMode }) {
    this.state = {
      tableId: params.tableId,
      smallBlind: params.smallBlind,
      bigBlind: params.bigBlind,
      buttonSeat: 1,
      street: "SHOWDOWN",
      board: [],
      pot: 0,
      currentBet: 0,
      minRaiseTo: params.bigBlind * 2,
      actorSeat: null,
      handId: null,
      players: [],
      actions: [],
      legalActions: null,
      mode: params.mode ?? "COACH",
      positions: {},
      pendingToAct: new Set<number>(),
      deck: [],
      holeCards: new Map(),
      contributed: new Map()
    };
  }

  getPublicState(): TableState {
    const { pendingToAct: _pending, deck: _deck, holeCards: _holes, contributed: _contrib, ...rest } = this.state;
    // Compute legalActions for current actor
    const legal = this.computeLegalActions();
    // Compute positions for all active players
    const positions: Record<number, string> = {};
    if (this.state.handId) {
      for (const p of this.state.players) {
        if (p.inHand) positions[p.seat] = this.getPosition(p.seat);
      }
    }
    return { ...rest, legalActions: legal, positions };
  }

  getHoleCards(seat: number): [string, string] | null {
    return this.state.holeCards.get(seat) ?? null;
  }

  addPlayer(player: { seat: number; userId: string; name: string; stack: number }): void {
    if (this.state.players.some((p) => p.seat === player.seat)) {
      throw new Error("seat already occupied");
    }
    this.state.players.push({
      seat: player.seat,
      userId: player.userId,
      name: player.name,
      stack: player.stack,
      inHand: false,
      folded: false,
      allIn: false,
      streetCommitted: 0
    });
    this.state.players.sort((a, b) => a.seat - b.seat);
  }

  removePlayer(seat: number): void {
    this.state.players = this.state.players.filter((p) => p.seat !== seat);
    this.state.pendingToAct.delete(seat);
    this.state.holeCards.delete(seat);
  }

  startHand(): { handId: string } {
    const seated = this.state.players.filter((p) => p.stack > 0);
    if (seated.length < 2) {
      throw new Error("need at least 2 players with chips");
    }

    const handId = uuidv4();
    this.state.handId = handId;
    this.state.street = "PREFLOP";
    this.state.board = [];
    this.state.actions = [];
    this.state.pot = 0;
    this.state.currentBet = this.state.bigBlind;
    this.state.minRaiseTo = this.state.bigBlind * 2;
    this.state.pendingToAct = new Set<number>();
    this.state.holeCards.clear();
    this.state.contributed.clear();
    this.state.deck = shuffledDeck();
    this.state.winners = undefined;
    this.allInRunCount = 1;
    this.runoutPending = false;

    const sortedSeats = seated.map((p) => p.seat).sort((a, b) => a - b);
    this.state.buttonSeat = nextSeatCircular(this.state.buttonSeat, sortedSeats);

    for (const player of this.state.players) {
      const active = sortedSeats.includes(player.seat);
      player.inHand = active;
      player.folded = !active;
      player.allIn = false;
      player.streetCommitted = 0;
      this.state.contributed.set(player.seat, 0);
    }

    for (const seat of sortedSeats) {
      const card1 = this.drawCard();
      const card2 = this.drawCard();
      this.state.holeCards.set(seat, [card1, card2]);
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

  getAllInRunCount(): 1 | 2 {
    return this.allInRunCount;
  }

  applyAction(seat: number, action: PlayerActionType, amount?: number): TableState {
    if (this.state.handId === null || this.state.actorSeat === null) {
      throw new Error("no active hand");
    }
    if (this.state.actorSeat !== seat) {
      throw new Error("not your turn");
    }

    const player = this.playerBySeat(seat);
    if (!player.inHand || player.folded || player.allIn) {
      throw new Error("player cannot act");
    }

    const toCall = Math.max(0, this.state.currentBet - player.streetCommitted);
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
    } else if (action === "check") {
      // no chip movement
    } else if (action === "call") {
      const commit = Math.min(toCall, player.stack);
      player.stack -= commit;
      player.streetCommitted += commit;
      this.state.pot += commit;
      actionAmount = commit;
      if (player.stack === 0) player.allIn = true;
    } else if (action === "raise") {
      const raiseTo = amount as number;
      const commit = raiseTo - player.streetCommitted;
      player.stack -= commit;
      player.streetCommitted = raiseTo;
      this.state.pot += commit;
      actionAmount = commit;
      this.state.minRaiseTo = raiseTo + (raiseTo - this.state.currentBet);
      this.state.currentBet = raiseTo;
      if (player.stack === 0) player.allIn = true;

      this.state.pendingToAct = new Set(
        this.activePlayers()
          .filter((p) => p.seat !== seat && !p.allIn)
          .map((p) => p.seat)
      );
    } else if (action === "all_in") {
      const commit = player.stack;
      const newTotal = player.streetCommitted + commit;
      player.stack = 0;
      player.streetCommitted = newTotal;
      this.state.pot += commit;
      actionAmount = commit;
      player.allIn = true;

      if (newTotal > this.state.currentBet) {
        // This is a raise all-in
        const raiseSize = newTotal - this.state.currentBet;
        if (raiseSize >= (this.state.minRaiseTo - this.state.currentBet)) {
          this.state.minRaiseTo = newTotal + raiseSize;
        }
        this.state.currentBet = newTotal;
        this.state.pendingToAct = new Set(
          this.activePlayers()
            .filter((p) => p.seat !== seat && !p.allIn)
            .map((p) => p.seat)
        );
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
      // Signal runout needed — server will handle sequential dealing & run-count prompt
      this.runoutPending = true;
      this.state.actorSeat = null;
      this.state.pendingToAct.clear();
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
    if (!cards) return "72o";
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
    const positions = activeSeats.length <= 2 ? POSITIONS_HU : POSITIONS_6MAX;
    const labelOrder = positions.slice(positions.length - order.length);
    const idx = order.indexOf(seat);
    return idx >= 0 ? labelOrder[idx] : "UNKNOWN";
  }

  isHandActive(): boolean {
    return this.state.handId !== null && (this.state.actorSeat !== null || this.runoutPending);
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

    // Can raise if player has enough chips above the call
    const canRaise = player.stack > toCall;
    const minRaise = Math.min(this.state.minRaiseTo, player.stack + player.streetCommitted);
    const maxRaise = player.stack + player.streetCommitted;

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
      this.state.board.push(this.drawCard(), this.drawCard(), this.drawCard());
      this.prepareNextStreet();
      return;
    }
    if (this.state.street === "FLOP") {
      this.state.street = "TURN";
      this.state.board.push(this.drawCard());
      this.prepareNextStreet();
      return;
    }
    if (this.state.street === "TURN") {
      this.state.street = "RIVER";
      this.state.board.push(this.drawCard());
      this.prepareNextStreet();
      return;
    }

    this.state.street = "SHOWDOWN";
    this.showdown();
  }

  private runOutBoardTwice(): void {
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

    const payouts = new Map<number, { amount: number; handName?: string }>();
    const sidePots = this.buildSidePots(contenders);
    const solvedFirst = this.solveContenders(contenders, firstBoard);
    const solvedSecond = this.solveContenders(contenders, secondBoard);

    for (const sidePot of sidePots) {
      const firstHalf = Math.floor(sidePot.amount / 2);
      const secondHalf = sidePot.amount - firstHalf;
      this.distributeSolvedPot(firstHalf, solvedFirst, sidePot.eligibleSeats, payouts);
      this.distributeSolvedPot(secondHalf, solvedSecond, sidePot.eligibleSeats, payouts);
    }

    this.state.board = secondBoard;
    this.state.street = "SHOWDOWN";
    this.state.winners = [...payouts.entries()]
      .map(([seat, v]) => ({ seat, amount: v.amount, handName: v.handName }))
      .sort((a, b) => a.seat - b.seat);
    this.state.pot = 0;
    this.state.actorSeat = null;
    this.state.pendingToAct.clear();
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
      const hand = Hand.solve(toSolverCards([...cards, ...board]));
      return { seat: p.seat, hand };
    });
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

    for (const seat of winnerSeats) {
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
    if (this.allInRunCount === 2) {
      this.runOutBoardTwice();
      return;
    }

    // Deal all remaining cards at once (will be revealed step by step by server)
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
    this.state.street = "SHOWDOWN";
    this.state.board = [];
    this.state.pot = 0;
    this.state.currentBet = 0;
    this.state.actorSeat = null;
    this.state.actions = [];
    this.state.winners = undefined;
    this.state.pendingToAct.clear();
    this.state.holeCards.clear();
    this.state.contributed.clear();
    this.runoutPending = false;
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
      newCards.push(this.drawCard(), this.drawCard(), this.drawCard());
      this.state.board.push(...newCards);
      this.state.street = "FLOP";
    } else if (nextStreet === "TURN" && this.state.board.length === 3) {
      const card = this.drawCard();
      newCards.push(card);
      this.state.board.push(card);
      this.state.street = "TURN";
    } else if (nextStreet === "RIVER" && this.state.board.length === 4) {
      const card = this.drawCard();
      newCards.push(card);
      this.state.board.push(card);
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
        this.runoutPending = true;
        this.state.actorSeat = null;
        this.state.pendingToAct.clear();
      }
    }
  }

  private showdown(): void {
    const contenders = this.activePlayers();
    const board = this.state.board;
    const solved = this.solveContenders(contenders, board);
    const sidePots = this.buildSidePots(contenders);
    const payouts = new Map<number, { amount: number; handName?: string }>();

    if (sidePots.length > 0) {
      for (const sidePot of sidePots) {
        this.distributeSolvedPot(sidePot.amount, solved, sidePot.eligibleSeats, payouts);
      }
    }

    this.state.winners = [...payouts.entries()]
      .map(([seat, v]) => ({ seat, amount: v.amount, handName: v.handName }))
      .sort((a, b) => a.seat - b.seat);
    this.state.pot = 0;
    this.state.actorSeat = null;
    this.state.pendingToAct.clear();
  }

  private finishNoShowdown(): void {
    const winner = this.activePlayers()[0];
    const won = this.state.pot;
    winner.stack += won;
    this.state.winners = [{ seat: winner.seat, amount: won }];
    this.state.pot = 0;
    this.state.street = "SHOWDOWN";
    this.state.actorSeat = null;
    this.state.pendingToAct.clear();
  }

  private commitBlind(seat: number, amount: number, type: "post_sb" | "post_bb") {
    const player = this.playerBySeat(seat);
    const commit = Math.min(player.stack, amount);
    player.stack -= commit;
    player.streetCommitted += commit;
    this.state.pot += commit;
    this.state.contributed.set(seat, (this.state.contributed.get(seat) ?? 0) + commit);
    if (player.stack === 0) {
      player.allIn = true;
    }
    this.logAction({ seat, street: "PREFLOP", type: type as unknown as PlayerActionType, amount: commit, at: Date.now() });
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
  if (seats.length === 0) return [];
  const gt = seats.filter((s) => s > buttonSeat);
  const lte = seats.filter((s) => s <= buttonSeat);
  return [...gt, ...lte];
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
