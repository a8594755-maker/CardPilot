import { useState, useCallback } from "react";
import type { Socket } from "socket.io-client";
import type {
  ClubDetailPayload,
  ClubRole,
  ClubRules,
} from "@cardpilot/shared-types";
import { canPerformClubAction } from "@cardpilot/shared-types";

type Tab = "overview" | "members" | "tables" | "rulesets" | "invites" | "audit";

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
  const [showCreateInvite, setShowCreateInvite] = useState(false);

  const { club, myMembership } = detail.detail;
  const myRole = myMembership?.role ?? "member";

  const canManageMembers = canPerformClubAction(myRole, "manage_members");
  const canApproveJoins = canPerformClubAction(myRole, "approve_joins");
  const canCreateTable = canPerformClubAction(myRole, "create_table");
  const canManageRulesets = canPerformClubAction(myRole, "manage_rulesets");
  const canCreateInvite = canPerformClubAction(myRole, "create_invite");
  const canViewAudit = canPerformClubAction(myRole, "view_audit_log");

  const handleCreateTable = useCallback(() => {
    if (!socket || !newTableName.trim()) return;
    socket.emit("club_table_create", {
      clubId: club.id,
      name: newTableName.trim(),
    });
    setShowCreateTable(false);
    setNewTableName("");
    showToast("Creating table...");
  }, [socket, club.id, newTableName, showToast]);

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
    { id: "overview", label: "Overview", show: true },
    { id: "members", label: `Members (${detail.members.length})`, show: true },
    { id: "tables", label: `Tables (${detail.tables.length})`, show: true },
    { id: "rulesets", label: "Rulesets", show: canManageRulesets },
    { id: "invites", label: "Invites", show: canCreateInvite },
    { id: "audit", label: "Audit Log", show: canViewAudit },
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
              <span>{detail.detail.tableCount} tables</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/10 uppercase">{myRole}</span>
            </div>
          </div>
        </div>

        {/* Pending Join Requests Banner */}
        {canApproveJoins && detail.pendingMembers.length > 0 && (
          <div className="glass-card p-3 bg-amber-500/10 border-amber-500/30">
            <div className="text-sm font-semibold text-amber-400 mb-2">
              {detail.pendingMembers.length} pending join request{detail.pendingMembers.length > 1 ? "s" : ""}
            </div>
            <div className="space-y-2">
              {detail.pendingMembers.map((m) => (
                <div key={m.userId} className="flex items-center gap-3 text-sm">
                  <span className="text-white">{m.displayName ?? m.userId.slice(0, 8)}</span>
                  <button onClick={() => handleApprove(m.userId)} className="btn-success text-xs !py-1 !px-2">
                    Approve
                  </button>
                  <button onClick={() => handleReject(m.userId)} className="btn-secondary text-xs !py-1 !px-2">
                    Reject
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
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-xl bg-indigo-500/10 border border-indigo-500/20 p-3 text-center">
                  <div className="text-lg font-bold text-indigo-300">{detail.detail.memberCount}</div>
                  <div className="text-[10px] text-slate-400 uppercase tracking-wider">Members</div>
                </div>
                <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/20 p-3 text-center">
                  <div className="text-lg font-bold text-emerald-300">{detail.tables.filter((t) => t.status === "open").length}</div>
                  <div className="text-[10px] text-slate-400 uppercase tracking-wider">Active Tables</div>
                </div>
                <div className="rounded-xl bg-amber-500/10 border border-amber-500/20 p-3 text-center">
                  <div className="text-lg font-bold text-amber-300">{detail.detail.tableCount}</div>
                  <div className="text-[10px] text-slate-400 uppercase tracking-wider">Total Tables</div>
                </div>
              </div>

              {/* Active tables quick-join */}
              {detail.tables.filter((t) => t.status === "open").length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-slate-300 mb-2">Active Tables</h3>
                  <div className="space-y-2">
                    {detail.tables.filter((t) => t.status === "open").map((t) => (
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

              {/* Description */}
              <div>
                <h3 className="text-sm font-semibold text-slate-300 mb-1">About</h3>
                <p className="text-sm text-slate-400">{club.description || "No description set."}</p>
              </div>

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
            </div>
          )}

          {tab === "members" && (
            <div className="space-y-2">
              {detail.members.map((m) => (
                <div key={m.userId} className="flex items-center gap-3 p-2 rounded-lg hover:bg-white/5">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-[10px] font-bold text-white uppercase">
                    {(m.displayName ?? m.nicknameInClub ?? "?")[0]}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-white truncate">{m.displayName ?? m.nicknameInClub ?? m.userId.slice(0, 8)}</div>
                    <div className="text-[10px] text-slate-500">{m.role} · joined {new Date(m.createdAt).toLocaleDateString()}</div>
                  </div>
                  {canManageMembers && m.userId !== userId && m.role !== "owner" && (
                    <div className="flex gap-1">
                      <select
                        value={m.role}
                        onChange={(e) => handleRoleChange(m.userId, e.target.value as ClubRole)}
                        className="text-[10px] bg-white/5 border border-white/10 rounded px-1 py-0.5 text-slate-300"
                      >
                        <option value="member">member</option>
                        <option value="mod">mod</option>
                        <option value="host">host</option>
                        <option value="admin">admin</option>
                      </select>
                      <button onClick={() => handleKick(m.userId)} className="text-[10px] text-red-400 hover:text-red-300 px-1">
                        Kick
                      </button>
                      <button onClick={() => handleBan(m.userId)} className="text-[10px] text-red-400 hover:text-red-300 px-1">
                        Ban
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {tab === "tables" && (
            <div className="space-y-3">
              {canCreateTable && (
                <div className="flex gap-2">
                  {showCreateTable ? (
                    <>
                      <input
                        type="text"
                        placeholder="Table name"
                        value={newTableName}
                        onChange={(e) => setNewTableName(e.target.value)}
                        className="flex-1 px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                        maxLength={80}
                        autoFocus
                      />
                      <button onClick={handleCreateTable} disabled={!newTableName.trim()} className="btn-primary text-xs">
                        Create
                      </button>
                      <button onClick={() => setShowCreateTable(false)} className="btn-secondary text-xs">
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button onClick={() => setShowCreateTable(true)} className="btn-primary text-xs">
                      + New Table
                    </button>
                  )}
                </div>
              )}

              {detail.tables.length === 0 ? (
                <p className="text-sm text-slate-400 text-center py-4">No tables open.</p>
              ) : (
                detail.tables.map((t) => (
                  <div key={t.id} className="flex items-center gap-3 p-3 rounded-lg bg-white/5">
                    <div className="flex-1">
                      <div className="text-sm font-medium text-white">{t.name}</div>
                      <div className="text-[10px] text-slate-400">
                        {t.stakes ?? "—"} · {t.playerCount ?? 0}/{t.maxPlayers ?? "?"} players ·{" "}
                        <span className={t.status === "open" ? "text-emerald-400" : "text-amber-400"}>{t.status}</span>
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
                        onClick={() => handleCloseTable(t.id)}
                        className="text-[10px] text-red-400 hover:text-red-300 px-2"
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
              <p className="text-xs text-slate-500">
                Rulesets define table rules. The default ruleset is used when creating tables without specifying one.
              </p>
              {detail.rulesets.length === 0 ? (
                <p className="text-sm text-slate-400 text-center py-4">No rulesets configured. Tables will use default rules.</p>
              ) : (
                detail.rulesets.map((rs) => (
                  <div key={rs.id} className="p-3 rounded-lg bg-white/5 space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-white">{rs.name}</span>
                      {rs.isDefault && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300">DEFAULT</span>
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
                <p className="text-sm text-slate-400 text-center py-4">No active invites.</p>
              ) : (
                detail.invites.map((inv) => (
                  <div key={inv.id} className="flex items-center gap-3 p-3 rounded-lg bg-white/5">
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
                      className="text-xs text-slate-400 hover:text-white px-2"
                    >
                      Copy
                    </button>
                    <button
                      onClick={() => handleRevokeInvite(inv.id)}
                      className="text-xs text-red-400 hover:text-red-300 px-2"
                    >
                      Revoke
                    </button>
                  </div>
                ))
              )}
            </div>
          )}

          {tab === "audit" && (
            <div className="space-y-1 max-h-96 overflow-y-auto">
              {detail.auditLog.length === 0 ? (
                <p className="text-sm text-slate-400 text-center py-4">No audit log entries.</p>
              ) : (
                detail.auditLog
                  .slice()
                  .reverse()
                  .map((entry) => (
                    <div key={entry.id} className="flex gap-2 text-[11px] py-1 border-b border-white/5">
                      <span className="text-slate-500 whitespace-nowrap">
                        {new Date(entry.createdAt).toLocaleString()}
                      </span>
                      <span className="text-indigo-400 font-mono">{entry.actionType}</span>
                      <span className="text-slate-400 truncate">
                        {JSON.stringify(entry.payloadJson).slice(0, 100)}
                      </span>
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
