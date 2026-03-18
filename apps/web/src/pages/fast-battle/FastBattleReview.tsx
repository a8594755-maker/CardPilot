/**
 * FastBattleReview — Full session analytics after clicking End.
 * Sections: Summary, Behavior Stats, GTO Leaks, Problem Hands, Recommendations, Hand History.
 */

import { useState } from 'react';
import type {
  FastBattleReport,
  FastBattleHandRecord,
  FastBattleProblemHand,
  SessionLeakSummary,
  GtoAuditResult,
  DrillSuggestion,
} from '@cardpilot/shared-types';
import { CardGlyph } from '../../components/CardGlyph';

interface Props {
  report: FastBattleReport;
  onPlayAgain: () => void;
  onExit: () => void;
}

// ── 6-max NLH GTO reference ranges ──

const REF_RANGES: Record<string, { low: number; high: number; pct?: boolean }> = {
  vpip: { low: 0.2, high: 0.28, pct: true },
  pfr: { low: 0.16, high: 0.22, pct: true },
  threeBet: { low: 0.07, high: 0.12, pct: true },
  foldTo3Bet: { low: 0.5, high: 0.65, pct: true },
  cbetFlop: { low: 0.55, high: 0.75, pct: true },
  cbetTurn: { low: 0.45, high: 0.65, pct: true },
  af: { low: 2.0, high: 4.0 },
  wtsd: { low: 0.25, high: 0.35, pct: true },
  wsd: { low: 0.48, high: 0.58, pct: true },
};

function rangeColor(key: string, value: number): string {
  const ref = REF_RANGES[key];
  if (!ref) return 'text-white';
  if (value >= ref.low && value <= ref.high) return 'text-emerald-400';
  return 'text-red-400';
}

export function FastBattleReview({ report, onPlayAgain, onExit }: Props) {
  const { stats, sessionLeak, problemHands, recommendations, handRecords } = report;
  const durationMin = Math.round(report.durationMs / 60_000);
  const [historyOpen, setHistoryOpen] = useState(handRecords.length <= 20);

  return (
    <main className="flex-1 p-4 overflow-y-auto">
      <div className="max-w-3xl mx-auto space-y-4">
        {/* ── A. Session Header ── */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-white">Session Review</h2>
            <p className="text-xs text-slate-500">
              {stats.handsPlayed} hands in {durationMin || '<1'}min
              {stats.decisionsPerHour > 0 && ` | ${stats.decisionsPerHour} dec/hr`}
            </p>
          </div>
          <div className="text-right">
            <div
              className={`text-lg font-bold font-mono ${stats.netChips >= 0 ? 'text-emerald-400' : 'text-red-400'}`}
            >
              {stats.netChips >= 0 ? '+' : ''}
              {stats.netChips}
            </div>
            <div className="text-xs text-slate-500">
              {stats.netBb >= 0 ? '+' : ''}
              {stats.netBb.toFixed(1)} BB
            </div>
          </div>
        </div>

        {/* ── B. Behavior Stats ── */}
        <div className="glass-card p-3">
          <h3 className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2">
            Behavior Overview
          </h3>
          <div className="grid grid-cols-5 gap-2 text-center text-xs">
            <StatCell label="VPIP" value={pct(stats.vpip)} color={rangeColor('vpip', stats.vpip)} />
            <StatCell label="PFR" value={pct(stats.pfr)} color={rangeColor('pfr', stats.pfr)} />
            <StatCell
              label="3-Bet"
              value={pct(stats.threeBet)}
              color={rangeColor('threeBet', stats.threeBet)}
            />
            <StatCell
              label="Fold 3B"
              value={pct(stats.foldTo3Bet)}
              color={rangeColor('foldTo3Bet', stats.foldTo3Bet)}
            />
            <StatCell
              label="AF"
              value={stats.aggressionFactor.toFixed(1)}
              color={rangeColor('af', stats.aggressionFactor)}
            />
          </div>
          <div className="grid grid-cols-5 gap-2 text-center text-xs mt-2">
            <StatCell
              label="CB Flop"
              value={pct(stats.cbetFlop)}
              color={rangeColor('cbetFlop', stats.cbetFlop)}
            />
            <StatCell
              label="CB Turn"
              value={pct(stats.cbetTurn)}
              color={rangeColor('cbetTurn', stats.cbetTurn)}
            />
            <StatCell label="WTSD" value={pct(stats.wtsd)} color={rangeColor('wtsd', stats.wtsd)} />
            <StatCell label="W$SD" value={pct(stats.wsd)} color={rangeColor('wsd', stats.wsd)} />
            <StatCell
              label="Won"
              value={`${stats.handsWon}/${stats.handsPlayed}`}
              color="text-white"
            />
          </div>
          <p className="text-[9px] text-slate-600 mt-2 text-center">
            <span className="text-emerald-400">Green</span> = GTO range &nbsp;
            <span className="text-red-400">Red</span> = outside range
          </p>
        </div>

        {/* ── C. GTO Leak Summary ── */}
        {sessionLeak && <LeakSummaryCard leak={sessionLeak} />}

        {/* ── D. Problem Hands ── */}
        {problemHands.length > 0 && <ProblemHandsCard hands={problemHands} />}

        {/* ── E. Training Recommendations ── */}
        {recommendations.length > 0 && <RecommendationsCard recommendations={recommendations} />}

        {/* ── F. Hand History (collapsible) ── */}
        <div>
          <button
            onClick={() => setHistoryOpen(!historyOpen)}
            className="flex items-center gap-1 text-xs font-semibold text-slate-400 uppercase tracking-wider hover:text-slate-300 transition-colors"
          >
            <span className="text-[10px]">{historyOpen ? '▼' : '▶'}</span>
            Hand History ({handRecords.length})
          </button>
          {historyOpen && (
            <div className="space-y-2 mt-2">
              {handRecords.length === 0 ? (
                <div className="text-sm text-slate-500 text-center py-4">No hands played</div>
              ) : (
                handRecords.map((hand, i) => <HandRow key={hand.handId} hand={hand} index={i} />)
              )}
            </div>
          )}
        </div>

        {/* ── G. Action Buttons ── */}
        <div className="flex gap-3 pt-2 pb-6">
          <button
            onClick={onPlayAgain}
            className="flex-1 py-3 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 text-black font-bold hover:from-amber-400 hover:to-orange-400 transition-all active:scale-[0.98]"
          >
            Play Again
          </button>
          <button
            onClick={onExit}
            className="px-6 py-3 rounded-xl bg-slate-700 text-slate-300 font-medium hover:bg-slate-600 transition-colors"
          >
            Exit
          </button>
        </div>
      </div>
    </main>
  );
}

// ── Leak Summary Card ──

function LeakSummaryCard({ leak }: { leak: SessionLeakSummary }) {
  const streets = ['PREFLOP', 'FLOP', 'TURN', 'RIVER'];
  const maxStreetLeak = Math.max(
    ...streets.map((s) => Math.abs(leak.byStreet[s]?.leakedBb ?? 0)),
    0.01,
  );

  const deviationTypes = ['OVERFOLD', 'UNDERFOLD', 'OVERBLUFF', 'UNDERBLUFF'] as const;
  const deviationLabels: Record<string, string> = {
    OVERFOLD: 'Overfold',
    UNDERFOLD: 'Underfold',
    OVERBLUFF: 'Overbluff',
    UNDERBLUFF: 'Underbluff',
  };

  return (
    <div className="glass-card p-3 space-y-3">
      <h3 className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
        GTO Leak Summary
      </h3>

      {/* Headline stats */}
      <div className="flex gap-4 text-xs">
        <div>
          <div className="text-red-400 font-mono font-medium text-sm">
            {leak.leakedBbPer100.toFixed(1)}
          </div>
          <div className="text-[10px] text-slate-500">BB/100 leaked</div>
        </div>
        <div>
          <div className="text-white font-mono font-medium text-sm">
            {leak.totalLeakedBb.toFixed(1)}
          </div>
          <div className="text-[10px] text-slate-500">Total BB leaked</div>
        </div>
        <div>
          <div className="text-white font-mono font-medium text-sm">
            {leak.handsAudited}/{leak.handsPlayed}
          </div>
          <div className="text-[10px] text-slate-500">Hands audited</div>
        </div>
      </div>

      {/* Street breakdown bars */}
      <div className="space-y-1">
        <div className="text-[10px] text-slate-500 font-semibold">Leak by Street</div>
        {streets.map((street) => {
          const bucket = leak.byStreet[street];
          if (!bucket) return null;
          const pctWidth = Math.max((Math.abs(bucket.leakedBb) / maxStreetLeak) * 100, 2);
          return (
            <div key={street} className="flex items-center gap-2 text-[10px]">
              <span className="text-slate-400 w-14 text-right">{street.slice(0, 3)}</span>
              <div className="flex-1 h-3 bg-slate-800 rounded overflow-hidden">
                <div className="h-full bg-red-500/60 rounded" style={{ width: `${pctWidth}%` }} />
              </div>
              <span className="text-red-400 font-mono w-12 text-right">
                {bucket.leakedBb.toFixed(1)}bb
              </span>
            </div>
          );
        })}
      </div>

      {/* Deviation type breakdown */}
      <div className="flex flex-wrap gap-2">
        {deviationTypes.map((dt) => {
          const bucket = leak.byDeviation[dt];
          if (!bucket || bucket.count === 0) return null;
          return (
            <div key={dt} className="text-[10px] bg-slate-800/60 px-2 py-1 rounded">
              <span className="text-slate-400">{deviationLabels[dt]}</span>
              <span className="text-white font-mono ml-1">{bucket.count}x</span>
              <span className="text-red-400 font-mono ml-1">-{bucket.leakedBb.toFixed(1)}bb</span>
            </div>
          );
        })}
      </div>

      {/* Top leaks */}
      {leak.topLeaks.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] text-slate-500 font-semibold">Top Leaks</div>
          {leak.topLeaks.slice(0, 5).map((lk, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              <span className="text-red-400 font-mono w-12 text-right shrink-0">
                -{lk.leakedBb.toFixed(1)}bb
              </span>
              <div>
                <span className="text-slate-200">{lk.label}</span>
                {lk.description && <span className="text-slate-500 ml-1">- {lk.description}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Problem Hands Card ──

function ProblemHandsCard({ hands }: { hands: FastBattleProblemHand[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className="glass-card p-3 space-y-2">
      <h3 className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
        Problem Hands (Top {hands.length})
      </h3>
      {hands.map((hand) => {
        const isOpen = expandedId === hand.handId;
        return (
          <div key={hand.handId}>
            <button
              onClick={() => setExpandedId(isOpen ? null : hand.handId)}
              className="w-full flex items-center gap-2 p-2 rounded-lg bg-slate-800/50 hover:bg-slate-700/50 transition-colors text-xs text-left"
            >
              <span className="text-slate-500 w-5 text-right">#{hand.rank}</span>
              <span className="text-slate-400 font-mono w-6">{hand.heroPosition || '?'}</span>
              <div className="flex gap-0.5">
                {hand.holeCards[0] !== '??' ? (
                  <>
                    <CardGlyph card={hand.holeCards[0]} size="sm" />
                    <CardGlyph card={hand.holeCards[1]} size="sm" />
                  </>
                ) : (
                  <span className="text-slate-500">??</span>
                )}
              </div>
              {hand.board.length > 0 && (
                <div className="flex gap-0.5 ml-1">
                  {hand.board.map((c, j) => (
                    <CardGlyph key={j} card={c} size="sm" />
                  ))}
                </div>
              )}
              <span className="text-red-400 font-mono ml-auto">
                -{hand.totalLeakedBb.toFixed(1)}bb
              </span>
              <span className="text-slate-500 text-[10px]">{isOpen ? '▼' : '▶'}</span>
            </button>
            {isOpen && hand.audits.length > 0 && (
              <div className="ml-7 mt-1 space-y-1">
                {hand.audits.map((audit, i) => (
                  <AuditRow key={i} audit={audit} />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Audit Row (per-decision detail) ──

function AuditRow({ audit }: { audit: GtoAuditResult }) {
  const evColor = audit.evDiffBb < 0 ? 'text-red-400' : 'text-emerald-400';
  const actionLabel = audit.actualAction === 'all_in' ? 'allin' : audit.actualAction;
  const recLabel = audit.recommendedAction;

  // Build GTO mix string
  const mixParts: string[] = [];
  if (audit.gtoMix) {
    for (const [action, freq] of Object.entries(audit.gtoMix)) {
      if (freq > 0) {
        mixParts.push(`${action} ${(freq * 100).toFixed(0)}%`);
      }
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] p-1.5 rounded bg-slate-900/50">
      <span className="text-slate-500 uppercase">{audit.street.slice(0, 3)}</span>
      <span className="text-slate-300">
        did <span className="text-amber-300 font-medium">{actionLabel}</span>
      </span>
      <span className="text-slate-500">
        GTO: <span className="text-slate-300">{recLabel}</span>
      </span>
      <span className={`font-mono ${evColor}`}>
        {audit.evDiffBb >= 0 ? '+' : ''}
        {audit.evDiffBb.toFixed(2)}bb
      </span>
      <span className="text-slate-600 italic">{audit.deviationType}</span>
      {mixParts.length > 0 && (
        <span className="text-slate-600 text-[9px]">({mixParts.join(', ')})</span>
      )}
    </div>
  );
}

// ── Recommendations Card ──

function RecommendationsCard({ recommendations }: { recommendations: DrillSuggestion[] }) {
  return (
    <div className="glass-card p-3 space-y-2">
      <h3 className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
        Recommended Practice
      </h3>
      {recommendations.slice(0, 5).map((rec, i) => (
        <div key={i} className="flex items-start gap-2 text-xs p-2 rounded-lg bg-slate-800/50">
          <span className="text-amber-400 shrink-0">{i + 1}.</span>
          <div>
            <span className="text-slate-200">{rec.title}</span>
            {rec.description && <p className="text-slate-500 mt-0.5">{rec.description}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Hand History Row ──

function HandRow({ hand, index }: { hand: FastBattleHandRecord; index: number }) {
  const resultColor =
    hand.result > 0 ? 'text-emerald-400' : hand.result < 0 ? 'text-red-400' : 'text-slate-400';

  const heroFolded = hand.heroActions.some((a) => a.action === 'fold');
  const allSeats = Object.keys(hand.allHoleCards ?? {})
    .map(Number)
    .sort((a, b) => a - b);

  return (
    <div className="glass-card p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500 w-6 text-right">#{index + 1}</span>
          <span className="text-xs text-slate-400 font-mono">{hand.heroPosition}</span>
          <div className="flex gap-0.5">
            <CardGlyph card={hand.holeCards[0]} size="sm" />
            <CardGlyph card={hand.holeCards[1]} size="sm" />
          </div>
          {heroFolded && <span className="text-[10px] text-slate-500">folded</span>}
        </div>
        <span className={`text-sm font-mono font-medium ${resultColor}`}>
          {hand.result > 0 ? '+' : ''}
          {hand.result}
        </span>
      </div>

      {hand.board.length > 0 && (
        <div className="flex gap-0.5 ml-8">
          {hand.board.map((card, j) => (
            <CardGlyph key={j} card={card} size="sm" />
          ))}
        </div>
      )}

      {allSeats.length > 0 && (
        <div className="flex flex-wrap gap-x-3 gap-y-1 ml-8">
          {allSeats.map((seat) => {
            const cards = hand.allHoleCards[seat];
            if (!cards) return null;
            const isHero = seat === hand.heroSeat;
            return (
              <div key={seat} className={`flex items-center gap-1 ${isHero ? 'opacity-50' : ''}`}>
                <span className="text-[10px] text-slate-500">S{seat}</span>
                <CardGlyph card={cards[0]} size="sm" />
                <CardGlyph card={cards[1]} size="sm" />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Helpers ──

function StatCell({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div>
      <div className={`font-mono font-medium ${color}`}>{value}</div>
      <div className="text-[10px] text-slate-500">{label}</div>
    </div>
  );
}

function pct(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}
