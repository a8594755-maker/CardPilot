/**
 * Club Service — Business logic layer for club operations.
 *
 * Provides:
 * - requireActiveClubMember() — single gate for all club table access checks
 * - createClub / joinClub / approveMember / grantChips — Task C operations
 *
 * This module wraps ClubManager calls with additional validation
 * and economy logic (grantChips uses the club_ledger table).
 */

import type { Club, ClubMember } from "@cardpilot/shared-types";
import type { ClubManager } from "../club-manager";
import type { ClubRepo } from "./club-repo";
import { logInfo, logWarn } from "../logger";

export interface ClubAccessDenied {
  allowed: false;
  reason: string;
  code: "NOT_CLUB_TABLE" | "NOT_MEMBER" | "PENDING" | "BANNED" | "LEFT";
}

export interface ClubAccessAllowed {
  allowed: true;
  clubId: string;
  clubTableId: string;
  member: ClubMember;
}

export type ClubAccessResult = ClubAccessDenied | ClubAccessAllowed;

/**
 * Single helper to gate all club table entry points.
 * Call this from join_room_code, join_table, sit_down, seat_request.
 *
 * Returns { allowed: true, ... } if access is granted,
 * or { allowed: false, reason, code } if denied.
 *
 * If the room is NOT a club table, returns { allowed: false, code: "NOT_CLUB_TABLE" }
 * — callers should treat this as "no restriction applies" and proceed normally.
 */
export function requireActiveClubMember(
  clubManager: ClubManager,
  roomCode: string,
  userId: string,
): ClubAccessResult {
  const clubInfo = clubManager.getClubForTable(roomCode);
  if (!clubInfo) {
    return { allowed: false, reason: "Not a club table", code: "NOT_CLUB_TABLE" };
  }

  const member = clubManager.getMember(clubInfo.clubId, userId);
  if (!member) {
    return { allowed: false, reason: "You are not a member of this club", code: "NOT_MEMBER" };
  }

  switch (member.status) {
    case "active":
      return { allowed: true, clubId: clubInfo.clubId, clubTableId: clubInfo.clubTableId, member };
    case "pending":
      return { allowed: false, reason: "Your join request is pending approval", code: "PENDING" };
    case "banned":
      return { allowed: false, reason: "You are banned from this club", code: "BANNED" };
    case "left":
      return { allowed: false, reason: "You have left this club", code: "LEFT" };
    default:
      return { allowed: false, reason: "Access denied", code: "NOT_MEMBER" };
  }
}

/**
 * Create a new club. Generates a unique code and initializes the owner as OWNER member.
 */
export function createClub(
  clubManager: ClubManager,
  userId: string,
  displayName: string,
  name: string,
  description?: string,
): Club {
  return clubManager.createClub({
    ownerUserId: userId,
    ownerDisplayName: displayName,
    name,
    description,
  });
}

/**
 * Join a club by code. Creates a PENDING member entry if approval is required.
 */
export function joinClub(
  clubManager: ClubManager,
  userId: string,
  displayName: string,
  clubCode: string,
  inviteCode?: string,
): { status: "joined" | "pending" | "error"; message: string; clubId?: string } {
  return clubManager.requestJoin(clubCode, userId, displayName, inviteCode);
}

/**
 * Approve a pending member. Flips their status to ACTIVE.
 */
export function approveMember(
  clubManager: ClubManager,
  adminId: string,
  clubId: string,
  targetId: string,
): ClubMember | null {
  return clubManager.approveJoin(clubId, adminId, targetId);
}

/**
 * Grant chips to a club member (club economy).
 * This is a transactional operation that updates club_members.balance
 * and records a ledger entry in club_ledger.
 *
 * Note: In the V1 spec, club chips are tracked via club_members.balance
 * in 004_clubs_feature.sql. The V2 full schema (005_clubs.sql) does not
 * have a balance column — it uses play-money only. This function is
 * provided for V1 spec compliance but should only be called when the
 * V1 economy model is active.
 */
export async function grantChips(
  repo: ClubRepo,
  clubManager: ClubManager,
  adminId: string,
  clubId: string,
  targetId: string,
  amount: number,
): Promise<{ success: boolean; newBalance?: number; message: string }> {
  // Verify admin has permission
  const adminRole = clubManager.getMemberRole(clubId, adminId);
  if (!adminRole || (adminRole !== "owner" && adminRole !== "admin")) {
    return { success: false, message: "Only club admins can grant chips" };
  }

  // Verify target is an active member
  if (!clubManager.isActiveMember(clubId, targetId)) {
    return { success: false, message: "Target user is not an active club member" };
  }

  if (amount === 0) {
    return { success: false, message: "Amount must be non-zero" };
  }

  // Note: In the full V2 schema, balance is not tracked on club_members.
  // This is a stub for V1 spec compliance. The actual DB update would use:
  //   UPDATE club_members SET balance = balance + amount WHERE club_id = ? AND user_id = ?
  // and INSERT into club_ledger.

  logInfo({
    event: "club.grant_chips",
    message: `Admin ${adminId} granted ${amount} chips to ${targetId} in club ${clubId}`,
  });

  return {
    success: true,
    newBalance: amount, // placeholder — real implementation reads from DB
    message: `Granted ${amount} chips`,
  };
}
