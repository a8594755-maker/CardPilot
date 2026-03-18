import { useState, useEffect } from 'react';
import type { ClubPermissions } from './useClubPermissions';

export type ClubTab =
  | 'overview'
  | 'chat'
  | 'analytics'
  | 'credits'
  | 'transactions'
  | 'leaderboard'
  | 'members'
  | 'tables'
  | 'rulesets'
  | 'invites'
  | 'admin'
  | 'audit'
  | 'settings';

export interface TabDef {
  id: ClubTab;
  label: string;
  show: boolean;
}

export function buildVisibleTabs(
  permissions: ClubPermissions,
  memberCount: number,
  tableCount: number,
): TabDef[] {
  const { isAdmin, canManageRulesets, canCreateInvite, canViewAudit } = permissions;
  return [
    { id: 'overview', label: 'Home', show: isAdmin },
    { id: 'tables', label: `Tables (${tableCount})`, show: true },
    { id: 'chat', label: 'Chat', show: true },
    { id: 'credits', label: 'Credits', show: true },
    { id: 'transactions', label: 'Transactions', show: true },
    { id: 'leaderboard', label: 'Leaderboard', show: true },
    { id: 'analytics', label: 'Analytics', show: true },
    { id: 'members', label: `Members (${memberCount})`, show: isAdmin },
    { id: 'rulesets', label: 'Rulesets', show: isAdmin && canManageRulesets },
    { id: 'invites', label: 'Invites', show: isAdmin && canCreateInvite },
    { id: 'admin', label: 'Admin', show: isAdmin },
    { id: 'audit', label: 'Activity', show: isAdmin && canViewAudit },
    { id: 'settings', label: 'Settings', show: isAdmin },
  ].filter((t) => t.show) as TabDef[];
}

export function useClubTab(
  clubId: string,
  permissions: ClubPermissions,
): [ClubTab, (tab: ClubTab) => void] {
  const defaultTab = permissions.isAdmin ? 'overview' : 'tables';
  const [tab, setTab] = useState<ClubTab>(defaultTab);

  // Reset tab on club change
  useEffect(() => {
    setTab(permissions.isAdmin ? 'overview' : 'tables');
  }, [clubId, permissions.isAdmin]);

  return [tab, setTab];
}
