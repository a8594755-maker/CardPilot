import type { Street, PlayerActionType, TableState, RunoutPayout, SettlementResult, AdvicePayload as AdvicePayloadFromIndex, LobbyRoomSummary as LobbyRoomSummaryFromIndex, HistoryRoomSummary, HistorySessionSummary, HistoryHandSummary, HistoryHandDetail } from './index.js';
export type { AdvicePayloadFromIndex as AdvicePayload, LobbyRoomSummaryFromIndex as LobbyRoomSummary };
export interface JoinTablePayload {
    roomId: string;
    seatIndex?: number;
}
export interface SitDownPayload {
    seatIndex: number;
    buyIn: number;
    name?: string;
}
export interface PlayerActionPayload {
    handId: string;
    action: 'fold' | 'check' | 'call' | 'raise' | 'all_in';
    amount?: number;
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
    communityCards: string[];
    pot: number;
    currentBet: number;
    actorSeat: number | null;
    timeRemaining: number;
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
    holeCards: [string, string];
    position: 'SB' | 'BB' | 'UTG' | 'MP' | 'HJ' | 'CO' | 'BTN';
}
export interface ActionAppliedPayload {
    handId: string;
    seatIndex: number;
    action: string;
    amount?: number;
    potAfter: number;
    nextActor?: number;
    streetEnds?: boolean;
}
export interface StreetAdvancedPayload {
    handId: string;
    newStreet: 'flop' | 'turn' | 'river' | 'showdown';
    communityCards: string[];
    pot: number;
    nextActor: number;
}
export interface StrategyMix {
    fold: number;
    call: number;
    raise: number;
}
export interface AdviceExplanation {
    tags: string[];
    shortText: string;
    details: string;
}
export interface AdviceContext {
    position: string;
    vsPosition?: string;
    effectiveStack: number;
    potOdds: number;
    toCall: number;
}
export interface WinnerInfo {
    seatIndex: number;
    winAmount: number;
    holeCards?: [string, string];
    handRank: string;
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
export interface LobbySnapshotPayload {
    rooms: LobbyRoomSummaryFromIndex[];
}
export interface ErrorPayload {
    code: string;
    message: string;
}
export declare const SOCKET_EVENT_NAMES: {
    clientToServer: readonly ["request_lobby", "create_room", "join_room_code", "join_table", "sit_down", "seat_request", "approve_seat", "reject_seat", "stand_up", "start_hand", "action_submit", "show_hand", "muck_hand", "submit_run_preference", "run_count_submit", "request_think_extension", "deposit_request", "approve_deposit", "reject_deposit", "request_session_stats", "request_table_snapshot", "leave_table", "request_room_state", "update_settings", "kick_player", "transfer_ownership", "set_cohost", "game_control", "close_room", "request_history_rooms", "request_history_sessions", "request_history_hands", "request_history_hand_detail", "history_gto_analyze"];
    serverToClient: readonly ["connected", "lobby_snapshot", "room_created", "room_joined", "table_snapshot", "presence", "hole_cards", "hand_started", "action_applied", "street_advanced", "board_reveal", "run_twice_reveal", "allin_locked", "all_in_prompt", "run_count_confirmed", "run_count_chosen", "reveal_hole_cards", "reveal_board_card", "showdown_results", "hand_ended", "hand_aborted", "advice_payload", "advice_deviation", "error_event", "left_table", "room_state_update", "timer_update", "room_log", "seat_request_pending", "seat_request_sent", "seat_approved", "seat_rejected", "deposit_request_pending", "session_stats", "settings_updated", "think_extension_result", "kicked", "room_closed", "stood_up", "system_message", "history_rooms", "history_sessions", "history_hands", "history_hand_detail", "history_gto_result", "hand_audit_complete", "session_leak_update"];
};
export interface ClientToServerEvents {
    request_lobby: () => void;
    create_room: (payload: {
        roomName?: string;
        maxPlayers?: number;
        smallBlind?: number;
        bigBlind?: number;
        isPublic?: boolean;
        buyInMin?: number;
        buyInMax?: number;
        visibility?: 'public' | 'private';
    }) => void;
    join_room_code: (payload: {
        roomCode: string;
        password?: string;
    }) => void;
    join_table: (payload: {
        tableId: string;
    }) => void;
    sit_down: (payload: {
        tableId: string;
        seat: number;
        buyIn: number;
        name?: string;
    }) => void;
    seat_request: (payload: {
        tableId: string;
        seat: number;
        buyIn: number;
        name?: string;
    }) => void;
    approve_seat: (payload: {
        tableId: string;
        orderId: string;
    }) => void;
    reject_seat: (payload: {
        tableId: string;
        orderId: string;
    }) => void;
    stand_up: (payload: {
        tableId: string;
        seat: number;
    }) => void;
    start_hand: (payload: {
        tableId: string;
    }) => void;
    action_submit: (payload: {
        tableId: string;
        handId: string;
        action: PlayerActionType;
        amount?: number;
    }) => void;
    show_hand: (payload: {
        tableId: string;
        handId: string;
        seat: number;
        scope: "table";
    }) => void;
    muck_hand: (payload: {
        tableId: string;
        handId: string;
        seat: number;
    }) => void;
    submit_run_preference: (payload: {
        tableId: string;
        handId: string;
        runCount: 1 | 2 | 3;
    }) => void;
    run_count_submit: (payload: {
        tableId: string;
        handId: string;
        runCount: 1 | 2 | 3;
    }) => void;
    request_think_extension: (payload: {
        tableId: string;
    }) => void;
    deposit_request: (payload: {
        tableId: string;
        amount: number;
    }) => void;
    approve_deposit: (payload: {
        tableId: string;
        orderId: string;
    }) => void;
    reject_deposit: (payload: {
        tableId: string;
        orderId: string;
    }) => void;
    request_session_stats: (payload: {
        tableId: string;
    }) => void;
    request_table_snapshot: (payload: {
        tableId: string;
    }) => void;
    leave_table: (payload: {
        tableId: string;
    }) => void;
    request_room_state: (payload: {
        tableId: string;
    }) => void;
    update_settings: (payload: {
        tableId: string;
        settings: Record<string, unknown>;
    }) => void;
    kick_player: (payload: {
        tableId: string;
        targetUserId: string;
        reason?: string;
        ban?: boolean;
    }) => void;
    transfer_ownership: (payload: {
        tableId: string;
        newOwnerId: string;
    }) => void;
    set_cohost: (payload: {
        tableId: string;
        userId: string;
        add: boolean;
    }) => void;
    game_control: (payload: {
        tableId: string;
        action: 'start' | 'pause' | 'resume' | 'end' | 'restart';
    }) => void;
    close_room: (payload: {
        tableId: string;
    }) => void;
    request_history_rooms: (payload?: {
        limit?: number;
    }) => void;
    request_history_sessions: (payload: {
        roomId: string;
        limit?: number;
    }) => void;
    request_history_hands: (payload: {
        roomSessionId: string;
        limit?: number;
        beforeEndedAt?: string;
    }) => void;
    request_history_hand_detail: (payload: {
        handHistoryId: string;
    }) => void;
}
export interface ServerToClientEvents {
    connected: (data: {
        socketId: string;
        userId: string;
        displayName?: string;
        supabaseEnabled: boolean;
    }) => void;
    lobby_snapshot: (payload: {
        rooms: LobbyRoomSummaryFromIndex[];
    }) => void;
    room_created: (payload: {
        tableId: string;
        roomCode: string;
        roomName: string;
    }) => void;
    room_joined: (payload: {
        tableId: string;
        roomCode: string;
        roomName: string;
    }) => void;
    table_snapshot: (payload: TableState) => void;
    presence: (payload: {
        players: Array<{
            seat: number;
            userId: string;
            name: string;
        }>;
    }) => void;
    hole_cards: (payload: {
        handId: string;
        cards: string[];
        seat: number;
    }) => void;
    hand_started: (payload: {
        handId: string;
    }) => void;
    action_applied: (payload: {
        seat: number;
        action: string;
        amount: number;
        pot: number;
        auto?: boolean;
    }) => void;
    street_advanced: (payload: {
        street: Street;
        board: string[];
    }) => void;
    board_reveal: (payload: {
        handId: string;
        street: Street;
        newCards: string[];
        board: string[];
        equities: Array<{
            seat: number;
            winRate: number;
            tieRate: number;
        }>;
    }) => void;
    run_twice_reveal: (payload: {
        handId: string | null;
        street: string;
        run1: {
            newCards: string[];
            board: string[];
        };
        run2: {
            newCards: string[];
            board: string[];
        };
    }) => void;
    allin_locked: (payload: {
        handId: string;
        eligiblePlayers: Array<{
            seat: number;
            name: string;
        }>;
        maxRunCountAllowed: 3;
        submittedPlayerIds?: number[];
    }) => void;
    all_in_prompt: (payload: {
        actorSeat: number;
        winRate: number;
        recommendedRunCount: 1 | 2 | 3;
        defaultRunCount: 1 | 2 | 3;
        allowedRunCounts: Array<1 | 2 | 3>;
        reason: string;
    }) => void;
    run_count_confirmed: (payload: {
        handId: string;
        runCount: 1 | 2 | 3;
    }) => void;
    run_count_chosen: (payload: {
        runCount: 1 | 2 | 3;
        seat: number;
    }) => void;
    reveal_hole_cards: (payload: {
        handId: string;
        revealed: Record<number, [string, string]>;
    }) => void;
    reveal_board_card: (payload: {
        handId: string;
        runIndex: 1 | 2 | 3;
        card: string;
        boardSizeNow: number;
        board: string[];
        street: Street;
    }) => void;
    showdown_results: (payload: {
        handId: string;
        runCount: 1 | 2 | 3;
        perRunWinners: Array<{
            run: 1 | 2 | 3;
            board: string[];
            winners: Array<{
                seat: number;
                amount: number;
                handName?: string;
            }>;
        }>;
        totalPayouts: Record<number, number>;
    }) => void;
    hand_ended: (payload: {
        handId?: string;
        finalState?: TableState;
        board?: string[];
        runoutBoards?: string[][];
        runoutPayouts?: RunoutPayout[];
        players?: TableState["players"];
        pot?: number;
        winners?: Array<{
            seat: number;
            amount: number;
            handName?: string;
        }>;
        settlement?: SettlementResult;
    }) => void;
    hand_aborted: (payload: {
        reason: string;
    }) => void;
    advice_payload: (payload: AdvicePayloadFromIndex) => void;
    advice_deviation: (payload: AdvicePayloadFromIndex & {
        deviation: number;
        playerAction: string;
    }) => void;
    error_event: (payload: {
        message: string;
    }) => void;
    left_table: (payload: {
        tableId: string;
    }) => void;
    room_state_update: (payload: unknown) => void;
    timer_update: (payload: unknown) => void;
    room_log: (payload: unknown) => void;
    seat_request_pending: (payload: {
        orderId: string;
        userId: string;
        userName: string;
        seat: number;
        buyIn: number;
    }) => void;
    seat_request_sent: (payload: {
        orderId: string;
        seat: number;
    }) => void;
    seat_approved: (payload: {
        seat: number;
        buyIn: number;
    }) => void;
    seat_rejected: (payload: {
        seat: number;
        reason: string;
    }) => void;
    deposit_request_pending: (payload: {
        orderId: string;
        userId: string;
        userName: string;
        seat: number;
        amount: number;
    }) => void;
    session_stats: (payload: {
        tableId: string;
        entries: Array<{
            seat: number | null;
            userId: string;
            name: string;
            totalBuyIn: number;
            currentStack: number;
            net: number;
            handsPlayed: number;
        }>;
    }) => void;
    settings_updated: (payload: {
        applied: Record<string, unknown>;
        deferred: Record<string, unknown>;
    }) => void;
    think_extension_result: (payload: {
        addedSeconds: number;
        remainingUses: number;
    }) => void;
    kicked: (payload: {
        reason: string;
        banned: boolean;
    }) => void;
    room_closed: (payload?: {
        tableId?: string;
        reason?: string;
    }) => void;
    stood_up: (payload: {
        seat: number;
        reason: string;
    }) => void;
    system_message: (payload: {
        message: string;
    }) => void;
    history_rooms: (payload: {
        rooms: HistoryRoomSummary[];
    }) => void;
    history_sessions: (payload: {
        roomId: string;
        sessions: HistorySessionSummary[];
    }) => void;
    history_hands: (payload: {
        roomSessionId: string;
        hands: HistoryHandSummary[];
        hasMore: boolean;
        nextCursor?: string;
    }) => void;
    history_hand_detail: (payload: {
        handHistoryId: string;
        hand: HistoryHandDetail | null;
    }) => void;
}
