import React, { memo } from 'react';
import type { ClubAuditLogEntry } from '@cardpilot/shared-types';
import { EmptyState } from '../shared';

// ── Props ──

interface AuditTabProps {
  auditLog: ClubAuditLogEntry[];
}

// ── Helper: format audit action into human-readable string ──

function formatAuditAction(actionType: string, payload: Record<string, unknown>): string {
  const target = (payload.targetDisplayName ?? payload.targetUserId ?? '') as string;
  switch (actionType) {
    case 'member_joined':
      return `${target || 'A member'} joined the club`;
    case 'member_left':
      return `${target || 'A member'} left the club`;
    case 'member_kicked':
      return `${target || 'A member'} was removed`;
    case 'member_banned':
      return `${target || 'A member'} was banned`;
    case 'member_unbanned':
      return `${target || 'A member'} was unbanned`;
    case 'role_changed':
      return `${target || 'Member'} role \u2192 ${payload.newRole ?? 'Unknown'}`;
    case 'table_created':
      return `Table "${payload.tableName ?? 'Unknown'}" created`;
    case 'table_closed':
      return `Table "${payload.tableName ?? 'Unknown'}" closed`;
    case 'invite_created':
      return `Invite code created`;
    case 'invite_revoked':
      return `Invite code revoked`;
    case 'club_updated':
      return `Club settings updated`;
    case 'ruleset_created':
      return `Ruleset "${payload.rulesetName ?? 'Unknown'}" created`;
    case 'ruleset_updated':
      return `Ruleset "${payload.rulesetName ?? 'Unknown'}" updated`;
    default:
      return actionType.replace(/_/g, ' ');
  }
}

// ── Helper: map action type to badge color classes ──

function actionBadgeClasses(actionType: string): string {
  if (actionType.includes('ban') || actionType.includes('kick')) {
    return 'bg-red-900/30 text-red-400';
  }
  if (actionType.includes('join') || actionType === 'member_joined') {
    return 'bg-emerald-900/30 text-emerald-400';
  }
  if (actionType.includes('table')) {
    return 'bg-cyan-900/30 text-cyan-400';
  }
  if (actionType.includes('role')) {
    return 'bg-purple-900/30 text-purple-400';
  }
  return 'bg-slate-700/40 text-slate-400';
}

// ── Component ──

export const AuditTab = memo(function AuditTab({ auditLog }: AuditTabProps) {
  if (auditLog.length === 0) {
    return (
      <EmptyState
        icon="📋"
        title="No audit log entries"
        description="Actions performed in this club will appear here."
      />
    );
  }

  return (
    <div className="max-h-[500px] overflow-y-auto rounded-lg border border-slate-700">
      <div className="divide-y divide-slate-800">
        {auditLog.map((entry) => (
          <div
            key={entry.id}
            className="flex items-start gap-3 px-4 py-3 hover:bg-slate-800/40 transition-colors"
          >
            {/* Date / Time */}
            <div className="shrink-0 w-28 pt-0.5">
              <div className="text-[11px] text-slate-500">
                {new Date(entry.createdAt).toLocaleDateString()}
              </div>
              <div className="text-[10px] text-slate-600">
                {new Date(entry.createdAt).toLocaleTimeString()}
              </div>
            </div>

            {/* Action badge */}
            <span
              className={`shrink-0 mt-0.5 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${actionBadgeClasses(
                entry.actionType,
              )}`}
            >
              {entry.actionType.replace(/_/g, ' ')}
            </span>

            {/* Description & actor */}
            <div className="min-w-0 flex-1">
              <div className="text-xs text-slate-300 truncate">
                {formatAuditAction(entry.actionType, entry.payloadJson)}
              </div>
              {entry.actorDisplayName && (
                <div className="text-[10px] text-slate-500 mt-0.5">by {entry.actorDisplayName}</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
});

export default AuditTab;
