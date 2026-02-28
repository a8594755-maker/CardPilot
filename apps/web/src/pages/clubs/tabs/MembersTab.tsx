import React, { useMemo, useState } from "react";
import type {
  Club,
  ClubMember,
  ClubRole,
} from "@cardpilot/shared-types";
import { RoleBadge } from "../shared";
import type { ClubPermissions } from "../hooks/useClubPermissions";
import type { ClubSocketActions } from "../hooks/useClubSocket";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ONLINE_THRESHOLD_MIN = 15;

function isRecentlyOnline(lastSeenAt: string): boolean {
  return Date.now() - new Date(lastSeenAt).getTime() < ONLINE_THRESHOLD_MIN * 60 * 1000;
}

const ROLE_RANK: Record<string, number> = { owner: 3, admin: 2, member: 1 };

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface MembersTabProps {
  club: Club;
  members: ClubMember[];
  userId: string;
  permissions: ClubPermissions;
  actions: ClubSocketActions;
  onGrantCredits: (userId: string, displayName: string) => void;
  onKickMember: (userId: string, displayName: string) => void;
  onBanMember: (userId: string, displayName: string) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const MembersTab = React.memo(function MembersTab({
  club,
  members,
  userId,
  permissions,
  actions,
  onGrantCredits,
  onKickMember,
  onBanMember,
}: MembersTabProps) {
  // ---------------------------------------------------------------------------
  // Selection state
  // ---------------------------------------------------------------------------
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [searchTerm, setSearchTerm] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("all");
  const [bulkCreditsAmount, setBulkCreditsAmount] = useState("");
  const [confirmingKick, setConfirmingKick] = useState(false);

  const toggleSelect = (uid: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(uid)) next.delete(uid);
      else next.add(uid);
      return next;
    });
  };

  // ---------------------------------------------------------------------------
  // Derived data
  // ---------------------------------------------------------------------------
  const onlineCount = useMemo(
    () => members.filter((m) => isRecentlyOnline(m.lastSeenAt)).length,
    [members],
  );

  const sortedMembers = useMemo(
    () =>
      members.slice().sort((a, b) => (ROLE_RANK[b.role] ?? 0) - (ROLE_RANK[a.role] ?? 0)),
    [members],
  );

  const selectableMembers = useMemo(
    () => sortedMembers.filter((m) => m.userId !== userId && m.role !== "owner"),
    [sortedMembers, userId],
  );

  const selectAll = () => {
    if (selected.size === selectableMembers.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(selectableMembers.map((m) => m.userId)));
    }
  };

  const filteredMembers = useMemo(() => {
    let result = sortedMembers;
    if (roleFilter !== "all") {
      result = result.filter((m) => m.role === roleFilter);
    }
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      result = result.filter((m) => {
        const name = (m.displayName ?? m.nicknameInClub ?? m.userId).toLowerCase();
        return name.includes(term);
      });
    }
    return result;
  }, [sortedMembers, roleFilter, searchTerm]);

  // ---------------------------------------------------------------------------
  // Bulk action handlers
  // ---------------------------------------------------------------------------
  const handleBulkGrantCredits = () => {
    const amount = parseInt(bulkCreditsAmount, 10);
    if (!amount || amount <= 0) return;
    actions.bulkGrantCredits(Array.from(selected), amount);
    setBulkCreditsAmount("");
    setSelected(new Set());
  };

  const handleBulkRoleChange = (newRole: ClubRole) => {
    actions.bulkRoleChange(Array.from(selected), newRole);
    setSelected(new Set());
  };

  const handleBulkKick = () => {
    if (!confirmingKick) {
      setConfirmingKick(true);
      return;
    }
    actions.bulkKick(Array.from(selected));
    setSelected(new Set());
    setConfirmingKick(false);
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  const ROLE_FILTERS = ["all", "owner", "admin", "member"] as const;

  return (
    <div className="space-y-1">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs text-slate-500">
          {members.length} members · {onlineCount} online
        </div>
        {permissions.canManageMembers && selectableMembers.length > 0 && (
          <button
            onClick={selectAll}
            className="text-[10px] text-cyan-400 hover:text-cyan-300 transition-colors"
          >
            {selected.size === selectableMembers.length ? "Deselect all" : "Select all"}
          </button>
        )}
      </div>

      {/* Search bar */}
      <div className="mb-2">
        <input
          type="text"
          placeholder="Search members..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full text-xs bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-slate-300 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 transition-colors"
        />
      </div>

      {/* Role filter buttons */}
      <div className="flex gap-1 mb-3">
        {ROLE_FILTERS.map((role) => (
          <button
            key={role}
            onClick={() => setRoleFilter(role)}
            className={`text-[10px] px-2.5 py-1 rounded-full transition-colors capitalize ${
              roleFilter === role
                ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30"
                : "bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10"
            }`}
          >
            {role === "all" ? "All" : role.charAt(0).toUpperCase() + role.slice(1)}
          </button>
        ))}
      </div>

      {/* Members list */}
      {filteredMembers.map((m) => {
        const online = isRecentlyOnline(m.lastSeenAt);
        const displayName = m.displayName ?? m.nicknameInClub ?? m.userId.slice(0, 8);
        const isSelectable =
          permissions.canManageMembers && m.userId !== userId && m.role !== "owner";

        return (
          <div
            key={m.userId}
            className={`flex items-center gap-3 p-2 rounded-lg hover:bg-white/5 transition-colors ${
              selected.has(m.userId) ? "bg-cyan-500/10 border border-cyan-500/20" : ""
            }`}
          >
            {/* Checkbox */}
            {isSelectable && (
              <input
                type="checkbox"
                checked={selected.has(m.userId)}
                onChange={() => toggleSelect(m.userId)}
                className="w-3.5 h-3.5 rounded border-white/20 bg-white/5 text-cyan-500 focus:ring-cyan-500/30 cursor-pointer shrink-0"
              />
            )}

            {/* Avatar with online indicator */}
            <div className="relative">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-[10px] font-bold text-white uppercase">
                {(displayName.trim().charAt(0) || "U").toUpperCase()}
              </div>
              {online && (
                <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-slate-900" />
              )}
            </div>

            {/* Name, role, join date */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm text-white truncate">{displayName}</span>
                <RoleBadge role={m.role} size="sm" />
                {m.userId === userId && (
                  <span className="text-[9px] text-cyan-400">(you)</span>
                )}
              </div>
              <div className="text-[10px] text-slate-500">
                joined {new Date(m.createdAt).toLocaleDateString()}
                {online ? (
                  <span className="text-emerald-400 ml-2">● online</span>
                ) : (
                  <span className="ml-2">
                    last seen {new Date(m.lastSeenAt).toLocaleDateString()}
                  </span>
                )}
              </div>
            </div>

            {/* Credit balance */}
            <div className="text-right shrink-0 mr-1">
              <div className="text-xs font-mono font-semibold text-amber-400">
                {(m.balance ?? 0).toLocaleString()}
              </div>
              <div className="text-[9px] text-slate-500">credits</div>
            </div>

            {/* Admin actions */}
            {permissions.canManageMembers && m.role !== "owner" && (
              <div className="flex gap-1 items-center shrink-0">
                {m.userId !== userId && (
                  <select
                    value={m.role}
                    onChange={(e) =>
                      actions.changeRole(m.userId, e.target.value as ClubRole)
                    }
                    className="text-[10px] bg-white/5 border border-white/10 rounded px-1.5 py-1 text-slate-300 cursor-pointer"
                  >
                    <option value="member">member</option>
                    <option value="admin">admin</option>
                  </select>
                )}
                <button
                  onClick={() => onGrantCredits(m.userId, displayName)}
                  className="text-[10px] text-emerald-400 hover:text-emerald-300 px-1.5 py-1 rounded hover:bg-emerald-500/10 transition-colors"
                  title="Grant credits"
                >
                  +$
                </button>
                {m.userId !== userId && (
                  <>
                    <button
                      onClick={() => onKickMember(m.userId, displayName)}
                      className="text-[10px] text-red-400 hover:text-red-300 px-1.5 py-1 rounded hover:bg-red-500/10 transition-colors"
                    >
                      Kick
                    </button>
                    <button
                      onClick={() => onBanMember(m.userId, displayName)}
                      className="text-[10px] text-red-400 hover:text-red-300 px-1.5 py-1 rounded hover:bg-red-500/10 transition-colors"
                    >
                      Ban
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        );
      })}

      {/* Empty state for filtered results */}
      {filteredMembers.length === 0 && (
        <div className="text-center py-6 text-xs text-slate-500">
          No members match the current filters.
        </div>
      )}

      {/* Bulk Operations Bar */}
      {selected.size > 0 && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-4 py-2.5 rounded-xl bg-slate-900/80 backdrop-blur-xl border border-white/10 shadow-2xl shadow-black/40">
          {/* Selection count */}
          <span className="text-xs font-medium text-cyan-400 whitespace-nowrap">
            {selected.size} selected
          </span>

          <div className="w-px h-5 bg-white/10" />

          {/* Grant Credits */}
          <div className="flex items-center gap-1">
            <input
              type="number"
              min="1"
              placeholder="Amt"
              value={bulkCreditsAmount}
              onChange={(e) => setBulkCreditsAmount(e.target.value)}
              className="w-16 text-[10px] bg-white/5 border border-white/10 rounded px-1.5 py-1 text-slate-300 placeholder-slate-500 focus:outline-none focus:border-emerald-500/50"
            />
            <button
              onClick={handleBulkGrantCredits}
              disabled={!bulkCreditsAmount || parseInt(bulkCreditsAmount, 10) <= 0}
              className="text-[10px] text-emerald-400 hover:text-emerald-300 px-2 py-1 rounded hover:bg-emerald-500/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
            >
              Grant Credits
            </button>
          </div>

          <div className="w-px h-5 bg-white/10" />

          {/* Change Role */}
          <select
            defaultValue=""
            onChange={(e) => {
              if (e.target.value) handleBulkRoleChange(e.target.value as ClubRole);
              e.target.value = "";
            }}
            className="text-[10px] bg-white/5 border border-white/10 rounded px-1.5 py-1 text-slate-300 cursor-pointer"
          >
            <option value="" disabled>
              Change Role
            </option>
            <option value="member">Member</option>
            <option value="admin">Admin</option>
          </select>

          <div className="w-px h-5 bg-white/10" />

          {/* Kick */}
          <button
            onClick={handleBulkKick}
            className={`text-[10px] px-2 py-1 rounded transition-colors whitespace-nowrap ${
              confirmingKick
                ? "bg-red-500/20 text-red-300 border border-red-500/30"
                : "text-red-400 hover:text-red-300 hover:bg-red-500/10"
            }`}
          >
            {confirmingKick ? "Confirm Kick?" : "Kick"}
          </button>

          <div className="w-px h-5 bg-white/10" />

          {/* Clear Selection */}
          <button
            onClick={() => {
              setSelected(new Set());
              setConfirmingKick(false);
            }}
            className="text-[10px] text-slate-400 hover:text-slate-300 px-2 py-1 rounded hover:bg-white/5 transition-colors whitespace-nowrap"
          >
            Clear
          </button>
        </div>
      )}
    </div>
  );
});

export default MembersTab;
