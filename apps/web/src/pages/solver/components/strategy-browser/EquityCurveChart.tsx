import { useMemo, useState } from 'react';
import type { GtoPlusCombo } from '../../lib/api-client';

interface EquityCurveChartProps {
  combos: GtoPlusCombo[];
  ipCombos?: GtoPlusCombo[];
}

const CHART_W = 300;
const CHART_H = 170;
const PAD = { top: 10, right: 15, bottom: 28, left: 38 };
const PLOT_W = CHART_W - PAD.left - PAD.right;
const PLOT_H = CHART_H - PAD.top - PAD.bottom;

export function EquityCurveChart({ combos, ipCombos }: EquityCurveChartProps) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const oopSorted = useMemo(() => [...combos].sort((a, b) => b.equity - a.equity), [combos]);

  const ipSorted = useMemo(
    () => (ipCombos ? [...ipCombos].sort((a, b) => b.equity - a.equity) : []),
    [ipCombos],
  );

  if (!oopSorted.length) return null;

  const hasIp = ipSorted.length > 0;

  function toPoints(sorted: GtoPlusCombo[]): string {
    const n = sorted.length;
    if (n === 0) return '';
    const step = Math.max(1, Math.floor(n / 200));
    const pts: string[] = [];
    for (let i = 0; i < n; i += step) {
      const x = PAD.left + (i / (n - 1)) * PLOT_W;
      const y = PAD.top + (1 - sorted[i].equity / 100) * PLOT_H;
      pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    }
    if ((n - 1) % step !== 0) {
      const x = PAD.left + PLOT_W;
      const y = PAD.top + (1 - sorted[n - 1].equity / 100) * PLOT_H;
      pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    }
    return pts.join(' ');
  }

  // Area fill path (polyline + close to bottom)
  function toAreaPath(sorted: GtoPlusCombo[]): string {
    const n = sorted.length;
    if (n === 0) return '';
    const step = Math.max(1, Math.floor(n / 200));
    const pts: string[] = [];
    pts.push(`M ${PAD.left},${PAD.top + PLOT_H}`);
    for (let i = 0; i < n; i += step) {
      const x = PAD.left + (i / (n - 1)) * PLOT_W;
      const y = PAD.top + (1 - sorted[i].equity / 100) * PLOT_H;
      pts.push(`L ${x.toFixed(1)},${y.toFixed(1)}`);
    }
    if ((n - 1) % step !== 0) {
      const x = PAD.left + PLOT_W;
      const y = PAD.top + (1 - sorted[n - 1].equity / 100) * PLOT_H;
      pts.push(`L ${x.toFixed(1)},${y.toFixed(1)}`);
    }
    pts.push(`L ${PAD.left + PLOT_W},${PAD.top + PLOT_H} Z`);
    return pts.join(' ');
  }

  const oopPoints = toPoints(oopSorted);
  const ipPoints = toPoints(ipSorted);
  const oopArea = toAreaPath(oopSorted);

  const yTicks = [0, 25, 50, 75, 100];
  const hoverCombo = hoverIdx !== null ? oopSorted[hoverIdx] : null;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${CHART_W} ${CHART_H}`}
        className="w-full h-auto"
        onMouseLeave={() => setHoverIdx(null)}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const svgX = ((e.clientX - rect.left) / rect.width) * CHART_W;
          const relX = svgX - PAD.left;
          if (relX < 0 || relX > PLOT_W) {
            setHoverIdx(null);
            return;
          }
          const idx = Math.round((relX / PLOT_W) * (oopSorted.length - 1));
          setHoverIdx(Math.max(0, Math.min(oopSorted.length - 1, idx)));
        }}
      >
        <defs>
          <linearGradient id="oopFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.02" />
          </linearGradient>
        </defs>

        {/* Grid lines */}
        {yTicks.map((tick) => {
          const y = PAD.top + (1 - tick / 100) * PLOT_H;
          return (
            <g key={tick}>
              <line
                x1={PAD.left}
                y1={y}
                x2={PAD.left + PLOT_W}
                y2={y}
                stroke="hsl(var(--border))"
                strokeWidth="0.5"
                strokeDasharray="2,2"
              />
              <text
                x={PAD.left - 4}
                y={y + 3}
                textAnchor="end"
                fill="hsl(var(--muted-foreground))"
                fontSize="7"
              >
                {tick}%
              </text>
            </g>
          );
        })}

        {/* X-axis labels */}
        <text
          x={PAD.left}
          y={CHART_H - 3}
          textAnchor="start"
          fill="hsl(var(--muted-foreground))"
          fontSize="7"
        >
          0
        </text>
        <text
          x={PAD.left + PLOT_W / 2}
          y={CHART_H - 3}
          textAnchor="middle"
          fill="hsl(var(--muted-foreground))"
          fontSize="7"
        >
          組合排名
        </text>
        <text
          x={PAD.left + PLOT_W}
          y={CHART_H - 3}
          textAnchor="end"
          fill="hsl(var(--muted-foreground))"
          fontSize="7"
        >
          {oopSorted.length}
        </text>

        {/* Axes */}
        <line
          x1={PAD.left}
          y1={PAD.top}
          x2={PAD.left}
          y2={PAD.top + PLOT_H}
          stroke="hsl(var(--border))"
          strokeWidth="1"
        />
        <line
          x1={PAD.left}
          y1={PAD.top + PLOT_H}
          x2={PAD.left + PLOT_W}
          y2={PAD.top + PLOT_H}
          stroke="hsl(var(--border))"
          strokeWidth="1"
        />

        {/* OOP area fill */}
        <path d={oopArea} fill="url(#oopFill)" />

        {/* IP curve (behind OOP) */}
        {ipPoints && (
          <polyline
            points={ipPoints}
            fill="none"
            stroke="#22c55e"
            strokeWidth="1.5"
            opacity="0.8"
          />
        )}

        {/* OOP curve */}
        <polyline points={oopPoints} fill="none" stroke="#3b82f6" strokeWidth="2" />

        {/* 50% reference line */}
        <line
          x1={PAD.left}
          y1={PAD.top + PLOT_H / 2}
          x2={PAD.left + PLOT_W}
          y2={PAD.top + PLOT_H / 2}
          stroke="hsl(var(--muted-foreground))"
          strokeWidth="0.5"
          opacity="0.3"
        />

        {/* Hover indicator */}
        {hoverIdx !== null && (
          <>
            <line
              x1={PAD.left + (hoverIdx / (oopSorted.length - 1)) * PLOT_W}
              y1={PAD.top}
              x2={PAD.left + (hoverIdx / (oopSorted.length - 1)) * PLOT_W}
              y2={PAD.top + PLOT_H}
              stroke="hsl(var(--foreground))"
              strokeWidth="0.5"
              opacity="0.5"
            />
            <circle
              cx={PAD.left + (hoverIdx / (oopSorted.length - 1)) * PLOT_W}
              cy={PAD.top + (1 - oopSorted[hoverIdx].equity / 100) * PLOT_H}
              r="3"
              fill="#3b82f6"
              stroke="white"
              strokeWidth="1"
            />
          </>
        )}

        {/* Player legend */}
        {hasIp && (
          <>
            <circle cx={PAD.left + PLOT_W - 50} cy={PAD.top + 6} r="3" fill="#3b82f6" />
            <text x={PAD.left + PLOT_W - 44} y={PAD.top + 9} fill="#3b82f6" fontSize="7">
              OOP
            </text>
            <circle cx={PAD.left + PLOT_W - 20} cy={PAD.top + 6} r="3" fill="#22c55e" />
            <text x={PAD.left + PLOT_W - 14} y={PAD.top + 9} fill="#22c55e" fontSize="7">
              IP
            </text>
          </>
        )}
      </svg>

      {/* Tooltip */}
      {hoverCombo && (
        <div className="absolute top-0 right-0 bg-card border border-border rounded px-2 py-1 text-[10px] font-mono shadow-md">
          <HandDisplay hand={hoverCombo.hand} />
          <span className="ml-2 text-muted-foreground">勝率: {hoverCombo.equity.toFixed(1)}%</span>
          <span className="ml-2">EV: {hoverCombo.evTotal.toFixed(3)}</span>
        </div>
      )}
    </div>
  );
}

function HandDisplay({ hand }: { hand: string }) {
  const cards: Array<{ rank: string; suit: string }> = [];
  let i = 0;
  while (i < hand.length) {
    if (i + 1 < hand.length) {
      cards.push({ rank: hand[i], suit: hand[i + 1] });
      i += 2;
    } else break;
  }

  return (
    <span>
      {cards.map((card, idx) => (
        <span key={idx} style={{ color: getSuitColor(card.suit) }}>
          {card.rank}
          {getSuitSymbol(card.suit)}
        </span>
      ))}
    </span>
  );
}

function getSuitColor(suit: string): string {
  switch (suit) {
    case 'h':
      return '#ef4444';
    case 'd':
      return '#3b82f6';
    case 'c':
      return '#22c55e';
    case 's':
      return '#94a3b8';
    default:
      return 'inherit';
  }
}

function getSuitSymbol(suit: string): string {
  switch (suit) {
    case 'h':
      return '\u2665';
    case 'd':
      return '\u2666';
    case 'c':
      return '\u2663';
    case 's':
      return '\u2660';
    default:
      return suit;
  }
}
