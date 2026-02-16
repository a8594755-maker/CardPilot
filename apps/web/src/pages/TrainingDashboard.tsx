/**
 * Training Dashboard — GTO Leaked Value Overview
 *
 * Shows real-time session leak summary, per-hand audit cards,
 * top leaks breakdown, and drill suggestions.
 */

import { useState } from "react";
import type { HandAuditSummary, SessionLeakSummary, GtoAuditResult } from "@cardpilot/shared-types";

// ── Props ──

interface TrainingDashboardProps {
  handAudits: HandAuditSummary[];
  sessionLeak: SessionLeakSummary | null;
  hasData: boolean;
}

export function TrainingDashboard({ handAudits, sessionLeak, hasData }: TrainingDashboardProps) {
  const [selectedHandId, setSelectedHandId] = useState<string | null>(null);
  const selectedHand = handAudits.find((h) => h.handId === selectedHandId) ?? null;

  if (!hasData) {
    return (
      <main className="flex-1 p-4 overflow-y-auto">
        <div className="max-w-4xl mx-auto">
          <div className="glass-card p-8 text-center">
            <div className="text-4xl mb-4">🎯</div>
            <h2 className="text-xl font-bold text-white mb-2">GTO Training Dashboard</h2>
            <p className="text-slate-400 text-sm max-w-md mx-auto">
              Play hands in Coach mode to see your GTO audit results here.
              Every decision is analyzed against optimal strategy after each hand.
            </p>
            <div className="mt-6 grid grid-cols-3 gap-4 max-w-sm mx-auto text-xs text-slate-500">
              <div className="glass-card p-3">
                <div className="text-lg mb-1">📊</div>
                <div>Leaked BB/100</div>
              </div>
              <div className="glass-card p-3">
                <div className="text-lg mb-1">🔍</div>
                <div>Top Leaks</div>
              </div>
              <div className="glass-card p-3">
                <div className="text-lg mb-1">💡</div>
                <div>Drill Suggestions</div>
              </div>
            </div>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="flex-1 p-2 sm:p-4 overflow-y-auto">
      <div className="max-w-5xl mx-auto space-y-4">
        {/* ── Header ── */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-white">GTO Training</h2>
            <p className="text-xs text-slate-500">Live audit of your decisions against GTO strategy</p>
          </div>
          {sessionLeak && (
            <div className="text-right">
              <div className="text-xs text-slate-500">Session</div>
              <div className="text-sm text-slate-300">
                {sessionLeak.handsAudited} / {sessionLeak.handsPlayed} hands
              </div>
            </div>
          )}
        </div>

        {/* ── Session Summary Card ── */}
        {sessionLeak && <SessionSummaryCard leak={sessionLeak} />}

        {/* ── Two-column layout: hand list + detail ── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Hand audit list */}
          <div className="lg:col-span-1 space-y-2">
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Recent Hands</div>
            <div className="space-y-1 max-h-[60vh] overflow-y-auto pr-1">
              {handAudits.map((h) => (
                <HandAuditCard
                  key={h.handId}
                  summary={h}
                  selected={h.handId === selectedHandId}
                  onClick={() => setSelectedHandId(h.handId)}
                />
              ))}
            </div>
          </div>

          {/* Detail panel */}
          <div className="lg:col-span-2">
            {selectedHand ? (
              <HandAuditDetail summary={selectedHand} />
            ) : (
              <div className="glass-card p-8 text-center text-slate-500 text-sm">
                Select a hand to see decision-by-decision GTO analysis
              </div>
            )}

            {/* Top Leaks */}
            {sessionLeak && sessionLeak.topLeaks.length > 0 && (
              <div className="mt-4">
                <TopLeaksCard leaks={sessionLeak.topLeaks} />
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}

// ── Session Summary Card ──

function SessionSummaryCard({ leak }: { leak: SessionLeakSummary }) {
  const leakedColor = leak.totalLeakedBb < -1
    ? "text-red-400"
    : leak.totalLeakedBb > 1
      ? "text-emerald-400"
      : "text-slate-300";

  const per100Color = leak.leakedBbPer100 < -2
    ? "text-red-400"
    : leak.leakedBbPer100 > 2
      ? "text-emerald-400"
      : "text-slate-300";

  return (
    <div className="glass-card p-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatBlock
          label="Leaked BB"
          value={formatBb(leak.totalLeakedBb)}
          color={leakedColor}
        />
        <StatBlock
          label="BB/100"
          value={formatBb(leak.leakedBbPer100)}
          color={per100Color}
        />
        <StatBlock
          label="Hands Audited"
          value={`${leak.handsAudited}`}
          color="text-slate-300"
        />
        <StatBlock
          label="Decisions"
          value={`${Object.values(leak.byStreet).reduce((s, b) => s + b.decisionCount, 0)}`}
          color="text-slate-300"
        />
      </div>

      {/* Street breakdown */}
      <div className="mt-3 pt-3 border-t border-white/5">
        <div className="text-xs text-slate-500 mb-2">Leaked by Street</div>
        <div className="flex gap-3">
          {(["PREFLOP", "FLOP", "TURN", "RIVER"] as const).map((street) => {
            const bucket = leak.byStreet[street];
            if (!bucket || bucket.decisionCount === 0) return null;
            const color = bucket.leakedBb < -0.5 ? "text-red-400" : bucket.leakedBb > 0.5 ? "text-emerald-400" : "text-slate-400";
            return (
              <div key={street} className="text-center">
                <div className="text-[10px] text-slate-500 uppercase">{street}</div>
                <div className={`text-sm font-mono ${color}`}>{formatBb(bucket.leakedBb)}</div>
                <div className="text-[10px] text-slate-600">{bucket.decisionCount} dec</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Deviation breakdown */}
      {Object.keys(leak.byDeviation).length > 0 && (
        <div className="mt-3 pt-3 border-t border-white/5">
          <div className="text-xs text-slate-500 mb-2">Deviation Types</div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(leak.byDeviation)
              .filter(([type]) => type !== "CORRECT")
              .sort(([, a], [, b]) => a.leakedBb - b.leakedBb)
              .map(([type, bucket]) => (
                <span
                  key={type}
                  className={`text-[10px] px-2 py-0.5 rounded-full ${
                    bucket.leakedBb < -0.5
                      ? "bg-red-500/10 text-red-400 border border-red-500/20"
                      : "bg-white/5 text-slate-400 border border-white/10"
                  }`}
                >
                  {formatDeviationType(type)} ({bucket.count}x, {formatBb(bucket.leakedBb)} bb)
                </span>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Hand Audit Card (list item) ──

function HandAuditCard({
  summary,
  selected,
  onClick,
}: {
  summary: HandAuditSummary;
  selected: boolean;
  onClick: () => void;
}) {
  const leaked = summary.totalLeakedBb;
  const color = leaked < -0.5 ? "text-red-400" : leaked > 0.5 ? "text-emerald-400" : "text-slate-400";
  const borderColor = selected ? "border-emerald-500/40" : "border-white/5";

  return (
    <button
      onClick={onClick}
      className={`w-full text-left glass-card p-2.5 border ${borderColor} hover:border-white/20 transition-all`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500 font-mono">#{summary.handId.slice(-6)}</span>
          <span className="text-[10px] text-slate-600 uppercase">{summary.spotType}</span>
        </div>
        <span className={`text-sm font-mono font-medium ${color}`}>
          {formatBb(leaked)} bb
        </span>
      </div>
      <div className="flex items-center gap-1 mt-1">
        <span className="text-[10px] text-slate-500">{summary.decisionCount} decisions</span>
        {summary.handLineTags.slice(0, 3).map((tag) => (
          <span key={tag} className="text-[9px] px-1.5 py-0.5 rounded bg-white/5 text-slate-500">
            {tag.replace(/_/g, " ")}
          </span>
        ))}
      </div>
    </button>
  );
}

// ── Hand Audit Detail ──

function HandAuditDetail({ summary }: { summary: HandAuditSummary }) {
  return (
    <div className="glass-card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-white">
          Hand #{summary.handId.slice(-6)}
        </h3>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-500 uppercase">{summary.spotType}</span>
          <span className={`text-sm font-mono font-medium ${
            summary.totalLeakedBb < -0.5 ? "text-red-400" : summary.totalLeakedBb > 0.5 ? "text-emerald-400" : "text-slate-300"
          }`}>
            {formatBb(summary.totalLeakedBb)} bb
          </span>
        </div>
      </div>

      {/* Per-decision audit rows */}
      <div className="space-y-2">
        {summary.audits.map((audit, i) => (
          <AuditRow key={audit.decisionPointId} audit={audit} index={i} />
        ))}
      </div>

      {summary.audits.length === 0 && (
        <div className="text-xs text-slate-500 text-center py-4">
          No auditable decisions in this hand
        </div>
      )}
    </div>
  );
}

// ── Single Audit Row ──

function AuditRow({ audit, index }: { audit: GtoAuditResult; index: number }) {
  const isCorrect = audit.deviationType === "CORRECT";
  const bgColor = isCorrect
    ? "bg-emerald-500/5 border-emerald-500/10"
    : "bg-red-500/5 border-red-500/10";
  const actionColor = isCorrect ? "text-emerald-400" : "text-red-400";

  return (
    <div className={`p-3 rounded-lg border ${bgColor}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-500 font-mono">#{index + 1}</span>
          <span className="text-xs text-slate-400 uppercase font-medium">{audit.street}</span>
          <span className={`text-xs font-medium ${actionColor}`}>
            {isCorrect ? "✓" : "✗"} {formatDeviationType(audit.deviationType)}
          </span>
        </div>
        <span className={`text-xs font-mono ${audit.evDiffBb < -0.1 ? "text-red-400" : "text-slate-400"}`}>
          {formatBb(audit.evDiffBb)} bb
        </span>
      </div>

      <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
        <div>
          <span className="text-slate-500">Hero did: </span>
          <span className="text-white font-medium">{audit.actualAction}</span>
        </div>
        <div>
          <span className="text-slate-500">GTO says: </span>
          <span className="text-white font-medium">{audit.recommendedAction}</span>
        </div>
        <div>
          <span className="text-slate-500">Position: </span>
          <span className="text-slate-300">{audit.heroPosition}</span>
        </div>
        <div>
          <span className="text-slate-500">Deviation: </span>
          <span className="text-slate-300">{(audit.deviationScore * 100).toFixed(0)}%</span>
        </div>
      </div>

      {/* GTO mix bar */}
      <div className="mt-2">
        <div className="flex h-2 rounded-full overflow-hidden bg-white/5">
          {audit.gtoMix.raise > 0.01 && (
            <div
              className="bg-red-500/70 transition-all"
              style={{ width: `${audit.gtoMix.raise * 100}%` }}
              title={`Raise ${(audit.gtoMix.raise * 100).toFixed(0)}%`}
            />
          )}
          {audit.gtoMix.call > 0.01 && (
            <div
              className="bg-emerald-500/70 transition-all"
              style={{ width: `${audit.gtoMix.call * 100}%` }}
              title={`Call ${(audit.gtoMix.call * 100).toFixed(0)}%`}
            />
          )}
          {audit.gtoMix.fold > 0.01 && (
            <div
              className="bg-slate-500/50 transition-all"
              style={{ width: `${audit.gtoMix.fold * 100}%` }}
              title={`Fold ${(audit.gtoMix.fold * 100).toFixed(0)}%`}
            />
          )}
        </div>
        <div className="flex justify-between text-[9px] text-slate-600 mt-0.5">
          <span>R {(audit.gtoMix.raise * 100).toFixed(0)}%</span>
          <span>C {(audit.gtoMix.call * 100).toFixed(0)}%</span>
          <span>F {(audit.gtoMix.fold * 100).toFixed(0)}%</span>
        </div>
      </div>
    </div>
  );
}

// ── Top Leaks Card ──

function TopLeaksCard({ leaks }: { leaks: SessionLeakSummary["topLeaks"] }) {
  return (
    <div className="glass-card p-4">
      <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Top Leaks</h3>
      <div className="space-y-2">
        {leaks.map((leak) => (
          <div key={leak.rank} className="flex items-start gap-3 p-2 rounded-lg bg-red-500/5 border border-red-500/10">
            <span className="text-red-400 font-bold text-sm">#{leak.rank}</span>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-white">{leak.label}</div>
              <div className="text-[10px] text-slate-500 mt-0.5">{leak.description}</div>
            </div>
            <span className="text-xs font-mono text-red-400 whitespace-nowrap">
              {formatBb(leak.leakedBb)} bb
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Shared components ──

function StatBlock({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="text-center">
      <div className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</div>
      <div className={`text-lg font-mono font-bold ${color}`}>{value}</div>
    </div>
  );
}

// ── Helpers ──

function formatBb(bb: number): string {
  if (Math.abs(bb) < 0.01) return "0.0";
  const sign = bb > 0 ? "+" : "";
  return `${sign}${bb.toFixed(1)}`;
}

function formatDeviationType(type: string): string {
  const labels: Record<string, string> = {
    OVERFOLD: "Over-fold",
    UNDERFOLD: "Under-fold",
    OVERBLUFF: "Over-bluff",
    UNDERBLUFF: "Under-bluff",
    OVERCALL: "Over-call",
    UNDERCALL: "Under-call",
    CORRECT: "Correct",
  };
  return labels[type] ?? type;
}
