import Foundation

// MARK: - Socket Event Names
// Mirrors SOCKET_EVENT_NAMES from packages/shared-types/src/socket-events.ts

enum SocketEvent {
    // MARK: Client → Server
    enum Client {
        static let requestLobby = "request_lobby"
        static let createRoom = "create_room"
        static let joinRoomCode = "join_room_code"
        static let joinTable = "join_table"
        static let sitDown = "sit_down"
        static let seatRequest = "seat_request"
        static let approveSeat = "approve_seat"
        static let rejectSeat = "reject_seat"
        static let standUp = "stand_up"
        static let startHand = "start_hand"
        static let actionSubmit = "action_submit"
        static let showHand = "show_hand"
        static let muckHand = "muck_hand"
        static let submitRunPreference = "submit_run_preference"
        static let runCountSubmit = "run_count_submit"
        static let requestThinkExtension = "request_think_extension"
        static let depositRequest = "deposit_request"
        static let approveDeposit = "approve_deposit"
        static let rejectDeposit = "reject_deposit"
        static let requestSessionStats = "request_session_stats"
        static let requestTableSnapshot = "request_table_snapshot"
        static let leaveTable = "leave_table"
        static let requestRoomState = "request_room_state"
        static let updateSettings = "update_settings"
        static let kickPlayer = "kick_player"
        static let transferOwnership = "transfer_ownership"
        static let setCohost = "set_cohost"
        static let gameControl = "game_control"
        static let closeRoom = "close_room"
        static let requestHistoryRooms = "request_history_rooms"
        static let requestHistorySessions = "request_history_sessions"
        static let requestHistoryHands = "request_history_hands"
        static let requestHistoryHandDetail = "request_history_hand_detail"
        static let requestRoomHands = "request_room_hands"
        static let historyGtoAnalyze = "history_gto_analyze"
        static let showHandPost = "show_hand_post"
        static let claimSevenTwoBounty = "claim_seven_two_bounty"
        static let fastBattleWarmup = "fast_battle_warmup"
        static let fastBattleStart = "fast_battle_start"
        static let fastBattleEnd = "fast_battle_end"
    }

    // MARK: Server → Client
    enum Server {
        static let connected = "connected"
        static let lobbySnapshot = "lobby_snapshot"
        static let roomCreated = "room_created"
        static let roomJoined = "room_joined"
        static let tableSnapshot = "table_snapshot"
        static let presence = "presence"
        static let holeCards = "hole_cards"
        static let handStarted = "hand_started"
        static let actionApplied = "action_applied"
        static let streetAdvanced = "street_advanced"
        static let boardReveal = "board_reveal"
        static let runTwiceReveal = "run_twice_reveal"
        static let allinLocked = "allin_locked"
        static let allInPrompt = "all_in_prompt"
        static let runCountConfirmed = "run_count_confirmed"
        static let runCountChosen = "run_count_chosen"
        static let revealHoleCards = "reveal_hole_cards"
        static let revealBoardCard = "reveal_board_card"
        static let showdownResults = "showdown_results"
        static let handEnded = "hand_ended"
        static let handAborted = "hand_aborted"
        static let advicePayload = "advice_payload"
        static let adviceDeviation = "advice_deviation"
        static let errorEvent = "error_event"
        static let leftTable = "left_table"
        static let roomStateUpdate = "room_state_update"
        static let timerUpdate = "timer_update"
        static let roomLog = "room_log"
        static let seatRequestPending = "seat_request_pending"
        static let seatRequestSent = "seat_request_sent"
        static let seatApproved = "seat_approved"
        static let seatRejected = "seat_rejected"
        static let depositRequestPending = "deposit_request_pending"
        static let sessionStats = "session_stats"
        static let settingsUpdated = "settings_updated"
        static let thinkExtensionResult = "think_extension_result"
        static let kicked = "kicked"
        static let roomClosed = "room_closed"
        static let stoodUp = "stood_up"
        static let systemMessage = "system_message"
        static let historyRooms = "history_rooms"
        static let historySessions = "history_sessions"
        static let historyHands = "history_hands"
        static let roomHands = "room_hands"
        static let historyHandDetail = "history_hand_detail"
        static let historyGtoResult = "history_gto_result"
        static let playerDisconnected = "player_disconnected"
        static let playerReconnected = "player_reconnected"
        static let playerAutoSitout = "player_auto_sitout"
        static let sevenTwoBountyClaimed = "seven_two_bounty_claimed"
        static let postHandReveal = "post_hand_reveal"
    }
}

// MARK: - Server Event Payload Types (for decoding)

struct ConnectedPayload: Codable {
    let socketId: String
    let userId: String
    var displayName: String?
    let supabaseEnabled: Bool
}

struct LobbySnapshotPayload: Codable {
    let rooms: [LobbyRoomSummary]
}

struct RoomCreatedPayload: Codable {
    let tableId: String
    let roomCode: String
    let roomName: String
}

struct RoomJoinedPayload: Codable {
    let tableId: String
    let roomCode: String
    let roomName: String
}

struct HoleCardsPayload: Codable {
    let handId: String
    let cards: [String]
    let seat: Int
}

struct HandStartedPayload: Codable {
    let handId: String
}

struct ActionAppliedPayload: Codable {
    let seat: Int
    let action: String
    let amount: Double
    let pot: Double
    var auto: Bool?
}

struct StreetAdvancedPayload: Codable {
    let street: Street
    let board: [String]
}

struct ShowdownResultsPayload: Codable {
    let handId: String
    let runCount: Int
    let perRunWinners: [RunoutPayout]
    let totalPayouts: [String: Double]
}

struct HandEndedPayload: Codable {
    var handId: String?
    var finalState: TableState?
    var board: [String]?
    var runoutBoards: [[String]]?
    var runoutPayouts: [RunoutPayout]?
    var pot: Double?
    var winners: [HandWinner]?
    var settlement: SettlementResult?
}

struct ErrorPayload: Codable {
    let code: String?
    let message: String
}

struct LeftTablePayload: Codable {
    let tableId: String
}

struct KickedPayload: Codable {
    let reason: String
    let banned: Bool
}

struct SessionStatsPayload: Codable {
    let tableId: String
    let entries: [SessionStatsEntry]
}

struct SessionStatsEntry: Codable {
    let seat: Int?
    let userId: String
    let name: String
    let totalBuyIn: Double
    let currentStack: Double
    let net: Double
    let handsPlayed: Int
}

struct SeatRequestPendingPayload: Codable {
    let orderId: String
    let userId: String
    let userName: String
    let seat: Int
    let buyIn: Double
}

struct HistoryRoomsPayload: Codable {
    let rooms: [HistoryRoomSummary]
}

struct HistorySessionsPayload: Codable {
    let roomId: String
    let sessions: [HistorySessionSummary]
}

struct HistoryHandsPayload: Codable {
    let roomSessionId: String
    let hands: [HistoryHandSummary]
    let hasMore: Bool
    var nextCursor: String?
}

struct HistoryHandDetailPayload: Codable {
    let handHistoryId: String
    let hand: HistoryHandDetail?
}

struct PostHandRevealPayload: Codable {
    let tableId: String
    let seat: Int
    let cards: [String]
}
