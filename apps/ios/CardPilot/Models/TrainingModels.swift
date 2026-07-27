import Foundation

// MARK: - Audit Types (mirrors audit-types.ts)

enum ActionDeviationType: String, Codable {
    case overfold = "OVERFOLD"
    case underfold = "UNDERFOLD"
    case overbluff = "OVERBLUFF"
    case underbluff = "UNDERBLUFF"
    case overcall = "OVERCALL"
    case undercall = "UNDERCALL"
    case correct = "CORRECT"
}

enum SpotType: String, Codable {
    case srp = "SRP"
    case threeBP = "3BP"
    case fourBP = "4BP"
    case limped = "LIMPED"
    case squeezePot = "SQUEEZE_POT"
}

struct GtoAuditResult: Codable, Identifiable {
    var id: String { decisionPointId }
    let decisionPointId: String
    let handId: String
    let heroUserId: String
    let gtoMix: StrategyMix
    let recommendedAction: String
    let actualAction: String
    let deviationScore: Double
    let evDiffBb: Double
    let evDiffChips: Double
    let deviationType: ActionDeviationType
    let street: String
    let spotType: SpotType
    var lineTags: [String]?
    var heroPosition: String?
    var stackDepthCategory: String?
    var equity: Double?
    var mdf: Double?
    var alpha: Double?
    let computedAt: Double
}

struct HandAuditSummary: Codable, Identifiable {
    var id: String { handId }
    let handId: String
    let handHistoryId: String
    let heroUserId: String
    let totalLeakedBb: Double
    let totalLeakedChips: Double
    let decisionCount: Int
    let worstDeviationScore: Double
    let audits: [GtoAuditResult]
    var handLineTags: [String]?
    var spotType: SpotType?
    let computedAt: Double
}

struct StreetLeakBucket: Codable {
    let leakedBb: Double
    let leakedChips: Double
    let decisions: Int
}

struct SpotLeakBucket: Codable {
    let leakedBb: Double
    let leakedChips: Double
    let decisions: Int
}

struct LineLeakBucket: Codable {
    let leakedBb: Double
    let decisions: Int
}

struct DeviationBucket: Codable {
    let count: Int
    let leakedBb: Double
}

struct LeakCategory: Codable, Identifiable {
    var id: String { label }
    let label: String
    let description: String
    let leakedBb: Double
    let rank: Int
}

struct DrillSuggestion: Codable, Identifiable {
    var id: String { title }
    let title: String
    let description: String
    var linkParams: [String: String]?
}

struct SessionLeakSummary: Codable {
    let sessionId: String
    let heroUserId: String
    let totalLeakedBb: Double
    let totalLeakedChips: Double
    let handsPlayed: Int
    let handsAudited: Int
    let leakedBbPer100: Double
    let byStreet: [String: StreetLeakBucket]
    let byDeviation: [String: DeviationBucket]
    var topLeaks: [LeakCategory]?
    var suggestedDrills: [DrillSuggestion]?
    let computedAt: Double
}

// MARK: - Preflop Trainer Types

enum ScenarioType: String, Codable {
    case rfi = "RFI"
    case facingOpen = "facing_open"
    case facing3Bet = "facing_3bet"
    case facing4Bet = "facing_4bet"
}

struct SolutionIndex: Codable {
    let format: String
    let configs: [String]
    let spots: [SpotIndexEntry]
    let solveDate: String
}

struct SpotIndexEntry: Codable {
    let file: String
    let spot: String
    let heroPosition: String
    let scenario: String
}

struct SpotSolution: Codable {
    let spot: String
    let format: String
    let heroPosition: String
    var villainPosition: String?
    let scenario: String
    let potSize: Double
    let actions: [String]
    let grid: [String: [String: Double]]
    let summary: SpotSummary
    let metadata: SpotMetadata
}

struct SpotSummary: Codable {
    let totalCombos: Double
    let rangeSize: Double
    let actionFrequencies: [String: Double]
}

struct SpotMetadata: Codable {
    var iterations: Int?
    var exploitability: Double?
    var solveDate: String?
    var solver: String?
}
