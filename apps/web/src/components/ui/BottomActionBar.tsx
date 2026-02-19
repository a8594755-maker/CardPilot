import { useState, useEffect, useMemo, useCallback } from "react";
import type { AdvicePayload, LegalActions } from "@cardpilot/shared-types";
import { getSuggestedPresets, userPresetsToButtons } from "../../lib/bet-sizing.js";
import type { DerivedActionBar, DerivedPreActionUI, PreAction, PreActionType } from "../../lib/action-derivations";
import { formatChips } from "../../lib/format-chips";

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
  preAction: PreAction | null;
  onSetPreAction: (action: PreActionType | null) => void;
  derivedActionBar: DerivedActionBar;
  derivedPreActionUI: DerivedPreActionUI;
  isMyTurn: boolean;
  onFoldAttempt: () => void;
  userBetPresets?: { flop: number[]; turn: number[]; river: number[] };
  onOpenGto?: () => void;
  isMobilePortrait?: boolean;
}

const VALID_ACTION_HOTKEYS = ["F", "C", "R", "A", "K"] as const;
type ActionHotkey = (typeof VALID_ACTION_HOTKEYS)[number];

const PRE_ACTION_FALLBACK_LABEL: Record<PreActionType, string> = {
  check: "Check",
  "check/fold": "Check / Fold",
  call: "Call",
  fold: "Fold",
};

function isInvalidButtonLabel(value: string): boolean {
  const normalized = value.trim();
  if (!normalized) return true;
  if (normalized === "?") return true;
  if (/^\?{2,}$/.test(normalized)) return true;
  if (/^\?\?.+\?\?$/.test(normalized)) return true;
  if (/^(undefined|null|nan)$/i.test(normalized)) return true;
  return false;
}

function safeButtonLabel(raw: unknown, fallback: string, context: string): string {
  const candidate = typeof raw === "string" ? raw.trim() : "";
  if (!candidate || isInvalidButtonLabel(candidate)) {
    if (import.meta.env.DEV) {
      console.warn(`[BottomActionBar] Missing button label for ${context}`, { raw, fallback });
    }
    return fallback;
  }
  return candidate;
}

function toValidHotkey(raw: string | null | undefined): ActionHotkey | null {
  if (!raw) return null;
  const normalized = raw.trim().toUpperCase();
  return (VALID_ACTION_HOTKEYS as readonly string[]).includes(normalized)
    ? (normalized as ActionHotkey)
    : null;
}

function getActionHotkey(type: "fold" | "check" | "call" | "raise" | "all_in"): ActionHotkey | null {
  if (type === "all_in") return "A";
  if (type === "check") return "K";
  return toValidHotkey(type.slice(0, 1).toUpperCase());
}

function getAriaShortcut(hotkey: ActionHotkey | null): string | undefined {
  if (!hotkey) return undefined;
  return hotkey;
}

function HotkeyBadge({ hotkey }: { hotkey: ActionHotkey }) {
  return (
    <span className="cp-hotkey-badge" aria-hidden="true">
      {hotkey}
    </span>
  );
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
  onOpenGto,
  isMobilePortrait,
}: BottomActionBarProps) {
  const [showRaiseSheet, setShowRaiseSheet] = useState(false);
  const [allInConfirm, setAllInConfirm] = useState(false);
  const [showUtilityMenu, setShowUtilityMenu] = useState(false);

  const min = legal?.minRaise ?? bigBlind * 2;
  const max = legal?.maxRaise ?? 10000;
  const callAmt = legal?.callAmount ?? 0;
  const bb = bigBlind || 1;

  useEffect(() => {
    if (!canAct) {
      setAllInConfirm(false);
      setShowRaiseSheet(false);
      setShowUtilityMenu(false);
    }
  }, [canAct]);

  useEffect(() => {
    if (!showRaiseSheet) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prevOverflow;
    };
  }, [showRaiseSheet]);

  useEffect(() => {
    if (legal?.canRaise) {
      if (raiseTo < min) setRaiseTo(min);
      else if (raiseTo > max) setRaiseTo(max);
    }
  }, [min, max, legal?.canRaise, raiseTo, setRaiseTo]);

  const fmtChips = useCallback((v: number) => {
    return formatChips(v, { mode: displayBB ? "bb" : "chips", bbSize: bb });
  }, [displayBB, bb]);

  const suggestedPresets = useMemo(() => {
    if (!legal?.canRaise || pot <= 0) return [];
    return getSuggestedPresets({
      street: street as "PREFLOP" | "FLOP" | "TURN" | "RIVER",
      pot,
      heroStack,
      board,
      numPlayers,
    });
  }, [legal, pot, street, board, heroStack, numPlayers]);

  const streetKey = street === "FLOP" ? "flop" : street === "TURN" ? "turn" : street === "RIVER" ? "river" : "flop";
  const customPresets = useMemo(() => {
    const presets = userBetPresets?.[streetKey as keyof typeof userBetPresets] ?? [33, 66, 100];
    return userPresetsToButtons(presets as [number, number, number]);
  }, [userBetPresets, streetKey]);

  const presetToChips = useCallback((pctOfPot: number): number => {
    const raw = Math.round(pot * pctOfPot / 100);
    return Math.max(min, Math.min(max, raw));
  }, [pot, min, max]);

  const formatActionAmount = useCallback((value: unknown): string | null => {
    if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) return null;
    return fmtChips(value);
  }, [fmtChips]);

  const handleRaiseConfirm = () => {
    onAction("raise", raiseTo);
    setShowRaiseSheet(false);
    setShowUtilityMenu(false);
  };

  const preActionLabel = preAction?.actionType ?? null;
  const canUseThinkExtension = canAct && !!thinkExtensionEnabled && (thinkExtensionRemainingUses ?? 0) > 0;
  const hasGtoButton = isMobilePortrait && !!onOpenGto;
  const hasUtilityActions = (canAct && !!advice) || canUseThinkExtension || hasGtoButton;

  if (!isMyTurn && !canAct) {
    if (!derivedPreActionUI.enabled) return null;

    return (
      <div className="cp-action-shell cp-action-shell--pre cp-action-shell--compact" style={{ zIndex: "var(--cp-z-action-bar)" }}>
        {preActionLabel && (
          <div className="flex items-center justify-center gap-2 mb-1.5">
            <span className="cp-preaction-badge">
              Pre-action: {preActionLabel}
              <button
                onClick={() => onSetPreAction(null)}
                className="ml-1 text-violet-300 hover:text-white"
                aria-label="Clear pre-action"
              >
                X
              </button>
            </span>
          </div>
        )}

        <div className="cp-action-panel cp-action-panel--pre">
          <div className="flex items-center gap-1.5 text-[10px] text-slate-400 mb-1.5 uppercase tracking-wider font-semibold">
            <span style={{ fontSize: 14 }}>+</span>
            Pre-action - set before your turn
          </div>
          <div className="cp-action-row cp-action-row--compact">
            {derivedPreActionUI.options.map((opt) => {
              const callAmountLabel = opt.type === "call" ? formatActionAmount(opt.amount) : null;
              const optionLabel = opt.type === "call" && callAmountLabel
                ? `Call ${callAmountLabel}`
                : safeButtonLabel(opt.label, PRE_ACTION_FALLBACK_LABEL[opt.type], `pre-action:${opt.type}`);
              return (
                <button
                  key={opt.type}
                  disabled={!opt.enabled}
                  onClick={() => onSetPreAction(preActionLabel === opt.type ? null : opt.type)}
                  className={`cp-btn cp-action-btn text-xs ${
                    preActionLabel === opt.type
                      ? "bg-violet-500/20 text-violet-300 border border-violet-500/40"
                      : "cp-btn-ghost"
                  }`}
                >
                  {optionLabel}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="cp-action-shell cp-action-shell--compact" style={{ zIndex: "var(--cp-z-action-bar)" }}>
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
          onAllIn={() => {
            onAction("all_in");
            setShowRaiseSheet(false);
            setShowUtilityMenu(false);
          }}
          actionPending={!!actionPending}
          street={street}
          displayBB={displayBB}
        />
      )}

      <div className="cp-action-panel-wrap">
        {preActionLabel && (
          <div className="flex items-center justify-center gap-2 mb-1.5">
            <span className="cp-preaction-badge">
              Pre-action queued: {preActionLabel}
              <button
                onClick={() => onSetPreAction(null)}
                className="ml-1 text-violet-300 hover:text-white"
                aria-label="Clear pre-action"
              >
                X
              </button>
            </span>
          </div>
        )}

        <div className={`cp-action-panel ${actionPending ? "opacity-50 pointer-events-none" : ""}`}>
          {actionPending && canAct && (
            <div className="flex items-center justify-center gap-2 mb-1.5">
              <span className="text-[11px] text-amber-400 animate-pulse font-medium">Processing...</span>
            </div>
          )}

          <div className="cp-action-row">
            {derivedActionBar.visibleActions.map((a) => {
              if (a.type === "fold") {
                const foldLabel = safeButtonLabel(a.label, "FOLD", "action:fold");
                const foldHotkey = getActionHotkey("fold");
                return (
                  <button
                    key={a.type}
                    disabled={!canAct || actionPending || !a.enabled}
                    onClick={() => {
                      onFoldAttempt();
                      setShowUtilityMenu(false);
                    }}
                    className={`cp-btn cp-btn-fold cp-action-btn ${!a.enabled ? "opacity-50" : ""}`}
                    aria-label="Fold"
                    title={a.reasonDisabled}
                    data-hotkey={foldHotkey ?? undefined}
                    aria-keyshortcuts={getAriaShortcut(foldHotkey)}
                  >
                    <span className="flex items-center gap-1 text-[13px] font-bold leading-tight">
                      <span>{foldLabel}</span>
                      {foldHotkey && <HotkeyBadge hotkey={foldHotkey} />}
                    </span>
                  </button>
                );
              }

              if (a.type === "check") {
                const checkLabel = safeButtonLabel(a.label, "CHECK", "action:check");
                const checkHotkey = getActionHotkey("check");
                return (
                  <button
                    key={a.type}
                    disabled={!canAct || actionPending || !a.enabled}
                    onClick={() => {
                      onAction("check");
                      setShowRaiseSheet(false);
                      setShowUtilityMenu(false);
                    }}
                    className="cp-btn cp-btn-check cp-action-btn"
                    aria-label={checkLabel}
                    data-hotkey={checkHotkey ?? undefined}
                    aria-keyshortcuts={getAriaShortcut(checkHotkey)}
                  >
                    <span className="flex items-center gap-1 text-[13px] font-bold leading-tight">
                      <span>{checkLabel}</span>
                      {checkHotkey && <HotkeyBadge hotkey={checkHotkey} />}
                    </span>
                  </button>
                );
              }

              if (a.type === "call") {
                const amt = typeof a.amount === "number" ? a.amount : callAmt;
                const callLabel = safeButtonLabel(a.label, "CALL", "action:call");
                const callAmountLabel = formatActionAmount(amt);
                const callHotkey = getActionHotkey("call");
                return (
                  <button
                    key={a.type}
                    disabled={!canAct || actionPending || !a.enabled}
                    onClick={() => {
                      onAction("call");
                      setShowRaiseSheet(false);
                      setShowUtilityMenu(false);
                    }}
                    className="cp-btn cp-btn-call cp-action-btn"
                    aria-label={callAmountLabel ? `${callLabel} ${callAmountLabel}` : callLabel}
                    data-hotkey={callHotkey ?? undefined}
                    aria-keyshortcuts={getAriaShortcut(callHotkey)}
                  >
                    <span className="flex items-center gap-1 text-[13px] font-bold leading-tight">
                      <span>{callLabel}</span>
                      {callAmountLabel ? <span className="cp-num">{callAmountLabel}</span> : null}
                      {callHotkey && <HotkeyBadge hotkey={callHotkey} />}
                    </span>
                  </button>
                );
              }

              if (a.type === "raise") {
                if (showRaiseSheet) return null;
                const raiseLabel = safeButtonLabel(a.label, "RAISE", "action:raise");
                const raiseHotkey = getActionHotkey("raise");
                return (
                  <button
                    key={a.type}
                    disabled={!canAct || actionPending || !a.enabled}
                    onClick={() => {
                      setShowRaiseSheet(true);
                      setShowUtilityMenu(false);
                    }}
                    className="cp-btn cp-btn-raise cp-action-btn"
                    aria-label={raiseLabel}
                    data-hotkey={raiseHotkey ?? undefined}
                    aria-keyshortcuts={getAriaShortcut(raiseHotkey)}
                  >
                    <span className="flex items-center gap-1 text-[13px] font-bold leading-tight">
                      <span>{raiseLabel}</span>
                      {raiseHotkey && <HotkeyBadge hotkey={raiseHotkey} />}
                    </span>
                  </button>
                );
              }

              if (a.type === "all_in") {
                if (showRaiseSheet) return null;
                const allInLabel = safeButtonLabel(a.label, "ALL-IN", "action:all_in");
                const allInHotkey = getActionHotkey("all_in");
                if (!allInConfirm) {
                  return (
                    <button
                      key={a.type}
                      disabled={!canAct || actionPending || !a.enabled}
                      onClick={() => setAllInConfirm(true)}
                      className="cp-btn cp-btn-allin cp-action-meta-btn cp-action-meta-btn--tight"
                      aria-label={allInLabel}
                      data-hotkey={allInHotkey ?? undefined}
                      aria-keyshortcuts={getAriaShortcut(allInHotkey)}
                    >
                      <span className="flex items-center gap-1 text-[12px] font-bold leading-tight">
                        <span>{allInLabel}</span>
                        {allInHotkey && <HotkeyBadge hotkey={allInHotkey} />}
                      </span>
                    </button>
                  );
                }

                return (
                  <div key={a.type} className="flex items-center gap-1.5 animate-[cpFadeSlideUp_0.2s_ease-out]">
                    <button
                      disabled={!canAct || actionPending || !a.enabled}
                      onClick={() => {
                        onAction("all_in");
                        setAllInConfirm(false);
                        setShowRaiseSheet(false);
                        setShowUtilityMenu(false);
                      }}
                      className="cp-btn cp-btn-allin cp-action-meta-btn cp-action-meta-btn--tight ring-2 ring-orange-400/50"
                      aria-label="Confirm All-In"
                    >
                      <span className="text-[11px] font-bold">CONFIRM</span>
                    </button>
                    <button
                      onClick={() => setAllInConfirm(false)}
                      className="cp-btn cp-btn-ghost cp-action-meta-btn cp-action-meta-btn--tight"
                    >
                      X
                    </button>
                  </div>
                );
              }

              return null;
            })}
          </div>

          {hasUtilityActions ? (
            <div className="cp-action-utility">
              {/* C2: GTO entry inside ActionBar for mobile portrait */}
              {hasGtoButton && (
                <button
                  onClick={() => { onOpenGto?.(); setShowUtilityMenu(false); }}
                  className={`cp-btn cp-action-meta-btn cp-action-meta-btn--tight text-[11px] ${
                    advice
                      ? "bg-gradient-to-r from-amber-500/20 to-orange-500/20 text-amber-300 border border-amber-500/30"
                      : "cp-btn-ghost"
                  }`}
                  aria-label="Open GTO Coach"
                  title="GTO Coach"
                >
                  <span className="flex items-center gap-1">
                    <span className="w-4 h-4 rounded bg-white/20 flex items-center justify-center text-[8px] font-extrabold shrink-0">G</span>
                    <span>GTO</span>
                    {advice?.recommended && <span className="text-[9px] font-bold uppercase bg-white/15 px-1 py-0.5 rounded-full">{advice.recommended}</span>}
                  </span>
                </button>
              )}
              <button
                onClick={() => setShowUtilityMenu((prev) => !prev)}
                className="cp-btn cp-btn-ghost cp-action-meta-btn cp-action-meta-btn--tight text-[11px]"
                aria-expanded={showUtilityMenu}
                aria-label="More actions"
              >
                More
              </button>
              {showUtilityMenu && (
                <div className="cp-action-utility-menu">
                  {canAct && advice && (
                    <button
                      onClick={() => {
                        const rec = advice.recommended;
                        if (rec) onAction(rec, rec === "raise" ? raiseTo : undefined);
                        setShowUtilityMenu(false);
                      }}
                      className="cp-btn cp-btn-ghost cp-action-utility-item"
                      title={`GTO: ${advice.recommended?.toUpperCase()} - ${advice.explanation}`}
                    >
                      GTO {advice.recommended?.toUpperCase() ?? "TIP"}
                    </button>
                  )}
                  {canUseThinkExtension && (
                    <button
                      onClick={() => {
                        onThinkExtension?.();
                        setShowUtilityMenu(false);
                      }}
                      className="cp-btn cp-btn-ghost cp-action-utility-item"
                      aria-label="Think extension"
                      title="Request more time"
                    >
                      +Time ({thinkExtensionRemainingUses})
                    </button>
                  )}
                </div>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

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
  fmtChips,
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

  const facingBet = currentBet > 0 && pot > 0;
  const preflop = !facingBet && pot <= bigBlind * 2;

  const presetButtons = useMemo(() => {
    const buttons: Array<{ label: string; chips: number }> = [];

    buttons.push({ label: "Min", chips: min });

    if (facingBet) {
      [2, 3].forEach((mult) => {
        const chips = Math.max(min, Math.min(max, Math.round(currentBet * mult)));
        buttons.push({ label: `${mult}x`, chips });
      });
    } else if (preflop) {
      [2, 3, 4].forEach((mult) => {
        const chips = Math.max(min, Math.min(max, Math.round(bigBlind * mult)));
        buttons.push({ label: `${mult}BB`, chips });
      });
    } else {
      [
        { label: "1/2 Pot", pct: 50 },
        { label: "3/4 Pot", pct: 75 },
        { label: "Pot", pct: 100 },
      ].forEach((p) => {
        buttons.push({ label: p.label, chips: presetToChips(p.pct) });
      });
    }

    buttons.push({ label: "All-in", chips: max });

    return buttons;
  }, [min, max, facingBet, preflop, currentBet, bigBlind, presetToChips]);

  return (
    <div className="cp-raise-sheet cp-bottom-sheet">
      <div className="cp-raise-sheet-panel space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="cp-raise-focus-label">Your Bet</div>
            <div className="cp-raise-focus-value">{fmtChips(raiseTo)}</div>
            {!displayBB && <div className="cp-raise-focus-sub">{(raiseTo / bb).toFixed(1)} BB</div>}
          </div>
          <div className="text-right">
            <div className="cp-raise-focus-label">Pot</div>
            <div className="text-lg font-bold text-amber-400 cp-num">{fmtChips(pot)}</div>
          </div>
        </div>

        <div className="cp-raise-presets">
          {presetButtons.map((p) => (
            <button
              key={p.label}
              onClick={() => (p.label === "All-in" ? onAllIn() : setRaiseTo(p.chips))}
              className="cp-raise-preset"
              data-active={raiseTo === p.chips && p.label !== "All-in" ? "true" : "false"}
              data-kind={p.label === "All-in" ? "allin" : "default"}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="cp-raise-slider-row">
          <button
            onClick={decrement}
            className="cp-btn cp-btn-ghost cp-action-meta-btn text-lg font-bold"
            aria-label="Decrease bet"
          >
            -
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
            className="cp-btn cp-btn-ghost cp-action-meta-btn text-lg font-bold"
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
              if (!Number.isNaN(v)) setRaiseTo(Math.max(min, Math.min(max, v)));
            }}
            className="cp-raise-number cp-num"
            aria-label="Bet size input"
          />
        </div>

        {customPresets.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[9px] text-slate-500 uppercase tracking-wider shrink-0">Custom</span>
            <div className="cp-raise-presets">
              {customPresets.slice(0, 3).map((p) => {
                const chips = presetToChips(p.pctOfPot);
                return (
                  <button
                    key={p.label}
                    onClick={() => setRaiseTo(chips)}
                    className="cp-raise-preset"
                    data-active={raiseTo === chips ? "true" : "false"}
                  >
                    {p.label}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="cp-raise-actions">
          <button onClick={onBack} className="cp-btn cp-btn-ghost">
            Back
          </button>
          <button disabled={actionPending} onClick={onConfirm} className="cp-btn cp-btn-raise">
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
