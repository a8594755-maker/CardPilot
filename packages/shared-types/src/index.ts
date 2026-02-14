// ===== Core Poker Types =====

export type Street = 'PREFLOP' | 'FLOP' | 'TURN' | 'RIVER' | 'SHOWDOWN';

export type PlayerActionType = 'fold' | 'check' | 'call' | 'raise' | 'all_in';

export type Position = 'SB' | 'BB' | 'UTG' | 'MP' | 'HJ' | 'CO' | 'BTN';

// ===== Player & Table Types =====

export interface TablePlayer {
  seat: number;
  userId: string;
  name: string;
  stack: number;
  inHand: boolean;
  folded: boolean;
  allIn: boolean;
  streetCommitted: number;
}

export interface HandAction {
  seat: number;
  street: Street;
  type: PlayerActionType;
  amount: number;
  at: number;
}

export interface TableState {
  tableId: string;
  smallBlind: number;
  bigBlind: number;
  buttonSeat: number;
  street: Street;
  board: string[];
  pot: number;
  currentBet: number;
  minRaiseTo: number;
  actorSeat: number | null;
  handId: string | null;
  players: TablePlayer[];
  actions: HandAction[];
}

// ===== Advice Types =====

export interface StrategyMix {
  raise: number;
  call: number;
  fold: number;
}

export interface AdvicePayload {
  tableId: string;
  handId: string;
  seat: number;
  spotKey: string;
  heroHand: string;
  mix: StrategyMix;
  tags: string[];
  explanation: string;
}

// ===== Action Types =====

export interface ActionSubmitPayload {
  tableId: string;
  handId: string;
  action: PlayerActionType;
  amount?: number;
}

// ===== Lobby Types =====

export interface LobbyRoomSummary {
  tableId: string;
  roomCode: string;
  roomName: string;
  smallBlind: number;
  bigBlind: number;
  maxPlayers: number;
  playerCount: number;
  status: 'OPEN' | 'CLOSED';
  updatedAt: string;
}

// ===== New Types (Coach Mode) =====

export interface SpotInfo {
  position: Position;
  vsPosition?: Position;
  effectiveStack: number; // in bb
  potSize: number;
  toCall: number;
  actionHistory: string[];
  isHeadsUp: boolean;
}

export interface PreflopChartEntry {
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

export interface AdviceLogEntry {
  handId: string;
  spotKey: string;
  heroHand: string;
  gtoMix: StrategyMix;
  actualAction: PlayerActionType;
  deviation: number; // 0 = perfect, 1 = completely wrong
  timestamp: Date;
}

// Re-export socket events
export * from './socket-events.js';
