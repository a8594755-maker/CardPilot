// WebSocket Event Types for CardPilot
// Namespace: /poker

import type { Street, PlayerActionType, AdvicePayload as AdvicePayloadFromIndex, LobbyRoomSummary as LobbyRoomSummaryFromIndex } from './index.js';

// Re-export types from index.ts for convenience
export type { AdvicePayloadFromIndex as AdvicePayload, LobbyRoomSummaryFromIndex as LobbyRoomSummary };

// ===== Client → Server Events =====

export interface JoinTablePayload {
  roomId: string;
  seatIndex?: number; // 指定座位或自動分配
}

export interface SitDownPayload {
  seatIndex: number;
  buyIn: number; // 購買籌碼量
  name?: string;
}

export interface PlayerActionPayload {
  handId: string;
  action: 'fold' | 'check' | 'call' | 'raise' | 'all_in';
  amount?: number; // raise 時必填
}

export interface RequestAdvicePayload {
  handId: string;
}

export interface CreateRoomPayload {
  roomName?: string;
  maxSeats?: number;
  smallBlind?: number;
  bigBlind?: number;
  isPublic?: boolean;
}

export interface JoinRoomCodePayload {
  roomCode: string;
}

// ===== Server → Client Events =====

export interface SeatInfo {
  index: number;
  user: { 
    id: string; 
    nickname: string; 
    avatar?: string;
  } | null;
  stack: number;
  status: 'empty' | 'active' | 'sitting_out';
  isButton: boolean;
  isSmallBlind: boolean;
  isBigBlind: boolean;
}

export interface CurrentHandInfo {
  handId: string;
  handNumber: number;
  status: 'preflop' | 'flop' | 'turn' | 'river' | 'showdown';
  communityCards: string[]; // ["As", "Kd", "Qh"]
  pot: number;
  currentBet: number; // 當前最高注
  actorSeat: number | null; // 輪到誰
  timeRemaining: number; // 倒數計時（秒）
}

export interface TableSnapshotPayload {
  roomId: string;
  roomCode: string;
  name: string;
  status: 'waiting' | 'playing';
  seats: SeatInfo[];
  currentHand: CurrentHandInfo | null;
  smallBlind: number;
  bigBlind: number;
}

export interface DealCardsPayload {
  handId: string;
  holeCards: [string, string]; // ["Ah", "Ks"]
  position: 'SB' | 'BB' | 'UTG' | 'MP' | 'HJ' | 'CO' | 'BTN';
}

export interface ActionAppliedPayload {
  handId: string;
  seatIndex: number;
  action: string;
  amount?: number;
  potAfter: number;
  nextActor?: number; // 下一位
  streetEnds?: boolean; // 這條街是否結束
}

export interface StreetAdvancedPayload {
  handId: string;
  newStreet: 'flop' | 'turn' | 'river' | 'showdown';
  communityCards: string[]; // 新增的牌
  pot: number;
  nextActor: number;
}

export interface StrategyMix {
  fold: number;
  call: number;
  raise: number;
}

export interface AdviceExplanation {
  tags: string[]; // ["IP_advantage", "blocker_A", "wheel_potential"]
  shortText: string; // "A5s 有 A blocker，且可形成小順..."
  details: string; // 詳細說明
}

export interface AdviceContext {
  position: string;
  vsPosition?: string;
  effectiveStack: number; // bb
  potOdds: number;
  toCall: number;
}

// Note: AdvicePayload is defined in index.ts to avoid duplication

export interface WinnerInfo {
  seatIndex: number;
  winAmount: number;
  holeCards?: [string, string];
  handRank: string; // "Royal Flush", "Two Pair"
}

export interface HandResultPayload {
  handId: string;
  winners: WinnerInfo[];
  showdown: boolean;
  communityCards: string[];
  pot: number;
}

export interface RoomCreatedPayload {
  roomId: string;
  roomCode: string;
  roomName: string;
}

export interface RoomJoinedPayload {
  roomId: string;
  roomCode: string;
  roomName: string;
}

// Note: LobbyRoomSummary is defined in index.ts to avoid duplication

export interface LobbySnapshotPayload {
  rooms: LobbyRoomSummaryFromIndex[];
}

export interface ErrorPayload {
  code: string;
  message: string;
}

// ===== Socket Event Maps =====

export interface ClientToServerEvents {
  'table:join': (payload: JoinTablePayload) => void;
  'seat:sit': (payload: SitDownPayload) => void;
  'seat:stand': (payload: { seatIndex: number }) => void;
  'hand:action': (payload: PlayerActionPayload) => void;
  'advice:request': (payload: RequestAdvicePayload) => void;
  'room:create': (payload: CreateRoomPayload) => void;
  'room:join_code': (payload: JoinRoomCodePayload) => void;
  'room:leave': () => void;
  'hand:start': () => void;
  'lobby:refresh': () => void;
}

export interface ServerToClientEvents {
  'connection:established': (data: { 
    socketId: string; 
    userId: string;
    nickname: string;
  }) => void;
  
  'table:snapshot': (payload: TableSnapshotPayload) => void;
  'hand:deal': (payload: DealCardsPayload) => void;
  'hand:action_applied': (payload: ActionAppliedPayload) => void;
  'hand:street_advanced': (payload: StreetAdvancedPayload) => void;
  'hand:result': (payload: HandResultPayload) => void;
  'hand:ended': (payload: HandResultPayload) => void;
  
  'advice:recommendation': (payload: AdvicePayloadFromIndex) => void;
  
  'room:created': (payload: RoomCreatedPayload) => void;
  'room:joined': (payload: RoomJoinedPayload) => void;
  'room:left': () => void;
  
  'lobby:snapshot': (payload: LobbySnapshotPayload) => void;
  
  'player:joined': (payload: { seatIndex: number; nickname: string }) => void;
  'player:left': (payload: { seatIndex: number }) => void;
  
  'error': (payload: ErrorPayload) => void;
}
