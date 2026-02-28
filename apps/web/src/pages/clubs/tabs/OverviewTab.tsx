import React, { useMemo } from "react";
import type {
  Club,
  ClubDetail,
  ClubMember,
  ClubTable,
  ClubAuditLogEntry,
} from "@cardpilot/shared-types";
import { RoleBadge, RulesSummary } from "../shared";
import type { ClubPermissions } from "../hooks/useClubPermissions";
import type { ClubSocketActions } from "../hooks/useClubSocket";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ONLINE_THRESHOLD_MIN = 15;

function isRecentlyOnline(lastSeenAt: string): boolean {
  return Date.now() - new Date(lastSeenAt).getTime() < ONLINE_THRESHOLD_MIN * 60 * 1000;
}

function formatAuditAction(actionType: string, payload: Record<string, unknown>): string {
  const target = (payload.targetDisplayName ?? payload.targetUserId ?? "") as string;
  switch (actionType) {
    case "member_joined": return `${target || "A member"} joined the club`;
    case "member_left": return `${target || "A member"} left the club`;
    case "member_kicked": return `${target || "A member"} was removed`;
    case "member_banned": return `${target || "A member"} was banned`;
    case "member_unbanned": return `${target || "A member"} was unbanned`;
    case "role_changed": return `${target || "Member"} role \u2192 ${payload.newRole ?? "Unknown"}`;
    case "table_created": return `Table "${payload.tableName ?? "Unknown"}" created`;
    case "table_closed": return `Table "${payload.tableName ?? "Unknown"}" closed`;
    case "invite_created": return `Invite code created`;
    case "invite_revoked": return `Invite code revoked`;
    case "club_updated": return `Club settings updated`;
    case "ruleset_created": return `Ruleset "${payload.rulesetName ?? "Unknown"}" created`;
    case "ruleset_updated": return `Ruleset "${payload.rulesetName ?? "Unknown"}" updated`;
    default: return actionType.replace(/_/g, " ");
  }
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface OverviewTabProps {
  club: Club;
  detail: ClubDetail;
  members: ClubMember[];
  tables: ClubTable[];
  auditLog: ClubAuditLogEntry[];
  permissions: ClubPermissions;
  actions: ClubSocketActions;
  onSwitchTab: (tab: string) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const OverviewTab = React.memo(function OverviewTab({
  club,
  detail,
  members,
  tables,
  auditLog,
  permissions,
  actions,
  onSwitchTab,
}: OverviewTabProps) {
  const onlineMembers = useMemo(
    () => members.filter((m) => isRecentlyOnline(m.lastSeenAt)),
    [members],
  );

  const activeTables = useMemo(
    () => tables.filter((t) => t.status === "open"),
    [tables],
  );

  return (
    <div className="space-y-5">
      {/* Stats strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-xl bg-indigo-500/10 border border-indigo-500/20 p-3 text-center">
          <div className="text-lg font-bold text-indigo-300">{detail.memberCount}</div>
          <div className="text-[10px] text-slate-400 uppercase tracking-wider">Members</div>
        </div>
        <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/20 p-3 text-center">
          <div className="text-lg font-bold text-emerald-300">{onlineMembers.length}</div>
          <div className="text-[10px] text-slate-400 uppercase tracking-wider">Online</div>
        </div>
        <div className="rounded-xl bg-cyan-500/10 border border-cyan-500/20 p-3 text-center">
          <div className="text-lg font-bold text-cyan-300">{activeTables.length}</div>
          <div className="text-[10px] text-slate-400 uppercase tracking-wider">Active Tables</div>
        </div>
        <div className="rounded-xl bg-amber-500/10 border border-amber-500/20 p-3 text-center">
          <div className="text-lg font-bold text-amber-300">{detail.tableCount}</div>
          <div className="text-[10px] text-slate-400 uppercase tracking-wider">Total Tables</div>
        </div>
      </div>

      {/* Announcements banner */}
      <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-indigo-300 flex items-center gap-2">
            Announcements
          </h3>
        </div>
        {club.description ? (
          <p className="text-sm text-slate-300 leading-relaxed">{club.description}</p>
        ) : (
          <p className="text-xs text-slate-500 italic">
            No announcements yet. The club description appears here.
          </p>
        )}
      </div>

      {/* Online members strip */}
      {onlineMembers.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
            Online Now
          </h3>
          <div className="flex flex-wrap gap-2">
            {onlineMembers.slice(0, 20).map((m) => (
              <div
                key={m.userId}
                className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-white/5 border border-white/5"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                <span className="text-[11px] text-slate-300">
                  {m.displayName ?? m.nicknameInClub ?? m.userId.slice(0, 8)}
                </span>
                <RoleBadge role={m.role} size="xs" />
              </div>
            ))}
            {onlineMembers.length > 20 && (
              <span className="text-[10px] text-slate-500 self-center">
                +{onlineMembers.length - 20} more
              </span>
            )}
          </div>
        </div>
      )}

      {/* Active tables quick-join cards */}
      {activeTables.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-2">Active Tables</h3>
          <div className="space-y-2">
            {activeTables.map((t) => (
              <div
                key={t.id}
                className="flex items-center gap-3 p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/20"
              >
                <div className="w-9 h-9 rounded-lg bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 text-sm font-bold">
                  {t.playerCount ?? 0}
                </div>
                <div className="flex-1">
                  <div className="text-sm font-medium text-white">{t.name}</div>
                  <div className="text-[10px] text-slate-400">
                    {t.stakes ?? "\u2014"} · {t.playerCount ?? 0}/{t.maxPlayers ?? "\u2014"} players
                  </div>
                </div>
                <button
                  onClick={() => actions.joinTable(t.id)}
                  className="btn-success text-xs !py-1.5 !px-4"
                >
                  Quick Join
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state CTA */}
      {activeTables.length === 0 && permissions.canCreateTable && (
        <div className="text-center py-4 rounded-xl border border-dashed border-white/10 bg-white/[0.02]">
          <p className="text-sm text-slate-400 mb-2">No active tables</p>
          <button
            onClick={() => onSwitchTab("tables")}
            className="btn-primary text-xs"
          >
            + Create a Table
          </button>
        </div>
      )}

      {/* Club info grid */}
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-slate-500">Visibility:</span>{" "}
          <span className="text-slate-300">{club.visibility}</span>
        </div>
        <div>
          <span className="text-slate-500">Approval required:</span>{" "}
          <span className="text-slate-300">{club.requireApprovalToJoin ? "Yes" : "No"}</span>
        </div>
        <div>
          <span className="text-slate-500">Default ruleset:</span>{" "}
          <span className="text-slate-300">{detail.defaultRuleset?.name ?? "None"}</span>
        </div>
        <div>
          <span className="text-slate-500">Created:</span>{" "}
          <span className="text-slate-300">{new Date(club.createdAt).toLocaleDateString()}</span>
        </div>
      </div>

      {/* Default rules summary */}
      {detail.defaultRuleset && (
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-2">Default Rules Summary</h3>
          <RulesSummary rules={detail.defaultRuleset.rulesJson} />
        </div>
      )}

      {/* Recent activity preview */}
      {permissions.canViewAudit && auditLog.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Recent Activity
            </h3>
            <button
              onClick={() => onSwitchTab("audit")}
              className="text-[10px] text-indigo-400 hover:text-indigo-300"
            >
              View all &rarr;
            </button>
          </div>
          <div className="space-y-1">
            {auditLog
              .slice(-5)
              .reverse()
              .map((entry) => (
                <div
                  key={entry.id}
                  className="flex items-center gap-2 text-[11px] py-1.5 px-2 rounded-lg bg-white/[0.02]"
                >
                  <span className="text-slate-600 text-[10px] shrink-0">
                    {new Date(entry.createdAt).toLocaleDateString()}
                  </span>
                  <span className="text-slate-300">
                    {formatAuditAction(entry.actionType, entry.payloadJson)}
                  </span>
                  {entry.actorDisplayName && (
                    <span className="text-slate-500 ml-auto text-[10px]">
                      by {entry.actorDisplayName}
                    </span>
                  )}
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
});

export default OverviewTab;
