import Foundation

// MARK: - Fast Battle Types (mirrors fast-battle-types.ts)

enum FastBattlePhase: String {
    case setup, playing, switching, report
}

struct FastBattleConfig {
    let targetHandCount: Int
    let bigBlind: Double
    var botModelVersion: String?
}

struct FastBattleHandResultEntry: Identifiable {
    let id: String
    let handId: String
    let handNumber: Int
    let result: Double
    let heroPosition: String
    let holeCards: [String]
    var board: [String]?
    let wentToShowdown: Bool
    let cumulativeResult: Double
    let timestamp: Double
}

struct FastBattleBehaviorStats: Codable {
    let handsPlayed: Int
    let handsWon: Int
    let vpip: Double
    let pfr: Double
    let threeBet: Double
    let foldTo3Bet: Double
    let cbetFlop: Double
    let cbetTurn: Double
    let aggressionFactor: Double
    let wtsd: Double
    let wsd: Double
    let netChips: Double
    let netBb: Double
    let decisionsPerHour: Double
}

struct FastBattleProblemHand: Codable, Identifiable {
    var id: Int { rank }
    let rank: Int
    let handId: String
    let heroPosition: String
    let holeCards: [String]
    let board: [String]
    let audits: [GtoAuditResult]
    let totalLeakedBb: Double
}

struct FastBattleHeroAction: Codable {
    let street: String
    let action: String
    let amount: Double
    let pot: Double
    let toCall: Double
}

struct FastBattleHandRecord: Codable, Identifiable {
    var id: String { handId }
    let handId: String
    let tableId: String
    let heroSeat: Int
    let heroPosition: String
    let holeCards: [String]
    let allHoleCards: [String: [String]]
    let board: [String]
    let heroActions: [FastBattleHeroAction]
    let result: Double
    let totalPot: Double
    let wentToShowdown: Bool
    let startedAt: Double
    let endedAt: Double
}

struct FastBattleReport: Codable {
    let sessionId: String
    let stats: FastBattleBehaviorStats
    var sessionLeak: SessionLeakSummary?
    let problemHands: [FastBattleProblemHand]
    var recommendations: [DrillSuggestion]?
    let handRecords: [FastBattleHandRecord]
    let handCount: Int
    let durationMs: Double
}

// MARK: - Socket Payloads

struct FBSessionStartedPayload: Codable {
    let sessionId: String
    let targetHandCount: Int
    let bigBlind: Double
}

struct FBTableAssignedPayload: Codable {
    let tableId: String
    let roomCode: String
    let seat: Int
    let buyIn: Double
    let handNumber: Int
    let totalHands: Int
}

struct FBHandResultPayload: Codable {
    let handId: String
    let handNumber: Int
    let result: Double
    let heroPosition: String
    let holeCards: [String]
    var board: [String]?
    let wentToShowdown: Bool
    let cumulativeResult: Double
}

struct FBProgressPayload: Codable {
    let handsPlayed: Int
    let targetHandCount: Int
    let cumulativeResult: Double
    let decisionsPerHour: Double
}

struct FBSessionEndedPayload: Codable {
    let sessionId: String
    let report: FastBattleReport
}

struct FBErrorPayload: Codable {
    let message: String
    let code: String
}
