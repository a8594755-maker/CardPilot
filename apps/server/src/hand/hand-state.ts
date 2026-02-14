import { randomUUID } from 'node:crypto';
import type { 
  Street, 
  PlayerActionType, 
  Position,
  TablePlayer 
} from '@cardpilot/shared-types';
import { createShuffledDeck, normalizeHand, type Card } from '@cardpilot/poker-evaluator';

export interface HandStateConfig {
  roomId: string;
  handNumber: number;
  smallBlind: number;
  bigBlind: number;
  maxSeats: number;
}

export interface SeatState {
  index: number;
  userId: string | null;
  nickname: string | null;
  stack: number;
  status: 'empty' | 'active' | 'sitting_out';
  holeCards: [Card, Card] | null;
  isFolded: boolean;
  isAllIn: boolean;
  invested: number; // Current street invested
  totalInvested: number; // Total in this hand
}

export interface HandActionRecord {
  seq: number;
  seatIndex: number;
  street: Street;
  action: PlayerActionType | 'SB_POST' | 'BB_POST';
  amount: number;
  timestamp: Date;
}

const POSITIONS_6MAX: Position[] = ['SB', 'BB', 'UTG', 'MP', 'CO', 'BTN'];

export class HandState {
  private id: string;
  private roomId: string;
  private handNumber: number;
  private status: Street = 'PREFLOP';
  
  private seats: Map<number, SeatState> = new Map();
  private deck: Card[] = [];
  private communityCards: Card[] = [];
  private pot: number = 0;
  private currentBet: number = 0;
  private minRaiseTo: number = 0;
  private actorSeat: number | null = null;
  
  private buttonSeat: number = 0;
  private smallBlind: number;
  private bigBlind: number;
  private maxSeats: number;
  
  private actions: HandActionRecord[] = [];
  private actionSeq: number = 0;
  private pendingToAct: Set<number> = new Set();
  
  private startedAt: Date = new Date();
  private endedAt: Date | null = null;
  
  private deckSeed: string;

  constructor(config: HandStateConfig) {
    this.id = randomUUID();
    this.roomId = config.roomId;
    this.handNumber = config.handNumber;
    this.smallBlind = config.smallBlind;
    this.bigBlind = config.bigBlind;
    this.maxSeats = config.maxSeats;
    this.minRaiseTo = this.bigBlind * 2;
    this.deckSeed = randomUUID();
  }

  // ===== Getters =====
  
  getId(): string { return this.id; }
  getRoomId(): string { return this.roomId; }
  getHandNumber(): number { return this.handNumber; }
  getStatus(): Street { return this.status; }
  getPot(): number { return this.pot; }
  getCurrentBet(): number { return this.currentBet; }
  getActorSeat(): number | null { return this.actorSeat; }
  getButtonSeat(): number { return this.buttonSeat; }
  getCommunityCards(): Card[] { return [...this.communityCards]; }
  getSmallBlind(): number { return this.smallBlind; }
  getBigBlind(): number { return this.bigBlind; }
  
  getSeats(): SeatState[] {
    return Array.from(this.seats.values()).sort((a, b) => a.index - b.index);
  }
  
  getSeat(index: number): SeatState | undefined {
    return this.seats.get(index);
  }
  
  getHoleCards(seatIndex: number): [Card, Card] | null {
    return this.seats.get(seatIndex)?.holeCards ?? null;
  }
  
  getActions(): HandActionRecord[] {
    return [...this.actions];
  }
  
  getActionsForStreet(street: Street): HandActionRecord[] {
    return this.actions.filter(a => a.street === street);
  }

  // ===== Setup =====

  addPlayer(seatIndex: number, userId: string, nickname: string, stack: number): void {
    if (this.seats.has(seatIndex)) {
      throw new Error(`Seat ${seatIndex} is already occupied`);
    }
    
    this.seats.set(seatIndex, {
      index: seatIndex,
      userId,
      nickname,
      stack,
      status: 'active',
      holeCards: null,
      isFolded: false,
      isAllIn: false,
      invested: 0,
      totalInvested: 0
    });
  }

  startHand(buttonSeat: number): void {
    this.buttonSeat = buttonSeat;
    this.deck = createShuffledDeck(this.deckSeed);
    this.communityCards = [];
    this.pot = 0;
    this.currentBet = 0;
    this.minRaiseTo = this.bigBlind * 2;
    this.actions = [];
    this.actionSeq = 0;
    
    // Get active seats (ordered)
    const activeSeats = this.getActiveSeatIndices();
    if (activeSeats.length < 2) {
      throw new Error('Need at least 2 players to start a hand');
    }
    
    // Deal hole cards
    for (const seatIdx of activeSeats) {
      const seat = this.seats.get(seatIdx)!;
      const card1 = this.drawCard();
      const card2 = this.drawCard();
      seat.holeCards = [card1, card2];
    }
    
    // Post blinds
    const sbSeat = this.getSeatRelativeToButton(1);
    const bbSeat = this.getSeatRelativeToButton(2);
    
    this.postBlind(sbSeat, this.smallBlind, 'SB_POST');
    this.postBlind(bbSeat, this.bigBlind, 'BB_POST');
    
    this.currentBet = this.bigBlind;
    
    // Set pending actors
    this.pendingToAct = new Set(
      activeSeats.filter(idx => {
        const seat = this.seats.get(idx)!;
        return !seat.isAllIn;
      })
    );
    
    // First actor is UTG (3 positions after button)
    this.actorSeat = this.getSeatRelativeToButton(3);
    
    this.status = 'PREFLOP';
    this.startedAt = new Date();
  }

  // ===== Actions =====

  applyAction(
    seatIndex: number, 
    action: PlayerActionType, 
    amount?: number
  ): { 
    success: boolean; 
    error?: string;
    stateChanged?: boolean;
    streetAdvanced?: boolean;
    handEnded?: boolean;
  } {
    // Validate turn
    if (this.actorSeat !== seatIndex) {
      return { success: false, error: 'Not your turn' };
    }
    
    const seat = this.seats.get(seatIndex);
    if (!seat || seat.status !== 'active') {
      return { success: false, error: 'Invalid seat' };
    }
    
    if (seat.isFolded || seat.isAllIn) {
      return { success: false, error: 'Player cannot act' };
    }
    
    const toCall = Math.max(0, this.currentBet - seat.invested);
    
    // Validate action
    switch (action) {
      case 'check':
        if (toCall > 0) {
          return { success: false, error: 'Cannot check when facing a bet' };
        }
        break;
        
      case 'call':
        if (toCall === 0) {
          return { success: false, error: 'Nothing to call' };
        }
        break;
        
      case 'raise':
        if (amount === undefined) {
          return { success: false, error: 'Raise amount required' };
        }
        if (amount < this.minRaiseTo) {
          return { success: false, error: `Raise must be at least ${this.minRaiseTo}` };
        }
        if (amount <= this.currentBet) {
          return { success: false, error: 'Raise must be greater than current bet' };
        }
        const needed = amount - seat.invested;
        if (needed > seat.stack) {
          return { success: false, error: 'Insufficient chips' };
        }
        break;
        
      case 'all_in':
        // All-in is always valid if player has chips
        break;
    }
    
    // Apply the action
    this.executeAction(seat, action, amount, toCall);
    
    // Record action
    this.recordAction(seatIndex, action, action === 'all_in' ? seat.invested : (amount || 0));
    
    // Remove from pending
    this.pendingToAct.delete(seatIndex);
    
    // Check for hand end (only one player left)
    const activePlayers = this.getActivePlayers();
    if (activePlayers.length <= 1) {
      this.endHand();
      return { success: true, stateChanged: true, handEnded: true };
    }
    
    // Check if street is complete
    if (this.pendingToAct.size === 0) {
      this.advanceStreet();
      return { success: true, stateChanged: true, streetAdvanced: true };
    }
    
    // Move to next actor
    this.actorSeat = this.getNextActor(seatIndex);
    
    return { success: true, stateChanged: true };
  }

  private executeAction(
    seat: SeatState, 
    action: PlayerActionType, 
    amount: number | undefined,
    toCall: number
  ): void {
    switch (action) {
      case 'fold':
        seat.isFolded = true;
        break;
        
      case 'check':
        // No chip movement
        break;
        
      case 'call':
        const callAmount = Math.min(toCall, seat.stack);
        seat.stack -= callAmount;
        seat.invested += callAmount;
        seat.totalInvested += callAmount;
        this.pot += callAmount;
        if (seat.stack === 0) seat.isAllIn = true;
        break;
        
      case 'raise':
        const raiseTo = amount!;
        const commit = raiseTo - seat.invested;
        seat.stack -= commit;
        seat.invested = raiseTo;
        seat.totalInvested += commit;
        this.pot += commit;
        
        // Update raise tracking
        this.minRaiseTo = raiseTo + (raiseTo - this.currentBet);
        this.currentBet = raiseTo;
        
        if (seat.stack === 0) seat.isAllIn = true;
        
        // Reset pending for other players
        this.pendingToAct = new Set(
          this.getActivePlayers()
            .filter(p => p.index !== seat.index && !p.isAllIn)
            .map(p => p.index)
        );
        break;
        
      case 'all_in':
        const allInAmount = seat.stack + seat.invested;
        this.pot += seat.stack;
        seat.invested += seat.stack;
        seat.totalInvested += seat.stack;
        seat.stack = 0;
        seat.isAllIn = true;
        
        if (allInAmount > this.currentBet) {
          // This is a raise
          this.minRaiseTo = allInAmount + (allInAmount - this.currentBet);
          this.currentBet = allInAmount;
          
          // Reset pending
          this.pendingToAct = new Set(
            this.getActivePlayers()
              .filter(p => p.index !== seat.index && !p.isAllIn)
              .map(p => p.index)
          );
        }
        break;
    }
  }

  private advanceStreet(): void {
    // Move invested to total and reset
    for (const seat of this.seats.values()) {
      seat.invested = 0;
    }
    this.currentBet = 0;
    this.minRaiseTo = this.bigBlind;
    
    switch (this.status) {
      case 'PREFLOP':
        this.status = 'FLOP';
        this.dealCommunityCards(3);
        break;
      case 'FLOP':
        this.status = 'TURN';
        this.dealCommunityCards(1);
        break;
      case 'TURN':
        this.status = 'RIVER';
        this.dealCommunityCards(1);
        break;
      case 'RIVER':
        this.status = 'SHOWDOWN';
        this.endHand();
        return;
    }
    
    // Set pending actors for new street
    const activePlayers = this.getActivePlayers();
    this.pendingToAct = new Set(
      activePlayers.filter(p => !p.isAllIn).map(p => p.index)
    );
    
    // First actor postflop is first active after button (SB or earliest)
    this.actorSeat = this.getFirstActorPostflop();
  }

  private endHand(): void {
    this.status = 'SHOWDOWN';
    this.endedAt = new Date();
    this.actorSeat = null;
    this.pendingToAct.clear();
    
    // Award pot to winner(s)
    const winners = this.determineWinners();
    const share = Math.floor(this.pot / winners.length);
    let remainder = this.pot - share * winners.length;
    
    for (const winner of winners) {
      const seat = this.seats.get(winner)!;
      seat.stack += share;
      if (remainder > 0) {
        seat.stack += 1;
        remainder--;
      }
    }
  }

  // ===== Helpers =====

  private drawCard(): Card {
    const card = this.deck.pop();
    if (!card) throw new Error('Deck exhausted');
    return card;
  }

  private dealCommunityCards(count: number): void {
    for (let i = 0; i < count; i++) {
      this.communityCards.push(this.drawCard());
    }
  }

  private postBlind(
    seatIndex: number, 
    amount: number, 
    type: 'SB_POST' | 'BB_POST'
  ): void {
    const seat = this.seats.get(seatIndex);
    if (!seat) return;
    
    const commit = Math.min(seat.stack, amount);
    seat.stack -= commit;
    seat.invested += commit;
    seat.totalInvested += commit;
    this.pot += commit;
    
    if (seat.stack === 0) seat.isAllIn = true;
    
    this.recordAction(seatIndex, type === 'SB_POST' ? 'raise' : 'call', commit);
  }

  private recordAction(
    seatIndex: number, 
    action: PlayerActionType | 'SB_POST' | 'BB_POST', 
    amount: number
  ): void {
    this.actionSeq++;
    this.actions.push({
      seq: this.actionSeq,
      seatIndex,
      street: this.status,
      action: action as PlayerActionType,
      amount,
      timestamp: new Date()
    });
  }

  private getActiveSeatIndices(): number[] {
    return Array.from(this.seats.values())
      .filter(s => s.status === 'active' && s.stack > 0)
      .map(s => s.index)
      .sort((a, b) => a - b);
  }

  private getActivePlayers(): SeatState[] {
    return Array.from(this.seats.values())
      .filter(s => s.status === 'active' && !s.isFolded);
  }

  private getSeatRelativeToButton(offset: number): number {
    const activeSeats = this.getActiveSeatIndices();
    const ordered = this.orderFromButton(activeSeats);
    return ordered[offset % ordered.length];
  }

  private orderFromButton(seats: number[]): number[] {
    if (seats.length === 0) return [];
    const greater = seats.filter(s => s > this.buttonSeat);
    const lesser = seats.filter(s => s <= this.buttonSeat);
    return [...greater, ...lesser];
  }

  private getNextActor(currentSeat: number): number | null {
    const activePlayers = this.getActivePlayers()
      .filter(p => !p.isAllIn)
      .map(p => p.index)
      .sort((a, b) => a - b);
    
    if (activePlayers.length === 0) return null;
    
    // Find next seat in order
    const currentIdx = activePlayers.findIndex(s => s > currentSeat);
    const startIdx = currentIdx === -1 ? 0 : currentIdx;
    
    for (let i = 0; i < activePlayers.length; i++) {
      const idx = (startIdx + i) % activePlayers.length;
      const seat = activePlayers[idx];
      if (this.pendingToAct.has(seat)) {
        return seat;
      }
    }
    
    return null;
  }

  private getFirstActorPostflop(): number | null {
    const activePlayers = this.getActivePlayers()
      .filter(p => !p.isAllIn)
      .map(p => p.index)
      .sort((a, b) => a - b);
    
    if (activePlayers.length === 0) return null;
    
    // Start from SB (first after button)
    const ordered = this.orderFromButton(activePlayers);
    for (const seat of ordered) {
      if (this.pendingToAct.has(seat)) {
        return seat;
      }
    }
    
    return null;
  }

  private determineWinners(): number[] {
    // For now, simple implementation - return first active player
    // In production, use @cardpilot/poker-evaluator
    const activePlayers = this.getActivePlayers();
    
    // If only one player, they win
    if (activePlayers.length === 1) {
      return [activePlayers[0].index];
    }
    
    // For showdown, we'd evaluate hands here
    // For now, just return the first player as winner (simplified)
    return [activePlayers[0].index];
  }

  // ===== Position & Spot Info =====

  getPosition(seatIndex: number): Position {
    const activeSeats = this.getActiveSeatIndices();
    const ordered = this.orderFromButton(activeSeats);
    const idx = ordered.indexOf(seatIndex);
    
    if (idx === -1) return 'UTG'; // Default
    
    // Map to positions based on number of players
    const positionsForCount = POSITIONS_6MAX.slice(6 - ordered.length);
    return positionsForCount[idx];
  }

  getSpotInfo(seatIndex: number): {
    position: Position;
    vsPosition?: Position;
    effectiveStack: number;
    potSize: number;
    toCall: number;
    actionHistory: string[];
    isUnopened: boolean;
  } {
    const position = this.getPosition(seatIndex);
    const seat = this.seats.get(seatIndex)!;
    const toCall = Math.max(0, this.currentBet - seat.invested);
    
    // Find last raiser position (for vsPosition)
    let vsPosition: Position | undefined;
    const streetActions = this.getActionsForStreet(this.status);
    for (let i = streetActions.length - 1; i >= 0; i--) {
      const action = streetActions[i];
      if (action.action === 'raise') {
        vsPosition = this.getPosition(action.seatIndex);
        break;
      }
    }
    
    // Check if pot is unopened (no voluntary action yet)
    const voluntaryActions = streetActions.filter(a => 
      (a.action === 'raise' || a.action === 'call') && 
      a.amount > this.bigBlind
    );
    const isUnopened = voluntaryActions.length === 0;
    
    // Calculate effective stack
    const activePlayers = this.getActivePlayers();
    const minStack = Math.min(...activePlayers.map(p => p.stack + p.invested));
    const effectiveStack = Math.floor(minStack / this.bigBlind);
    
    // Action history for this street
    const actionHistory = streetActions.map(a => 
      `${this.getPosition(a.seatIndex)}_${a.action}_${a.amount}`
    );
    
    return {
      position,
      vsPosition,
      effectiveStack,
      potSize: this.pot,
      toCall,
      actionHistory,
      isUnopened
    };
  }

  getNormalizedHand(seatIndex: number): string | null {
    const holeCards = this.getHoleCards(seatIndex);
    if (!holeCards) return null;
    return normalizeHand(holeCards);
  }
}
