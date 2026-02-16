import { useState } from "react";

/* ═══════════════════════════════════════════════════════════════
   FoldConfirmModal
   Confirmation modal for "unnecessary fold" — when user can
   check for free but clicks Fold.
   Human-friendly, non-judgmental copy.
   ═══════════════════════════════════════════════════════════════ */

interface FoldConfirmModalProps {
  open: boolean;
  onConfirmFold: () => void;
  onCancel: () => void;
  suppressedThisSession: boolean;
  onSuppressChange: (suppress: boolean) => void;
}

export function FoldConfirmModal({
  open,
  onConfirmFold,
  onCancel,
  suppressedThisSession,
  onSuppressChange,
}: FoldConfirmModalProps) {
  if (!open) return null;

  return (
    <div className="cp-modal-backdrop" onClick={onCancel}>
      <div className="cp-modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="cp-panel p-6 space-y-4">
          {/* Header */}
          <div className="text-center">
            <div className="text-2xl mb-2">🤔</div>
            <h3 className="text-base font-bold text-white">You can check for free</h3>
            <p className="text-sm text-slate-400 mt-1">
              There's no bet to call — are you sure you want to fold?
            </p>
          </div>

          {/* Buttons */}
          <div className="flex items-center gap-3">
            <button
              onClick={onCancel}
              className="cp-btn cp-btn-check flex-1"
              autoFocus
            >
              Check instead
            </button>
            <button
              onClick={onConfirmFold}
              className="cp-btn cp-btn-ghost flex-1"
            >
              Fold anyway
            </button>
          </div>

          {/* Suppress checkbox */}
          <label className="flex items-center gap-2 cursor-pointer justify-center">
            <input
              type="checkbox"
              checked={suppressedThisSession}
              onChange={(e) => onSuppressChange(e.target.checked)}
              className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-blue-500 focus:ring-blue-500/30"
            />
            <span className="text-xs text-slate-500">Don't show again this session</span>
          </label>
        </div>
      </div>
    </div>
  );
}

export default FoldConfirmModal;
