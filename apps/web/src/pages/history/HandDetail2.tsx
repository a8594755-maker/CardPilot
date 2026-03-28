import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  HandActionRecord,
  HandRecord,
  GTOAnalysis,
  LocalGTOSpot,
} from '../../lib/hand-history.js';
import { formatHandAsPokerStars } from '../../lib/hand-history.js';
import { PokerCard } from '../../components/PokerCard.js';
import type { Socket } from 'socket.io-client';
import type { HistoryGTOAnalysis } from '@cardpilot/shared-types';

const STREETS = ['PREFLOP', 'FLOP', 'TURN', 'RIVER'];
const EDITABLE_TAGS = ['SRP', '3bet_pot', '4bet_pot', 'all_in'];

function splitBoard(board: string[]) {
  return {
    flop: board.slice(0, 3),
    turn: board.slice(3, 4),
    river: board.slice(4, 5),
  };
}

function streetGroups(actions: HandActionRecord[]) {
  return STREETS.map((street) => ({
    street,
    actions: actions.filter((a) => a.street.toUpperCase() === street),
  })).filter((g) => g.actions.length > 0);
}

/** Compute running pot total for action display */
function computeRunningPot(actions: HandActionRecord[], upToIndex: number): number {
  let pot = 0;
  for (let i = 0; i <= upToIndex; i++) {
    const a = actions[i];
    if (a.type !== 'fold' && a.type !== 'check') {
      pot += a.amount;
    }
  }
  return pot;
}

type GtoState = 'idle' | 'loading' | 'success' | 'error';

function mapServerToLocal(server: HistoryGTOAnalysis): GTOAnalysis {
  return {
    overallScore: server.overallScore,
    streets: server.spots.map((s) => ({
      street: s.street,
      action: s.heroAction,
      gtoAction: s.recommended.action,
      evDiff: s.deviationScore,
      accuracy: s.deviationScore <= 20 ? 'good' : s.deviationScore <= 50 ? 'ok' : 'bad',
    })),
    analyzedAt: server.computedAt,
    precision: server.precision,
    streetScores: server.streetScores,
    spots: server.spots.map(
      (s): LocalGTOSpot => ({
        street: s.street,
        pot: s.pot,
        toCall: s.toCall,
        effectiveStack: s.effectiveStack,
        heroAction: s.heroAction,
        heroAmount: s.heroAmount,
        recommendedAction: s.recommended.action,
        recommendedMix: s.recommended.mix,
        deviationScore: s.deviationScore,
        evLossBb: s.evLossBb,
        actionTimelineIdx: s.actionTimelineIdx,
        decisionIndex: s.decisionIndex,
        note: s.note,
      }),
    ),
  };
}

interface DecisionPointView {
  id: string;
  street: string;
  pot: number;
  toCall?: number;
  effectiveStack?: number;
  heroAction: string;
  heroAmount: number;
  recommendedAction: string;
  deviationScore: number;
  actionTimelineIdx?: number;
  evLossBb?: number;
  note?: string;
}

/** Action type color helper */
function actionColor(type: string): string {
  if (type === 'fold') return 'text-slate-500';
  if (type === 'raise' || type === 'all_in' || type === 'bet') return 'text-amber-400';
  if (type === 'call') return 'text-emerald-400';
  return 'text-slate-300'; // check
}

export function HandDetail2({
  hand,
  onCopy,
  onDownload,
  onToggleTag,
  socket,
  onSaveAnalysis,
}: {
  hand: HandRecord | null;
  onCopy: (text: string) => Promise<void>;
  onDownload: (hand: HandRecord) => void;
  onToggleTag: (tag: string) => void;
  socket?: Socket | null;
  onSaveAnalysis?: (handId: string, analysis: GTOAnalysis) => void;
}) {
  const [customTag, setCustomTag] = useState('');
  const [copied, setCopied] = useState<'hh' | 'json' | null>(null);
  const [gtoState, setGtoState] = useState<GtoState>('idle');
  const [gtoResult, setGtoResult] = useState<HistoryGTOAnalysis | null>(null);
  const [gtoError, setGtoError] = useState<string | null>(null);
  const [selectedActionIdx, setSelectedActionIdx] = useState<number | null>(null);
  const actionRefs = useRef<Record<number, HTMLDivElement | null>>({});

  // Reset GTO state when hand changes; restore from local cache if available
  useEffect(() => {
    setGtoState(hand?.gtoAnalysis ? 'success' : 'idle');
    setGtoResult(null);
    setGtoError(null);
    setSelectedActionIdx(null);
  }, [hand?.id]);

  // Listen for GTO result from server
  useEffect(() => {
    if (!socket || !hand) return;
    const handler = (payload: {
      handId: string;
      gtoAnalysis: HistoryGTOAnalysis | null;
      error?: string;
    }) => {
      if (payload.handId !== hand.id) return;
      if (payload.error || !payload.gtoAnalysis) {
        setGtoState('error');
        setGtoError(payload.error ?? 'Analysis failed');
        return;
      }
      setGtoResult(payload.gtoAnalysis);
      setGtoState('success');
      // Persist to localStorage
      const localAnalysis = mapServerToLocal(payload.gtoAnalysis);
      onSaveAnalysis?.(hand.id, localAnalysis);
    };
    socket.on('history_gto_result' as string, handler);
    return () => {
      socket.off('history_gto_result' as string, handler);
    };
  }, [socket, hand?.id, onSaveAnalysis]);

  const requestAnalysis = useCallback(
    (precision: 'fast' | 'deep') => {
      if (!socket || !hand) return;
      if (hand.heroCards.length < 2) return;
      setGtoState('loading');
      setGtoError(null);
      setGtoResult(null);
      socket.emit('history_gto_analyze' as string, {
        handId: hand.id,
        handRecord: {
          heroCards: [hand.heroCards[0], hand.heroCards[1]],
          board: hand.board,
          heroSeat: hand.heroSeat ?? 0,
          heroPosition: hand.position,
          stakes: hand.stakes,
          tableSize: hand.tableSize,
          potSize: hand.potSize,
          stackSize: hand.stackSize,
          actions: hand.actions,
          actionTimeline: hand.actionTimeline,
          buttonSeat: hand.buttonSeat,
          positionsBySeat: hand.positionsBySeat,
          stacksBySeatAtStart: hand.stacksBySeatAtStart,
          potLayers: hand.potLayers,
          payoutLedger: hand.payoutLedger,
          smallBlind: hand.smallBlind,
          bigBlind: hand.bigBlind,
          playerNames: hand.playerNames,
        },
        precision,
      });
    },
    [socket, hand],
  );

  const groupedActions = useMemo(() => (hand ? streetGroups(hand.actions) : []), [hand]);
  const groupedActionsWithIndex = useMemo(() => {
    let cursor = 0;
    return groupedActions.map((group) => ({
      ...group,
      actions: group.actions.map((action) => {
        const globalIdx = cursor;
        cursor += 1;
        return { action, globalIdx };
      }),
    }));
  }, [groupedActions]);

  const decisionPoints = useMemo<DecisionPointView[]>(() => {
    if (gtoResult?.spots?.length) {
      return gtoResult.spots.map((spot, idx) => ({
        id: `server-${idx}`,
        street: spot.street,
        pot: spot.pot,
        toCall: spot.toCall,
        effectiveStack: spot.effectiveStack,
        heroAction: spot.heroAction,
        heroAmount: spot.heroAmount,
        recommendedAction: spot.recommended.action,
        deviationScore: spot.deviationScore,
        actionTimelineIdx: spot.actionTimelineIdx,
        evLossBb: spot.evLossBb,
        note: spot.note,
      }));
    }

    if (hand?.gtoAnalysis?.spots?.length) {
      return hand.gtoAnalysis.spots.map((spot, idx) => ({
        id: `local-${idx}`,
        street: spot.street,
        pot: spot.pot,
        toCall: spot.toCall,
        effectiveStack: spot.effectiveStack,
        heroAction: spot.heroAction,
        heroAmount: spot.heroAmount,
        recommendedAction: spot.recommendedAction,
        deviationScore: spot.deviationScore,
        actionTimelineIdx: spot.actionTimelineIdx,
        evLossBb: spot.evLossBb,
        note: spot.note,
      }));
    }

    return [];
  }, [gtoResult, hand?.gtoAnalysis]);

  const onSelectDecisionPoint = useCallback((point: DecisionPointView) => {
    if (typeof point.actionTimelineIdx !== 'number') return;
    setSelectedActionIdx(point.actionTimelineIdx);
    const node = actionRefs.current[point.actionTimelineIdx];
    if (node) {
      node.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, []);

  if (!hand) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <div className="w-14 h-14 rounded-2xl bg-white/[0.03] border border-white/[0.08] flex items-center justify-center mb-4">
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-slate-600"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
        </div>
        <p className="text-slate-400 text-sm font-medium">Select a hand to view details</p>
        <p className="text-slate-600 text-xs mt-1">Click on any hand from the list</p>
      </div>
    );
  }

  const runouts =
    hand.runoutBoards && hand.runoutBoards.length > 0
      ? hand.runoutBoards
      : hand.doubleBoardPayouts && hand.doubleBoardPayouts.length > 0
        ? hand.doubleBoardPayouts.map((run) => run.board)
        : [hand.board];
  const result = hand.result ?? 0;
  const heroSeat = hand.heroSeat;

  const handleCopyHH = async () => {
    const text = formatHandAsPokerStars(hand);
    await onCopy(text);
    setCopied('hh');
    setTimeout(() => setCopied(null), 2000);
  };

  const handleCopyJSON = async () => {
    await onCopy(JSON.stringify(hand, null, 2));
    setCopied('json');
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div className="flex-1 overflow-auto p-3 space-y-3 cp-history-scroll">
      {/* ── Header Card ── */}
      <div className="cp-detail-header rounded-xl bg-gradient-to-br from-slate-800/50 to-slate-800/30 border border-white/[0.06] p-4">
        <div className="flex items-start justify-between gap-3">
          {/* Left: info */}
          <div className="min-w-0 flex-1">
            {/* Room + ID */}
            <div className="flex items-center gap-2 mb-2">
              {(hand.roomName || hand.roomCode) && (
                <span className="text-[11px] text-slate-400 font-medium truncate">
                  {hand.roomName || hand.roomCode}
                </span>
              )}
              {hand.handId && (
                <span className="text-[9px] font-mono text-slate-600 bg-white/[0.04] px-1.5 py-0.5 rounded">
                  #{hand.handId.slice(0, 10)}
                </span>
              )}
            </div>
            {/* Meta row */}
            <div className="flex items-center gap-2 text-[11px] text-slate-400 flex-wrap">
              <span className="font-semibold text-white">
                {hand.gameType} {hand.stakes}
              </span>
              <span className="text-slate-700">/</span>
              <span>{hand.tableSize}-max</span>
              <span className="text-slate-700">/</span>
              <span className="text-cyan-400/80 font-semibold">{hand.position}</span>
              {hand.heroName && (
                <>
                  <span className="text-slate-700">/</span>
                  <span className="text-slate-300">{hand.heroName}</span>
                </>
              )}
            </div>
            <div className="text-[10px] text-slate-600 mt-1.5">
              {hand.endedAt
                ? new Date(hand.endedAt).toLocaleString()
                : new Date(hand.createdAt).toLocaleString()}
            </div>
          </div>
          {/* Right: result */}
          <div className="flex flex-col items-end gap-1 shrink-0">
            <div
              className={`text-2xl font-extrabold tabular-nums leading-none ${
                result > 0 ? 'text-emerald-400' : result < 0 ? 'text-red-400' : 'text-slate-400'
              }`}
            >
              {result > 0 ? '+' : ''}
              {result.toLocaleString()}
            </div>
            <div className="flex items-center gap-2 text-[10px] text-slate-500 mt-1">
              <span className="tabular-nums">Pot {hand.potSize.toLocaleString()}</span>
              <span className="text-slate-700">/</span>
              <span className="tabular-nums">Stack {hand.stackSize.toLocaleString()}</span>
            </div>
          </div>
        </div>

        {/* Hero cards inline */}
        <div className="flex items-center gap-3 mt-3 pt-3 border-t border-white/[0.06]">
          <div className="flex gap-1">
            {hand.heroCards.map((c) => (
              <PokerCard key={c} card={c} variant="seat" />
            ))}
          </div>
          {/* Board inline */}
          {hand.board.length > 0 && (
            <>
              <div className="w-px h-10 bg-white/[0.08]" />
              <div className="flex gap-1">
                {hand.board.map((c, i) => (
                  <PokerCard key={`b${i}`} card={c} variant="mini" />
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* ── Board / Runouts (only if multiple) ── */}
      {runouts.length > 1 && (
        <div className="cp-detail-section">
          <SectionTitle>Runouts</SectionTitle>
          {runouts.map((board, idx) => {
            const split = splitBoard(board);
            return (
              <div
                key={idx}
                className="rounded-lg bg-white/[0.02] border border-white/[0.06] p-3 mb-1.5"
              >
                <div className="text-[10px] font-semibold text-amber-400/80 uppercase mb-2">
                  Run {idx + 1}
                </div>
                <div className="flex items-center gap-4 flex-wrap">
                  {split.flop.length > 0 && <StreetCards label="Flop" cards={split.flop} />}
                  {split.turn.length > 0 && <StreetCards label="Turn" cards={split.turn} />}
                  {split.river.length > 0 && <StreetCards label="River" cards={split.river} />}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── GTO Analysis ── */}
      <div className="cp-detail-section rounded-xl bg-white/[0.02] border border-white/[0.06] p-4">
        <div className="flex items-center justify-between mb-3">
          <SectionTitle noMargin>GTO Analysis</SectionTitle>
          <div className="flex items-center gap-1.5">
            {gtoState !== 'loading' && (
              <>
                <button
                  onClick={() => requestAnalysis('deep')}
                  disabled={!socket}
                  title={!socket ? 'Connect to server to enable GTO analysis.' : 'Deep analysis'}
                  className="text-[10px] px-3 py-1.5 rounded-lg bg-gradient-to-r from-purple-600/70 to-indigo-600/70 text-white/90 font-semibold border border-purple-500/25 hover:from-purple-500/80 hover:to-indigo-500/80 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Analyze
                </button>
                <button
                  onClick={() => requestAnalysis('fast')}
                  disabled={!socket}
                  className="text-[10px] px-2.5 py-1.5 rounded-lg bg-white/[0.04] text-slate-400 border border-white/[0.07] hover:bg-white/[0.08] transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Fast
                </button>
              </>
            )}
          </div>
        </div>

        {gtoState === 'loading' && (
          <div className="flex items-center gap-3 py-4">
            <div className="w-4 h-4 border-2 border-purple-400 border-t-transparent rounded-full animate-spin" />
            <span className="text-[11px] text-slate-400">Analyzing...</span>
          </div>
        )}

        {gtoState === 'error' && (
          <div className="text-[11px] text-red-400/80 py-2">{gtoError ?? 'Analysis failed'}</div>
        )}

        {gtoState === 'success' && (gtoResult || hand.gtoAnalysis) && (
          <GtoResultView result={gtoResult} localAnalysis={hand.gtoAnalysis} />
        )}

        {gtoState === 'idle' && !hand.gtoAnalysis && (
          <div className="text-[11px] text-slate-600 py-2">
            {socket
              ? 'Press Analyze to evaluate against GTO.'
              : 'Connect to server for GTO analysis.'}
          </div>
        )}
      </div>

      {/* ── Decision Points ── */}
      {decisionPoints.length > 0 && (
        <div className="cp-detail-section">
          <SectionTitle>Decision Points</SectionTitle>
          <div className="space-y-1.5">
            {decisionPoints.map((point, idx) => {
              const badge = deviationBadge(point.deviationScore);
              const isLinked = typeof point.actionTimelineIdx === 'number';
              return (
                <button
                  key={point.id}
                  onClick={() => onSelectDecisionPoint(point)}
                  disabled={!isLinked}
                  className={`w-full text-left rounded-lg border p-3 transition-all ${
                    isLinked
                      ? 'border-white/[0.06] bg-white/[0.02] hover:border-purple-500/30 hover:bg-purple-500/[0.03]'
                      : 'border-white/[0.04] bg-white/[0.01] opacity-70'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-[10px] font-bold text-cyan-400 uppercase">
                      {point.street}
                    </span>
                    <span
                      className={`text-[9px] px-1.5 py-0.5 rounded-md border font-semibold ${badge.cls}`}
                    >
                      {badge.label}
                    </span>
                    <span className="text-[9px] text-slate-600">#{idx + 1}</span>
                    <span className="ml-auto text-[10px] text-slate-600 tabular-nums">
                      pot {point.pot.toLocaleString()}
                      {typeof point.toCall === 'number'
                        ? ` / call ${point.toCall.toLocaleString()}`
                        : ''}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-300">
                    <span className="text-slate-500">You: </span>
                    <span className="font-semibold uppercase">{point.heroAction}</span>
                    {point.heroAmount > 0 && (
                      <span className="ml-1 tabular-nums text-slate-400">
                        {point.heroAmount.toLocaleString()}
                      </span>
                    )}
                    <span className="mx-2 text-slate-700">→</span>
                    <span className="text-slate-500">GTO: </span>
                    <span className="font-semibold uppercase text-purple-300">
                      {point.recommendedAction}
                    </span>
                    {typeof point.evLossBb === 'number' && point.evLossBb > 0 && (
                      <span className="ml-2 text-[10px] text-amber-400/70 tabular-nums">
                        -{point.evLossBb.toFixed(2)} bb
                      </span>
                    )}
                  </div>
                  {point.note && (
                    <div className="text-[10px] text-slate-600 mt-1 truncate">{point.note}</div>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Showdown Hands ── */}
      {hand.showdownHands && Object.keys(hand.showdownHands).length > 0 && (
        <div className="cp-detail-section">
          <SectionTitle>Showdown</SectionTitle>
          <div className="space-y-1">
            {Object.entries(hand.showdownHands).map(([seatStr, cards]) => {
              const seatNum = Number(seatStr);
              const playerName = hand.playerNames?.[seatNum] || `Seat ${seatNum}`;
              const isHero = seatNum === heroSeat;
              return (
                <div
                  key={seatStr}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2 border transition-all ${
                    isHero
                      ? 'border-sky-500/20 bg-sky-500/[0.04]'
                      : 'border-white/[0.05] bg-white/[0.015]'
                  }`}
                >
                  <span
                    className={`text-[11px] font-medium min-w-[80px] ${isHero ? 'text-sky-300' : 'text-slate-400'}`}
                  >
                    {playerName}
                    {isHero && <span className="text-[9px] text-sky-500/60 ml-1">you</span>}
                  </span>
                  {cards === 'mucked' ? (
                    <span className="text-[11px] text-slate-600 italic">Mucked</span>
                  ) : (
                    <div className="flex gap-[2px]">
                      {cards.map((c) => (
                        <PokerCard key={c} card={c} variant="mini" />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Tags ── */}
      <div className="cp-detail-section">
        <SectionTitle>Tags</SectionTitle>
        <div className="flex items-center flex-wrap gap-1.5">
          {EDITABLE_TAGS.map((tag) => (
            <button
              key={tag}
              onClick={() => onToggleTag(tag)}
              className={`text-[10px] px-2.5 py-1 rounded-lg border transition-all font-medium ${
                hand.tags.includes(tag)
                  ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                  : 'bg-white/[0.03] text-slate-500 border-white/[0.07] hover:border-white/[0.12] hover:text-slate-300'
              }`}
            >
              {tag}
            </button>
          ))}
          <input
            className="text-[10px] bg-white/[0.03] border border-white/[0.07] rounded-lg px-2.5 py-1 text-slate-300 w-[80px] outline-none focus:border-sky-500/30 focus:w-[120px] transition-all placeholder:text-slate-600"
            value={customTag}
            placeholder="+ tag"
            onChange={(e) => setCustomTag(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                const tag = customTag.trim();
                if (tag && !hand.tags.includes(tag)) onToggleTag(tag);
                setCustomTag('');
              }
            }}
          />
        </div>
      </div>

      {/* ── Action Timeline ── */}
      <div className="cp-detail-section">
        <SectionTitle>Actions</SectionTitle>
        <div className="space-y-2">
          {groupedActionsWithIndex.map((group) => (
            <div
              key={group.street}
              className="rounded-xl border border-white/[0.06] overflow-hidden"
            >
              <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.1em] text-cyan-400/80 bg-white/[0.03] border-b border-white/[0.06]">
                {group.street}
              </div>
              {group.actions.map(({ action: a, globalIdx }, idx) => {
                const isHeroAction = heroSeat != null && a.seat === heroSeat;
                const runningPot = computeRunningPot(hand.actions, globalIdx);
                const isSelected = selectedActionIdx === globalIdx;
                const playerName = hand.playerNames?.[a.seat] || `Seat ${a.seat}`;
                return (
                  <div
                    key={`${group.street}_${idx}`}
                    ref={(el) => {
                      actionRefs.current[globalIdx] = el;
                    }}
                    className={`flex items-center gap-2 px-3 py-1.5 text-[11px] border-b border-white/[0.04] last:border-b-0 transition-all ${
                      isSelected
                        ? 'bg-amber-500/10 ring-1 ring-amber-500/30 ring-inset'
                        : isHeroAction
                          ? 'bg-sky-500/[0.04]'
                          : ''
                    }`}
                  >
                    <span
                      className={`min-w-[72px] truncate text-[11px] ${isHeroAction ? 'text-sky-300 font-medium' : 'text-slate-500'}`}
                    >
                      {playerName}
                    </span>
                    <span className={`font-semibold uppercase text-[11px] ${actionColor(a.type)}`}>
                      {a.type}
                    </span>
                    {a.amount > 0 && (
                      <span className="text-slate-300 tabular-nums text-[11px]">
                        {a.amount.toLocaleString()}
                      </span>
                    )}
                    <span className="ml-auto text-[9px] text-slate-700 tabular-nums">
                      {runningPot.toLocaleString()}
                    </span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {/* ── Export ── */}
      <div className="flex items-center gap-1.5 pt-3 border-t border-white/[0.06]">
        <ExportBtn
          onClick={handleCopyHH}
          active={copied === 'hh'}
          label="Copy HH"
          activeLabel="Copied"
        />
        <ExportBtn
          onClick={handleCopyJSON}
          active={copied === 'json'}
          label="Copy JSON"
          activeLabel="Copied"
        />
        <ExportBtn onClick={() => onDownload(hand)} label="Export" />
      </div>
    </div>
  );
}

// ── Small reusable pieces ──

function SectionTitle({ children, noMargin }: { children: React.ReactNode; noMargin?: boolean }) {
  return (
    <div
      className={`text-[10px] uppercase tracking-[0.1em] text-slate-500 font-semibold ${noMargin ? '' : 'mb-2'}`}
    >
      {children}
    </div>
  );
}

function StreetCards({ label, cards }: { label: string; cards: string[] }) {
  return (
    <div>
      <div className="text-[9px] text-slate-600 uppercase mb-1 font-medium">{label}</div>
      <div className="flex gap-[2px]">
        {cards.map((c, i) => (
          <PokerCard key={`${label}${i}`} card={c} variant="mini" />
        ))}
      </div>
    </div>
  );
}

function ExportBtn({
  onClick,
  label,
  active,
  activeLabel,
}: {
  onClick: () => void;
  label: string;
  active?: boolean;
  activeLabel?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`text-[10px] px-3 py-1.5 rounded-lg border transition-all font-medium ${
        active
          ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
          : 'bg-white/[0.03] text-slate-500 border-white/[0.07] hover:bg-white/[0.06] hover:text-slate-300'
      }`}
    >
      {active && activeLabel ? activeLabel : label}
    </button>
  );
}

// ── GTO Result View ──

function scoreColor(score: number): string {
  if (score >= 80) return 'text-emerald-400';
  if (score >= 50) return 'text-amber-400';
  return 'text-red-400';
}

function scoreBg(score: number): string {
  if (score >= 80) return 'bg-emerald-500';
  if (score >= 50) return 'bg-amber-500';
  return 'bg-red-500';
}

function deviationBadge(score: number): { label: string; cls: string } {
  if (score <= 20)
    return { label: 'Good', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25' };
  if (score <= 50)
    return { label: 'OK', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/25' };
  return { label: 'Miss', cls: 'bg-red-500/15 text-red-300 border-red-500/25' };
}

function GtoResultView({
  result,
  localAnalysis,
}: {
  result: HistoryGTOAnalysis | null;
  localAnalysis?: GTOAnalysis | null;
}) {
  const overallScore = result?.overallScore ?? localAnalysis?.overallScore ?? 0;
  const streetScores = result?.streetScores ?? null;
  const spots = result?.spots ?? [];
  const precision = result?.precision ?? 'cached';
  const computedAt = result?.computedAt ?? localAnalysis?.analyzedAt ?? 0;

  return (
    <div className="space-y-3">
      {/* Overall score */}
      <div className="flex items-center gap-4">
        <div className={`text-3xl font-extrabold tabular-nums ${scoreColor(overallScore)}`}>
          {Math.round(overallScore)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[10px] text-slate-500 mb-1">Overall GTO Score</div>
          <div className="h-2 rounded-full bg-slate-700/50 overflow-hidden">
            <div
              className={`h-full rounded-full ${scoreBg(overallScore)} transition-all`}
              style={{ width: `${overallScore}%` }}
            />
          </div>
        </div>
        <div className="text-[9px] text-slate-600 text-right shrink-0">
          {precision !== 'cached' && <div>{precision}</div>}
          {computedAt > 0 && <div>{new Date(computedAt).toLocaleTimeString()}</div>}
        </div>
      </div>

      {/* Street breakdown */}
      {streetScores && (
        <div className="flex items-center gap-3">
          {(['flop', 'turn', 'river'] as const).map((s) => {
            const val = streetScores[s];
            if (val === null) return null;
            return (
              <div key={s} className="flex-1 min-w-0">
                <div className="text-[9px] text-slate-600 uppercase mb-1 font-medium">{s}</div>
                <div className="h-1.5 rounded-full bg-slate-700/50 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${scoreBg(val)} transition-all`}
                    style={{ width: `${val}%` }}
                  />
                </div>
                <div className={`text-[10px] font-bold tabular-nums mt-0.5 ${scoreColor(val)}`}>
                  {Math.round(val)}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Spots list */}
      {spots.length > 0 && (
        <div className="space-y-1.5 max-h-[280px] overflow-auto cp-history-scroll">
          {spots.map((spot, idx) => {
            const badge = deviationBadge(spot.deviationScore);
            return (
              <div
                key={idx}
                className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5"
              >
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-[10px] font-bold text-cyan-400 uppercase">
                    {spot.street}
                  </span>
                  <span
                    className={`text-[9px] px-1.5 py-0.5 rounded-md border font-semibold ${badge.cls}`}
                  >
                    {badge.label}
                  </span>
                  <span className="ml-auto text-[10px] text-slate-600 tabular-nums">
                    pot {spot.pot.toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-[11px]">
                  <div>
                    <span className="text-slate-500">You: </span>
                    <span className="text-white font-semibold uppercase">{spot.heroAction}</span>
                    {spot.heroAmount > 0 && (
                      <span className="text-slate-500 ml-1">
                        {spot.heroAmount.toLocaleString()}
                      </span>
                    )}
                  </div>
                  <div>
                    <span className="text-slate-500">GTO: </span>
                    <span className="text-purple-300 font-semibold uppercase">
                      {spot.recommended.action}
                    </span>
                    <span className="text-slate-600 ml-1 text-[10px]">
                      (R{Math.round(spot.recommended.mix.raise * 100)}/C
                      {Math.round(spot.recommended.mix.call * 100)}/F
                      {Math.round(spot.recommended.mix.fold * 100)})
                    </span>
                  </div>
                </div>
                {spot.alpha > 0 && (
                  <div className="flex items-center gap-3 mt-1 text-[10px] text-slate-600">
                    <span>Alpha: {Math.round(spot.alpha * 100)}%</span>
                    <span>MDF: {Math.round(spot.mdf * 100)}%</span>
                    <span>Eq: {Math.round(spot.equity * 100)}%</span>
                  </div>
                )}
                {spot.note && <div className="text-[10px] text-slate-500 mt-1">{spot.note}</div>}
              </div>
            );
          })}
        </div>
      )}

      {/* Local-only fallback */}
      {spots.length === 0 && localAnalysis && localAnalysis.streets.length > 0 && (
        <div className="space-y-1.5">
          {localAnalysis.streets.map((s, idx) => {
            const badge = deviationBadge(s.evDiff);
            return (
              <div
                key={idx}
                className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5"
              >
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold text-cyan-400 uppercase">{s.street}</span>
                  <span
                    className={`text-[9px] px-1.5 py-0.5 rounded-md border font-semibold ${badge.cls}`}
                  >
                    {badge.label}
                  </span>
                </div>
                <div className="text-[11px] mt-1">
                  <span className="text-slate-500">You: </span>
                  <span className="text-white font-semibold uppercase">{s.action}</span>
                  <span className="text-slate-600 mx-1">vs GTO:</span>
                  <span className="text-purple-300 font-semibold uppercase">{s.gtoAction}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
