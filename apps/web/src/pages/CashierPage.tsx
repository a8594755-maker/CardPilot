import { isRealMoneyEnabled } from "../lib/feature-flags";

export function CashierPage() {
  const realMoneyEnabled = isRealMoneyEnabled();

  return (
    <main className="flex-1 p-6 overflow-y-auto">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="glass-card p-4 bg-amber-500/5 border-amber-500/20 text-center">
          <h2 className="text-xl font-bold text-white">Cashier</h2>
          <p className="text-xs text-amber-300 mt-1">
            CardPilot is a play-money training tool. Real-money features are not active.
          </p>
        </div>

        <section className="glass-card p-5 space-y-3">
          <h3 className="text-sm font-semibold text-white">Virtual Credits</h3>
          <p className="text-xs text-slate-400">
            Existing virtual-credit actions remain available through room and club workflows.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="rounded-lg border border-white/10 bg-white/5 p-3">
              <p className="text-[11px] uppercase text-slate-500">Buy-in / Rebuy</p>
              <p className="text-sm text-slate-300 mt-1">Available at table join and host-approved rebuy flow.</p>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/5 p-3">
              <p className="text-[11px] uppercase text-slate-500">Club Credits</p>
              <p className="text-sm text-slate-300 mt-1">Managed via club credit grant/deduct controls.</p>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/5 p-3">
              <p className="text-[11px] uppercase text-slate-500">Cash Value</p>
              <p className="text-sm text-amber-300 mt-1">No real-money value or redemption path.</p>
            </div>
          </div>
        </section>

        <section className="glass-card p-5 space-y-4 border border-white/10">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">Real Money</h3>
            <span className="text-[10px] px-2 py-1 rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-300">
              Coming Soon
            </span>
          </div>

          {!realMoneyEnabled && (
            <p className="text-xs text-slate-400">
              Feature flag <code className="text-amber-300">VITE_ENABLE_REAL_MONEY=false</code>. UI remains disabled.
            </p>
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="rounded-lg border border-white/10 bg-white/5 p-4 space-y-2">
              <h4 className="text-sm text-white font-medium">Deposit</h4>
              <p className="text-xs text-slate-400">Add funds to your wallet.</p>
              <button
                type="button"
                disabled
                className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-slate-500 cursor-not-allowed"
              >
                Deposit (Coming Soon)
              </button>
            </div>

            <div className="rounded-lg border border-white/10 bg-white/5 p-4 space-y-2">
              <h4 className="text-sm text-white font-medium">Withdraw</h4>
              <p className="text-xs text-slate-400">Withdraw available wallet balance.</p>
              <button
                type="button"
                disabled
                className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-slate-500 cursor-not-allowed"
              >
                Withdraw (Coming Soon)
              </button>
            </div>

            <div className="rounded-lg border border-white/10 bg-white/5 p-4 space-y-2">
              <h4 className="text-sm text-white font-medium">Transactions</h4>
              <p className="text-xs text-slate-500">Coming soon</p>
              <div className="rounded border border-dashed border-white/10 p-3 text-[11px] text-slate-500 text-center">
                Coming soon
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-white/10 bg-black/20 p-3 space-y-1">
            <h4 className="text-xs uppercase tracking-wide text-slate-400">Compliance Notices</h4>
            <ul className="text-xs text-slate-500 list-disc list-inside">
              <li>KYC verification — coming soon</li>
              <li>Region checks — coming soon</li>
              <li>Age checks — coming soon</li>
            </ul>
          </div>
        </section>
      </div>
    </main>
  );
}
