import Foundation

// MARK: - Enums (mirroring shared-types/index.ts)

enum Street: String, Codable {
    case preflop = "PREFLOP"
    case flop = "FLOP"
    case turn = "TURN"
    case river = "RIVER"
    case showdown = "SHOWDOWN"
    case runItTwicePrompt = "RUN_IT_TWICE_PROMPT"
}

enum PlayerActionType: String, Codable {
    case fold, check, call, raise, all_in, vote_rit
}

enum HandActionType: String, Codable {
    case fold, check, call, raise, all_in, vote_rit
    case post_sb, post_bb, post_dead_blind
    case ante
}

enum Position: String, Codable {
    case sb = "SB"
    case bb = "BB"
    case utg = "UTG"
    case mp = "MP"
    case hj = "HJ"
    case co = "CO"
    case btn = "BTN"
}

enum PlayerStatus: String, Codable {
    case active, sitting_out
}

enum GameType: String, Codable {
    case texas, omaha
}

enum RoomVisibility: String, Codable {
    case `public`, `private`
}

enum RoomStatus: String, Codable {
    case waiting = "WAITING"
    case playing = "PLAYING"
    case paused = "PAUSED"
    case closed = "CLOSED"
}

enum TableMode: String, Codable {
    case coach = "COACH"
    case review = "REVIEW"
    case casual = "CASUAL"
}

enum RunItTwiceMode: String, Codable {
    case always, ask_players, off
}

enum ShowdownSpeed: String, Codable {
    case turbo, fast, normal, slow
}

enum DoubleBoardMode: String, Codable {
    case always, bomb_pot, off
}

enum BombPotTriggerMode: String, Codable {
    case frequency, manual, probability
}

enum BombPotAnteMode: String, Codable {
    case bb_multiplier, fixed
}

// MARK: - Core Game Types

struct LegalActions: Codable {
    let canFold: Bool
    let canCheck: Bool
    let canCall: Bool
    let callAmount: Double
    let canRaise: Bool
    let minRaise: Double
    let maxRaise: Double
}

struct TablePlayer: Codable, Identifiable {
    var id: Int { seat }

    let seat: Int
    let userId: String
    let name: String
    let stack: Double
    let inHand: Bool
    let folded: Bool
    let allIn: Bool
    let streetCommitted: Double
    let status: PlayerStatus
    let isNewPlayer: Bool
    var isBot: Bool?
    var modelVersion: String?
}

struct HandAction: Codable {
    let seat: Int
    let street: Street
    let type: HandActionType
    let amount: Double
    let at: Double
}

struct HandWinner: Codable {
    let seat: Int
    let amount: Double
    var handName: String?
}

struct PlayerEquity: Codable {
    let seat: Int
    let winRate: Double
    let tieRate: Double
}

struct PotLayer: Codable {
    let label: String
    let amount: Double
    let eligibleSeats: [Int]
}

struct SeatLedgerEntry: Codable {
    let seat: Int
    let playerName: String
    let startStack: Double
    let invested: Double
    let won: Double
    let endStack: Double
    let net: Double
}

struct RunoutPayout: Codable {
    let run: Int
    let board: [String]
    let winners: [HandWinner]
}

// MARK: - All-In Prompt

struct AllInPrompt: Codable {
    let actorSeat: Int
    let winRate: Double
    let recommendedRunCount: Int
    let defaultRunCount: Int
    let allowedRunCounts: [Int]
    let reason: String
    var promptMode: String?
    var voteStep: String?
    var requestedBySeat: Int?
}

// MARK: - Seven-Two Bounty

struct SevenTwoBountyInfo: Codable {
    let bountyPerPlayer: Double
    let winnerSeat: Int
    let winnerCards: [String]
    let payingSeats: [Int]
    let totalBounty: Double
    let bountyBySeat: [String: Double]  // JSON encodes int keys as strings
}

// MARK: - Settlement

struct SettlementResult: Codable {
    let handId: String
    let totalPot: Double
    let rake: Double
    let collectedFee: Double
    let totalPaid: Double
    let runCount: Int
    let boards: [[String]]
    let potLayers: [PotLayer]
    let winnersByRun: [RunoutPayout]
    let payoutsBySeat: [String: Double]
    let ledger: [SeatLedgerEntry]
    let contributions: [String: Double]
    let showdown: Bool
    let buttonSeat: Int
    let timestamp: Double
    var sevenTwoBounty: SevenTwoBountyInfo?
    var doubleBoardPayouts: [RunoutPayout]?
}

// MARK: - Pending Rebuy

struct PendingRebuy: Codable {
    let orderId: String
    let seat: Int
    let userId: String
    let userName: String
    let amount: Double
}

// MARK: - TableState (the main game state)

struct TableState: Codable {
    let tableId: String
    let stateVersion: Int
    let smallBlind: Double
    let bigBlind: Double
    var ante: Double?
    let buttonSeat: Int
    let street: Street
    let board: [String]
    let pot: Double
    let currentBet: Double
    let minRaiseTo: Double
    let lastFullRaiseSize: Double
    let lastFullBet: Double
    let actorSeat: Int?
    let handId: String?
    let players: [TablePlayer]
    let actions: [HandAction]
    let legalActions: LegalActions?
    let mode: TableMode
    var gameType: GameType?
    var holeCardCount: Int?
    var isBombPotHand: Bool?
    var bombPotQueued: Bool?
    var isDoubleBoardHand: Bool?
    var winners: [HandWinner]?
    let positions: [String: String]  // JSON int keys → String
    var allInPrompt: AllInPrompt?
    var runoutBoards: [[String]]?
    var runoutPayouts: [RunoutPayout]?
    var pendingStandUp: [Int]?
    var pendingPause: Bool?
    var pendingRebuys: [PendingRebuy]?
    var shownCards: [String: [String]]?
    var shownHands: [String: [String]]?
    var revealedHoles: [String: [String]]?
    var muckedSeats: [Int]?
    var showdownPhase: String?
    var ritVotes: [String: Bool?]?
    var runItTwiceEnabled: Bool?
    var nextBlindLevel: NextBlindLevel?
}

struct NextBlindLevel: Codable {
    let smallBlind: Double
    let bigBlind: Double
    let ante: Double
}

// MARK: - Board Reveal Event

struct BoardRevealEvent: Codable {
    let handId: String
    let street: Street
    let newCards: [String]
    let board: [String]
    let equities: [PlayerEquity]
    var hints: [SeatHint]?
}

struct SeatHint: Codable {
    let seat: Int
    let label: String
}

// MARK: - GTO / Advice Types

struct StrategyMix: Codable {
    let raise: Double
    let call: Double
    let fold: Double
}

struct StackProfile: Codable {
    let effectiveStackBb: Double
    let requestedBucket: String
    let resolvedFormat: String
    let resolvedStackBb: Double
    let usedFallback: Bool
}

struct MathBreakdown: Codable {
    var potOdds: Double?
    var equityRequired: Double?
    var callAmount: Double?
    var potAfterCall: Double?
    var mdf: Double?
    var spr: Double?
    var effectiveStack: Double?
    var commitmentThreshold: Double?
    var isLowSpr: Bool?
}

struct BoardTextureProfile: Codable {
    let isPaired: Bool
    let isMonotone: Bool
    let hasFlushDraw: Bool
    let isConnected: Bool
    let isDisconnected: Bool
    let isHighCardHeavy: Bool
    let wetness: String
    let labels: [String]
}

struct PostflopFrequency: Codable {
    let check: Double
    let betSmall: Double
    let betBig: Double
}

struct PostflopAdvice: Codable {
    let bucketKey: String
    let preferredAction: String
    let frequency: PostflopFrequency
    let frequencyText: String
    let rationale: String
    let boardTexture: BoardTextureProfile
    var alpha: Double?
    var mdf: Double?
    var isStandardNode: Bool?
}

struct AdvicePayload: Codable {
    let tableId: String
    let handId: String
    let seat: Int
    var stage: String?
    let spotKey: String
    let heroHand: String
    let mix: StrategyMix
    let tags: [String]
    let explanation: String
    var recommended: String?
    var randomSeed: Double?
    var deviation: Double?
    var stackProfile: StackProfile?
    var math: MathBreakdown?
    var postflop: PostflopAdvice?
}

// MARK: - Timer State

struct TimerState: Codable {
    let seat: Int
    let remaining: Double
    let timeBankRemaining: Double
    let usingTimeBank: Bool
    let startedAt: Double
}
