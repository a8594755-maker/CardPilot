// ===== Minimal local types to avoid depending on shared-types (web-only transitive deps) =====

export type Street = 'PREFLOP' | 'FLOP' | 'TURN' | 'RIVER' | 'SHOWDOWN' | 'RUN_IT_TWICE_PROMPT';

export type PlayerActionType = 'fold' | 'check' | 'call' | 'raise' | 'all_in' | 'vote_rit';

export interface LegalActions {
  canFold: boolean;
  canCheck: boolean;
  canCall: boolean;
  callAmount: number;
  canRaise: boolean;
  minRaise: number;
  maxRaise: number;
}

export interface TablePlayer {
  seat: number;
  userId: string;
  name: string;
  stack: number;
  inHand: boolean;
  folded: boolean;
  allIn: boolean;
  streetCommitted: number;
  status: 'active' | 'sitting_out';
  isNewPlayer: boolean;
}

export interface HandAction {
  seat: number;
  street: Street;
  type: string;
  amount: number;
  at: number;
}

export interface TableState {
  tableId: string;
  smallBlind: number;
  bigBlind: number;
  ante?: number;
  buttonSeat: number;
  street: Street;
  board: string[];
  pot: number;
  currentBet: number;
  minRaiseTo: number;
  lastFullRaiseSize: number;
  lastFullBet: number;
  actorSeat: number | null;
  handId: string | null;
  players: TablePlayer[];
  actions: HandAction[];
  legalActions: LegalActions | null;
  mode: 'COACH' | 'REVIEW' | 'CASUAL';
  positions: Record<number, string>;
  [key: string]: unknown; // allow extra fields we don't use
}

export interface StrategyMix {
  raise: number;
  call: number;
  fold: number;
}

export interface AdvicePayload {
  tableId: string;
  handId: string;
  seat: number;
  mix: StrategyMix;
  recommended?: 'raise' | 'call' | 'fold';
  [key: string]: unknown;
}

export interface ActionSubmitPayload {
  tableId: string;
  handId: string;
  action: PlayerActionType;
  amount?: number;
}

// ===== Bot profile types =====

export type Mix = { raise: number; call: number; fold: number };

export interface RaiseSizingContext {
  street: 'preflop' | 'flop' | 'turn' | 'river';
  bigBlind: number;
  pot: number;
  toCall: number;
  currentBet: number;
  minRaiseTo: number;
  maxRaiseTo: number;
}

export interface BotProfile {
  id: string;
  displayName: string;

  /** Multiply baseMix then normalize; larger = stronger preference */
  actionWeights: Mix;

  /** Only for preflop unopened: shift part of raise probability to call */
  unopenedLimpShare?: number;

  /** Betting/raising sizing preference */
  chooseRaiseTo: (ctx: RaiseSizingContext) => number;

  /** true = sample action by probabilities; false = always pick max-prob action */
  stochastic: boolean;
}
