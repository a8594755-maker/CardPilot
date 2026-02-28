import React, { memo, useEffect, useState } from "react";
import type { Club } from "@cardpilot/shared-types";
import type { ClubPermissions } from "../hooks/useClubPermissions";
import type { ClubSocketActions } from "../hooks/useClubSocket";

// ── Props ──

interface SettingsTabProps {
  club: Club;
  permissions: ClubPermissions;
  actions: ClubSocketActions;
  showToast: (msg: string) => void;
}

// ── Badge color palette ──

const BADGE_COLORS = [
  "#6366f1", // indigo
  "#8b5cf6", // violet
  "#ec4899", // pink
  "#ef4444", // red
  "#f97316", // orange
  "#eab308", // yellow
  "#22c55e", // green
  "#06b6d4", // cyan
];

// ── Component ──

export const SettingsTab = memo(function SettingsTab({
  club,
  permissions,
  actions,
  showToast,
}: SettingsTabProps) {
  // ── Editable state (initialized from club) ──
  const [editName, setEditName] = useState(club.name);
  const [editDesc, setEditDesc] = useState(club.description);
  const [editApproval, setEditApproval] = useState(club.requireApprovalToJoin);
  const [editColor, setEditColor] = useState(club.badgeColor ?? BADGE_COLORS[0]);

  // Re-sync when the club prop changes (e.g. after a socket update)
  useEffect(() => {
    setEditName(club.name);
    setEditDesc(club.description);
    setEditApproval(club.requireApprovalToJoin);
    setEditColor(club.badgeColor ?? BADGE_COLORS[0]);
  }, [club]);

  // ── Handlers ──

  function handleSave() {
    actions.updateClub({
      name: editName.trim() || club.name,
      description: editDesc.trim(),
      requireApprovalToJoin: editApproval,
      badgeColor: editColor,
    });
  }

  function handleCopyCode() {
    navigator.clipboard.writeText(club.code).then(() => {
      showToast("Club code copied!");
    });
  }

  // ── Render ──

  return (
    <div className="space-y-8 max-w-lg">
      {/* ── Club Profile ── */}
      <section className="space-y-4">
        <h3 className="text-sm font-semibold text-slate-300">Club Profile</h3>

        {/* Name */}
        <div>
          <label className="mb-1 block text-xs text-slate-400">Name</label>
          <input
            type="text"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            disabled={!permissions.isOwner}
            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed"
          />
        </div>

        {/* Description */}
        <div>
          <label className="mb-1 block text-xs text-slate-400">Description</label>
          <textarea
            value={editDesc}
            onChange={(e) => setEditDesc(e.target.value)}
            rows={3}
            disabled={!permissions.isOwner}
            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500 resize-none disabled:opacity-50 disabled:cursor-not-allowed"
          />
        </div>

        {/* Badge Color Picker */}
        <div>
          <label className="mb-2 block text-xs text-slate-400">Badge Color</label>
          <div className="flex flex-wrap gap-2">
            {BADGE_COLORS.map((color) => (
              <button
                key={color}
                onClick={() => setEditColor(color)}
                disabled={!permissions.isOwner}
                className={`h-8 w-8 rounded-lg border-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
                  editColor === color
                    ? "border-white scale-110 shadow-lg"
                    : "border-transparent hover:border-slate-500"
                }`}
                style={{ backgroundColor: color }}
                aria-label={`Select color ${color}`}
              />
            ))}
          </div>
        </div>
      </section>

      {/* ── Join Policy ── */}
      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-slate-300">Join Policy</h3>
        <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
          <input
            type="checkbox"
            checked={editApproval}
            onChange={(e) => setEditApproval(e.target.checked)}
            disabled={!permissions.isOwner}
            className="rounded border-slate-600 bg-slate-900 text-cyan-500 focus:ring-cyan-500 disabled:opacity-50"
          />
          Require approval to join
        </label>
      </section>

      {/* ── Rake / Service Fee ── */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-slate-300">Rake / Service Fee</h3>
          <span className="rounded-full bg-slate-700 px-2 py-0.5 text-[10px] font-medium text-slate-400">
            Coming Soon
          </span>
        </div>
        <div className="rounded-lg border border-slate-700 bg-slate-800/30 px-4 py-3">
          <p className="text-xs text-slate-500">
            Rake and service fee configuration will be available in a future update.
          </p>
        </div>
      </section>

      {/* ── Share Club ── */}
      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-slate-300">Share Club</h3>
        <div className="flex items-center gap-3">
          <div className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2">
            <span className="font-mono text-sm font-bold text-amber-400">{club.code}</span>
          </div>
          <button
            onClick={handleCopyCode}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-400 hover:text-slate-200 transition-colors"
          >
            Copy
          </button>
        </div>
        <p className="text-[11px] text-slate-500">
          Share this code with others so they can join your club.
        </p>
      </section>

      {/* ── Save Button ── */}
      {permissions.isOwner && (
        <button
          onClick={handleSave}
          className="w-full rounded-lg bg-cyan-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-cyan-500 transition-colors"
        >
          Save Settings
        </button>
      )}
    </div>
  );
});

export default SettingsTab;
