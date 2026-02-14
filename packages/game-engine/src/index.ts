import { randomInt } from "node:crypto";
import { v4 as uuidv4 } from "uuid";
import pokersolver from "pokersolver";
import type { HandAction, PlayerActionType, Street, TablePlayer, TableState } from "@cardpilot/shared-types";

const RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"];
const SUITS = ["s", "h", "d", "c"];
const { Hand } = pokersolver as unknown as {
  Hand: {
    solve(cards: string[]): { descr: string; rank: number };
    winners(hands: Array<{ descr: string; rank: number }>): Array<{ descr: string; rank: number }>;
  };
};

const POSITIONS = ["SB", "BB", "UTG", "HJ", "CO", "BTN"] as const;

type MutableTableState = TableState & {
  pendingToAct: Set<number>;
  deck: string[];
  holeCards: Map<number, [string, string]>;
};

export class GameTable {
  private state: MutableTableState;

  constructor(params: { tableId: string; smallBlind: number; bigBlind: number }) {
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
      pendingToAct: new Set<number>(),
      deck: [],
      holeCards: new Map()
    };
  }

  getPublicState(): TableState {
    const { pendingToAct: _pending, deck: _deck, holeCards: _holes, ...publicState } = this.state;
    return publicState;
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
    this.state.deck = shuffledDeck();

    const sortedSeats = seated.map((p) => p.seat).sort((a, b) => a - b);
    this.state.buttonSeat = nextSeatCircular(this.state.buttonSeat, sortedSeats);

    for (const player of this.state.players) {
      const active = sortedSeats.includes(player.seat);
      player.inHand = active;
      player.folded = !active;
      player.allIn = false;
      player.streetCommitted = 0;
    }

    for (const seat of sortedSeats) {
      const card1 = this.drawCard();
      const card2 = this.drawCard();
      this.state.holeCards.set(seat, [card1, card2]);
    }

    const sbSeat = this.getRelativeSeat(1);
    const bbSeat = this.getRelativeSeat(2);
    this.commitBlind(sbSeat, this.state.smallBlind, "POST_SB");
    this.commitBlind(bbSeat, this.state.bigBlind, "POST_BB");

    this.state.pendingToAct = new Set(
      this.activePlayers()
        .filter((p) => !p.allIn)
        .map((p) => p.seat)
    );
    this.state.actorSeat = this.nextActorFrom(this.getRelativeSeat(3));

    return { handId };
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
      if (amount < this.state.minRaiseTo) {
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
      if (player.stack === 0) player.allIn = true;
    } else if (action === "raise") {
      const raiseTo = amount as number;
      const commit = raiseTo - player.streetCommitted;
      player.stack -= commit;
      player.streetCommitted = raiseTo;
      this.state.pot += commit;
      this.state.minRaiseTo = raiseTo + (raiseTo - this.state.currentBet);
      this.state.currentBet = raiseTo;
      if (player.stack === 0) player.allIn = true;

      this.state.pendingToAct = new Set(
        this.activePlayers()
          .filter((p) => p.seat !== seat && !p.allIn)
          .map((p) => p.seat)
      );
    }

    this.logAction({
      seat,
      street: this.state.street,
      type: action,
      amount: amount ?? (action === "call" ? toCall : 0),
      at: Date.now()
    });

    this.state.pendingToAct.delete(seat);

    const remaining = this.activePlayers();
    if (remaining.length <= 1) {
      this.finishNoShowdown();
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
    const labelOrder = POSITIONS.slice(6 - order.length);
    const idx = order.indexOf(seat);
    return idx >= 0 ? labelOrder[idx] : "UNKNOWN";
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

    const first = this.nextActorFrom(this.getRelativeSeat(1));
    this.state.actorSeat = first;
  }

  private showdown(): void {
    const contenders = this.activePlayers();
    const board = this.state.board;

    const solved = contenders.map((p) => {
      const cards = this.state.holeCards.get(p.seat) ?? ["2c", "7d"];
      const hand = Hand.solve(toSolverCards([...cards, ...board]));
      return { seat: p.seat, hand };
    });

    const winners = Hand.winners(solved.map((s) => s.hand));
    const winnerSeats = solved
      .filter((s) =>
        winners.some((w: { descr: string; rank: number }) => w.descr === s.hand.descr && w.rank === s.hand.rank)
      )
      .map((s) => s.seat);

    const share = Math.floor(this.state.pot / winnerSeats.length);
    let remainder = this.state.pot - share * winnerSeats.length;

    for (const seat of winnerSeats) {
      const player = this.playerBySeat(seat);
      player.stack += share;
      if (remainder > 0) {
        player.stack += 1;
        remainder -= 1;
      }
    }

    this.state.actorSeat = null;
    this.state.pendingToAct.clear();
  }

  private finishNoShowdown(): void {
    const winner = this.activePlayers()[0];
    winner.stack += this.state.pot;
    this.state.street = "SHOWDOWN";
    this.state.actorSeat = null;
    this.state.pendingToAct.clear();
  }

  private commitBlind(seat: number, amount: number, type: "POST_SB" | "POST_BB") {
    const player = this.playerBySeat(seat);
    const commit = Math.min(player.stack, amount);
    player.stack -= commit;
    player.streetCommitted += commit;
    this.state.pot += commit;
    if (player.stack === 0) {
      player.allIn = true;
    }
    this.logAction({ seat, street: "PREFLOP", type: type === "POST_SB" ? "raise" : "call", amount: commit, at: Date.now() });
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
