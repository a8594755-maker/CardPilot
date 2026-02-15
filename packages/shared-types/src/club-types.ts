// ===== Club Domain Types =====

// ── Roles & Status ──

export type ClubRole = 'owner' | 'admin' | 'host' | 'mod' | 'member';

export type ClubMemberStatus = 'active' | 'pending' | 'banned' | 'left';

export type ClubVisibility = 'private' | 'unlisted';

export type ClubTableStatus = 'open' | 'paused' | 'closed';

export type RunItTwiceChooser = 'underdog' | 'all-in-initiator' | 'host';

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
  autoDealDelaySec: number;
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
  straddleAllowed: boolean;
  bombPotEnabled: boolean;
  rabbitHuntEnabled: boolean;
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
    autoDealDelaySec: 3,
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
    straddleAllowed: false,
    bombPotEnabled: false,
    rabbitHuntEnabled: false,
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
  owner: 5,
  admin: 4,
  host: 3,
  mod: 2,
  member: 1,
};

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
      return hasClubPermission(actorRole, 'admin');
    case 'manage_tables':
      return hasClubPermission(actorRole, 'admin');
    case 'approve_joins':
      return hasClubPermission(actorRole, 'mod');
    case 'ban':
      return hasClubPermission(actorRole, 'mod');
    case 'create_table':
      return hasClubPermission(actorRole, 'host');
    case 'close_table':
    case 'pause_table':
      return hasClubPermission(actorRole, 'host');
    case 'moderate_chat':
      return hasClubPermission(actorRole, 'mod');
    case 'create_invite':
      return hasClubPermission(actorRole, 'mod');
    case 'view_audit_log':
      return hasClubPermission(actorRole, 'mod');
    default:
      return false;
  }
}
