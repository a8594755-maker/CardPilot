import { memo } from "react";
import type { TablePlayer, TimerState } from "@cardpilot/shared-types";
import { PokerCard } from "./PokerCard";
import { formatChips, formatDelta } from "../lib/format-chips";

export function Field({ label, w, children }: { label: string; w: string; children: React.ReactNode }) {
  return (
    <div className={`space-y-1 ${w}`}>
      <label className="text-[10px] font-medium text-slate-500 uppercase tracking-wider">{label}</label>
      {children}
    </div>
  );
}

export function InfoCell({ label, value, highlight, cyan }: { label: string; value: string; highlight?: boolean; cyan?: boolean }) {
  return (
    <div>
      <span className="cp-street-label text-[10px] text-slate-500 uppercase tracking-wider font-medium">{label}</span>
      <div className={`cp-action-label text-sm font-semibold cp-num ${highlight ? "text-amber-400 uppercase" : cyan ? "text-cyan-400" : "text-white"}`}>{value}</div>
    </div>
  );
}

function TimerRing({ remaining, total, urgent, usingTimeBank }: {
  remaining: number; total: number; urgent: boolean; usingTimeBank: boolean;
}) {
  const pct = Math.max(0, Math.min(1, remaining / Math.max(total, 1)));
  const r = 18;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - pct);
  const color = urgent ? "#ef4444" : usingTimeBank ? "#f59e0b" : "#22c55e";
  return (
    <svg className="cp-timer-ring" width="44" height="44" viewBox="0 0 44 44" aria-hidden="true">
      <circle cx="22" cy="22" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="3" />
      <circle cx="22" cy="22" r={r} fill="none" stroke={color} strokeWidth="3"
        strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={offset}
        transform="rotate(-90 22 22)"
        style={{ transition: "stroke-dashoffset 1s linear, stroke 0.3s ease" }} />
    </svg>
  );
}

export const SeatChip = memo(function SeatChip({ player, seatNum, isActor, isMe, isOwner, isCoHost, timer, timerTotal, posLabel, isButton, displayBB, bigBlind, lastAction, equity, isAllInLocked, handHint, pendingLeave, revealedCards, revealedHandName, isMucked, onClickRevealed, onClickEmpty, isWinner, isWinnerPulse, netDelta }: {
  player?: TablePlayer; seatNum: number; isActor: boolean; isMe: boolean;
  isOwner?: boolean; isCoHost?: boolean; timer?: TimerState | null; timerTotal?: number;
  posLabel?: string; isButton?: boolean; displayBB?: boolean; bigBlind?: number;
  lastAction?: { action: string; amount: number } | null;
  equity?: { winRate: number; tieRate: number; equityRate: number } | null;
  isAllInLocked?: boolean;
  handHint?: string;
  pendingLeave?: boolean;
  revealedCards?: [string, string];
  revealedHandName?: string;
  isMucked?: boolean;
  onClickRevealed?: () => void;
  onClickEmpty?: (seatNum: number) => void;
  isWinner?: boolean;
  isWinnerPulse?: boolean;
  netDelta?: number;
}) {
  const bb = bigBlind || 1;
  const fmt = (v: number) => formatChips(v, { mode: displayBB ? "bb" : "chips", bbSize: bb });

  if (!player) {
    return (
      <div onClick={() => onClickEmpty?.(seatNum)}
        data-empty-seat
        className="cp-seat-empty w-20 h-20 md:w-24 md:h-24 rounded-full bg-black/50 border border-dashed border-white/15 flex items-center justify-center cursor-pointer hover:border-emerald-500/40 hover:bg-emerald-500/5 transition-colors group">
        <span className="cp-seat-empty-label text-sm text-slate-500 group-hover:text-emerald-400">+Sit</span>
      </div>
    );
  }

  // Timer progress calculation (for border color + inline badge)
  const timerUrgent = timer && timer.remaining <= 3;
  const timerColor = timerUrgent ? "text-red-400" : timer?.usingTimeBank ? "text-amber-400" : "text-emerald-400";
  // Border glow based on timer state
  const timerBorderClass = timer
    ? timerUrgent ? "ring-2 ring-red-500/60" : timer.usingTimeBank ? "ring-2 ring-amber-500/50" : "ring-2 ring-emerald-500/40"
    : "";

  // Position label colors
  const posColor = posLabel === "BTN" ? "bg-amber-500 text-white" : posLabel === "SB" ? "bg-blue-500 text-white" : posLabel === "BB" ? "bg-red-500 text-white" : "bg-slate-600 text-slate-200";
  const actionType = (lastAction?.action ?? "").toLowerCase();
  let actionLabel = "BET";
  let actionBadgeClass = "text-emerald-300 border-emerald-500/25";
  if (actionType === "raise") {
    actionLabel = "RAISE";
    actionBadgeClass = "text-rose-300 border-rose-500/30";
  } else if (actionType === "all_in") {
    actionLabel = "ALL-IN";
    actionBadgeClass = "text-orange-300 border-orange-500/30";
  } else if (actionType === "call") {
    actionLabel = "CALL";
    actionBadgeClass = "text-sky-300 border-sky-500/30";
  }

  const fmtDelta = (v: number) => formatDelta(v, { mode: displayBB ? "bb" : "chips", bbSize: bb });
  const equityText = isAllInLocked
    ? (equity ? `${Math.round(equity.equityRate * 100)}%` : "—")
    : "Unlocked";

  const heroReveal = isMe && !!revealedCards;

  const seatLabel = (
    <div className={`cp-seat-label relative z-10 ${heroReveal ? "w-44 md:w-48 p-3" : "w-52 md:w-60 p-5"} min-h-[4.5rem] rounded-xl text-center transition-all ${timerBorderClass} ${isWinner ? "cp-seat-win" : ""} ${isWinnerPulse ? "cp-seat-win-pop" : ""} ${
      isActor ? "bg-amber-500/20 border-2 border-amber-400 shadow-[0_0_16px_rgba(245,158,11,0.3)]"
      : isMe ? "bg-cyan-500/10 border-2 border-cyan-400/50"
      : "bg-black/60 border border-white/10"
    }`}>
      {/* Position label */}
      {posLabel && (
        <div className="absolute -top-2 -left-1 z-20">
          <span className={`text-xs px-2.5 py-1 rounded-full font-bold uppercase ${posColor}`}>{posLabel}</span>
        </div>
      )}
      {/* Host badge */}
      {(isOwner || isCoHost) && (
        <div className="absolute -top-2 -right-1 z-20">
          <span className={`text-[11px] px-1.5 py-0.5 rounded font-bold ${isOwner ? "bg-amber-500 text-white" : "bg-blue-500 text-white"}`}>
            {isOwner ? "👑" : "⭐"}
          </span>
        </div>
      )}
      <div className="cp-seat-name text-xl font-bold text-white truncate max-w-full">
        {player.name}
      </div>
      <div className="flex items-center justify-center gap-2">
        <div className="cp-seat-stack text-2xl font-extrabold text-amber-400 cp-num">{fmt(player.stack)}</div>
        {isAllInLocked && equity && (
          <div className="cp-seat-equity flex items-center gap-1">
            <span className="text-xs font-bold text-orange-400 uppercase">ALL-IN</span>
            <span className="text-base font-extrabold text-emerald-300">{Math.round(equity.equityRate * 100)}%</span>
          </div>
        )}
      </div>
      {player.status === "sitting_out" && <div className="cp-seat-status text-sm text-orange-400 font-bold uppercase">Sit Out</div>}
      {player.folded && player.status !== "sitting_out" && <div className="cp-seat-status text-sm text-red-400 font-bold">FOLDED</div>}
      {player.allIn && !equity && <div className="cp-seat-status text-sm text-orange-400 font-bold">ALL-IN</div>}
      {handHint && !player.folded && !revealedCards && (
        <div className="text-xs leading-tight text-cyan-200/90 max-w-[140px] truncate mx-auto" title={handHint}>
          {handHint}
        </div>
      )}
      {/* Timer countdown with progress ring */}
      {timer && (
        <div className="cp-timer-wrap">
          <TimerRing
            remaining={timer.usingTimeBank ? timer.timeBankRemaining : timer.remaining}
            total={timer.usingTimeBank ? (timerTotal ?? 15) : (timerTotal ?? 15)}
            urgent={!!timerUrgent}
            usingTimeBank={!!timer.usingTimeBank}
          />
          <span className={`cp-seat-timer text-sm font-bold tabular-nums min-w-[3.5em] inline-block ${timerColor} ${timerUrgent ? "animate-pulse" : ""}`}>
            {timer.usingTimeBank ? `⏱ ${String(Math.ceil(timer.timeBankRemaining)).padStart(2, "\u2007")}s` : `${String(Math.ceil(timer.remaining)).padStart(2, "\u2007")}s`}
          </span>
        </div>
      )}
      {pendingLeave && (
        <div className="text-xs text-slate-300 italic">Leaving</div>
      )}
    </div>
  );

  return (
    <div className="relative flex flex-col items-center gap-0.5">
      {/* Delta tag (hand-end net change) — enhanced with larger styling */}
      {netDelta !== undefined && netDelta !== 0 && (
        <div className={`cp-delta-tag ${netDelta > 0 ? "cp-delta-tag--positive" : "cp-delta-tag--negative"}`}>
          {netDelta > 0 ? "+" : ""}{fmtDelta(netDelta)}
        </div>
      )}
      {/* BTN dealer chip */}
      {isButton && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 z-30">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-amber-300 to-amber-500 border-2 border-amber-200 shadow-lg flex items-center justify-center">
            <span className="text-[11px] font-black text-amber-900">D</span>
          </div>
        </div>
      )}
      {/* Hero seat with revealed cards: horizontal layout (cards left, info right) */}
      {heroReveal ? (
        <div className="flex flex-col items-center gap-0.5">
          <div className="flex items-center gap-2">
            <button onClick={onClickRevealed} className="flex flex-col items-center gap-1 shrink-0" title="Tap to zoom revealed hand">
              <PokerCard card={revealedCards![0]} variant="mini" className={isWinner ? "cp-card-winner-highlight" : "border-emerald-500/40"} />
              <PokerCard card={revealedCards![1]} variant="mini" className={isWinner ? "cp-card-winner-highlight" : "border-emerald-500/40"} />
            </button>
            {seatLabel}
          </div>
          <div className={`text-sm font-semibold max-w-[200px] truncate ${isWinner ? "text-amber-400" : "text-emerald-300"}`}>{revealedHandName ?? "Revealed"}</div>
        </div>
      ) : (
        <>
          {seatLabel}
          {revealedCards && (
            <button onClick={onClickRevealed} className="flex flex-col items-center gap-1 mt-1" title="Tap to zoom revealed hand">
              <div className="flex items-center gap-1.5">
                <PokerCard card={revealedCards[0]} variant="mini" className={isWinner ? "cp-card-winner-highlight" : "border-emerald-500/40"} />
                <PokerCard card={revealedCards[1]} variant="mini" className={isWinner ? "cp-card-winner-highlight" : "border-emerald-500/40"} />
              </div>
              <div className={`text-sm font-semibold max-w-[200px] truncate ${isWinner ? "text-amber-400" : "text-emerald-300"}`}>{revealedHandName ?? "Revealed"}</div>
            </button>
          )}
        </>
      )}
      {!revealedCards && isMucked && (
        <div className="text-xs uppercase tracking-wider text-slate-500">Mucked</div>
      )}
      {/* Street bet amount — shown below the chip */}
      {player.streetCommitted > 0 && !player.folded && (
        <div className={`cp-bet-pill bg-black/75 px-3 py-1 rounded-full text-base font-bold shadow-sm border ${actionBadgeClass}`}>
          <span className="cp-action-label uppercase text-sm tracking-wider mr-1">{actionLabel}</span>
          <span className="cp-num">{fmt(player.streetCommitted)}</span>
        </div>
      )}
    </div>
  );
});

export function Bar({ label, pct, color }: { label: string; pct: number; color: string }) {
  const p = Math.round(pct * 100);
  return (
    <div className="flex items-center gap-2">
      <span className="w-12 text-[11px] font-medium text-slate-400 uppercase">{label}</span>
      <div className="flex-1 h-5 rounded-full bg-white/5 overflow-hidden">
        <div className={`h-full rounded-full bg-gradient-to-r ${color} transition-all duration-500`} style={{ width: `${p}%` }} />
      </div>
      <span className="w-10 text-right text-xs font-semibold text-slate-300 tabular-nums">{p}%</span>
    </div>
  );
}
