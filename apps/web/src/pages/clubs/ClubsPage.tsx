import { useState, useCallback } from "react";
import type { Socket } from "socket.io-client";
import type {
  ClubListItem,
  ClubDetail,
  ClubMember,
  ClubInvite,
  ClubRuleset,
  ClubTable,
  ClubAuditLogEntry,
  ClubDetailPayload,
  ClubRole,
} from "@cardpilot/shared-types";
import { canPerformClubAction } from "@cardpilot/shared-types";
import { ClubDetailView } from "./ClubDetailView";

interface ClubsPageProps {
  socket: Socket | null;
  isConnected: boolean;
  userId: string;
  clubs: ClubListItem[];
  clubsLoading: boolean;
  clubDetail: ClubDetailPayload | null;
  onSelectClub: (clubId: string) => void;
  onRefreshClubs: () => void;
  onJoinClubTable: (roomCode: string) => void;
  showToast: (msg: string) => void;
}

export function ClubsPage({
  socket,
  isConnected,
  userId,
  clubs,
  clubsLoading,
  clubDetail,
  onSelectClub,
  onRefreshClubs,
  onJoinClubTable,
  showToast,
}: ClubsPageProps) {
  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createDesc, setCreateDesc] = useState("");
  const [createRequireApproval, setCreateRequireApproval] = useState(true);
  const [createColor, setCreateColor] = useState("#6366f1");
  const [joinCode, setJoinCode] = useState("");
  const [inviteCode, setInviteCode] = useState("");

  const handleCreate = useCallback(() => {
    if (!socket || !createName.trim()) return;
    socket.emit("club_create", {
      name: createName.trim(),
      description: createDesc.trim(),
      requireApprovalToJoin: createRequireApproval,
      badgeColor: createColor,
    });
    setShowCreate(false);
    setCreateName("");
    setCreateDesc("");
    showToast("Creating club...");
  }, [socket, createName, createDesc, createRequireApproval, createColor, showToast]);

  const handleJoin = useCallback(() => {
    if (!socket || !joinCode.trim()) return;
    socket.emit("club_join_request", {
      clubCode: joinCode.trim().toUpperCase(),
      inviteCode: inviteCode.trim() || undefined,
    });
    setJoinCode("");
    setInviteCode("");
    showToast("Joining club...");
  }, [socket, joinCode, inviteCode, showToast]);

  // If viewing a club detail
  if (clubDetail) {
    return (
      <ClubDetailView
        socket={socket}
        isConnected={isConnected}
        userId={userId}
        detail={clubDetail}
        onBack={() => onSelectClub("")}
        onJoinTable={onJoinClubTable}
        showToast={showToast}
      />
    );
  }

  return (
    <main className="flex-1 p-6 overflow-y-auto">
      <div className="max-w-3xl mx-auto space-y-6">
        {/* Disclaimer */}
        <div className="glass-card p-3 bg-amber-500/5 border-amber-500/20 text-xs text-amber-400/80 text-center">
          🎓 CardPilot is a <strong>play-money training tool</strong> — not real-money gambling. Clubs use virtual credits only.
        </div>

        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-white">My Clubs</h2>
          <div className="flex gap-2">
            <button
              onClick={onRefreshClubs}
              disabled={!isConnected || clubsLoading}
              className="px-3 py-1.5 rounded-lg text-xs font-medium bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10 transition-all disabled:opacity-50"
              title="Refresh clubs"
            >
              {clubsLoading ? "Syncing\u2026" : "\u21bb Refresh"}
            </button>
            <button
              onClick={() => setShowCreate(true)}
              disabled={!isConnected}
              className="btn-primary text-sm"
            >
              + Create Club
            </button>
          </div>
        </div>

        {/* Join Club */}
        <div className="glass-card p-4">
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Join a Club</h3>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Club code (e.g. ABC123)"
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
              className="flex-1 px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              maxLength={8}
            />
            <input
              type="text"
              placeholder="Invite code (optional)"
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
              className="flex-1 px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              maxLength={16}
            />
            <button
              onClick={handleJoin}
              disabled={!isConnected || !joinCode.trim()}
              className="btn-primary text-sm whitespace-nowrap"
            >
              Join
            </button>
          </div>
        </div>

        {/* Club List */}
        {clubsLoading && clubs.length === 0 ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="glass-card p-4 animate-pulse">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-white/10" />
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-32 rounded bg-white/10" />
                    <div className="h-3 w-48 rounded bg-white/5" />
                  </div>
                  <div className="space-y-1 text-right">
                    <div className="h-3 w-16 rounded bg-white/5" />
                    <div className="h-3 w-12 rounded bg-white/5" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : clubs.length === 0 ? (
          <div className="glass-card p-8 text-center">
            <p className="text-slate-400 text-sm mb-2">You haven't joined any clubs yet.</p>
            <p className="text-slate-500 text-xs">Create one or join using a club code above.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {clubs.map((club) => (
              <button
                key={club.id}
                onClick={() => onSelectClub(club.id)}
                className="glass-card p-4 w-full text-left hover:bg-white/5 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div
                    className="w-10 h-10 rounded-xl flex items-center justify-center text-lg font-bold text-white shadow-lg"
                    style={{ backgroundColor: club.badgeColor ?? "#6366f1" }}
                  >
                    {club.name[0]?.toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-white truncate">{club.name}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/10 text-slate-400 uppercase">
                        {club.myRole}
                      </span>
                    </div>
                    <div className="text-xs text-slate-400 mt-0.5">
                      {club.description ? (
                        <span className="truncate block max-w-sm">{club.description}</span>
                      ) : null}
                    </div>
                  </div>
                  <div className="text-right text-xs text-slate-400 space-y-1">
                    <div>{club.memberCount} members</div>
                    <div>{club.tableCount} tables</div>
                  </div>
                  <span className="text-slate-600 text-sm">→</span>
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Create Club Modal */}
        {showCreate && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="glass-card p-6 w-full max-w-md mx-4 space-y-4">
              <h3 className="text-lg font-bold text-white">Create Club</h3>

              <div>
                <label className="block text-xs text-slate-400 mb-1">Club Name *</label>
                <input
                  type="text"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  placeholder="e.g. NLH Study Group"
                  maxLength={80}
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">Description</label>
                <textarea
                  value={createDesc}
                  onChange={(e) => setCreateDesc(e.target.value)}
                  className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  placeholder="Short description of your club"
                  rows={2}
                  maxLength={500}
                />
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">Badge Color</label>
                <div className="flex gap-2">
                  {["#6366f1", "#ef4444", "#22c55e", "#f59e0b", "#06b6d4", "#ec4899"].map((c) => (
                    <button
                      key={c}
                      onClick={() => setCreateColor(c)}
                      className={`w-8 h-8 rounded-lg transition-transform ${createColor === c ? "ring-2 ring-white scale-110" : "opacity-60 hover:opacity-100"}`}
                      style={{ backgroundColor: c }}
                    />
                  ))}
                </div>
              </div>

              <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={createRequireApproval}
                  onChange={(e) => setCreateRequireApproval(e.target.checked)}
                  className="rounded"
                />
                Require approval to join
              </label>

              <div className="flex gap-2 pt-2">
                <button onClick={() => setShowCreate(false)} className="flex-1 btn-secondary text-sm">
                  Cancel
                </button>
                <button
                  onClick={handleCreate}
                  disabled={!createName.trim()}
                  className="flex-1 btn-primary text-sm disabled:opacity-50"
                >
                  Create
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
