// ===== Club Socket Events =====

import type {
  Club,
  ClubDetail,
  ClubListItem,
  ClubMember,
  ClubInvite,
  ClubRuleset,
  ClubTable,
  ClubAuditLogEntry,
  ClubRules,
  ClubRole,
  ClubVisibility,
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
  rulesetId?: string;
}

export interface ClubTableClosePayload {
  clubId: string;
  tableId: string;
}

export interface ClubTablePausePayload {
  clubId: string;
  tableId: string;
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
  roomCode: string;
}

export interface ClubErrorPayload {
  code: string;
  message: string;
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
  club_table_list: (payload: { clubId: string }) => void;
  club_table_close: (payload: ClubTableClosePayload) => void;
  club_table_pause: (payload: ClubTablePausePayload) => void;
  club_ruleset_create: (payload: ClubRulesetCreatePayload) => void;
  club_ruleset_update: (payload: ClubRulesetUpdatePayload) => void;
  club_ruleset_set_default: (payload: ClubRulesetSetDefaultPayload) => void;
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
  club_error: (payload: ClubErrorPayload) => void;
}
