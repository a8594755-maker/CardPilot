import React from 'react';
import type { ClubPermissions } from '../hooks/useClubPermissions';
import type { ClubSocketActions } from '../hooks/useClubSocket';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface CreditsTabProps {
  creditBalance: number;
  permissions: ClubPermissions;
  actions: ClubSocketActions;
  onGrantCredits: () => void;
  onAdjustCredits: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const CreditsTab = React.memo(function CreditsTab({
  creditBalance,
  permissions,
  actions,
  onGrantCredits,
  onAdjustCredits,
}: CreditsTabProps) {
  return (
    <div className="space-y-4">
      {/* Balance display card */}
      <div className="flex items-center justify-between rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-emerald-300">
            My Club Credits
          </div>
          <div className="text-2xl font-bold text-white font-mono">
            {creditBalance.toLocaleString()}
          </div>
        </div>
        <button onClick={() => actions.refreshCredits()} className="btn-secondary text-xs">
          Refresh
        </button>
      </div>

      {/* Credit info section */}
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-3">
        <h3 className="text-base font-semibold text-white">Credits</h3>
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-400">Virtual Credits</p>
          <p className="text-sm text-slate-300">
            Existing credit actions remain available through room and club workflows.
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-400">Buy-in / Rebuy</p>
          <p className="text-sm text-slate-300">
            Club tables are hostless: rebuys auto-approve if table limits and club funds allow.
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-400">Club Credits</p>
          <p className="text-sm text-slate-300">Managed via club credit grant/deduct controls.</p>
        </div>
      </div>

      {/* Admin controls */}
      {permissions.isAdmin && (
        <div className="flex gap-2">
          <button onClick={onGrantCredits} className="btn-primary text-xs">
            Grant Credits
          </button>
          <button onClick={onAdjustCredits} className="btn-secondary text-xs">
            Adjust Credits
          </button>
        </div>
      )}
    </div>
  );
});

export default CreditsTab;
