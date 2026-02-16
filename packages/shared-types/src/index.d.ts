export type Street = 'PREFLOP' | 'FLOP' | 'TURN' | 'RIVER' | 'SHOWDOWN';
export type PlayerActionType = 'fold' | 'check' | 'call' | 'raise' | 'all_in';
export type BlindActionType = 'post_sb' | 'post_bb';
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
export type TransactionType = 'DEPOSIT' | 'WITHDRAW';
export type TransactionStatus = 'COMING_SOON' | 'LOCKED' | 'PENDING' | 'COMPLETED' | 'FAILED';
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
    type: PlayerActionType;
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
    winnersByRun: Array<{
        run: 1 | 2;
        board: string[];
        winners: HandWinner[];
    }>;
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
    pendingDeposits?: Array<{
        orderId: string;
        seat: number;
        userId: string;
        userName: string;
        amount: number;
    }>;
    /** Showdown-revealed hole cards by seat (always public once shown) */
    shownCards: Record<number, [string, string]>;
    /** Backward-compatible alias for shownCards */
    shownHands: Record<number, [string, string]>;
    /** Publicly revealed hole cards by seat */
    revealedHoles?: Record<number, [string, string]>;
    /** Seats that explicitly mucked at showdown */
    muckedSeats?: number[];
    /** Showdown reveal state used by clients to render SHOW/MUCK actions */
    showdownPhase?: "none" | "decision";
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
    spotKey: string;
    heroHand: string;
    mix: StrategyMix;
    tags: string[];
    explanation: string;
    recommended?: 'raise' | 'call' | 'fold';
    randomSeed?: number;
    deviation?: number;
}
export interface ActionSubmitPayload {
    tableId: string;
    handId: string;
    action: PlayerActionType;
    amount?: number;
    runCount?: 1 | 2;
}
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
}
export interface SpotInfo {
    position: Position;
    vsPosition?: Position;
    effectiveStack: number;
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
    deviation: number;
    timestamp: Date;
}
export type GameType = 'texas' | 'omaha';
export type RunItTwiceMode = 'always' | 'ask_players' | 'off';
export type ShowdownSpeed = 'fast' | 'normal' | 'slow';
export declare const SHOWDOWN_SPEED_DELAYS_MS: Record<ShowdownSpeed, number>;
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
    blindStructure: BlindStructureLevel[] | null;
    buyInMin: number;
    buyInMax: number;
    rebuyAllowed: boolean;
    addOnAllowed: boolean;
    straddleAllowed: boolean;
    runItTwice: boolean;
    runItTwiceMode: RunItTwiceMode;
    visibility: RoomVisibility;
    password: string | null;
    hostStartRequired: boolean;
    actionTimerSeconds: number;
    timeBankSeconds: number;
    timeBankRefillPerHand: number;
    timeBankHandsToFill: number;
    thinkExtensionSecondsPerUse: number;
    thinkExtensionQuotaPerHour: number;
    disconnectGracePeriod: number;
    maxConsecutiveTimeouts: number;
    useCentsValues: boolean;
    rabbitHunting: boolean;
    autoStartNextHand: boolean;
    showdownSpeed: ShowdownSpeed;
    dealToAwayPlayers: boolean;
    revealAllAtShowdown: boolean;
    autoRevealOnAllInCall: boolean;
    autoRevealWinningHands: boolean;
    autoMuckLosingHands: boolean;
    allowShowAfterFold: boolean;
    allowShowCalledHandRequest: boolean;
    bombPotEnabled: boolean;
    bombPotFrequency: number;
    doubleBoardMode: DoubleBoardMode;
    sevenTwoBounty: number;
    simulatedFeeEnabled: boolean;
    simulatedFeePercent: number;
    simulatedFeeCap: number;
    allowGuestChat: boolean;
    autoTrimExcessBets: boolean;
    roomFundsTracking: boolean;
}
export declare const DEFAULT_ROOM_SETTINGS: RoomSettings;
export interface RoomOwnership {
    ownerId: string;
    ownerName: string;
    coHostIds: string[];
}
export type RoomStatus = 'WAITING' | 'PLAYING' | 'PAUSED' | 'CLOSED';
export type RoomLogEventType = 'OWNER_CHANGED' | 'SETTINGS_CHANGED' | 'PLAYER_KICKED' | 'PLAYER_BANNED' | 'PLAYER_TIMED_OUT' | 'PLAYER_SAT_OUT' | 'GAME_STARTED' | 'GAME_PAUSED' | 'GAME_RESUMED' | 'GAME_ENDED' | 'CHAT_MESSAGE' | 'SYSTEM_MESSAGE';
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
    remaining: number;
    timeBankRemaining: number;
    usingTimeBank: boolean;
    startedAt: number;
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
    banList: string[];
    timer: TimerState | null;
    thinkExtensionUsageByUser?: Record<string, ThinkExtensionUsageState>;
    log: RoomLogEntry[];
    emptySince: number | null;
}
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
    add: boolean;
}
export interface GameControlPayload {
    tableId: string;
    action: 'start' | 'pause' | 'resume' | 'end' | 'restart';
}
export interface JoinRoomWithPasswordPayload {
    roomCode: string;
    password?: string;
}
export * from './socket-events.js';
export * from './club-types.js';
export * from './club-events.js';
export * from './audit-types.js';
