import React, { memo } from "react";
import type { ClubInvite } from "@cardpilot/shared-types";
import { EmptyState } from "../shared";
import type { ClubSocketActions } from "../hooks/useClubSocket";

// ── Props ──

interface InvitesTabProps {
  invites: ClubInvite[];
  actions: ClubSocketActions;
  showToast: (msg: string) => void;
}

// ── Component ──

export const InvitesTab = memo(function InvitesTab({
  invites,
  actions,
  showToast,
}: InvitesTabProps) {
  function handleCopy(code: string) {
    navigator.clipboard.writeText(code).then(() => {
      showToast("Invite code copied!");
    });
  }

  const activeInvites = invites.filter((inv) => !inv.revoked);

  return (
    <div className="space-y-4">
      {/* ── Create Invite Button ── */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Invite Links</h3>
        <button
          onClick={() => actions.createInvite()}
          className="rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-cyan-500 transition-colors"
        >
          Create Invite
        </button>
      </div>

      {/* ── Invite List ── */}
      {activeInvites.length === 0 ? (
        <EmptyState
          icon="🔗"
          title="No active invites"
          description="Create an invite link to share with potential members."
        />
      ) : (
        <div className="space-y-3">
          {activeInvites.map((inv) => (
            <div
              key={inv.id}
              className="rounded-lg border border-slate-700 bg-slate-800/50 px-4 py-3"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0 flex-1 space-y-1">
                  {/* Invite code */}
                  <div className="font-mono text-sm font-bold text-amber-400 truncate">
                    {inv.inviteCode}
                  </div>

                  {/* Meta */}
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
                    <span>
                      Used:{" "}
                      <span className="text-slate-400">
                        {inv.usesCount}
                        {inv.maxUses !== null ? ` / ${inv.maxUses}` : ""}
                      </span>
                    </span>
                    {inv.expiresAt && (
                      <span>
                        Expires:{" "}
                        <span className="text-slate-400">
                          {new Date(inv.expiresAt).toLocaleDateString()}
                        </span>
                      </span>
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => handleCopy(inv.inviteCode)}
                    className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
                  >
                    Copy
                  </button>
                  <button
                    onClick={() => actions.revokeInvite(inv.id)}
                    className="rounded-lg border border-red-800/40 bg-red-900/20 px-3 py-1.5 text-xs text-red-400 hover:bg-red-900/40 transition-colors"
                  >
                    Revoke
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
});

export default InvitesTab;
