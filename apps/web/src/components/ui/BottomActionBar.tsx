import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import type { AdvicePayload, LegalActions } from '@cardpilot/shared-types';
import type {
  DerivedActionBar,
  DerivedPreActionUI,
  PreAction,
  PreActionType,
} from '../../lib/action-derivations';
import { formatChips } from '../../lib/format-chips';
import { haptic } from '../../lib/haptic';
import { loadPrefs } from '../../pages/ProfilePage';

interface BottomActionBarProps {
  canAct: boolean;
  legal: LegalActions | null;
  pot: number;
  bigBlind: number;
  currentBet: number;
  raiseTo: number;
  setRaiseTo: (v: number) => void;
  onAction: (action: 'fold' | 'check' | 'call' | 'raise' | 'all_in', amount?: number) => void;
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

const VALID_ACTION_HOTKEYS = ['F', 'C', 'R', 'A', 'K'] as const;
type ActionHotkey = (typeof VALID_ACTION_HOTKEYS)[number];

const PRE_ACTION_FALLBACK_LABEL: Record<PreActionType, string> = {
  check: 'Check',
  'check/fold': 'Check / Fold',
  call: 'Call',
  fold: 'Fold',
};

function isInvalidButtonLabel(value: string): boolean {
  const normalized = value.trim();
  if (!normalized) return true;
  if (normalized === '?') return true;
  if (/^\?{2,}$/.test(normalized)) return true;
  if (/^\?\?.+\?\?$/.test(normalized)) return true;
  if (/^(undefined|null|nan)$/i.test(normalized)) return true;
  return false;
}

function safeButtonLabel(raw: unknown, fallback: string, context: string): string {
  const candidate = typeof raw === 'string' ? raw.trim() : '';
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

function getActionHotkey(
  type: 'fold' | 'check' | 'call' | 'raise' | 'all_in',
): ActionHotkey | null {
  if (type === 'all_in') return 'A';
  if (type === 'check') return 'K';
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

/* ── Inline Raise Strip (single-row, replaces old overlay RaiseSheet) ── */

function clampNum(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

interface InlineRaiseStripProps {
  raiseTo: number;
  setRaiseTo: (v: number) => void;
  min: number;
  max: number;
  pot: number;
  bigBlind: number;
  currentBet: number;
  fmtChips: (v: number) => string;
  onConfirm: () => void;
  onBack: () => void;
  actionPending: boolean;
}

function InlineRaiseStrip({
  raiseTo,
  setRaiseTo,
  min,
  max,
  pot,
  bigBlind,
  currentBet,
  fmtChips,
  onConfirm,
  onBack,
  actionPending,
}: InlineRaiseStripProps) {
  const step = bigBlind || 1;
  const facingBet = currentBet > 0 && pot > 0;
  const preflop = !facingBet && pot <= bigBlind * 2;

  const userPrefs = useMemo(() => loadPrefs(), []);
  const multipliers = userPrefs.raiseMultipliers ?? [2, 3];
  const potPcts = userPrefs.potPercentages ?? [33, 50, 100];

  const presets = useMemo(() => {
    const result: Array<{ label: string; chips: number }> = [];
    result.push({ label: 'Min', chips: min });

    if (facingBet) {
      multipliers.forEach((m) => {
        result.push({ label: `${m}x`, chips: clampNum(Math.round(currentBet * m), min, max) });
      });
    } else if (preflop) {
      multipliers.forEach((m) => {
        result.push({ label: `${m}x`, chips: clampNum(Math.round(bigBlind * m), min, max) });
      });
    } else {
      potPcts.forEach((pct) => {
        const label = pct === 100 ? 'Pot' : `${pct}%`;
        result.push({ label, chips: clampNum(Math.round((pot * pct) / 100), min, max) });
      });
    }

    return result;
  }, [min, max, facingBet, preflop, currentBet, bigBlind, pot, multipliers, potPcts]);

  return (
    <div className="cp-action-row cp-raise-strip">
      <button
        onClick={onBack}
        className="cp-btn cp-btn-ghost cp-raise-strip-back"
        aria-label="Cancel raise"
      >
        ✕
      </button>

      {presets.map((p) => (
        <button
          key={p.label}
          onClick={() => setRaiseTo(p.chips)}
          className="cp-raise-strip-preset"
          data-active={raiseTo === p.chips ? 'true' : 'false'}
        >
          {p.label}
        </button>
      ))}

      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={raiseTo}
        onChange={(e) => setRaiseTo(Number(e.target.value))}
        className="cp-slider cp-raise-strip-slider"
        aria-label="Bet size slider"
      />

      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={raiseTo}
        onChange={(e) => {
          const v = Number(e.target.value);
          if (!Number.isNaN(v)) setRaiseTo(clampNum(v, min, max));
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') onConfirm();
        }}
        className="cp-raise-strip-input cp-num"
        aria-label="Bet size input"
      />

      <button
        disabled={actionPending}
        onClick={onConfirm}
        className="cp-btn cp-btn-raise cp-raise-strip-confirm"
      >
        RAISE {fmtChips(raiseTo)}
      </button>
    </div>
  );
}

/* ── Main BottomActionBar ── */

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
  advice,
  actionPending,
  displayBB,
  preAction,
  onSetPreAction,
  derivedActionBar,
  derivedPreActionUI,
  isMyTurn,
  onFoldAttempt,
  onOpenGto,
  isMobilePortrait,
}: BottomActionBarProps) {
  const [showRaiseSheet, setShowRaiseSheet] = useState(false);
  const [allInConfirm, setAllInConfirm] = useState(false);
  const [showUtilityMenu, setShowUtilityMenu] = useState(false);
  const [confirmedAction, setConfirmedAction] = useState<string | null>(null);

  const min = legal?.minRaise ?? bigBlind * 2;
  const max = legal?.maxRaise ?? 10000;
  const callAmt = legal?.callAmount ?? 0;
  const bb = bigBlind || 1;

  // Haptic feedback when it becomes your turn
  const prevIsMyTurn = useRef(isMyTurn);
  useEffect(() => {
    if (isMyTurn && !prevIsMyTurn.current) {
      haptic('turn');
    }
    prevIsMyTurn.current = isMyTurn;
  }, [isMyTurn]);

  const confirmAndAct = useCallback(
    (action: 'fold' | 'check' | 'call' | 'raise' | 'all_in', amount?: number) => {
      setConfirmedAction(action);
      haptic('action');
      onAction(action, amount);
      setTimeout(() => setConfirmedAction(null), 350);
    },
    [onAction],
  );

  useEffect(() => {
    if (!canAct) {
      setAllInConfirm(false);
      setShowRaiseSheet(false);
      setShowUtilityMenu(false);
      setConfirmedAction(null);
    }
  }, [canAct]);

  useEffect(() => {
    if (legal?.canRaise) {
      if (raiseTo < min) setRaiseTo(min);
      else if (raiseTo > max) setRaiseTo(max);
    }
  }, [min, max, legal?.canRaise, raiseTo, setRaiseTo]);

  const fmtChips = useCallback(
    (v: number) => {
      return formatChips(v, { mode: displayBB ? 'bb' : 'chips', bbSize: bb });
    },
    [displayBB, bb],
  );

  const formatActionAmount = useCallback(
    (value: unknown): string | null => {
      if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return null;
      return fmtChips(value);
    },
    [fmtChips],
  );

  const handleRaiseConfirm = () => {
    confirmAndAct('raise', raiseTo);
    setShowRaiseSheet(false);
    setShowUtilityMenu(false);
  };

  const preActionLabel = preAction?.actionType ?? null;
  const hasGtoButton = isMobilePortrait && !!onOpenGto;

  // ── Determine which mode to render ──
  const showPreActions = !isMyTurn && !canAct && derivedPreActionUI.enabled;
  const showMainActions = isMyTurn || canAct;

  if (!showPreActions && !showMainActions) return null;

  return (
    <div
      className="cp-action-shell cp-action-shell--compact"
      style={{ zIndex: 'var(--cp-z-action-bar)' }}
    >
      <div className="cp-action-panel-wrap">
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

        <div
          className={`cp-action-panel ${isMyTurn && canAct ? 'cp-action-panel--your-turn' : ''} ${actionPending ? 'opacity-50 pointer-events-none' : ''}`}
        >
          {actionPending && canAct && (
            <div className="flex items-center justify-center gap-2 mb-1.5">
              <span className="text-[11px] text-amber-400 animate-pulse font-medium">
                Processing...
              </span>
            </div>
          )}

          {/* ── State 2: Inline Raise Strip ── */}
          {showMainActions && showRaiseSheet && legal?.canRaise && canAct ? (
            <InlineRaiseStrip
              raiseTo={raiseTo}
              setRaiseTo={setRaiseTo}
              min={min}
              max={max}
              pot={pot}
              bigBlind={bigBlind}
              currentBet={currentBet}
              fmtChips={fmtChips}
              onConfirm={handleRaiseConfirm}
              onBack={() => setShowRaiseSheet(false)}
              actionPending={!!actionPending}
            />
          ) : showMainActions ? (
            /* ── State 1: Normal Action Row ── */
            <div className="cp-action-row">
              {derivedActionBar.visibleActions.map((a) => {
                if (a.type === 'fold') {
                  const foldLabel = safeButtonLabel(a.label, 'FOLD', 'action:fold');
                  const foldHotkey = getActionHotkey('fold');
                  return (
                    <button
                      key={a.type}
                      disabled={!canAct || actionPending || !a.enabled}
                      onClick={() => {
                        onFoldAttempt();
                        setShowUtilityMenu(false);
                      }}
                      className={`cp-btn cp-btn-fold cp-action-btn ${!a.enabled ? 'opacity-50' : ''}`}
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

                if (a.type === 'check') {
                  const checkLabel = safeButtonLabel(a.label, 'CHECK', 'action:check');
                  const checkHotkey = getActionHotkey('check');
                  return (
                    <button
                      key={a.type}
                      disabled={!canAct || actionPending || !a.enabled}
                      onClick={() => {
                        confirmAndAct('check');
                        setShowRaiseSheet(false);
                        setShowUtilityMenu(false);
                      }}
                      className={`cp-btn cp-btn-check cp-action-btn ${confirmedAction === 'check' ? 'cp-action-btn--confirmed' : ''}`}
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

                if (a.type === 'call') {
                  const amt = typeof a.amount === 'number' ? a.amount : callAmt;
                  const callLabel = safeButtonLabel(a.label, 'CALL', 'action:call');
                  const callAmountLabel = formatActionAmount(amt);
                  const callHotkey = getActionHotkey('call');
                  return (
                    <button
                      key={a.type}
                      disabled={!canAct || actionPending || !a.enabled}
                      onClick={() => {
                        confirmAndAct('call', amt);
                        setShowRaiseSheet(false);
                        setShowUtilityMenu(false);
                      }}
                      className={`cp-btn cp-btn-call cp-action-btn ${confirmedAction === 'call' ? 'cp-action-btn--confirmed' : ''}`}
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

                if (a.type === 'raise') {
                  const raiseLabel = safeButtonLabel(a.label, 'RAISE', 'action:raise');
                  const raiseHotkey = getActionHotkey('raise');
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

                if (a.type === 'all_in') {
                  const allInLabel = safeButtonLabel(a.label, 'ALL-IN', 'action:all_in');
                  const allInHotkey = getActionHotkey('all_in');
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
                    <div
                      key={a.type}
                      className="flex items-center gap-1.5 animate-[cpFadeSlideUp_0.2s_ease-out]"
                    >
                      <button
                        disabled={!canAct || actionPending || !a.enabled}
                        onClick={() => {
                          confirmAndAct('all_in');
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
          ) : showPreActions ? (
            /* ── State 3: Pre-Action Row ── */
            <div className="cp-action-row">
              {derivedPreActionUI.options.map((opt) => {
                const callAmountLabel = opt.type === 'call' ? formatActionAmount(opt.amount) : null;
                const optionLabel =
                  opt.type === 'call' && callAmountLabel
                    ? `Call ${callAmountLabel}`
                    : safeButtonLabel(
                        opt.label,
                        PRE_ACTION_FALLBACK_LABEL[opt.type],
                        `pre-action:${opt.type}`,
                      );
                return (
                  <button
                    key={opt.type}
                    disabled={!opt.enabled}
                    onClick={() => onSetPreAction(preActionLabel === opt.type ? null : opt.type)}
                    className={`cp-btn cp-action-btn text-xs ${
                      preActionLabel === opt.type
                        ? 'bg-violet-500/20 text-violet-300 border border-violet-500/40'
                        : 'cp-btn-ghost'
                    }`}
                  >
                    {optionLabel}
                  </button>
                );
              })}
            </div>
          ) : null}

          {/* GTO button (mobile only) */}
          {hasGtoButton && (
            <div className="cp-action-utility">
              <button
                onClick={() => {
                  onOpenGto?.();
                  setShowUtilityMenu(false);
                }}
                className={`cp-btn cp-action-meta-btn cp-action-meta-btn--tight text-[11px] ${
                  advice
                    ? 'bg-gradient-to-r from-amber-500/20 to-orange-500/20 text-amber-300 border border-amber-500/30'
                    : 'cp-btn-ghost'
                }`}
                aria-label="Open GTO Coach"
                title="GTO Coach"
              >
                <span className="flex items-center gap-1">
                  <span className="w-4 h-4 rounded bg-white/20 flex items-center justify-center text-[8px] font-extrabold shrink-0">
                    G
                  </span>
                  <span>GTO</span>
                  {advice?.recommended && (
                    <span className="text-[9px] font-bold uppercase bg-white/15 px-1 py-0.5 rounded-full">
                      {advice.recommended}
                    </span>
                  )}
                </span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default BottomActionBar;
