import { useMemo, useState } from 'react';
import type { GtoPlusCombo } from '../../lib/api-client';

interface EvEquityScatterProps {
  combos: GtoPlusCombo[];
  ipCombos?: GtoPlusCombo[];
}

const CHART_W = 300;
const CHART_H = 170;
const PAD = { top: 10, right: 15, bottom: 28, left: 38 };
const PLOT_W = CHART_W - PAD.left - PAD.right;
const PLOT_H = CHART_H - PAD.top - PAD.bottom;

export function EvEquityScatter({ combos, ipCombos }: EvEquityScatterProps) {
  const [hoverCombo, setHoverCombo] = useState<GtoPlusCombo | null>(null);
  const [hoverPlayer, setHoverPlayer] = useState<'oop' | 'ip' | null>(null);

  const { evMin, evMax } = useMemo(() => {
    const all = ipCombos ? [...combos, ...ipCombos] : combos;
    if (!all.length) return { evMin: 0, evMax: 1 };
    let min = Infinity,
      max = -Infinity;
    for (const c of all) {
      if (c.evTotal < min) min = c.evTotal;
      if (c.evTotal > max) max = c.evTotal;
    }
    const range = max - min || 1;
    return { evMin: min - range * 0.05, evMax: max + range * 0.05 };
  }, [combos, ipCombos]);

  if (!combos.length) return null;

  const hasIp = ipCombos && ipCombos.length > 0;

  function scaleX(equity: number): number {
    return PAD.left + (equity / 100) * PLOT_W;
  }

  function scaleY(ev: number): number {
    return PAD.top + (1 - (ev - evMin) / (evMax - evMin)) * PLOT_H;
  }

  function downsample(arr: GtoPlusCombo[], max: number): GtoPlusCombo[] {
    if (arr.length <= max) return arr;
    const step = arr.length / max;
    const result: GtoPlusCombo[] = [];
    for (let i = 0; i < max; i++) {
      result.push(arr[Math.floor(i * step)]);
    }
    return result;
  }

  const oopDots = downsample(combos, 300);
  const ipDots = ipCombos ? downsample(ipCombos, 300) : [];

  // Y-axis ticks
  const evRange = evMax - evMin;
  const yTickCount = 5;
  const yTicks: number[] = [];
  for (let i = 0; i <= yTickCount; i++) {
    yTicks.push(evMin + (i / yTickCount) * evRange);
  }

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${CHART_W} ${CHART_H}`}
        className="w-full h-auto"
        onMouseLeave={() => {
          setHoverCombo(null);
          setHoverPlayer(null);
        }}
      >
        {/* Grid lines */}
        {yTicks.map((tick, i) => {
          const y = scaleY(tick);
          return (
            <g key={i}>
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
                {tick.toFixed(2)}
              </text>
            </g>
          );
        })}

        {/* X-axis ticks */}
        {[0, 25, 50, 75, 100].map((tick) => (
          <text
            key={tick}
            x={scaleX(tick)}
            y={CHART_H - 3}
            textAnchor="middle"
            fill="hsl(var(--muted-foreground))"
            fontSize="7"
          >
            {tick}%
          </text>
        ))}

        {/* Axis labels */}
        <text
          x={PAD.left + PLOT_W / 2}
          y={CHART_H - 14}
          textAnchor="middle"
          fill="hsl(var(--muted-foreground))"
          fontSize="7"
        >
          勝率
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

        {/* Zero EV reference line */}
        {evMin < 0 && evMax > 0 && (
          <line
            x1={PAD.left}
            y1={scaleY(0)}
            x2={PAD.left + PLOT_W}
            y2={scaleY(0)}
            stroke="hsl(var(--muted-foreground))"
            strokeWidth="0.5"
            opacity="0.4"
          />
        )}

        {/* Diagonal reference line (EV proportional to equity) */}
        <line
          x1={scaleX(0)}
          y1={scaleY(evMin)}
          x2={scaleX(100)}
          y2={scaleY(evMax)}
          stroke="hsl(var(--muted-foreground))"
          strokeWidth="0.5"
          opacity="0.2"
          strokeDasharray="3,3"
        />

        {/* IP dots (behind) */}
        {ipDots.map((c, i) => (
          <circle
            key={`ip-${i}`}
            cx={scaleX(c.equity)}
            cy={scaleY(c.evTotal)}
            r="2"
            fill="#22c55e"
            opacity="0.5"
            onMouseEnter={() => {
              setHoverCombo(c);
              setHoverPlayer('ip');
            }}
          />
        ))}

        {/* OOP dots */}
        {oopDots.map((c, i) => (
          <circle
            key={`oop-${i}`}
            cx={scaleX(c.equity)}
            cy={scaleY(c.evTotal)}
            r="2"
            fill="#3b82f6"
            opacity="0.65"
            onMouseEnter={() => {
              setHoverCombo(c);
              setHoverPlayer('oop');
            }}
          />
        ))}

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
        <div className="absolute top-0 right-0 bg-card border border-border rounded px-2 py-1 text-[10px] font-mono shadow-md z-10">
          <span style={{ color: hoverPlayer === 'ip' ? '#22c55e' : '#3b82f6' }}>
            {hoverPlayer === 'ip' ? 'IP' : 'OOP'}
          </span>
          <span className="ml-1.5">{hoverCombo.hand}</span>
          <span className="ml-2 text-muted-foreground">勝率: {hoverCombo.equity.toFixed(1)}%</span>
          <span className="ml-2">EV: {hoverCombo.evTotal.toFixed(3)}</span>
        </div>
      )}
    </div>
  );
}
