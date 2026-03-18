import { memo, useMemo, useState } from 'react';
import type { StrategyViewerState, StrategyViewerActions } from '../../hooks/useStrategyViewer';
import { useActionTree } from '../../hooks/useActionTree';
import { useHandMatrix } from '../../hooks/useHandMatrix';
import { aggregateByPrimaryBucket } from '../../lib/cfr-computations';
import {
  STREET_LABELS,
  PLAYER_LABELS,
  actionCharToFullLabel,
  type Street,
} from '../../lib/cfr-labels';
import { getActionColor, getActionBtnClass } from '../../lib/cfr-colors';
import { PokerCardDisplay } from '../shared/PokerCardDisplay';
import { SegmentedControl } from '../shared/SegmentedControl';
import { ActionColorBar } from '../shared/ActionColorBar';
import { HandMatrix, getStrengthLabel } from './HandMatrix';

interface StrategyViewerProps {
  state: StrategyViewerState;
  actions: StrategyViewerActions;
}

export const StrategyViewer = memo(function StrategyViewer({
  state,
  actions,
}: StrategyViewerProps) {
  const {
    meta,
    indexed,
    prefixIndex,
    handMap,
    isV2,
    bucketCount,
    player,
    street,
    historyKey,
    heatmapMode,
    selectedHand,
  } = state;

  const [hoveredHand, setHoveredHand] = useState<string | null>(null);

  const treeActions = useMemo(
    () => ({
      setHistoryKey: actions.setHistoryKey,
      setStreet: actions.setStreet,
      setPlayer: actions.setPlayer,
    }),
    [actions],
  );

  const tree = useActionTree(
    {
      indexed,
      prefixIndex,
      meta,
      player,
      street,
      historyKey,
      bucketCount,
      isV2,
    },
    treeActions,
  );

  const matrixCells = useHandMatrix({
    indexed,
    prefixIndex,
    handMap,
    player,
    prefix: tree.prefix,
    isV2,
    bucketCount,
    heatmapMode,
    actionLabels: tree.actionLabels,
  });

  const aggregate = useMemo(() => {
    const bucketMap = aggregateByPrimaryBucket(
      indexed,
      tree.prefix,
      bucketCount,
      isV2,
      prefixIndex,
    );
    if (bucketMap.size === 0) return null;
    let sums: number[] | null = null;
    let count = 0;
    for (const probs of bucketMap.values()) {
      if (!sums) sums = new Array(probs.length).fill(0);
      for (let i = 0; i < probs.length; i++) sums[i] += probs[i];
      count++;
    }
    if (!sums) return null;
    const total = sums.reduce((a, b) => a + b, 0);
    return { sums, total, count };
  }, [indexed, prefixIndex, tree.prefix, bucketCount, isV2]);

  const detailCell = useMemo(() => {
    const hand = selectedHand ?? hoveredHand;
    if (!hand) return null;
    return matrixCells.find((c) => c.handClass === hand) ?? null;
  }, [selectedHand, hoveredHand, matrixCells]);

  if (!meta) return null;

  const numPlayers = state.configs.find((c) => c.name === state.selectedConfig)?.players ?? 2;

  /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   *  Layout: two-panel on desktop (matrix + detail side panel)
   *  Falls back to stacked layout on mobile (max-lg)
   * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
  return (
    <div className="flex flex-col h-full min-h-0">
      {/* ── Top bar: Board + Controls ── */}
      <div className="flex items-center gap-4 flex-wrap pb-3 border-b border-white/10 shrink-0">
        <div className="flex gap-1.5">
          {meta.flopCards.map((c, i) => (
            <PokerCardDisplay key={i} cardIndex={c} size="sm" />
          ))}
        </div>
        <div className="flex gap-3 text-xs text-slate-400">
          <span>
            <b className="text-amber-400 tabular-nums">{(meta.iterations || 0).toLocaleString()}</b>{' '}
            iters
          </span>
          <span>
            <b className="text-amber-400 tabular-nums">{(meta.infoSets || 0).toLocaleString()}</b>{' '}
            sits
          </span>
          <span>
            <b className="text-amber-400 tabular-nums">{meta.bucketCount || 50}</b> grps
          </span>
        </div>
        <div className="ml-auto flex gap-3">
          <SegmentedControl
            label="Player"
            options={Array.from({ length: numPlayers }, (_, i) => ({
              value: String(i),
              label: PLAYER_LABELS[i] || `P${i}`,
            }))}
            value={String(player)}
            onChange={(v) => actions.setPlayer(parseInt(v, 10))}
            size="sm"
          />
          <SegmentedControl
            label="Street"
            options={[
              { value: 'F' as Street, label: 'Flop' },
              { value: 'T' as Street, label: 'Turn' },
              { value: 'R' as Street, label: 'River' },
            ]}
            value={street}
            onChange={actions.setStreet}
            size="sm"
          />
        </div>
      </div>

      {/* ── Action path + navigation ── */}
      <div className="flex items-center gap-2 flex-wrap py-2 border-b border-white/10 shrink-0">
        <span className="text-xs text-slate-400">
          {STREET_LABELS[street]} · {PLAYER_LABELS[player]}
        </span>
        {historyKey ? (
          <>
            <span className="text-slate-600 text-xs">·</span>
            {historyKey.split('/').map((part, si) => (
              <span key={si} className="flex items-center gap-0.5">
                {si > 0 && <span className="text-slate-600 text-xs">/</span>}
                {part.split('').map((ch, ci) => {
                  const label = actionCharToFullLabel(ch);
                  const color = getActionColor(label);
                  return (
                    <span
                      key={ci}
                      className="px-1.5 py-0.5 rounded text-[10px] font-semibold"
                      style={{ background: `${color}22`, color }}
                    >
                      {label}
                    </span>
                  );
                })}
              </span>
            ))}
          </>
        ) : (
          <>
            <span className="text-slate-600 text-xs">·</span>
            <span className="text-xs text-slate-500">Root</span>
          </>
        )}

        <div className="ml-auto flex gap-1.5 items-center flex-wrap">
          {historyKey && (
            <>
              <button
                onClick={tree.goRoot}
                className="px-2 py-1 rounded-md border border-white/10 bg-white/5 text-[11px] text-slate-400 hover:text-white transition-colors"
              >
                ← Reset
              </button>
              <button
                onClick={tree.goBack}
                className="px-2 py-1 rounded-md border border-white/10 bg-white/5 text-[11px] text-slate-400 hover:text-white transition-colors"
              >
                ↩ Undo
              </button>
              <span className="w-px h-4 bg-white/10" />
            </>
          )}
          {tree.childActions.length > 0 ? (
            <>
              <span className="text-[10px] text-slate-500">Next:</span>
              {tree.childActions.map((action) => {
                const actionIdx = tree.actionLabels.indexOf(action.label);
                const pct =
                  aggregate && actionIdx >= 0 && aggregate.total > 0
                    ? (aggregate.sums[actionIdx] / aggregate.total) * 100
                    : null;
                return (
                  <button
                    key={action.historyKey + action.street + action.player}
                    onClick={() => {
                      actions.setHistoryKey(action.historyKey);
                      actions.setPlayer(action.player);
                    }}
                    className={`px-3 py-1 rounded-lg border-2 text-[11px] font-semibold transition-all hover:-translate-y-px ${getActionBtnClass(action.label)}`}
                  >
                    {action.label}
                    {pct !== null && (
                      <span className="ml-1 opacity-60 tabular-nums">{pct.toFixed(0)}%</span>
                    )}
                  </button>
                );
              })}
            </>
          ) : (
            <span className="text-[10px] text-slate-500">Terminal</span>
          )}
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════
       *  Main content: Matrix (left) + Detail Panel (right)
       * ══════════════════════════════════════════════════════ */}
      <div className="flex gap-5 mt-3 flex-1 min-h-0">
        {/* ── Left: Hand Matrix ── */}
        {/* Width = available height so the square matrix fills vertically.
            On small screens it just takes full width. */}
        <div
          className="shrink-0 flex flex-col max-lg:w-full"
          style={{ width: 'clamp(400px, calc(100vh - 240px), 900px)' }}
        >
          <HandMatrix
            cells={matrixCells}
            actionLabels={tree.actionLabels}
            selectedHand={selectedHand}
            onSelectHand={actions.setSelectedHand}
            onHoverHand={setHoveredHand}
            bucketCount={bucketCount}
          />
        </div>

        {/* ── Right: Detail Panel (desktop only) ── */}
        <div className="flex-1 min-w-[220px] flex flex-col gap-3 max-lg:hidden overflow-y-auto">
          {/* Heatmap mode toggle */}
          <SegmentedControl
            options={[
              { value: 'actions' as const, label: 'Actions' },
              { value: 'aggression' as const, label: 'Aggression' },
              { value: 'strength' as const, label: 'Strength' },
            ]}
            value={heatmapMode}
            onChange={actions.setHeatmapMode}
            size="sm"
          />

          {/* Range overview card */}
          {aggregate && (
            <div className="bg-white/[0.03] border border-white/5 rounded-xl p-4 space-y-3">
              <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                Range Overview
              </div>
              <div className="flex rounded-md overflow-hidden h-6">
                {tree.actionLabels.map((label, i) => {
                  const pct = aggregate.total > 0 ? (aggregate.sums[i] / aggregate.total) * 100 : 0;
                  return (
                    <div
                      key={label}
                      className="h-full flex items-center justify-center text-[10px] font-bold text-white"
                      style={{
                        width: `${pct}%`,
                        background: getActionColor(label),
                        textShadow: '0 1px 2px rgba(0,0,0,0.5)',
                      }}
                    >
                      {pct >= 8 ? `${pct.toFixed(0)}%` : ''}
                    </div>
                  );
                })}
              </div>
              <div className="space-y-1.5">
                {tree.actionLabels.map((label, i) => {
                  const pct = aggregate.total > 0 ? (aggregate.sums[i] / aggregate.total) * 100 : 0;
                  return (
                    <div key={label} className="flex items-center gap-2 text-[12px]">
                      <div
                        className="w-3 h-3 rounded"
                        style={{ background: getActionColor(label) }}
                      />
                      <span className="text-slate-300">{label}</span>
                      <span className="ml-auto text-white font-semibold tabular-nums">
                        {pct.toFixed(1)}%
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Selected / hovered hand detail card */}
          {detailCell && detailCell.hasData && detailCell.probs ? (
            <div className="bg-white/[0.03] border border-white/5 rounded-xl p-4 space-y-3">
              <div className="flex items-baseline gap-2">
                <span className="text-lg font-bold text-white">{detailCell.handClass}</span>
                {detailCell.bucket !== undefined && (
                  <span className="text-[11px] text-slate-500">
                    {getStrengthLabel(detailCell.bucket, bucketCount)} · Grp {detailCell.bucket}/
                    {bucketCount - 1}
                  </span>
                )}
              </div>
              <ActionColorBar labels={tree.actionLabels} probs={detailCell.probs} height={24} />
              <div className="space-y-1.5">
                {tree.actionLabels.map((label, i) => {
                  const pct = detailCell.probs![i] * 100;
                  return (
                    <div key={label} className="flex items-center gap-2 text-[12px]">
                      <div
                        className="w-3 h-3 rounded"
                        style={{ background: getActionColor(label) }}
                      />
                      <span className="text-slate-300">{label}</span>
                      <span
                        className="ml-auto font-bold tabular-nums"
                        style={{ color: getActionColor(label) }}
                      >
                        {pct.toFixed(1)}%
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="bg-white/[0.02] border border-white/5 rounded-xl p-4 flex items-center justify-center min-h-[80px]">
              <p className="text-[12px] text-slate-600">Hover or click a hand to see details</p>
            </div>
          )}
        </div>
      </div>

      {/* ── Mobile-only fallback: stacked layout below matrix ── */}
      <div className="lg:hidden mt-3 shrink-0 space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          {tree.actionLabels.length > 0 && (
            <div className="flex gap-2 flex-wrap">
              {tree.actionLabels.map((label) => (
                <div key={label} className="flex items-center gap-1 text-[11px] text-slate-400">
                  <div
                    className="w-2.5 h-2.5 rounded-sm"
                    style={{ background: getActionColor(label) }}
                  />
                  {label}
                </div>
              ))}
            </div>
          )}
          <div className="ml-auto">
            <SegmentedControl
              options={[
                { value: 'actions' as const, label: 'Actions' },
                { value: 'aggression' as const, label: 'Aggr' },
                { value: 'strength' as const, label: 'Str' },
              ]}
              value={heatmapMode}
              onChange={actions.setHeatmapMode}
              size="sm"
            />
          </div>
        </div>

        {aggregate && (
          <div className="flex rounded overflow-hidden h-5">
            {tree.actionLabels.map((label, i) => {
              const pct = aggregate.total > 0 ? (aggregate.sums[i] / aggregate.total) * 100 : 0;
              return (
                <div
                  key={label}
                  className="h-full flex items-center justify-center text-[9px] font-bold text-white"
                  style={{
                    width: `${pct}%`,
                    background: getActionColor(label),
                    textShadow: '0 1px 2px rgba(0,0,0,0.5)',
                  }}
                >
                  {pct >= 10 ? `${pct.toFixed(0)}%` : ''}
                </div>
              );
            })}
          </div>
        )}

        {detailCell && detailCell.hasData && detailCell.probs && (
          <div className="flex items-center gap-4 flex-wrap pt-2 border-t border-white/10">
            <span className="text-sm font-bold text-white">{detailCell.handClass}</span>
            {detailCell.bucket !== undefined && (
              <span className="text-[11px] text-slate-400">
                {getStrengthLabel(detailCell.bucket, bucketCount)} · Grp {detailCell.bucket}/
                {bucketCount - 1}
              </span>
            )}
            <div className="flex-1 min-w-[100px]">
              <ActionColorBar labels={tree.actionLabels} probs={detailCell.probs} height={20} />
            </div>
            <div className="flex gap-3">
              {tree.actionLabels.map((label, i) => (
                <span
                  key={label}
                  className="text-[11px] tabular-nums"
                  style={{ color: getActionColor(label) }}
                >
                  <b>{(detailCell.probs![i] * 100).toFixed(1)}%</b>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
});
