import Foundation

// MARK: - Club Types (mirrors club-types.ts)

enum ClubRole: String, Codable {
    case owner, admin, member
}

enum ClubMemberStatus: String, Codable {
    case active, pending, banned, left
}

struct Club: Codable, Identifiable {
    let id: String
    let code: String
    let name: String
    var description: String?
    let ownerUserId: String
    var visibility: String?
    var requireApprovalToJoin: Bool?
    var badgeColor: String?
    var logoUrl: String?
    var createdAt: String?
}

struct ClubMember: Codable, Identifiable {
    var id: String { "\(clubId)_\(userId)" }
    let clubId: String
    let userId: String
    let role: ClubRole
    let status: ClubMemberStatus
    var nicknameInClub: String?
    var balance: Double?
    var displayName: String?
    var lastSeenAt: String?
}

struct ClubDetail: Codable {
    let club: Club
    var myMembership: ClubMember?
    let memberCount: Int
    var pendingCount: Int?
    var tableCount: Int?
    var defaultRuleset: ClubRuleset?
}

struct ClubListItem: Codable, Identifiable {
    let id: String
    let code: String
    let name: String
    var description: String?
    var badgeColor: String?
    let memberCount: Int
    var tableCount: Int?
    var myRole: ClubRole?
    var myStatus: ClubMemberStatus?
}

struct ClubTable: Codable, Identifiable {
    let id: String
    let clubId: String
    let name: String
    let status: String
    var createdBy: String?
    var handsPlayed: Int?
    var playerCount: Int?
    var maxPlayers: Int?
    var stakes: String?
    var roomCode: String?
}

struct ClubRuleset: Codable, Identifiable {
    let id: String
    let clubId: String
    let name: String
    var isDefault: Bool?
}

struct ClubInvite: Codable, Identifiable {
    let id: String
    let clubId: String
    let inviteCode: String
    var createdBy: String?
    var expiresAt: String?
    var maxUses: Int?
    var usesCount: Int?
    var revoked: Bool?
}

struct ClubWalletTransaction: Codable, Identifiable {
    let id: String
    let clubId: String
    let userId: String
    let type: String
    let amount: Double
    var note: String?
    let createdAt: String
}

struct ClubLeaderboardEntry: Codable, Identifiable {
    var id: String { "\(clubId)_\(userId)" }
    let rank: Int
    let clubId: String
    let userId: String
    let displayName: String
    var metric: String?
    var metricValue: Double?
    var balance: Double?
    var hands: Int?
    var net: Double?
}

struct ClubAuditLogEntry: Codable, Identifiable {
    let id: String
    let clubId: String
    var actorUserId: String?
    let actionType: String
    var actorDisplayName: String?
    let createdAt: String
}

// MARK: - Club Socket Payloads

struct ClubCreatedPayload: Codable { let club: Club }
struct ClubListPayload: Codable { let clubs: [ClubListItem] }

struct ClubDetailPayload: Codable {
    let detail: ClubDetail
    let members: [ClubMember]
    var invites: [ClubInvite]?
    var rulesets: [ClubRuleset]?
    var tables: [ClubTable]?
    var pendingMembers: [ClubMember]?
    var auditLog: [ClubAuditLogEntry]?
}

struct ClubJoinResultPayload: Codable {
    let clubId: String
    let status: String  // "joined" | "pending" | "error"
    var message: String?
}

struct ClubTableCreatedPayload: Codable {
    let clubId: String
    let table: ClubTable
}

struct ClubTableJoinedPayload: Codable {
    let tableId: String
    let clubId: String
    var roomName: String?
}

struct ClubErrorPayload: Codable {
    let code: String
    let message: String
}

struct ClubLeaderboardPayload: Codable {
    let clubId: String
    var timeRange: String?
    var metric: String?
    let entries: [ClubLeaderboardEntry]
    var myRank: Int?
}

struct ClubWalletBalancePayload: Codable {
    let balance: ClubWalletBalance
}

struct ClubWalletBalance: Codable {
    let clubId: String
    let userId: String
    let balance: Double
}

struct ClubWalletLedgerPayload: Codable {
    let clubId: String
    let transactions: [ClubWalletTransaction]
}
