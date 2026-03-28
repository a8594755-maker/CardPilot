import Foundation

// MARK: - Local Hand Record
// Mirrors hand-history.ts HandRecord

struct LocalHandRecord: Codable, Identifiable {
    let id: String
    let createdAt: Double
    let expiresAt: Double
    let gameType: String  // "NLH" | "PLO"
    let stakes: String
    let tableSize: Int
    let position: String
    let heroCards: [String]
    var startingHandBucket: String?
    let board: [String]
    var runoutBoards: [[String]]?
    let actions: [LocalHandAction]
    let potSize: Double
    let stackSize: Double
    let result: Double
    let tags: [String]
    var roomCode: String?
    var roomName: String?
    var tableId: String?
    var handId: String?
    var endedAt: String?
    var heroSeat: Int?
    var heroName: String?
    var smallBlind: Double?
    var bigBlind: Double?
    var playersCount: Int?
    var didWinAnyRun: Bool?
    var showdownHands: [Int: [String]]?
    var playerNames: [Int: String]?
    var buttonSeat: Int?
    var isBombPotHand: Bool?
    var isDoubleBoardHand: Bool?

    // Custom init for creating from PokerTableViewModel
    init(
        gameType: String, stakes: String, tableSize: Int, position: String,
        heroCards: [String], board: [String], runoutBoards: [[String]]? = nil,
        actions: [LocalHandAction], potSize: Double, stackSize: Double, result: Double,
        tags: [String], roomCode: String? = nil, roomName: String? = nil,
        tableId: String? = nil, handId: String? = nil, endedAt: String? = nil,
        heroSeat: Int? = nil, heroName: String? = nil,
        smallBlind: Double? = nil, bigBlind: Double? = nil, playersCount: Int? = nil,
        didWinAnyRun: Bool? = nil, showdownHands: [Int: [String]]? = nil,
        playerNames: [Int: String]? = nil, buttonSeat: Int? = nil,
        isBombPotHand: Bool? = nil, isDoubleBoardHand: Bool? = nil
    ) {
        let now = Date.timeIntervalSinceReferenceDate
        self.id = "h_\(Int(now))_\(String(Int.random(in: 100000...999999)))"
        self.createdAt = now
        self.expiresAt = now + HandHistoryManager.retentionSeconds
        self.gameType = gameType
        self.stakes = stakes
        self.tableSize = tableSize
        self.position = position
        self.heroCards = heroCards
        self.startingHandBucket = HandHistoryManager.classifyStartingHand(heroCards, gameType: gameType)
        self.board = board
        self.runoutBoards = runoutBoards
        self.actions = actions
        self.potSize = potSize
        self.stackSize = stackSize
        self.result = result
        self.tags = tags
        self.roomCode = roomCode
        self.roomName = roomName
        self.tableId = tableId
        self.handId = handId
        self.endedAt = endedAt
        self.heroSeat = heroSeat
        self.heroName = heroName
        self.smallBlind = smallBlind
        self.bigBlind = bigBlind
        self.playersCount = playersCount
        self.didWinAnyRun = didWinAnyRun
        self.showdownHands = showdownHands
        self.playerNames = playerNames
        self.buttonSeat = buttonSeat
        self.isBombPotHand = isBombPotHand
        self.isDoubleBoardHand = isDoubleBoardHand
    }
}

struct LocalHandAction: Codable {
    let seat: Int
    let street: String
    let type: String
    let amount: Double
}

// MARK: - Local Room Summary

struct LocalRoomSummary: Identifiable {
    var id: String { roomCode }
    let roomCode: String
    let roomName: String
    let stakes: String
    let lastPlayedAt: Double
    let handsCount: Int
    let netResult: Double
    let smallBlind: Double
    let bigBlind: Double
}

// MARK: - Hand History Manager
// Mirrors hand-history.ts with UserDefaults instead of localStorage

enum HandHistoryManager {
    static let storageKey = "cardpilot_hand_history"
    static let retentionSeconds: TimeInterval = 30 * 24 * 60 * 60  // 30 days
    static let maxRecords = 500

    // MARK: - CRUD

    static func saveHand(_ record: LocalHandRecord) {
        var all = pruneExpired(readAll())
        all.append(record)
        if all.count > maxRecords {
            all = Array(all.suffix(maxRecords))
        }
        writeAll(all)
    }

    static func getHands(position: String? = nil, tags: [String]? = nil) -> [LocalHandRecord] {
        var records = pruneExpired(readAll())
        if let position { records = records.filter { $0.position == position } }
        if let tags, !tags.isEmpty {
            records = records.filter { r in tags.contains { r.tags.contains($0) } }
        }
        return records.sorted { $0.createdAt > $1.createdAt }
    }

    static func getHand(id: String) -> LocalHandRecord? {
        pruneExpired(readAll()).first { $0.id == id }
    }

    static func getHandsByRoom() -> (rooms: [LocalRoomSummary], handsByRoom: [String: [LocalHandRecord]]) {
        let all = pruneExpired(readAll()).sorted { $0.createdAt > $1.createdAt }
        var byRoom: [String: [LocalHandRecord]] = [:]

        for h in all {
            let code = h.roomCode ?? "_local"
            byRoom[code, default: []].append(h)
        }

        let rooms: [LocalRoomSummary] = byRoom.map { code, hands in
            let last = hands[0]
            let net = hands.reduce(0.0) { $0 + $1.result }
            return LocalRoomSummary(
                roomCode: code,
                roomName: last.roomName ?? (code == "_local" ? "Local" : code),
                stakes: last.stakes,
                lastPlayedAt: last.createdAt,
                handsCount: hands.count,
                netResult: net,
                smallBlind: last.smallBlind ?? 0,
                bigBlind: last.bigBlind ?? 0
            )
        }.sorted { $0.lastPlayedAt > $1.lastPlayedAt }

        return (rooms, byRoom)
    }

    static func clearAll() {
        UserDefaults.standard.removeObject(forKey: storageKey)
    }

    // MARK: - Auto-Tag (mirrors autoTag from hand-history.ts)

    static func autoTag(_ actions: [LocalHandAction]) -> [String] {
        var tags: [String] = []
        let preflopRaises = actions.filter { $0.street == "PREFLOP" && $0.type == "raise" }
        if preflopRaises.count >= 2 { tags.append("3bet_pot") }
        if preflopRaises.count >= 3 { tags.append("4bet_pot") }
        if preflopRaises.count <= 1 { tags.append("SRP") }
        if actions.contains(where: { $0.type == "all_in" }) { tags.append("all_in") }
        return tags
    }

    // MARK: - Starting Hand Classification

    static func classifyStartingHand(_ cards: [String], gameType: String) -> String {
        guard cards.count >= 2 else { return "unknown" }
        let rankOrder = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"]
        func rankValue(_ r: String) -> Int { rankOrder.firstIndex(of: r) ?? -1 }

        if gameType == "PLO" || cards.count >= 4 {
            let ranks = cards.compactMap { String($0.prefix(1)) }
            let sorted = ranks.sorted { rankValue($0) > rankValue($1) }
            return "\(sorted[0])\(sorted[1])xx"
        }

        let ra = String(cards[0].prefix(1))
        let sa = String(cards[0].suffix(1))
        let rb = String(cards[1].prefix(1))
        let sb = String(cards[1].suffix(1))

        let highFirst = rankValue(ra) >= rankValue(rb)
        let high = highFirst ? ra : rb
        let low = highFirst ? rb : ra

        if high == low { return "\(high)\(low)" }
        let suited = sa == sb
        if high == "A" && low == "K" { return suited ? "AKs" : "AKo" }
        if high == "A" { return suited ? "Axs" : "Axo" }
        return suited ? "\(high)\(low)s" : "\(high)\(low)o"
    }

    // MARK: - Private Persistence

    private static func readAll() -> [LocalHandRecord] {
        guard let data = UserDefaults.standard.data(forKey: storageKey),
              let records = try? JSONDecoder().decode([LocalHandRecord].self, from: data)
        else { return [] }
        return records
    }

    private static func writeAll(_ records: [LocalHandRecord]) {
        guard let data = try? JSONEncoder().encode(records) else { return }
        UserDefaults.standard.set(data, forKey: storageKey)
    }

    private static func pruneExpired(_ records: [LocalHandRecord]) -> [LocalHandRecord] {
        let now = Date.timeIntervalSinceReferenceDate
        return records.filter { $0.expiresAt > now }
    }
}
