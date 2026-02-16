import { useState, useCallback, useMemo, useEffect } from "react";
import type { Socket } from "socket.io-client";
import type {
  ClubDetailPayload,
  ClubRole,
  ClubRules,
  ClubVisibility,
} from "@cardpilot/shared-types";
import { DEFAULT_CLUB_RULES } from "@cardpilot/shared-types";
import { canPerformClubAction } from "@cardpilot/shared-types";

type Tab = "overview" | "members" | "tables" | "rulesets" | "invites" | "audit" | "settings";

/** Consider a member "recently online" if lastSeenAt is within this many minutes */
const ONLINE_THRESHOLD_MIN = 15;

function isRecentlyOnline(lastSeenAt: string): boolean {
  const diff = Date.now() - new Date(lastSeenAt).getTime();
  return diff < ONLINE_THRESHOLD_MIN * 60 * 1000;
}

/** Human-readable audit action descriptions */
function formatAuditAction(actionType: string, payload: Record<string, unknown>): string {
  const target = (payload.targetDisplayName ?? payload.targetUserId ?? "") as string;
  switch (actionType) {
    case "member_joined": return `${target || "A member"} joined the club`;
    case "member_left": return `${target || "A member"} left the club`;
    case "member_kicked": return `${target || "A member"} was removed`;
    case "member_banned": return `${target || "A member"} was banned`;
    case "member_unbanned": return `${target || "A member"} was unbanned`;
    case "role_changed": return `${target || "Member"} role → ${payload.newRole ?? "?"}`;
    case "table_created": return `Table "${payload.tableName ?? "?"}" created`;
    case "table_closed": return `Table "${payload.tableName ?? "?"}" closed`;
    case "invite_created": return `Invite code created`;
    case "invite_revoked": return `Invite code revoked`;
    case "club_updated": return `Club settings updated`;
    case "ruleset_created": return `Ruleset "${payload.rulesetName ?? "?"}" created`;
    case "ruleset_updated": return `Ruleset "${payload.rulesetName ?? "?"}" updated`;
    default: return actionType.replace(/_/g, " ");
  }
}

const ROLE_BADGE_COLORS: Record<string, string> = {
  owner: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  admin: "bg-purple-500/20 text-purple-300 border-purple-500/30",
  host: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  mod: "bg-cyan-500/20 text-cyan-300 border-cyan-500/30",
  member: "bg-white/5 text-slate-400 border-white/10",
};

interface ClubDetailViewProps {
  socket: Socket | null;
  isConnected: boolean;
  userId: string;
  detail: ClubDetailPayload;
  onBack: () => void;
  onJoinTable: (roomCode: string) => void;
  showToast: (msg: string) => void;
}

export function ClubDetailView({
  socket,
  isConnected,
  userId,
  detail,
  onBack,
  onJoinTable,
  showToast,
}: ClubDetailViewProps) {
  const [tab, setTab] = useState<Tab>("overview");
  const [showCreateTable, setShowCreateTable] = useState(false);
  const [newTableName, setNewTableName] = useState("");
  const [newTableRulesetId, setNewTableRulesetId] = useState<string>("");
  const [showCreateInvite, setShowCreateInvite] = useState(false);
  const [showCreateRuleset, setShowCreateRuleset] = useState(false);
  const [rsName, setRsName] = useState("");
  const [rsSB, setRsSB] = useState(1);
  const [rsBB, setRsBB] = useState(2);
  const [rsSeats, setRsSeats] = useState(6);
  const [rsBuyMin, setRsBuyMin] = useState(40);
  const [rsBuyMax, setRsBuyMax] = useState(200);
  const [rsTimer, setRsTimer] = useState(15);
  const [rsTimeBank, setRsTimeBank] = useState(60);
  const [rsRIT, setRsRIT] = useState(false);
  const [rsIsDefault, setRsIsDefault] = useState(false);

  const { club, myMembership } = detail.detail;
  const myRole = myMembership?.role ?? "member";

  // Settings form state
  const [editName, setEditName] = useState(club.name);
  const [editDesc, setEditDesc] = useState(club.description);
  const [editApproval, setEditApproval] = useState(club.requireApprovalToJoin);
  const [editColor, setEditColor] = useState(club.badgeColor ?? "#6366f1");
  useEffect(() => {
    setEditName(club.name);
    setEditDesc(club.description);
    setEditApproval(club.requireApprovalToJoin);
    setEditColor(club.badgeColor ?? "#6366f1");
  }, [club.name, club.description, club.requireApprovalToJoin, club.badgeColor]);

  const canManageMembers = canPerformClubAction(myRole, "manage_members");
  const canApproveJoins = canPerformClubAction(myRole, "approve_joins");
  const canCreateTable = canPerformClubAction(myRole, "create_table");
  const canManageRulesets = canPerformClubAction(myRole, "manage_rulesets");
  const canCreateInvite = canPerformClubAction(myRole, "create_invite");
  const canViewAudit = canPerformClubAction(myRole, "view_audit_log");
  const canManageTables = canPerformClubAction(myRole, "manage_tables");
  const isAdmin = canManageMembers;

  const onlineMembers = useMemo(() =>
    detail.members.filter((m) => isRecentlyOnline(m.lastSeenAt)),
    [detail.members],
  );

  const activeTables = useMemo(() =>
    detail.tables.filter((t) => t.status === "open"),
    [detail.tables],
  );

  const handleCreateTable = useCallback(() => {
    if (!socket || !newTableName.trim()) return;
    socket.emit("club_table_create", {
      clubId: club.id,
      name: newTableName.trim(),
      rulesetId: newTableRulesetId || undefined,
    });
    setShowCreateTable(false);
    setNewTableName("");
    setNewTableRulesetId("");
    showToast("Creating table...");
  }, [socket, club.id, newTableName, newTableRulesetId, showToast]);

  const handleCreateRuleset = useCallback(() => {
    if (!socket || !rsName.trim()) return;
    const rules: ClubRules = {
      ...DEFAULT_CLUB_RULES,
      stakes: { smallBlind: rsSB, bigBlind: rsBB },
      maxSeats: rsSeats,
      buyIn: { minBuyIn: rsBuyMin, maxBuyIn: rsBuyMax, defaultBuyIn: Math.round((rsBuyMin + rsBuyMax) / 2) },
      time: { ...DEFAULT_CLUB_RULES.time, actionTimeSec: rsTimer, timeBankSec: rsTimeBank },
      runit: { ...DEFAULT_CLUB_RULES.runit, allowRunItTwice: rsRIT },
    };
    socket.emit("club_ruleset_create", { clubId: club.id, name: rsName.trim(), rules, isDefault: rsIsDefault });
    setShowCreateRuleset(false);
    setRsName("");
    showToast("Creating ruleset...");
  }, [socket, club.id, rsName, rsSB, rsBB, rsSeats, rsBuyMin, rsBuyMax, rsTimer, rsTimeBank, rsRIT, rsIsDefault, showToast]);

  const handleUpdateClub = useCallback(() => {
    if (!socket) return;
    socket.emit("club_update", {
      clubId: club.id,
      name: editName.trim(),
      description: editDesc.trim(),
      requireApprovalToJoin: editApproval,
      badgeColor: editColor,
    });
    showToast("Saving settings...");
  }, [socket, club.id, editName, editDesc, editApproval, editColor, showToast]);

  const copyToClipboard = useCallback((text: string, label: string) => {
    void navigator.clipboard.writeText(text);
    showToast(`Copied ${label}: ${text}`);
  }, [showToast]);

  const handleApprove = useCallback((targetUserId: string) => {
    if (!socket) return;
    socket.emit("club_join_approve", { clubId: club.id, userId: targetUserId, approve: true });
    showToast("Approving...");
  }, [socket, club.id, showToast]);

  const handleReject = useCallback((targetUserId: string) => {
    if (!socket) return;
    socket.emit("club_join_reject", { clubId: club.id, userId: targetUserId, approve: false });
    showToast("Rejecting...");
  }, [socket, club.id, showToast]);

  const handleRoleChange = useCallback((targetUserId: string, newRole: ClubRole) => {
    if (!socket) return;
    socket.emit("club_member_update_role", { clubId: club.id, userId: targetUserId, newRole });
    showToast("Updating role...");
  }, [socket, club.id, showToast]);

  const handleKick = useCallback((targetUserId: string) => {
    if (!socket) return;
    socket.emit("club_member_kick", { clubId: club.id, userId: targetUserId });
    showToast("Removing member...");
  }, [socket, club.id, showToast]);

  const handleBan = useCallback((targetUserId: string) => {
    if (!socket) return;
    socket.emit("club_member_ban", { clubId: club.id, userId: targetUserId, reason: "Banned by admin" });
    showToast("Banning member...");
  }, [socket, club.id, showToast]);

  const handleCreateInvite = useCallback(() => {
    if (!socket) return;
    socket.emit("club_invite_create", { clubId: club.id, maxUses: 50, expiresInHours: 168 });
    setShowCreateInvite(false);
    showToast("Creating invite link...");
  }, [socket, club.id, showToast]);

  const handleRevokeInvite = useCallback((inviteId: string) => {
    if (!socket) return;
    socket.emit("club_invite_revoke", { clubId: club.id, inviteId });
    showToast("Revoking invite...");
  }, [socket, club.id, showToast]);

  const handleCloseTable = useCallback((tableId: string) => {
    if (!socket) return;
    socket.emit("club_table_close", { clubId: club.id, tableId });
    showToast("Closing table...");
  }, [socket, club.id, showToast]);

  const tabs: { id: Tab; label: string; show: boolean }[] = [
    { id: "overview", label: "Home", show: true },
    { id: "members", label: `Members (${detail.members.length})`, show: true },
    { id: "tables", label: `Tables (${detail.tables.length})`, show: true },
    { id: "rulesets", label: "Rulesets", show: canManageRulesets },
    { id: "invites", label: "Invites", show: canCreateInvite },
    { id: "audit", label: "Activity", show: canViewAudit },
    { id: "settings", label: "Settings", show: isAdmin },
  ];

  return (
    <main className="flex-1 p-6 overflow-y-auto">
      <div className="max-w-4xl mx-auto space-y-4">
        {/* Disclaimer */}
        <div className="glass-card p-2 bg-amber-500/5 border-amber-500/20 text-[10px] text-amber-400/80 text-center">
          🎓 Play-money training tool — not real-money gambling. All credits are virtual.
        </div>

        {/* Header */}
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="text-slate-400 hover:text-white transition-colors text-sm">
            ← Back
          </button>
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center text-xl font-bold text-white shadow-lg"
            style={{ backgroundColor: club.badgeColor ?? "#6366f1" }}
          >
            {club.name[0]?.toUpperCase()}
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-bold text-white">{club.name}</h2>
            <div className="flex items-center gap-3 text-xs text-slate-400">
              <span>Code: <code className="text-amber-400 font-mono">{club.code}</code></span>
              <span>{detail.detail.memberCount} members</span>
              <span className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
                {onlineMembers.length} online
              </span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded border ${ROLE_BADGE_COLORS[myRole] ?? ROLE_BADGE_COLORS.member} uppercase font-semibold`}>{myRole}</span>
            </div>
          </div>
          <button
            onClick={() => { socket?.emit("club_get_detail", { clubId: club.id }); showToast("Refreshing..."); }}
            className="text-[10px] px-2 py-1 rounded-lg bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10 transition-all"
            title="Refresh club data"
          >
            ↻ Refresh
          </button>
        </div>

        {/* Pending Join Requests Banner */}
        {canApproveJoins && detail.pendingMembers.length > 0 && (
          <div className="glass-card p-3 bg-amber-500/10 border-amber-500/30 animate-pulse">
            <div className="text-sm font-semibold text-amber-400 mb-2">
              🎫 {detail.pendingMembers.length} pending join request{detail.pendingMembers.length > 1 ? "s" : ""}
            </div>
            <div className="space-y-2">
              {detail.pendingMembers.map((m) => (
                <div key={m.userId} className="flex items-center gap-3 text-sm bg-black/20 rounded-lg p-2">
                  <div className="w-7 h-7 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-[10px] font-bold text-white uppercase">
                    {(m.displayName ?? "?")[0]}
                  </div>
                  <span className="text-white flex-1">{m.displayName ?? m.userId.slice(0, 8)}</span>
                  <button onClick={() => handleApprove(m.userId)} className="px-2 py-1 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30">
                    ✓ Approve
                  </button>
                  <button onClick={() => handleReject(m.userId)} className="px-2 py-1 rounded text-[10px] font-semibold bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30">
                    ✗ Reject
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tabs */}
        <nav className="flex gap-1 bg-white/5 rounded-xl p-1 overflow-x-auto">
          {tabs
            .filter((t) => t.show)
            .map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all whitespace-nowrap ${
                  tab === t.id
                    ? "bg-white/10 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {t.label}
              </button>
            ))}
        </nav>

        {/* Tab Content */}
        <div className="glass-card p-5">
          {tab === "overview" && (
            <div className="space-y-5">
              {/* Club Home: quick stats strip */}
              <div className="grid grid-cols-4 gap-3">
                <div className="rounded-xl bg-indigo-500/10 border border-indigo-500/20 p-3 text-center">
                  <div className="text-lg font-bold text-indigo-300">{detail.detail.memberCount}</div>
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
                  <div className="text-lg font-bold text-amber-300">{detail.detail.tableCount}</div>
                  <div className="text-[10px] text-slate-400 uppercase tracking-wider">Total Tables</div>
                </div>
              </div>

              {/* Announcements / MOTD */}
              <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-semibold text-indigo-300 flex items-center gap-2">
                    📢 Announcements
                  </h3>
                </div>
                {club.description ? (
                  <p className="text-sm text-slate-300 leading-relaxed">{club.description}</p>
                ) : (
                  <p className="text-xs text-slate-500 italic">No announcements yet. The club description appears here.</p>
                )}
              </div>

              {/* Online members strip */}
              {onlineMembers.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Online Now</h3>
                  <div className="flex flex-wrap gap-2">
                    {onlineMembers.slice(0, 20).map((m) => (
                      <div key={m.userId} className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-white/5 border border-white/5">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                        <span className="text-[11px] text-slate-300">{m.displayName ?? m.nicknameInClub ?? m.userId.slice(0, 8)}</span>
                        <span className={`text-[8px] px-1 py-0.5 rounded border ${ROLE_BADGE_COLORS[m.role] ?? ROLE_BADGE_COLORS.member} uppercase`}>{m.role}</span>
                      </div>
                    ))}
                    {onlineMembers.length > 20 && (
                      <span className="text-[10px] text-slate-500 self-center">+{onlineMembers.length - 20} more</span>
                    )}
                  </div>
                </div>
              )}

              {/* Active tables quick-join */}
              {activeTables.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-slate-300 mb-2">Active Tables</h3>
                  <div className="space-y-2">
                    {activeTables.map((t) => (
                      <div key={t.id} className="flex items-center gap-3 p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/20">
                        <div className="w-9 h-9 rounded-lg bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 text-sm font-bold">
                          {t.playerCount ?? 0}
                        </div>
                        <div className="flex-1">
                          <div className="text-sm font-medium text-white">{t.name}</div>
                          <div className="text-[10px] text-slate-400">{t.stakes ?? "—"} · {t.playerCount ?? 0}/{t.maxPlayers ?? "?"} players</div>
                        </div>
                        {t.roomCode && (
                          <button onClick={() => onJoinTable(t.roomCode!)} className="btn-success text-xs !py-1.5 !px-4">
                            Quick Join
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {activeTables.length === 0 && canCreateTable && (
                <div className="text-center py-4 rounded-xl border border-dashed border-white/10 bg-white/[0.02]">
                  <p className="text-sm text-slate-400 mb-2">No active tables</p>
                  <button onClick={() => { setTab("tables"); setShowCreateTable(true); }} className="btn-primary text-xs">
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
                  <span className="text-slate-300">{detail.detail.defaultRuleset?.name ?? "None"}</span>
                </div>
                <div>
                  <span className="text-slate-500">Created:</span>{" "}
                  <span className="text-slate-300">{new Date(club.createdAt).toLocaleDateString()}</span>
                </div>
              </div>
              {detail.detail.defaultRuleset && (
                <div>
                  <h3 className="text-sm font-semibold text-slate-300 mb-2">Default Rules Summary</h3>
                  <RulesSummary rules={detail.detail.defaultRuleset.rulesJson} />
                </div>
              )}

              {/* Recent Activity Preview (last 5 entries) */}
              {canViewAudit && detail.auditLog.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Recent Activity</h3>
                    <button onClick={() => setTab("audit")} className="text-[10px] text-indigo-400 hover:text-indigo-300">View all →</button>
                  </div>
                  <div className="space-y-1">
                    {detail.auditLog.slice(-5).reverse().map((entry) => (
                      <div key={entry.id} className="flex items-center gap-2 text-[11px] py-1.5 px-2 rounded-lg bg-white/[0.02]">
                        <span className="text-slate-600 text-[10px] shrink-0">{new Date(entry.createdAt).toLocaleDateString()}</span>
                        <span className="text-slate-300">{formatAuditAction(entry.actionType, entry.payloadJson)}</span>
                        {entry.actorDisplayName && <span className="text-slate-500 ml-auto text-[10px]">by {entry.actorDisplayName}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {tab === "members" && (
            <div className="space-y-1">
              <div className="flex items-center justify-between mb-3">
                <div className="text-xs text-slate-500">
                  {detail.members.length} members · {onlineMembers.length} online
                </div>
              </div>
              {detail.members
                .slice()
                .sort((a, b) => {
                  const RANK: Record<string, number> = { owner: 5, admin: 4, host: 3, mod: 2, member: 1 };
                  return (RANK[b.role] ?? 0) - (RANK[a.role] ?? 0);
                })
                .map((m) => {
                  const online = isRecentlyOnline(m.lastSeenAt);
                  return (
                    <div key={m.userId} className="flex items-center gap-3 p-2 rounded-lg hover:bg-white/5 transition-colors">
                      <div className="relative">
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-[10px] font-bold text-white uppercase">
                          {(m.displayName ?? m.nicknameInClub ?? "?")[0]}
                        </div>
                        {online && (
                          <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-slate-900" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-white truncate">{m.displayName ?? m.nicknameInClub ?? m.userId.slice(0, 8)}</span>
                          <span className={`text-[9px] px-1.5 py-0.5 rounded border ${ROLE_BADGE_COLORS[m.role] ?? ROLE_BADGE_COLORS.member} uppercase font-semibold`}>{m.role}</span>
                          {m.userId === userId && <span className="text-[9px] text-cyan-400">(you)</span>}
                        </div>
                        <div className="text-[10px] text-slate-500">
                          joined {new Date(m.createdAt).toLocaleDateString()}
                          {online ? <span className="text-emerald-400 ml-2">● online</span> : <span className="ml-2">last seen {new Date(m.lastSeenAt).toLocaleDateString()}</span>}
                        </div>
                      </div>
                      {/* Virtual credits balance */}
                      <div className="text-right shrink-0 mr-1">
                        <div className="text-xs font-mono font-semibold text-amber-400">{(m.balance ?? 0).toLocaleString()}</div>
                        <div className="text-[9px] text-slate-500">credits</div>
                      </div>
                      {canManageMembers && m.role !== "owner" && (
                        <div className="flex gap-1 items-center shrink-0">
                          {m.userId !== userId && (
                            <select
                              value={m.role}
                              onChange={(e) => handleRoleChange(m.userId, e.target.value as ClubRole)}
                              className="text-[10px] bg-white/5 border border-white/10 rounded px-1.5 py-1 text-slate-300 cursor-pointer"
                            >
                              <option value="member">member</option>
                              <option value="mod">mod</option>
                              <option value="host">host</option>
                              <option value="admin">admin</option>
                            </select>
                          )}
                          <button onClick={() => {
                            const amt = prompt(`Grant credits to ${m.displayName ?? m.userId.slice(0, 8)}:`, "1000");
                            if (amt && Number(amt) > 0) socket?.emit("club_grant_credits", { clubId: club.id, userId: m.userId, amount: Number(amt) });
                          }}
                            className="text-[10px] text-emerald-400 hover:text-emerald-300 px-1.5 py-1 rounded hover:bg-emerald-500/10 transition-colors" title="Grant credits">
                            +$
                          </button>
                          {m.userId !== userId && (
                            <>
                              <button onClick={() => { if (confirm(`Remove ${m.displayName ?? m.userId.slice(0, 8)} from club?`)) handleKick(m.userId); }}
                                className="text-[10px] text-red-400 hover:text-red-300 px-1.5 py-1 rounded hover:bg-red-500/10 transition-colors">
                                Kick
                              </button>
                              <button onClick={() => { if (confirm(`Ban ${m.displayName ?? m.userId.slice(0, 8)}?`)) handleBan(m.userId); }}
                                className="text-[10px] text-red-400 hover:text-red-300 px-1.5 py-1 rounded hover:bg-red-500/10 transition-colors">
                                Ban
                              </button>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
            </div>
          )}

          {tab === "tables" && (
            <div className="space-y-3">
              {canCreateTable && (
                <div className="space-y-2">
                  {showCreateTable ? (
                    <div className="p-3 rounded-xl border border-emerald-500/30 bg-emerald-500/5 space-y-2">
                      <h4 className="text-xs font-semibold text-emerald-300">Create Table</h4>
                      <input
                        type="text"
                        placeholder="Table name"
                        value={newTableName}
                        onChange={(e) => setNewTableName(e.target.value)}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                        maxLength={80}
                        autoFocus
                      />
                      {detail.rulesets.length > 0 && (
                        <div>
                          <label className="block text-[10px] text-slate-400 mb-0.5">Ruleset</label>
                          <select value={newTableRulesetId} onChange={(e) => setNewTableRulesetId(e.target.value)}
                            className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded text-sm text-white focus:outline-none focus:border-indigo-500">
                            <option value="">Default</option>
                            {detail.rulesets.map((rs) => (
                              <option key={rs.id} value={rs.id}>{rs.name} ({rs.rulesJson.stakes.smallBlind}/{rs.rulesJson.stakes.bigBlind})</option>
                            ))}
                          </select>
                        </div>
                      )}
                      <div className="flex gap-2">
                        <button onClick={handleCreateTable} disabled={!newTableName.trim()} className="btn-primary text-xs disabled:opacity-50">
                          Create
                        </button>
                        <button onClick={() => setShowCreateTable(false)} className="btn-ghost text-xs">
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button onClick={() => setShowCreateTable(true)} className="btn-primary text-xs">
                      + New Table
                    </button>
                  )}
                </div>
              )}

              {detail.tables.length === 0 ? (
                <div className="text-center py-8">
                  <div className="text-3xl mb-2 opacity-20">🎴</div>
                  <p className="text-sm text-slate-400">No tables yet.</p>
                  {canCreateTable && <p className="text-xs text-slate-500 mt-1">Create one to get started!</p>}
                </div>
              ) : (
                detail.tables.map((t) => (
                  <div key={t.id} className={`flex items-center gap-3 p-3 rounded-lg border ${t.status === "open" ? "bg-emerald-500/5 border-emerald-500/20" : "bg-white/[0.02] border-white/5"}`}>
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-sm font-bold border ${
                      t.status === "open" ? "bg-emerald-500/20 border-emerald-500/30 text-emerald-400" : "bg-white/5 border-white/10 text-slate-500"
                    }`}>
                      {t.playerCount ?? 0}
                    </div>
                    <div className="flex-1">
                      <div className="text-sm font-medium text-white">{t.name}</div>
                      <div className="text-[10px] text-slate-400">
                        {t.stakes ?? "—"} · {t.playerCount ?? 0}/{t.maxPlayers ?? "?"} players ·{" "}
                        <span className={t.status === "open" ? "text-emerald-400" : t.status === "paused" ? "text-amber-400" : "text-slate-500"}>
                          {t.status}
                        </span>
                      </div>
                    </div>
                    {t.roomCode && t.status === "open" && (
                      <button
                        onClick={() => onJoinTable(t.roomCode!)}
                        className="btn-success text-xs !py-1.5 !px-3"
                      >
                        Join Table
                      </button>
                    )}
                    {canCreateTable && t.status !== "closed" && (
                      <button
                        onClick={() => { if (confirm(`Close table "${t.name}"?`)) handleCloseTable(t.id); }}
                        className="text-[10px] text-red-400 hover:text-red-300 px-2 py-1 rounded hover:bg-red-500/10 transition-colors"
                      >
                        Close
                      </button>
                    )}
                  </div>
                ))
              )}
            </div>
          )}

          {tab === "rulesets" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-xs text-slate-500">
                  Rulesets define table rules. The default ruleset is used when creating tables without specifying one.
                </p>
                {canManageRulesets && !showCreateRuleset && (
                  <button onClick={() => setShowCreateRuleset(true)} className="btn-primary text-xs shrink-0">+ New Ruleset</button>
                )}
              </div>

              {/* Ruleset creation form */}
              {showCreateRuleset && canManageRulesets && (
                <div className="p-4 rounded-xl border border-indigo-500/30 bg-indigo-500/5 space-y-3">
                  <h4 className="text-sm font-semibold text-indigo-300">Create Ruleset</h4>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="col-span-2">
                      <label className="block text-[10px] text-slate-400 mb-0.5">Name</label>
                      <input type="text" value={rsName} onChange={(e) => setRsName(e.target.value)} placeholder="e.g. 1/2 NLH Deep"
                        className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded text-sm text-white focus:outline-none focus:border-indigo-500" maxLength={80} autoFocus />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-400 mb-0.5">Small Blind</label>
                      <input type="number" value={rsSB} onChange={(e) => setRsSB(Number(e.target.value))} min={1}
                        className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded text-sm text-white focus:outline-none focus:border-indigo-500" />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-400 mb-0.5">Big Blind</label>
                      <input type="number" value={rsBB} onChange={(e) => setRsBB(Number(e.target.value))} min={1}
                        className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded text-sm text-white focus:outline-none focus:border-indigo-500" />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-400 mb-0.5">Max Seats</label>
                      <select value={rsSeats} onChange={(e) => setRsSeats(Number(e.target.value))}
                        className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded text-sm text-white focus:outline-none focus:border-indigo-500">
                        {[2, 3, 4, 5, 6, 7, 8, 9].map((n) => <option key={n} value={n}>{n}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-400 mb-0.5">Action Timer (sec)</label>
                      <input type="number" value={rsTimer} onChange={(e) => setRsTimer(Number(e.target.value))} min={5} max={120}
                        className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded text-sm text-white focus:outline-none focus:border-indigo-500" />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-400 mb-0.5">Min Buy-In</label>
                      <input type="number" value={rsBuyMin} onChange={(e) => setRsBuyMin(Number(e.target.value))} min={1}
                        className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded text-sm text-white focus:outline-none focus:border-indigo-500" />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-400 mb-0.5">Max Buy-In</label>
                      <input type="number" value={rsBuyMax} onChange={(e) => setRsBuyMax(Number(e.target.value))} min={1}
                        className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded text-sm text-white focus:outline-none focus:border-indigo-500" />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-400 mb-0.5">Time Bank (sec)</label>
                      <input type="number" value={rsTimeBank} onChange={(e) => setRsTimeBank(Number(e.target.value))} min={0}
                        className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded text-sm text-white focus:outline-none focus:border-indigo-500" />
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer">
                      <input type="checkbox" checked={rsRIT} onChange={(e) => setRsRIT(e.target.checked)} className="rounded" />
                      Run-it-twice
                    </label>
                    <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer">
                      <input type="checkbox" checked={rsIsDefault} onChange={(e) => setRsIsDefault(e.target.checked)} className="rounded" />
                      Set as default
                    </label>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={handleCreateRuleset} disabled={!rsName.trim()} className="btn-primary text-xs disabled:opacity-50">Create</button>
                    <button onClick={() => setShowCreateRuleset(false)} className="btn-ghost text-xs">Cancel</button>
                  </div>
                </div>
              )}

              {detail.rulesets.length === 0 && !showCreateRuleset ? (
                <p className="text-sm text-slate-400 text-center py-4">No rulesets configured. Tables will use default rules.</p>
              ) : (
                detail.rulesets.map((rs) => (
                  <div key={rs.id} className="p-3 rounded-lg bg-white/5 space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-white">{rs.name}</span>
                      {rs.isDefault && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">DEFAULT</span>
                      )}
                    </div>
                    <RulesSummary rules={rs.rulesJson} />
                    {!rs.isDefault && canManageRulesets && (
                      <button
                        onClick={() => {
                          socket?.emit("club_ruleset_set_default", { clubId: club.id, rulesetId: rs.id });
                          showToast("Setting as default...");
                        }}
                        className="text-xs text-indigo-400 hover:text-indigo-300"
                      >
                        Set as default
                      </button>
                    )}
                  </div>
                ))
              )}
            </div>
          )}

          {tab === "invites" && (
            <div className="space-y-3">
              <div className="flex gap-2">
                <button onClick={handleCreateInvite} className="btn-primary text-xs">
                  + Create Invite Link
                </button>
              </div>
              {detail.invites.length === 0 ? (
                <div className="text-center py-6">
                  <div className="text-2xl mb-2 opacity-20">🔗</div>
                  <p className="text-sm text-slate-400">No active invites.</p>
                  <p className="text-xs text-slate-500 mt-1">Create one to share with potential members.</p>
                </div>
              ) : (
                detail.invites.map((inv) => (
                  <div key={inv.id} className="flex items-center gap-3 p-3 rounded-lg bg-white/5 border border-white/5">
                    <div className="flex-1">
                      <code className="text-sm text-amber-400 font-mono">{inv.inviteCode}</code>
                      <div className="text-[10px] text-slate-400 mt-0.5">
                        Used: {inv.usesCount}/{inv.maxUses ?? "∞"} ·{" "}
                        {inv.expiresAt ? `Expires: ${new Date(inv.expiresAt).toLocaleDateString()}` : "No expiry"}
                      </div>
                    </div>
                    <button
                      onClick={() => {
                        void navigator.clipboard.writeText(inv.inviteCode);
                        showToast(`Copied: ${inv.inviteCode}`);
                      }}
                      className="text-xs text-slate-400 hover:text-white px-2 py-1 rounded hover:bg-white/5 transition-colors"
                    >
                      📋 Copy
                    </button>
                    <button
                      onClick={() => handleRevokeInvite(inv.id)}
                      className="text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded hover:bg-red-500/10 transition-colors"
                    >
                      Revoke
                    </button>
                  </div>
                ))
              )}
            </div>
          )}

          {tab === "settings" && isAdmin && (
            <div className="space-y-6">
              {/* Club Profile */}
              <div>
                <h3 className="text-sm font-semibold text-white mb-3">Club Profile</h3>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Club Name</label>
                    <input type="text" value={editName} onChange={(e) => setEditName(e.target.value)}
                      className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-indigo-500" maxLength={80} />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Description / Announcements</label>
                    <textarea value={editDesc} onChange={(e) => setEditDesc(e.target.value)}
                      className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-indigo-500" rows={3} maxLength={500} />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Badge Color</label>
                    <div className="flex gap-2">
                      {["#6366f1", "#ef4444", "#22c55e", "#f59e0b", "#06b6d4", "#ec4899", "#8b5cf6", "#14b8a6"].map((c) => (
                        <button key={c} onClick={() => setEditColor(c)}
                          className={`w-7 h-7 rounded-lg transition-transform ${editColor === c ? "ring-2 ring-white scale-110" : "opacity-60 hover:opacity-100"}`}
                          style={{ backgroundColor: c }} />
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* Join Policy */}
              <div>
                <h3 className="text-sm font-semibold text-white mb-3">Join Policy</h3>
                <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                  <input type="checkbox" checked={editApproval} onChange={(e) => setEditApproval(e.target.checked)} className="rounded" />
                  Require admin approval for new members
                </label>
                <p className="text-[10px] text-slate-500 mt-1">When disabled, anyone with the club code can join instantly.</p>
              </div>

              {/* Club Monetization (Future) */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-white">Rake / Service Fee</h3>
                  <span className="text-[10px] px-1.5 py-0.5 rounded border border-amber-500/30 bg-amber-500/10 text-amber-300">
                    Coming Soon
                  </span>
                </div>
                <div className="space-y-2 p-3 rounded-lg bg-white/5 border border-white/10">
                  <label className="flex items-center justify-between text-xs text-slate-400">
                    <span className="flex items-center gap-2">
                      <input type="checkbox" checked={false} disabled className="rounded opacity-50 cursor-not-allowed" />
                      Rake enabled
                    </span>
                    <span className="text-[10px] text-slate-500">Default: Off</span>
                  </label>
                  <label className="flex items-center justify-between text-xs text-slate-400">
                    <span className="flex items-center gap-2">
                      <input type="checkbox" checked={false} disabled className="rounded opacity-50 cursor-not-allowed" />
                      Service fee enabled
                    </span>
                    <span className="text-[10px] text-slate-500">Default: Off</span>
                  </label>
                  <p className="text-[10px] text-slate-500">
                    Monetization controls are intentionally disabled. Club play remains virtual-credit only.
                  </p>
                </div>
              </div>

              {/* Club Code & Invite */}
              <div>
                <h3 className="text-sm font-semibold text-white mb-3">Share Club</h3>
                <div className="flex items-center gap-3 p-3 rounded-lg bg-white/5">
                  <div>
                    <div className="text-[10px] text-slate-500 uppercase">Club Code</div>
                    <code className="text-lg font-mono font-bold text-amber-400 tracking-wider">{club.code}</code>
                  </div>
                  <button onClick={() => copyToClipboard(club.code, "club code")}
                    className="ml-auto text-xs text-slate-400 hover:text-white px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 transition-all">
                    Copy Code
                  </button>
                </div>
              </div>

              {/* Save */}
              <div className="flex gap-2 pt-2">
                <button onClick={handleUpdateClub} disabled={!editName.trim()}
                  className="btn-primary text-sm disabled:opacity-50">
                  Save Settings
                </button>
              </div>
            </div>
          )}

          {tab === "audit" && (
            <div className="space-y-1 max-h-[500px] overflow-y-auto">
              {detail.auditLog.length === 0 ? (
                <div className="text-center py-6">
                  <div className="text-2xl mb-2 opacity-20">📋</div>
                  <p className="text-sm text-slate-400">No activity yet.</p>
                </div>
              ) : (
                detail.auditLog
                  .slice()
                  .reverse()
                  .map((entry) => (
                    <div key={entry.id} className="flex items-center gap-3 text-[11px] py-2 px-2 rounded-lg hover:bg-white/[0.03] transition-colors border-b border-white/[0.03] last:border-0">
                      <span className="text-slate-600 text-[10px] shrink-0 w-20">
                        {new Date(entry.createdAt).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                        <br />
                        <span className="text-[9px]">{new Date(entry.createdAt).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</span>
                      </span>
                      <span className={`shrink-0 text-[9px] px-1.5 py-0.5 rounded font-medium uppercase ${
                        entry.actionType.includes("ban") ? "bg-red-500/10 text-red-400" :
                        entry.actionType.includes("kick") ? "bg-red-500/10 text-red-400" :
                        entry.actionType.includes("join") ? "bg-emerald-500/10 text-emerald-400" :
                        entry.actionType.includes("table") ? "bg-cyan-500/10 text-cyan-400" :
                        entry.actionType.includes("role") ? "bg-purple-500/10 text-purple-400" :
                        "bg-white/5 text-slate-400"
                      }`}>
                        {entry.actionType.replace(/_/g, " ")}
                      </span>
                      <span className="text-slate-300 flex-1">{formatAuditAction(entry.actionType, entry.payloadJson)}</span>
                      {entry.actorDisplayName && (
                        <span className="text-slate-500 text-[10px] shrink-0">by {entry.actorDisplayName}</span>
                      )}
                    </div>
                  ))
              )}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

function RulesSummary({ rules }: { rules: ClubRules }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1 text-[11px]">
      <div>
        <span className="text-slate-500">Stakes:</span>{" "}
        <span className="text-slate-300">{rules.stakes.smallBlind}/{rules.stakes.bigBlind}</span>
      </div>
      <div>
        <span className="text-slate-500">Seats:</span>{" "}
        <span className="text-slate-300">{rules.maxSeats}</span>
      </div>
      <div>
        <span className="text-slate-500">Buy-in:</span>{" "}
        <span className="text-slate-300">{rules.buyIn.minBuyIn}–{rules.buyIn.maxBuyIn}</span>
      </div>
      <div>
        <span className="text-slate-500">Timer:</span>{" "}
        <span className="text-slate-300">{rules.time.actionTimeSec}s + {rules.time.timeBankSec}s bank</span>
      </div>
      <div>
        <span className="text-slate-500">Run-it-twice:</span>{" "}
        <span className="text-slate-300">{rules.runit.allowRunItTwice ? "Yes" : "No"}</span>
      </div>
      <div>
        <span className="text-slate-500">Spectators:</span>{" "}
        <span className="text-slate-300">{rules.moderation.allowSpectators ? "Yes" : "No"}</span>
      </div>
      <div>
        <span className="text-slate-500">Auto-deal:</span>{" "}
        <span className="text-slate-300">{rules.dealing.autoDealEnabled ? `${rules.dealing.autoDealDelaySec}s` : "Off"}</span>
      </div>
      <div>
        <span className="text-slate-500">Chat:</span>{" "}
        <span className="text-slate-300">{rules.moderation.chatEnabled ? "On" : "Off"}</span>
      </div>
    </div>
  );
}
