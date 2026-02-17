import { useState, useEffect, useMemo, useCallback } from "react";
import type { AdvicePayload, LegalActions } from "@cardpilot/shared-types";
import { getSuggestedPresets, userPresetsToButtons } from "../../lib/bet-sizing.js";
import type { DerivedActionBar, DerivedPreActionUI, PreAction, PreActionType } from "../../lib/action-derivations";
import { formatChips } from "../../lib/format-chips";

/* ═══════════════════════════════════════════════════════════════
   BottomActionBar
   Sticky bottom action bar with 44px+ touch targets.
   Shows decision-critical info directly on buttons.
   Integrates RaiseSheet as a bottom tray.
   ═══════════════════════════════════════════════════════════════ */

interface BottomActionBarProps {
  canAct: boolean;
  legal: LegalActions | null;
  pot: number;
  bigBlind: number;
  currentBet: number;
  raiseTo: number;
  setRaiseTo: (v: number) => void;
  onAction: (action: "fold" | "check" | "call" | "raise" | "all_in", amount?: number) => void;
  street: string;
  board: string[];
  heroStack: number;
  numPlayers: number;
  advice: AdvicePayload | null;
  thinkExtensionEnabled?: boolean;
  thinkExtensionRemainingUses?: number;
  onThinkExtension?: () => void;
  actionPending?: boolean;
  displayBB?: boolean;
  // Pre-action
  preAction: PreAction | null;
  onSetPreAction: (action: PreActionType | null) => void;
  derivedActionBar: DerivedActionBar;
  derivedPreActionUI: DerivedPreActionUI;
  isMyTurn: boolean;
  // Unnecessary fold
  onFoldAttempt: () => void;
  // User prefs for bet presets
  userBetPresets?: { flop: number[]; turn: number[]; river: number[] };
}

export function BottomActionBar({
  canAct,
  legal,
  pot,
  bigBlind,
  currentBet,
  raiseTo,
  setRaiseTo,
  onAction,
  street,
  board,
  heroStack,
  numPlayers,
  advice,
  thinkExtensionEnabled,
  thinkExtensionRemainingUses,
  onThinkExtension,
  actionPending,
  displayBB,
  preAction,
  onSetPreAction,
  derivedActionBar,
  derivedPreActionUI,
  isMyTurn,
  onFoldAttempt,
  userBetPresets,
}: BottomActionBarProps) {
  const [showRaiseSheet, setShowRaiseSheet] = useState(false);
  const [allInConfirm, setAllInConfirm] = useState(false);

  const min = legal?.minRaise ?? bigBlind * 2;
  const max = legal?.maxRaise ?? 10000;
  const callAmt = legal?.callAmount ?? 0;
  const bb = bigBlind || 1;

  // Reset states when turn changes
  useEffect(() => { if (!canAct) { setAllInConfirm(false); setShowRaiseSheet(false); } }, [canAct]);

  // Auto-clamp raiseTo
  useEffect(() => {
    if (legal?.canRaise) {
      if (raiseTo < min) setRaiseTo(min);
      else if (raiseTo > max) setRaiseTo(max);
    }
  }, [min, max, legal?.canRaise, raiseTo, setRaiseTo]);

  const fmtChips = useCallback((v: number) => {
    return formatChips(v, { mode: displayBB ? "bb" : "chips", bbSize: bb });
  }, [displayBB, bb]);

  // Suggested presets
  const suggestedPresets = useMemo(() => {
    if (!legal?.canRaise || pot <= 0) return [];
    return getSuggestedPresets({ street: street as "PREFLOP" | "FLOP" | "TURN" | "RIVER", pot, heroStack, board, numPlayers });
  }, [legal, pot, street, board, heroStack, numPlayers]);

  const streetKey = street === "FLOP" ? "flop" : street === "TURN" ? "turn" : street === "RIVER" ? "river" : "flop";
  const customPresets = useMemo(() => {
    const presets = userBetPresets?.[streetKey as keyof typeof userBetPresets] ?? [33, 66, 100];
    return userPresetsToButtons(presets as [number, number, number]);
  }, [userBetPresets, streetKey]);

  function presetToChips(pctOfPot: number): number {
    const raw = Math.round(pot * pctOfPot / 100);
    return Math.max(min, Math.min(max, raw));
  }

  const handleFold = () => {
    onFoldAttempt();
  };

  const handleRaiseConfirm = () => {
    onAction("raise", raiseTo);
    setShowRaiseSheet(false);
  };

  const preActionLabel = preAction?.actionType ? preAction.actionType : null;

  // ── Pre-action controls (when NOT your turn) ──
  if (!isMyTurn && !canAct) {
    if (!derivedPreActionUI.enabled) return null;
    return (
      <div className="shrink-0 px-3 pb-2 pt-1.5" style={{ zIndex: 'var(--cp-z-action-bar)' }}>
        {/* Pre-action indicator */}
        {preActionLabel && (
          <div className="flex items-center justify-center gap-2 mb-2">
            <span className="cp-preaction-badge">
              Pre-action: {preActionLabel}
              <button
                onClick={() => onSetPreAction(null)}
                className="ml-1 text-violet-300 hover:text-white"
                aria-label="Clear pre-action"
              >
                ✕
              </button>
            </span>
          </div>
        )}
        <div className="cp-panel px-3 py-2">
          <div className="flex items-center gap-1.5 text-[10px] text-slate-400 mb-2 uppercase tracking-wider font-semibold">
            <span style={{ fontSize: 14 }}>⏳</span>
            Pre-action — set before your turn
          </div>
          <div className="flex items-center gap-2">
            {derivedPreActionUI.options.map((opt) => (
              <button
                key={opt.type}
                disabled={!opt.enabled}
                onClick={() => onSetPreAction(preActionLabel === opt.type ? null : opt.type)}
                className={`cp-btn flex-1 text-xs ${
                  preActionLabel === opt.type
                    ? "bg-violet-500/20 text-violet-300 border border-violet-500/40"
                    : "cp-btn-ghost"
                }`}
              >
                {opt.type === "call" && typeof opt.amount === "number" ? `Call ${fmtChips(opt.amount)}` : opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ── Main action bar (your turn) ──
  return (
    <div className="shrink-0" style={{ zIndex: 'var(--cp-z-action-bar)' }}>
      {/* Raise Sheet (bottom tray) */}
      {showRaiseSheet && legal?.canRaise && canAct && (
        <RaiseSheet
          raiseTo={raiseTo}
          setRaiseTo={setRaiseTo}
          min={min}
          max={max}
          pot={pot}
          bigBlind={bigBlind}
          currentBet={currentBet}
          heroStack={heroStack}
          fmtChips={fmtChips}
          suggestedPresets={suggestedPresets}
          customPresets={customPresets}
          presetToChips={presetToChips}
          onConfirm={handleRaiseConfirm}
          onBack={() => setShowRaiseSheet(false)}
          onAllIn={() => { onAction("all_in"); setShowRaiseSheet(false); }}
          actionPending={!!actionPending}
          street={street}
          displayBB={displayBB}
        />
      )}

      {/* Action buttons row */}
      <div className="px-3 pb-2 pt-1.5">
        {/* Pre-action indicator (still visible when it's your turn, pre-action applied) */}
        {preActionLabel && (
          <div className="flex items-center justify-center gap-2 mb-1.5">
            <span className="cp-preaction-badge">
              Pre-action queued: {preActionLabel}
              <button
                onClick={() => onSetPreAction(null)}
                className="ml-1 text-violet-300 hover:text-white"
                aria-label="Clear pre-action"
              >
                ✕
              </button>
            </span>
          </div>
        )}

        <div className={`cp-panel px-3 py-2.5 ${actionPending ? 'opacity-50 pointer-events-none' : ''}`}>
          {actionPending && canAct && (
            <div className="flex items-center justify-center gap-2 mb-2">
              <span className="text-xs text-amber-400 animate-pulse font-medium">Processing…</span>
            </div>
          )}

          <div className="flex items-center gap-2">
            {derivedActionBar.visibleActions.map((a) => {
              if (a.type === "fold") {
                return (
                  <button
                    key={a.type}
                    disabled={!canAct || actionPending || !a.enabled}
                    onClick={handleFold}
                    className={`cp-btn cp-btn-fold flex-1 ${!a.enabled ? "opacity-50" : ""}`}
                    aria-label="Fold"
                    title={a.reasonDisabled}
                  >
                    <span className="flex flex-col items-center leading-tight">
                      <span className="text-sm font-bold">FOLD</span>
                    </span>
                  </button>
                );
              }

              if (a.type === "check") {
                return (
                  <button
                    key={a.type}
                    disabled={!canAct || actionPending || !a.enabled}
                    onClick={() => { onAction("check"); setShowRaiseSheet(false); }}
                    className="cp-btn cp-btn-check flex-1"
                    aria-label="Check"
                  >
                    <span className="flex flex-col items-center leading-tight">
                      <span className="text-sm font-bold">CHECK</span>
                    </span>
                  </button>
                );
              }

              if (a.type === "call") {
                const amt = typeof a.amount === "number" ? a.amount : callAmt;
                return (
                  <button
                    key={a.type}
                    disabled={!canAct || actionPending || !a.enabled}
                    onClick={() => { onAction("call"); setShowRaiseSheet(false); }}
                    className="cp-btn cp-btn-call flex-1"
                    aria-label={`Call ${amt}`}
                  >
                    <span className="flex flex-col items-center leading-tight">
                      <span className="text-sm font-bold">CALL</span>
                      <span className="text-[11px] font-semibold opacity-90 cp-num">{fmtChips(amt)}</span>
                    </span>
                  </button>
                );
              }

              if (a.type === "raise") {
                if (showRaiseSheet) return null;
                return (
                  <button
                    key={a.type}
                    disabled={!canAct || actionPending || !a.enabled}
                    onClick={() => setShowRaiseSheet(true)}
                    className="cp-btn cp-btn-raise flex-1"
                    aria-label={a.label}
                  >
                    <span className="text-sm font-bold">{a.label}</span>
                  </button>
                );
              }

              if (a.type === "all_in") {
                if (showRaiseSheet) return null;
                if (!allInConfirm) {
                  return (
                    <button
                      key={a.type}
                      disabled={!canAct || actionPending || !a.enabled}
                      onClick={() => setAllInConfirm(true)}
                      className="cp-btn cp-btn-allin"
                      style={{ minWidth: 64 }}
                      aria-label="All-In"
                    >
                      <span className="flex flex-col items-center leading-tight">
                        <span className="text-xs font-bold">ALL-IN</span>
                      </span>
                    </button>
                  );
                }

                return (
                  <div key={a.type} className="flex items-center gap-1.5 animate-[cpFadeSlideUp_0.2s_ease-out]">
                    <button
                      disabled={!canAct || actionPending || !a.enabled}
                      onClick={() => { onAction("all_in"); setAllInConfirm(false); setShowRaiseSheet(false); }}
                      className="cp-btn cp-btn-allin ring-2 ring-orange-400/50"
                      aria-label="Confirm All-In"
                    >
                      <span className="text-xs font-bold">CONFIRM</span>
                    </button>
                    <button
                      onClick={() => setAllInConfirm(false)}
                      className="cp-btn cp-btn-ghost !min-h-[38px] !px-2"
                    >
                      ✕
                    </button>
                  </div>
                );
              }

              return null;
            })}

            {/* AI Suggestion pill */}
            {canAct && advice && (
              <button
                onClick={() => {
                  const rec = advice.recommended;
                  if (rec) onAction(rec, rec === "raise" ? raiseTo : undefined);
                }}
                className="cp-btn text-xs bg-amber-500/15 text-amber-400 border border-amber-500/30 hover:bg-amber-500/25"
                title={`GTO: ${advice.recommended?.toUpperCase()} — ${advice.explanation}`}
                style={{ minWidth: 44 }}
              >
                <span className="flex flex-col items-center leading-tight">
                  <span className="text-[10px] font-bold">GTO</span>
                  <span className="text-[9px] uppercase opacity-80">{advice.recommended}</span>
                </span>
              </button>
            )}

            {/* Think extension */}
            {canAct && thinkExtensionEnabled && (thinkExtensionRemainingUses ?? 0) > 0 && (
              <button
                onClick={() => onThinkExtension?.()}
                className="cp-btn text-xs bg-violet-500/10 text-violet-300 border border-violet-500/30"
                aria-label="Think extension"
                title="Request more time"
                style={{ minWidth: 44 }}
              >
                +⏱ {thinkExtensionRemainingUses}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   RaiseSheet
   Bottom tray with presets, slider, +/- buttons, BB equivalent.
   ═══════════════════════════════════════════════════════════════ */

interface RaiseSheetProps {
  raiseTo: number;
  setRaiseTo: (v: number) => void;
  min: number;
  max: number;
  pot: number;
  bigBlind: number;
  currentBet: number;
  heroStack: number;
  fmtChips: (v: number) => string;
  suggestedPresets: Array<{ label: string; pctOfPot: number }>;
  customPresets: Array<{ label: string; pctOfPot: number }>;
  presetToChips: (pctOfPot: number) => number;
  onConfirm: () => void;
  onBack: () => void;
  onAllIn: () => void;
  actionPending: boolean;
  street: string;
  displayBB?: boolean;
}

function RaiseSheet({
  raiseTo,
  setRaiseTo,
  min,
  max,
  pot,
  bigBlind,
  currentBet,
  heroStack,
  fmtChips,
  suggestedPresets,
  customPresets,
  presetToChips,
  onConfirm,
  onBack,
  onAllIn,
  actionPending,
  displayBB,
}: RaiseSheetProps) {
  const bb = bigBlind || 1;
  const step = bigBlind;

  const increment = () => setRaiseTo(Math.min(max, raiseTo + step));
  const decrement = () => setRaiseTo(Math.max(min, raiseTo - step));

  // Determine preset buttons based on context
  const facingBet = currentBet > 0 && (pot > 0);
  const preflop = !facingBet && pot <= bigBlind * 2;

  const presetButtons = useMemo(() => {
    const buttons: Array<{ label: string; chips: number }> = [];

    // Min
    buttons.push({ label: "Min", chips: min });

    if (facingBet) {
      // 2x, 3x current bet
      [2, 3].forEach(mult => {
        const chips = Math.max(min, Math.min(max, Math.round(currentBet * mult)));
        buttons.push({ label: `${mult}x`, chips });
      });
    } else if (preflop) {
      // 2x, 3x, 4x BB
      [2, 3, 4].forEach(mult => {
        const chips = Math.max(min, Math.min(max, Math.round(bigBlind * mult)));
        buttons.push({ label: `${mult}BB`, chips });
      });
    } else {
      // Pot-based: 1/2, 3/4, Pot
      [
        { label: "½ Pot", pct: 50 },
        { label: "¾ Pot", pct: 75 },
        { label: "Pot", pct: 100 },
      ].forEach(p => {
        buttons.push({ label: p.label, chips: presetToChips(p.pct) });
      });
    }

    // All-in
    buttons.push({ label: "All-in", chips: max });

    return buttons;
  }, [min, max, facingBet, preflop, currentBet, bigBlind, presetToChips]);

  return (
    <div className="px-3 pb-1 cp-bottom-sheet">
      <div className="cp-panel px-4 py-3 space-y-3">
        {/* Your bet — big number + BB equivalent */}
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Your bet</div>
            <div className="text-2xl font-extrabold text-white cp-num">{fmtChips(raiseTo)}</div>
            {!displayBB && <div className="text-xs text-slate-400 cp-num">{(raiseTo / bb).toFixed(1)} BB</div>}
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Pot</div>
            <div className="text-lg font-bold text-amber-400 cp-num">{fmtChips(pot)}</div>
          </div>
        </div>

        {/* Presets row */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {presetButtons.map((p) => (
            <button
              key={p.label}
              onClick={() => p.label === "All-in" ? onAllIn() : setRaiseTo(p.chips)}
              className={`cp-btn !min-h-[36px] !px-3 !py-1.5 text-xs font-semibold transition-all ${
                raiseTo === p.chips && p.label !== "All-in"
                  ? "bg-red-500/20 text-red-400 border border-red-500/30"
                  : p.label === "All-in"
                  ? "bg-orange-500/15 text-orange-400 border border-orange-500/30 hover:bg-orange-500/25"
                  : "bg-white/5 text-slate-300 border border-white/10 hover:bg-white/10"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* Slider with +/- buttons */}
        <div className="flex items-center gap-3">
          <button
            onClick={decrement}
            className="cp-btn cp-btn-ghost !min-h-[36px] !min-w-[36px] !px-0 text-lg font-bold"
            aria-label="Decrease bet"
          >
            −
          </button>
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={raiseTo}
            onChange={(e) => setRaiseTo(Number(e.target.value))}
            className="cp-slider flex-1"
            aria-label="Bet size slider"
          />
          <button
            onClick={increment}
            className="cp-btn cp-btn-ghost !min-h-[36px] !min-w-[36px] !px-0 text-lg font-bold"
            aria-label="Increase bet"
          >
            +
          </button>
          <input
            type="number"
            min={min}
            max={max}
            step={step}
            value={raiseTo}
            onChange={(e) => {
              const v = Number(e.target.value);
              if (!isNaN(v)) setRaiseTo(Math.max(min, Math.min(max, v)));
            }}
            className="w-20 text-center text-sm font-semibold cp-num text-white bg-white/5 border border-white/10 rounded-lg py-2 focus:border-red-500/50 focus:outline-none"
            aria-label="Bet size input"
          />
        </div>

        {/* Custom presets (from user preferences) */}
        {customPresets.length > 0 && (
          <div className="flex items-center gap-1.5">
            <span className="text-[9px] text-slate-500 uppercase tracking-wider shrink-0">Custom</span>
            {customPresets.slice(0, 3).map((p) => {
              const chips = presetToChips(p.pctOfPot);
              return (
                <button
                  key={p.label}
                  onClick={() => setRaiseTo(chips)}
                  className={`cp-btn !min-h-[32px] !px-2.5 !py-1 text-[10px] font-semibold ${
                    raiseTo === chips
                      ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                      : "bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10"
                  }`}
                >
                  {p.label}
                </button>
              );
            })}
          </div>
        )}

        {/* Back / Confirm row */}
        <div className="flex items-center gap-2">
          <button
            onClick={onBack}
            className="cp-btn cp-btn-ghost flex-1"
          >
            Back
          </button>
          <button
            disabled={actionPending}
            onClick={onConfirm}
            className="cp-btn cp-btn-raise flex-[2]"
          >
            <span className="flex flex-col items-center leading-tight">
              <span className="text-sm font-bold">RAISE TO {fmtChips(raiseTo)}</span>
              {!displayBB && <span className="text-[10px] opacity-80 cp-num">{(raiseTo / bb).toFixed(1)} BB</span>}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}

export default BottomActionBar;
