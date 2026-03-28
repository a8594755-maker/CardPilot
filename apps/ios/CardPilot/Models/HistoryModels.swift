import Foundation

// MARK: - History Room Summary

struct HistoryRoomSummary: Codable, Identifiable {
    var id: String { roomId }

    let roomId: String
    let roomCode: String
    let roomName: String
    let lastPlayedAt: String
    let totalHands: Int
}

// MARK: - History Session Summary

struct HistorySessionSummary: Codable, Identifiable {
    var id: String { roomSessionId }

    let roomSessionId: String
    let roomId: String
    let openedAt: String
    let closedAt: String?
    let handCount: Int
}

// MARK: - History Hand Player Summary

struct HistoryHandPlayerSummary: Codable {
    let seat: Int
    let userId: String
    let name: String
}

// MARK: - History Hand Flags

struct HistoryHandFlags: Codable {
    let allIn: Bool
    let runItTwice: Bool
    let showdown: Bool
    var bombPot: Bool?
    var doubleBoard: Bool?
}

// MARK: - History Hand Summary Core

struct HistoryHandSummaryCore: Codable {
    let totalPot: Double
    let runCount: Int
    let winners: [HandWinner]
    let myNetByUser: [String: Double]
    var netByPosition: [String: Double]?
    var startingHandBucketsByUser: [String: String]?
    var gameType: GameType?
    let flags: HistoryHandFlags
}

// MARK: - History Hand Detail Core

struct HistoryHandDetailCore: Codable {
    let board: [String]
    let runoutBoards: [[String]]
    var doubleBoardPayouts: [RunoutPayout]?
    let potLayers: [PotLayer]
    let contributionsBySeat: [String: Double]
    let actionTimeline: [HandAction]
    let revealedHoles: [String: [String]]
    var privateHoleCardsByUser: [String: [String]]?
    let payoutLedger: [SeatLedgerEntry]
}

// MARK: - History Hand Summary

struct HistoryHandSummary: Codable, Identifiable {
    let id: String
    let roomId: String
    let roomSessionId: String
    let handId: String
    let handNo: Int
    let endedAt: String
    let blinds: HistoryBlinds
    let players: [HistoryHandPlayerSummary]
    let summary: HistoryHandSummaryCore
}

struct HistoryBlinds: Codable {
    let sb: Double
    let bb: Double
}

// MARK: - History Hand Detail

struct HistoryHandDetail: Codable {
    let id: String
    let roomId: String
    let roomSessionId: String
    let handId: String
    let handNo: Int
    let endedAt: String
    let blinds: HistoryBlinds
    let players: [HistoryHandPlayerSummary]
    let summary: HistoryHandSummaryCore
    let detail: HistoryHandDetailCore
}

// MARK: - GTO Analysis

struct HistoryGTOSpotAnalysis: Codable {
    let street: String
    let board: [String]
    let pot: Double
    var toCall: Double?
    var effectiveStack: Double?
    let heroAction: String
    let heroAmount: Double
    var actionTimelineIdx: Int?
    var decisionIndex: Int?
    let recommended: GTORecommendation
    let deviationScore: Double
    var evLossBb: Double?
    let alpha: Double
    let mdf: Double
    let equity: Double
    let note: String
}

struct GTORecommendation: Codable {
    let action: String
    let mix: StrategyMix
}

struct HistoryGTOAnalysis: Codable {
    let overallScore: Double
    let streetScores: GTOStreetScores
    let spots: [HistoryGTOSpotAnalysis]
    let computedAt: Double
    let precision: String
}

struct GTOStreetScores: Codable {
    let flop: Double?
    let turn: Double?
    let river: Double?
}
