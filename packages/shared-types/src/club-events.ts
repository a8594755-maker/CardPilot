// ===== Club Socket Events =====

import type {
  Club,
  ClubDetail,
  ClubListItem,
  ClubMember,
  ClubInvite,
  ClubRuleset,
  ClubTable,
  ClubTableConfig,
  ClubAuditLogEntry,
  ClubRules,
  ClubRole,
  ClubVisibility,
  ClubWalletTransaction,
  ClubWalletBalance,
  ClubLeaderboardEntry,
  ClubLeaderboardMetric,
  ClubLeaderboardRange,
} from './club-types.js';

// ── Client → Server Payloads ──

export interface ClubCreatePayload {
  name: string;
  description?: string;
  visibility?: ClubVisibility;
  requireApprovalToJoin?: boolean;
  badgeColor?: string;
}

export interface ClubUpdatePayload {
  clubId: string;
  name?: string;
  description?: string;
  visibility?: ClubVisibility;
  requireApprovalToJoin?: boolean;
  badgeColor?: string;
  logoUrl?: string | null;
}

export interface ClubJoinRequestPayload {
  clubCode: string;
  inviteCode?: string;
}

export interface ClubJoinDecisionPayload {
  clubId: string;
  userId: string;
  approve: boolean;
}

export interface ClubInviteCreatePayload {
  clubId: string;
  maxUses?: number;
  expiresInHours?: number;
}

export interface ClubInviteRevokePayload {
  clubId: string;
  inviteId: string;
}

export interface ClubMemberUpdateRolePayload {
  clubId: string;
  userId: string;
  newRole: ClubRole;
}

export interface ClubMemberKickPayload {
  clubId: string;
  userId: string;
}

export interface ClubMemberBanPayload {
  clubId: string;
  userId: string;
  reason?: string;
  expiresInHours?: number;
}

export interface ClubMemberUnbanPayload {
  clubId: string;
  userId: string;
}

export interface ClubRulesetCreatePayload {
  clubId: string;
  name: string;
  rules: ClubRules;
  isDefault?: boolean;
}

export interface ClubRulesetUpdatePayload {
  clubId: string;
  rulesetId: string;
  name?: string;
  rules?: Partial<ClubRules>;
}

export interface ClubRulesetSetDefaultPayload {
  clubId: string;
  rulesetId: string;
}

export interface ClubTableCreatePayload {
  clubId: string;
  name: string;
  config: ClubTableConfig;
  templateRulesetId?: string;
}

export interface ClubTableUpdatePayload {
  clubId: string;
  tableId: string;
  name?: string;
  config?: Partial<ClubTableConfig>;
}

export interface ClubTableClosePayload {
  clubId: string;
  tableId: string;
}

export interface ClubTablePausePayload {
  clubId: string;
  tableId: string;
}

export interface ClubWalletBalanceGetPayload {
  clubId: string;
  userId?: string;
  currency?: string;
}

export interface ClubWalletLedgerListPayload {
  clubId: string;
  userId?: string;
  currency?: string;
  limit?: number;
  offset?: number;
}

export interface ClubWalletAdminGrantPayload {
  clubId: string;
  userId: string;
  amount: number;
  currency?: string;
  note?: string;
  idempotencyKey?: string;
}

export interface ClubWalletAdminAdjustPayload {
  clubId: string;
  userId: string;
  amount: number; // signed delta
  currency?: string;
  note?: string;
  idempotencyKey?: string;
}

export interface ClubLeaderboardGetPayload {
  clubId: string;
  timeRange?: ClubLeaderboardRange;
  metric?: ClubLeaderboardMetric;
  limit?: number;
}

// ── Server → Client Payloads ──

export interface ClubCreatedPayload {
  club: Club;
}

export interface ClubUpdatedPayload {
  club: Club;
}

export interface ClubDetailPayload {
  detail: ClubDetail;
  members: ClubMember[];
  invites: ClubInvite[];
  rulesets: ClubRuleset[];
  tables: ClubTable[];
  pendingMembers: ClubMember[];
  auditLog: ClubAuditLogEntry[];
}

export interface ClubListPayload {
  clubs: ClubListItem[];
}

export interface ClubJoinResultPayload {
  clubId: string;
  status: 'joined' | 'pending' | 'error';
  message: string;
}

export interface ClubMemberUpdatePayload {
  clubId: string;
  member: ClubMember;
}

export interface ClubTableCreatedPayload {
  clubId: string;
  table: ClubTable;
}

export interface ClubTableJoinPayload {
  clubId: string;
  tableId: string;
}

export interface ClubTableJoinedPayload {
  tableId: string;
  clubId: string;
  roomName: string;
}

export interface ClubErrorPayload {
  code: string;
  message: string;
}

export interface ClubWalletBalancePayload {
  balance: ClubWalletBalance;
}

export interface ClubWalletLedgerPayload {
  clubId: string;
  userId: string;
  currency: string;
  limit: number;
  offset: number;
  transactions: ClubWalletTransaction[];
}

export interface ClubLeaderboardPayload {
  clubId: string;
  timeRange: ClubLeaderboardRange;
  metric: ClubLeaderboardMetric;
  entries: ClubLeaderboardEntry[];
  myRank: number | null;
}

// ── Batch Operation Payloads ──

export interface ClubBulkApprovePayload {
  clubId: string;
  userIds: string[];
}

export interface ClubBulkGrantCreditsPayload {
  clubId: string;
  userIds: string[];
  amount: number;
  note?: string;
}

export interface ClubBulkRoleChangePayload {
  clubId: string;
  userIds: string[];
  newRole: ClubRole;
}

export interface ClubBulkKickPayload {
  clubId: string;
  userIds: string[];
}

export interface ClubBulkResultPayload {
  clubId: string;
  operation: string;
  succeeded: number;
  failed: number;
  errors: string[];
}

// ── Event Maps ──

export interface ClubClientToServerEvents {
  club_create: (payload: ClubCreatePayload) => void;
  club_update: (payload: ClubUpdatePayload) => void;
  club_join_request: (payload: ClubJoinRequestPayload) => void;
  club_join_approve: (payload: ClubJoinDecisionPayload) => void;
  club_join_reject: (payload: ClubJoinDecisionPayload) => void;
  club_invite_create: (payload: ClubInviteCreatePayload) => void;
  club_invite_revoke: (payload: ClubInviteRevokePayload) => void;
  club_member_update_role: (payload: ClubMemberUpdateRolePayload) => void;
  club_member_kick: (payload: ClubMemberKickPayload) => void;
  club_member_ban: (payload: ClubMemberBanPayload) => void;
  club_member_unban: (payload: ClubMemberUnbanPayload) => void;
  club_list_my_clubs: () => void;
  club_get_detail: (payload: { clubId: string }) => void;
  club_table_create: (payload: ClubTableCreatePayload) => void;
  club_table_update: (payload: ClubTableUpdatePayload) => void;
  club_table_list: (payload: { clubId: string }) => void;
  club_table_close: (payload: ClubTableClosePayload) => void;
  club_table_pause: (payload: ClubTablePausePayload) => void;
  club_table_join: (payload: ClubTableJoinPayload) => void;
  club_ruleset_create: (payload: ClubRulesetCreatePayload) => void;
  club_ruleset_update: (payload: ClubRulesetUpdatePayload) => void;
  club_ruleset_set_default: (payload: ClubRulesetSetDefaultPayload) => void;
  club_wallet_balance_get: (payload: ClubWalletBalanceGetPayload) => void;
  club_wallet_transactions_list: (payload: ClubWalletLedgerListPayload) => void;
  club_wallet_admin_deposit: (payload: ClubWalletAdminGrantPayload) => void;
  club_wallet_admin_adjust: (payload: ClubWalletAdminAdjustPayload) => void;
  club_leaderboard_get: (payload: ClubLeaderboardGetPayload) => void;
  club_bulk_approve: (payload: ClubBulkApprovePayload) => void;
  club_bulk_grant_credits: (payload: ClubBulkGrantCreditsPayload) => void;
  club_bulk_role_change: (payload: ClubBulkRoleChangePayload) => void;
  club_bulk_kick: (payload: ClubBulkKickPayload) => void;
}

export interface ClubServerToClientEvents {
  club_created: (payload: ClubCreatedPayload) => void;
  club_updated: (payload: ClubUpdatedPayload) => void;
  club_list: (payload: ClubListPayload) => void;
  club_detail: (payload: ClubDetailPayload) => void;
  club_join_result: (payload: ClubJoinResultPayload) => void;
  club_member_update: (payload: ClubMemberUpdatePayload) => void;
  club_table_created: (payload: ClubTableCreatedPayload) => void;
  club_table_updated: (payload: { clubId: string; table: ClubTable }) => void;
  club_table_joined: (payload: ClubTableJoinedPayload) => void;
  club_error: (payload: ClubErrorPayload) => void;
  club_wallet_balance: (payload: ClubWalletBalancePayload) => void;
  club_wallet_transactions: (payload: ClubWalletLedgerPayload) => void;
  club_leaderboard: (payload: ClubLeaderboardPayload) => void;
  club_bulk_result: (payload: ClubBulkResultPayload) => void;
}
