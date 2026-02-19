// ===== Club Domain Types =====

// ── Roles & Status ──

export type ClubRole = 'owner' | 'admin' | 'member';

export type ClubMemberStatus = 'active' | 'pending' | 'banned' | 'left';

export type ClubVisibility = 'private' | 'unlisted';

export type ClubTableStatus = 'open' | 'paused' | 'closed';

export type RunItTwiceChooser = 'underdog' | 'all-in-initiator';
export type ClubGameType = 'texas' | 'omaha';

// ── Club Rules ("Club Charter") ──

export interface ClubRulesStakes {
  smallBlind: number;
  bigBlind: number;
}

export interface ClubRulesBuyIn {
  minBuyIn: number;
  maxBuyIn: number;
  defaultBuyIn: number;
}

export interface ClubRulesTime {
  actionTimeSec: number;
  timeBankSec: number;
  disconnectGraceSec: number;
}

export interface ClubRulesDealing {
  autoDealEnabled: boolean;
  minPlayersToStart: number;
  autoDealDelaySec: number;
  autoStartNextHand: boolean;
  allowManualDeal: boolean;
  preventDealMidHand: boolean; // must be true
}

export interface ClubRulesRunIt {
  allowRunItTwice: boolean;
  runItTwiceWhoChooses: RunItTwiceChooser;
  promptTimeoutSec: number;
}

export interface ClubRulesTableControls {
  canPauseMidHand: boolean;        // must be false
  pauseAppliesAfterHand: boolean;  // must be true
  standUpAppliesAfterHand: boolean;
}

export interface ClubRulesModeration {
  chatEnabled: boolean;
  profanityFilter: boolean;
  allowSpectators: boolean;
}

export interface ClubRulesEconomy {
  rakeEnabled: boolean;     // default false — play-money only
  serviceFeeEnabled: boolean; // default false
}

export interface ClubRulesExtras {
  gameType: ClubGameType;
  straddleAllowed: boolean;
  bombPotEnabled: boolean;
  rabbitHuntEnabled: boolean;
  sevenTwoBounty: number;
  rebuyPolicy: 'hand_boundary' | 'anytime';
}

export interface ClubRules {
  stakes: ClubRulesStakes;
  maxSeats: number; // 2–9
  buyIn: ClubRulesBuyIn;
  time: ClubRulesTime;
  dealing: ClubRulesDealing;
  runit: ClubRulesRunIt;
  tableControls: ClubRulesTableControls;
  moderation: ClubRulesModeration;
  economy: ClubRulesEconomy;
  extras: ClubRulesExtras;
}

export const DEFAULT_CLUB_RULES: ClubRules = {
  stakes: { smallBlind: 1, bigBlind: 2 },
  maxSeats: 6,
  buyIn: { minBuyIn: 40, maxBuyIn: 200, defaultBuyIn: 100 },
  time: { actionTimeSec: 15, timeBankSec: 60, disconnectGraceSec: 30 },
  dealing: {
    autoDealEnabled: true,
    minPlayersToStart: 2,
    autoDealDelaySec: 3,
    autoStartNextHand: true,
    allowManualDeal: true,
    preventDealMidHand: true,
  },
  runit: {
    allowRunItTwice: false,
    runItTwiceWhoChooses: 'all-in-initiator',
    promptTimeoutSec: 15,
  },
  tableControls: {
    canPauseMidHand: false,
    pauseAppliesAfterHand: true,
    standUpAppliesAfterHand: true,
  },
  moderation: {
    chatEnabled: true,
    profanityFilter: false,
    allowSpectators: true,
  },
  economy: {
    rakeEnabled: false,
    serviceFeeEnabled: false,
  },
  extras: {
    gameType: 'texas',
    straddleAllowed: false,
    bombPotEnabled: false,
    rabbitHuntEnabled: false,
    sevenTwoBounty: 0,
    rebuyPolicy: 'hand_boundary',
  },
};

// ── Entity Interfaces (match DB schema) ──

export interface Club {
  id: string;
  code: string;
  name: string;
  description: string;
  ownerUserId: string;
  visibility: ClubVisibility;
  defaultRulesetId: string | null;
  isArchived: boolean;
  requireApprovalToJoin: boolean;
  badgeColor: string | null;
  logoUrl: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ClubMember {
  clubId: string;
  userId: string;
  role: ClubRole;
  status: ClubMemberStatus;
  nicknameInClub: string | null;
  balance: number; // virtual credits balance
  createdAt: string;
  lastSeenAt: string;
  displayName?: string; // populated from player_profiles join
}

export interface ClubInvite {
  id: string;
  clubId: string;
  inviteCode: string;
  createdBy: string;
  expiresAt: string | null;
  maxUses: number | null;
  usesCount: number;
  revoked: boolean;
  createdAt: string;
}

export interface ClubBan {
  id: string;
  clubId: string;
  userId: string;
  reason: string;
  bannedBy: string;
  createdAt: string;
  expiresAt: string | null;
}

export interface ClubRuleset {
  id: string;
  clubId: string;
  name: string;
  rulesJson: ClubRules;
  createdBy: string;
  isDefault: boolean;
  createdAt: string;
}

export interface ClubTable {
  id: string;
  clubId: string;
  roomCode: string | null;
  name: string;
  rulesetId: string | null;
  status: ClubTableStatus;
  createdBy: string;
  createdAt: string;
  // Joined from live room state (populated server-side)
  playerCount?: number;
  maxPlayers?: number;
  stakes?: string;
  minPlayersToStart?: number;
}

export type ClubWalletTxType =
  | "deposit"
  | "admin_grant"
  | "admin_deduct"
  | "buy_in"
  | "cash_out"
  | "transfer_in"
  | "transfer_out"
  | "adjustment";

export interface ClubWalletTransaction {
  id: string;
  clubId: string;
  userId: string;
  type: ClubWalletTxType;
  amount: number;
  currency: string;
  refType: string | null;
  refId: string | null;
  createdAt: string;
  createdBy: string | null;
  note: string | null;
  metaJson: Record<string, unknown>;
  idempotencyKey?: string | null;
}

export interface ClubWalletBalance {
  clubId: string;
  userId: string;
  currency: string;
  balance: number;
}

export type ClubLeaderboardMetric = "net" | "hands" | "buyin" | "deposits";

export type ClubLeaderboardRange = "day" | "week" | "month" | "all";

export interface ClubLeaderboardEntry {
  rank: number;
  clubId: string;
  userId: string;
  displayName?: string;
  metric: ClubLeaderboardMetric;
  metricValue: number;
  balance: number;
  hands: number;
  buyIn: number;
  cashOut: number;
  deposits: number;
  net: number;
}

export interface ClubAuditLogEntry {
  id: number;
  clubId: string;
  actorUserId: string | null;
  actionType: string;
  payloadJson: Record<string, unknown>;
  createdAt: string;
  actorDisplayName?: string; // populated via join
}

// ── Club Detail (aggregated for UI) ──

export interface ClubDetail {
  club: Club;
  myMembership: ClubMember | null;
  memberCount: number;
  pendingCount: number;
  tableCount: number;
  defaultRuleset: ClubRuleset | null;
}

export interface ClubListItem {
  id: string;
  code: string;
  name: string;
  description: string;
  badgeColor: string | null;
  memberCount: number;
  tableCount: number;
  myRole: ClubRole;
  myStatus: ClubMemberStatus;
}

// ── Permission Helpers ──

const ROLE_RANK: Record<ClubRole, number> = {
  owner: 3,
  admin: 2,
  member: 1,
};

export function normalizeClubRole(role: string | null | undefined): ClubRole {
  if (role === "owner" || role === "admin" || role === "member") {
    return role;
  }
  return "member";
}

export function hasClubPermission(
  actorRole: ClubRole,
  requiredRole: ClubRole,
): boolean {
  return ROLE_RANK[actorRole] >= ROLE_RANK[requiredRole];
}

/** Permission matrix check for specific operations */
export function canPerformClubAction(
  actorRole: ClubRole,
  action:
    | 'manage_members'
    | 'manage_tables'
    | 'manage_rulesets'
    | 'approve_joins'
    | 'ban'
    | 'create_table'
    | 'close_table'
    | 'pause_table'
    | 'moderate_chat'
    | 'create_invite'
    | 'view_audit_log',
): boolean {
  switch (action) {
    case 'manage_members':
    case 'manage_rulesets':
    case 'manage_tables':
    case 'approve_joins':
    case 'ban':
    case 'create_table':
    case 'pause_table':
    case 'create_invite':
    case 'view_audit_log':
      return hasClubPermission(actorRole, 'admin');
    case 'close_table':
      return hasClubPermission(actorRole, 'owner');
    case 'moderate_chat':
      return hasClubPermission(actorRole, 'admin');
    default:
      return false;
  }
}
