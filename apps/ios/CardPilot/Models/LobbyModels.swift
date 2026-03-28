import Foundation

// MARK: - Lobby Room Summary

struct LobbyRoomSummary: Codable, Identifiable {
    var id: String { tableId }

    let tableId: String
    let roomCode: String
    let roomName: String
    let smallBlind: Double
    let bigBlind: Double
    let maxPlayers: Int
    let playerCount: Int
    let status: String
    let visibility: RoomVisibility
    let updatedAt: String
    var clubId: String?
    var clubName: String?
    var isClubTable: Bool?
}

// MARK: - Room Settings

struct RoomSettings: Codable {
    let gameType: GameType
    let maxPlayers: Int
    let spectatorAllowed: Bool
    let smallBlind: Double
    let bigBlind: Double
    let ante: Double
    var blindStructure: [BlindStructureLevel]?
    let buyInMin: Double
    let buyInMax: Double
    let rebuyAllowed: Bool
    let addOnAllowed: Bool
    let straddleAllowed: Bool
    let runItTwice: Bool
    let runItTwiceMode: RunItTwiceMode
    let visibility: RoomVisibility
    var password: String?
    let hostStartRequired: Bool
    let actionTimerSeconds: Int
    let timeBankSeconds: Int
    let timeBankRefillPerHand: Int
    let timeBankHandsToFill: Int
    let thinkExtensionSecondsPerUse: Int
    let thinkExtensionQuotaPerHour: Int
    let disconnectGracePeriod: Int
    let maxConsecutiveTimeouts: Int
    let useCentsValues: Bool
    let rabbitHunting: Bool
    let autoStartNextHand: Bool
    let minPlayersToStart: Int
    let showdownSpeed: ShowdownSpeed
    let dealToAwayPlayers: Bool
    let revealAllAtShowdown: Bool
    let autoRevealOnAllInCall: Bool
    let autoRevealWinningHands: Bool
    let autoMuckLosingHands: Bool
    let allowShowAfterFold: Bool
    let allowShowCalledHandRequest: Bool
    let bombPotEnabled: Bool
    let bombPotTriggerMode: BombPotTriggerMode
    let bombPotFrequency: Int
    let bombPotProbability: Double
    let bombPotAnteMode: BombPotAnteMode
    let bombPotAnteValue: Double
    let doubleBoardMode: DoubleBoardMode
    let sevenTwoBounty: Double
    let simulatedFeeEnabled: Bool
    let simulatedFeePercent: Double
    let simulatedFeeCap: Double
    let allowGuestChat: Bool
    let autoTrimExcessBets: Bool
    let roomFundsTracking: Bool
    var botSeats: [BotSeatConfig]?
    var botBuyIn: Double?
    var selfPlayTurbo: Bool?
}

struct BlindStructureLevel: Codable {
    let smallBlind: Double
    let bigBlind: Double
    let ante: Double
    let durationMinutes: Int
}

struct BotSeatConfig: Codable {
    let seat: Int
    let profile: String
    var displayName: String?
    var modelVersion: String?
}

// MARK: - Room Ownership

struct RoomOwnership: Codable {
    let ownerId: String
    let ownerName: String
    let coHostIds: [String]
}

// MARK: - Room Full State

struct RoomFullState: Codable {
    let tableId: String
    let roomCode: String
    let roomName: String
    var hasStartedHand: Bool?
    var isClubTable: Bool?
    var clubId: String?
    let settings: RoomSettings
    let ownership: RoomOwnership
    let status: RoomStatus
    let banList: [String]
    let timer: TimerState?
    var emptySince: Double?
}
