// ===== Core Poker Types =====

export type Street = 'PREFLOP' | 'FLOP' | 'TURN' | 'RIVER' | 'SHOWDOWN' | 'RUN_IT_TWICE_PROMPT';

export type PlayerActionType = 'fold' | 'check' | 'call' | 'raise' | 'all_in' | 'vote_rit';

export type BlindActionType = 'post_sb' | 'post_bb' | 'post_dead_blind';

export type AnteActionType = 'ante';

export type HandActionType = PlayerActionType | BlindActionType | AnteActionType;

export interface LegalActions {
  canFold: boolean;
  canCheck: boolean;
  canCall: boolean;
  callAmount: number;
  canRaise: boolean;
  minRaise: number;
  maxRaise: number;
}

export type Position = 'SB' | 'BB' | 'UTG' | 'MP' | 'HJ' | 'CO' | 'BTN';

// ===== Player & Table Types =====

export type PlayerStatus = 'active' | 'sitting_out';

/**
 * Canonical clockwise order helper.
 *
 * Returns seats in clockwise order starting from the seat immediately left of button
 * (i.e. first seat after button in clockwise direction).
 */
export function getClockwiseSeatsFromButton(buttonSeat: number, seats: number[]): number[] {
  if (seats.length === 0) return [];
  const uniq = [...new Set(seats)].sort((a, b) => a - b);
  const gt = uniq.filter((s) => s > buttonSeat);
  const lte = uniq.filter((s) => s <= buttonSeat);
  return [...gt, ...lte];
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
  /** Player table status — sitting_out players are skipped during deal */
  status: PlayerStatus;
  /** True if player has not yet played a hand at this table (must wait for BB or post dead) */
  isNewPlayer: boolean;
}

export interface AllInPrompt {
  actorSeat: number;
  winRate: number;
  recommendedRunCount: 1 | 2;
  defaultRunCount: 1 | 2;
  allowedRunCounts: Array<1 | 2>;
  reason: string;
}

export interface PlayerEquity {
  seat: number;
  winRate: number;
  tieRate: number;
}

export interface BoardRevealEvent {
  handId: string;
  street: Street;
  newCards: string[];
  board: string[];
  equities: PlayerEquity[];
}

export interface HandAction {
  seat: number;
  street: Street;
  type: HandActionType;
  amount: number;
  at: number;
}

export interface HandWinner {
  seat: number;
  amount: number;
  handName?: string;
}

export interface RunoutPayout {
  run: 1 | 2;
  board: string[];
  winners: HandWinner[];
}

export interface PotLayer {
  label: string;
  amount: number;
  eligibleSeats: number[];
}

export interface SeatLedgerEntry {
  seat: number;
  playerName: string;
  startStack: number;
  invested: number;
  won: number;
  endStack: number;
  net: number;
}

export interface SettlementResult {
  handId: string;
  totalPot: number;
  rake: number;
  collectedFee: number;
  totalPaid: number;
  runCount: 1 | 2;
  boards: string[][];
  potLayers: PotLayer[];
  winnersByRun: Array<{ run: 1 | 2; board: string[]; winners: HandWinner[] }>;
  payoutsBySeat: Record<number, number>;
  payoutsBySeatByRun?: Array<Record<number, number>>;
  ledger: SeatLedgerEntry[];
  contributions: Record<number, number>;
  showdown: boolean;
  buttonSeat: number;
  timestamp: number;
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
  /** The size of the last full (legal) raise. Used for the "full raise" rule:
   *  a short all-in that doesn't meet lastFullRaiseSize does NOT reopen betting. */
  lastFullRaiseSize: number;
  /** The currentBet level where betting was last fully reopened by a full bet/raise. */
  lastFullBet: number;
  actorSeat: number | null;
  handId: string | null;
  players: TablePlayer[];
  actions: HandAction[];
  legalActions: LegalActions | null;
  mode: 'COACH' | 'REVIEW' | 'CASUAL';
  winners?: HandWinner[];
  /** Map of seat number → position label (BTN, SB, BB, UTG, etc.) */
  positions: Record<number, string>;
  allInPrompt?: AllInPrompt;
  /** When run-it-twice is chosen, both completed boards (length 2, each with 5 cards) */
  runoutBoards?: string[][];
  /** Per-run payouts when run-it-twice is used */
  runoutPayouts?: RunoutPayout[];
  /** Seats marked as pending stand-up (will leave after current hand ends) */
  pendingStandUp?: number[];
  /** True when host requested pause but a hand is still active */
  pendingPause?: boolean;
  /** Pending deposit requests visible to all players */
  pendingDeposits?: Array<{ orderId: string; seat: number; userId: string; userName: string; amount: number }>;
  /** Showdown-revealed hole cards by seat (always public once shown). */
  shownCards: Record<number, [string, string]>;
  /** Backward-compatible alias for shownCards. */
  shownHands: Record<number, [string, string]>;
  /** Publicly revealed hole cards by seat */
  revealedHoles?: Record<number, [string, string]>;
  /** Seats that explicitly mucked at showdown */
  muckedSeats?: number[];
  /** Showdown reveal state used by clients to render SHOW/MUCK actions */
  showdownPhase?: "none" | "decision";
  /** Run-it-twice prompt votes keyed by seat while in RUN_IT_TWICE_PROMPT street. */
  ritVotes?: Record<number, boolean | null>;
  /** Feature flag for run-it-twice negotiation at all-in closures. */
  runItTwiceEnabled?: boolean;
  /** Blind level already scheduled and to be applied on next startHand(). */
  nextBlindLevel?: { smallBlind: number; bigBlind: number; ante: number } | null;
}

// ===== Advice Types =====

export interface StrategyMix {
  raise: number;
  call: number;
  fold: number;
}

export type AdviceStage = 'preflop' | 'postflop';

export type StackDepthBucket = 'short' | 'medium' | 'standard' | 'deep';

export interface StackProfile {
  effectiveStackBb: number;
  requestedBucket: StackDepthBucket;
  resolvedFormat: string;
  resolvedStackBb: number;
  usedFallback: boolean;
}

export type PostflopPreferredAction = 'check' | 'bet_small' | 'bet_big';

export interface PostflopFrequency {
  check: number;
  betSmall: number;
  betBig: number;
}

export interface BoardTextureProfile {
  isPaired: boolean;
  isMonotone: boolean;
  hasFlushDraw: boolean;
  isConnected: boolean;
  isDisconnected: boolean;
  isHighCardHeavy: boolean;
  wetness: 'dry' | 'neutral' | 'wet';
  labels: string[];
}

export interface MathBreakdown {
  potOdds?: number;
  equityRequired?: number;
  callAmount?: number;
  potAfterCall?: number;
  mdf?: number;
  spr?: number;
  effectiveStack?: number;
  commitmentThreshold?: number;
  isLowSpr?: boolean;
}

export interface AdvicePayload {
  tableId: string;
  handId: string;
  seat: number;
  stage?: AdviceStage;
  spotKey: string;
  heroHand: string;
  mix: StrategyMix;
  tags: string[];
  explanation: string;
  recommended?: 'raise' | 'call' | 'fold';
  randomSeed?: number;
  deviation?: number;
  stackProfile?: StackProfile;
  math?: MathBreakdown;
  postflop?: {
    bucketKey: string;
    preferredAction: PostflopPreferredAction;
    frequency: PostflopFrequency;
    frequencyText: string;
    rationale: string;
    boardTexture: BoardTextureProfile;
    alpha?: number;
    mdf?: number;
    isStandardNode?: boolean;
  };
}

// ===== Action Types =====

export interface ActionSubmitPayload {
  tableId: string;
  handId: string;
  action: PlayerActionType;
  amount?: number;
  ritVote?: 'yes' | 'no';
  runCount?: 1 | 2;
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
  visibility: RoomVisibility;
  updatedAt: string;
  /** Optional club metadata (backward-compatible extension). */
  clubId?: string;
  clubName?: string;
  isClubTable?: boolean;
}

// ===== Hand History Types =====

export interface HistoryHandPlayerSummary {
  seat: number;
  userId: string;
  name: string;
}

export interface HistoryHandSummaryCore {
  totalPot: number;
  runCount: 1 | 2;
  winners: HandWinner[];
  myNetByUser: Record<string, number>;
  flags: {
    allIn: boolean;
    runItTwice: boolean;
    showdown: boolean;
  };
}

export interface HistoryHandDetailCore {
  board: string[];
  runoutBoards: string[][];
  potLayers: PotLayer[];
  contributionsBySeat: Record<number, number>;
  actionTimeline: HandAction[];
  revealedHoles: Record<number, [string, string]>;
  payoutLedger: SeatLedgerEntry[];
}

export interface HistoryRoomSummary {
  roomId: string;
  roomCode: string;
  roomName: string;
  lastPlayedAt: string;
  totalHands: number;
}

export interface HistorySessionSummary {
  roomSessionId: string;
  roomId: string;
  openedAt: string;
  closedAt: string | null;
  handCount: number;
}

export interface HistoryHandSummary {
  id: string;
  roomId: string;
  roomSessionId: string;
  handId: string;
  handNo: number;
  endedAt: string;
  blinds: {
    sb: number;
    bb: number;
  };
  players: HistoryHandPlayerSummary[];
  summary: HistoryHandSummaryCore;
}

export interface HistoryHandDetail extends HistoryHandSummary {
  detail: HistoryHandDetailCore;
}

// ===== History GTO Analysis Types =====

export interface HistoryGTOHandRecord {
  heroCards: [string, string];
  board: string[];
  heroSeat: number;
  heroPosition: string;
  stakes: string;
  tableSize: number;
  potSize: number;
  stackSize: number;
  actions: Array<{
    seat: number;
    street: string;
    type: string;
    amount: number;
  }>;
  smallBlind?: number;
  bigBlind?: number;
  playerNames?: Record<number, string>;
}

export interface HistoryGTOSpotAnalysis {
  street: string;
  board: string[];
  pot: number;
  heroAction: string;
  heroAmount: number;
  recommended: {
    action: string;
    mix: StrategyMix;
  };
  deviationScore: number;
  alpha: number;
  mdf: number;
  equity: number;
  note: string;
}

export interface HistoryGTOAnalysis {
  overallScore: number;
  streetScores: {
    flop: number | null;
    turn: number | null;
    river: number | null;
  };
  spots: HistoryGTOSpotAnalysis[];
  computedAt: number;
  precision: 'fast' | 'deep';
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

// ===== Room Management Types =====

export type GameType = 'texas' | 'omaha';

export type RunItTwiceMode = 'always' | 'ask_players' | 'off';

export type ShowdownSpeed = 'fast' | 'normal' | 'slow';

export const SHOWDOWN_SPEED_DELAYS_MS: Record<ShowdownSpeed, number> = {
  fast: 3_000,
  normal: 6_000,
  slow: 9_000,
};

export type DoubleBoardMode = 'always' | 'bomb_pot' | 'off';

export type DeckStyle = 'four_color' | 'two_color';

export type ValuesDisplayStyle = 'big_blinds' | 'formatted' | 'none';

export type RunItTwicePlayerPref = 'yes' | 'no' | 'ask';

export type RoomVisibility = 'public' | 'private';

export interface BlindStructureLevel {
  smallBlind: number;
  bigBlind: number;
  ante: number;
  durationMinutes: number;
}

export interface RoomSettings {
  gameType: GameType;
  maxPlayers: number;
  spectatorAllowed: boolean;
  smallBlind: number;
  bigBlind: number;
  ante: number;
  blindStructure: BlindStructureLevel[] | null; // null = no blind increases
  buyInMin: number;
  buyInMax: number;
  rebuyAllowed: boolean;
  addOnAllowed: boolean;
  straddleAllowed: boolean;
  runItTwice: boolean;
  runItTwiceMode: RunItTwiceMode;         // Always / Ask Players / Off
  visibility: RoomVisibility;
  password: string | null;
  hostStartRequired: boolean;
  actionTimerSeconds: number;              // per-action countdown (e.g. 15)
  timeBankSeconds: number;                 // extra time bank per player (e.g. 60)
  timeBankRefillPerHand: number;           // seconds refilled each hand (e.g. 5)
  timeBankHandsToFill: number;             // number of played hands to fill time bank
  thinkExtensionSecondsPerUse: number;     // extra seconds added when player requests extension
  thinkExtensionQuotaPerHour: number;      // per-player max extension uses per hour
  disconnectGracePeriod: number;           // seconds to reconnect before auto-fold
  maxConsecutiveTimeouts: number;          // auto sit-out after N timeouts
  // ── New PokerNow-style settings (Host-only) ──
  useCentsValues: boolean;                 // display chip values as cents
  rabbitHunting: boolean;                  // allow players to see undealt cards
  autoStartNextHand: boolean;              // auto start the next hand
  showdownSpeed: ShowdownSpeed;            // fast(3s) / normal(6s) / slow(9s)
  dealToAwayPlayers: boolean;              // deal hands to players marked as away
  revealAllAtShowdown: boolean;            // reveal all hands when no more action possible
  autoRevealOnAllInCall: boolean;          // auto reveal involved hands when action is closed and only runout remains
  autoRevealWinningHands: boolean;         // force winners to reveal at showdown
  autoMuckLosingHands: boolean;            // default losing hands to muck
  allowShowAfterFold: boolean;             // allow folded players to voluntarily show before hand end
  allowShowCalledHandRequest: boolean;     // optional casino-style called hand request
  bombPotEnabled: boolean;                 // enable bomb pots
  bombPotFrequency: number;                // every N hands (0 = manual only)
  doubleBoardMode: DoubleBoardMode;        // always / only on bomb pot / off
  sevenTwoBounty: number;                  // 0 = off, >0 = bounty amount per player
  simulatedFeeEnabled: boolean;            // simulated rake/fee
  simulatedFeePercent: number;             // fee as % of pot (e.g. 5)
  simulatedFeeCap: number;                 // max fee per hand
  allowGuestChat: boolean;                 // allow guests to send chat messages
  autoTrimExcessBets: boolean;             // auto trim bets exceeding pot/call
  roomFundsTracking: boolean;              // track session funds and allow rejoin stack restoration
}

export const DEFAULT_ROOM_SETTINGS: RoomSettings = {
  gameType: 'texas',
  maxPlayers: 6,
  spectatorAllowed: true,
  smallBlind: 50,
  bigBlind: 100,
  ante: 0,
  blindStructure: null,
  buyInMin: 2000,
  buyInMax: 20000,
  rebuyAllowed: true,
  addOnAllowed: false,
  straddleAllowed: false,
  runItTwice: false,
  runItTwiceMode: 'off',
  visibility: 'public',
  password: null,
  hostStartRequired: false,
  actionTimerSeconds: 15,
  timeBankSeconds: 60,
  timeBankRefillPerHand: 5,
  timeBankHandsToFill: 10,
  thinkExtensionSecondsPerUse: 10,
  thinkExtensionQuotaPerHour: 3,
  disconnectGracePeriod: 30,
  maxConsecutiveTimeouts: 3,
  useCentsValues: false,
  rabbitHunting: false,
  autoStartNextHand: true,
  showdownSpeed: 'normal',
  dealToAwayPlayers: false,
  revealAllAtShowdown: true,
  autoRevealOnAllInCall: true,
  autoRevealWinningHands: true,
  autoMuckLosingHands: true,
  allowShowAfterFold: false,
  allowShowCalledHandRequest: false,
  bombPotEnabled: false,
  bombPotFrequency: 0,
  doubleBoardMode: 'off',
  sevenTwoBounty: 0,
  simulatedFeeEnabled: false,
  simulatedFeePercent: 5,
  simulatedFeeCap: 0,
  allowGuestChat: true,
  autoTrimExcessBets: true,
  roomFundsTracking: false,
};

export interface RoomOwnership {
  ownerId: string;
  ownerName: string;
  coHostIds: string[];
}

export type RoomStatus = 'WAITING' | 'PLAYING' | 'PAUSED' | 'CLOSED';

export type RoomLogEventType =
  | 'OWNER_CHANGED'
  | 'SETTINGS_CHANGED'
  | 'PLAYER_KICKED'
  | 'PLAYER_BANNED'
  | 'PLAYER_TIMED_OUT'
  | 'PLAYER_SAT_OUT'
  | 'GAME_STARTED'
  | 'GAME_PAUSED'
  | 'GAME_RESUMED'
  | 'GAME_ENDED'
  | 'CHAT_MESSAGE'
  | 'SYSTEM_MESSAGE';

export interface RoomLogEntry {
  id: string;
  timestamp: number;
  type: RoomLogEventType;
  actorId?: string;
  actorName?: string;
  targetId?: string;
  targetName?: string;
  message: string;
  payload?: Record<string, unknown>;
}

export interface TimerState {
  seat: number;
  remaining: number;        // seconds left on action timer
  timeBankRemaining: number; // seconds left in time bank
  usingTimeBank: boolean;
  startedAt: number;         // timestamp when timer started
}

export interface ThinkExtensionUsageState {
  used: number;
  quota: number;
  remaining: number;
  windowStartedAt: number;
  windowResetAt: number;
}

export interface RoomFullState {
  tableId: string;
  roomCode: string;
  roomName: string;
  settings: RoomSettings;
  ownership: RoomOwnership;
  status: RoomStatus;
  banList: string[];         // banned userIds
  timer: TimerState | null;
  thinkExtensionUsageByUser?: Record<string, ThinkExtensionUsageState>;
  log: RoomLogEntry[];
  emptySince: number | null; // timestamp when room became empty, null if occupied
}

// ===== Room Management Payloads =====

export interface UpdateSettingsPayload {
  tableId: string;
  settings: Partial<RoomSettings>;
}

export interface KickPlayerPayload {
  tableId: string;
  targetUserId: string;
  reason?: string;
  ban?: boolean;
}

export interface TransferOwnershipPayload {
  tableId: string;
  newOwnerId: string;
}

export interface SetCoHostPayload {
  tableId: string;
  userId: string;
  add: boolean; // true = add co-host, false = remove
}

export interface GameControlPayload {
  tableId: string;
  action: 'start' | 'pause' | 'resume' | 'end' | 'restart';
}

export interface JoinRoomWithPasswordPayload {
  roomCode: string;
  password?: string;
}

// Re-export socket events
export * from './socket-events.js';

// Re-export club types and events
export * from './club-types.js';
export * from './club-events.js';
