import React from 'react';
import type { ClubWalletTransaction } from '@cardpilot/shared-types';
import { StatusBadge, EmptyState } from '../shared';
import type { ClubSocketActions } from '../hooks/useClubSocket';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface TransactionsTabProps {
  transactions: ClubWalletTransaction[];
  txLoading: boolean;
  txHasMore: boolean;
  actions: ClubSocketActions;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const TransactionsTab = React.memo(function TransactionsTab({
  transactions,
  txLoading,
  txHasMore,
  actions,
}: TransactionsTabProps) {
  return (
    <div className="space-y-4">
      {/* Header with refresh */}
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-white">Transaction History</h3>
        <button onClick={() => actions.fetchTransactions()} className="btn-secondary text-xs">
          Refresh
        </button>
      </div>

      {/* Initial loading state (no transactions loaded yet) */}
      {txLoading && transactions.length === 0 ? (
        <div className="text-center py-8 text-sm text-slate-400">Loading transactions...</div>
      ) : transactions.length === 0 ? (
        /* Empty state */
        <EmptyState
          icon="--"
          title="No transactions yet"
          description="Wallet transactions will appear here as they occur."
        />
      ) : (
        /* Transaction table */
        <div className="rounded-xl border border-white/10 overflow-hidden">
          {/* Column headers */}
          <div className="grid grid-cols-4 gap-2 text-[10px] uppercase tracking-wider text-slate-500 bg-white/5 px-3 py-2">
            <span>Time</span>
            <span>Type</span>
            <span className="text-right">Amount</span>
            <span className="text-right">Status</span>
          </div>

          {/* Rows */}
          {transactions.map((tx) => {
            const txStatus = tx.status ?? 'success';

            return (
              <div
                key={tx.id}
                className="grid grid-cols-4 gap-2 text-xs px-3 py-2 border-t border-white/5 items-center"
              >
                {/* Time */}
                <span className="text-slate-400 text-[11px]">
                  {new Date(tx.createdAt).toLocaleDateString(undefined, {
                    month: 'short',
                    day: 'numeric',
                  })}{' '}
                  <span className="text-[10px] text-slate-600">
                    {new Date(tx.createdAt).toLocaleTimeString(undefined, {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                </span>

                {/* Type */}
                <span className="text-slate-300 capitalize text-[11px]">
                  {tx.type.replace(/_/g, ' ')}
                </span>

                {/* Amount */}
                <span
                  className={`text-right font-mono font-semibold ${
                    tx.amount >= 0 ? 'text-emerald-400' : 'text-red-400'
                  }`}
                >
                  {tx.amount >= 0 ? '+' : ''}
                  {tx.amount.toLocaleString()}
                </span>

                {/* Status */}
                <div className="flex justify-end" title={tx.errorDetail ?? undefined}>
                  <StatusBadge status={txStatus} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Load More button */}
      {transactions.length > 0 && txHasMore && (
        <div className="flex justify-center pt-2">
          <button
            onClick={() => actions.fetchTransactions(transactions.length)}
            disabled={txLoading}
            className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs text-slate-300 hover:text-white hover:border-slate-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {txLoading ? 'Loading...' : 'Load More'}
          </button>
        </div>
      )}
    </div>
  );
});

export default TransactionsTab;
