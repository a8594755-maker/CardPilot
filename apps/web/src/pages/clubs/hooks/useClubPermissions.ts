import { useMemo } from "react";
import type { ClubRole } from "@cardpilot/shared-types";
import { canPerformClubAction } from "@cardpilot/shared-types";

export interface ClubPermissions {
  role: ClubRole;
  isOwner: boolean;
  isAdmin: boolean;
  canManageMembers: boolean;
  canApproveJoins: boolean;
  canCreateTable: boolean;
  canManageRulesets: boolean;
  canCreateInvite: boolean;
  canViewAudit: boolean;
  canManageTables: boolean;
  canCloseTable: boolean;
  canModerateChat: boolean;
}

export function useClubPermissions(role: ClubRole | undefined): ClubPermissions {
  return useMemo(() => {
    const r = role ?? "member";
    return {
      role: r,
      isOwner: r === "owner",
      isAdmin: r === "owner" || r === "admin",
      canManageMembers: canPerformClubAction(r, "manage_members"),
      canApproveJoins: canPerformClubAction(r, "approve_joins"),
      canCreateTable: canPerformClubAction(r, "create_table"),
      canManageRulesets: canPerformClubAction(r, "manage_rulesets"),
      canCreateInvite: canPerformClubAction(r, "create_invite"),
      canViewAudit: canPerformClubAction(r, "view_audit_log"),
      canManageTables: canPerformClubAction(r, "manage_tables"),
      canCloseTable: r === "owner",
      canModerateChat: canPerformClubAction(r, "moderate_chat"),
    };
  }, [role]);
}
