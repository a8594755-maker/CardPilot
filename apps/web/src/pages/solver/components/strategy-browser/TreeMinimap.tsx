import { useState, useCallback } from 'react';
import { useStrategyBrowser } from '../../stores/strategy-browser';
import { getActionColor, formatActionLabel } from '../../lib/strategy-utils';

// ── Layout constants ────────────────────────────────────────
const NODE_R = 12;
const MINIMAP_HEIGHT = 110;
const CHILD_SPACING = 32;

// ── TreeMinimap ─────────────────────────────────────────────
// Shows the current node and its immediate child actions as a
// compact, clickable 1-level tree (GTO+ style).

export function TreeMinimap() {
  const { currentPath, nodeActions, nodeSummary, goBack, goToRoot, navigateTo } =
    useStrategyBrowser();

  const [hoveredAction, setHoveredAction] = useState<string | null>(null);

  // Get action frequencies from nodeSummary
  const actionPercentages = nodeSummary?.actionPercentages ?? {};

  const handleActionClick = useCallback(
    (action: string) => {
      navigateTo(action);
    },
    [navigateTo],
  );

  if (!nodeActions.length) {
    return null;
  }

  // Calculate layout
  const numActions = nodeActions.length;
  const totalChildHeight = (numActions - 1) * CHILD_SPACING;
  const startY = (MINIMAP_HEIGHT - totalChildHeight) / 2;

  // Parent node position
  const parentX = 30;
  const parentY = MINIMAP_HEIGHT / 2;

  // Child nodes
  const children = nodeActions.map((action, i) => {
    const y = startY + i * CHILD_SPACING;
    const x = 250;
    const freq = actionPercentages[action] ?? 0;
    const color = getActionColor(action);
    return { action, x, y, freq, color };
  });

  // Determine the current player from path length (OOP=P1 starts, alternates)
  const currentPlayer = currentPath.length % 2 === 0 ? 1 : 2;
  const nextPlayer = currentPlayer === 1 ? 2 : 1;
  // GTO+: P1=cyan outline, P2=green filled
  const isCurrentP1 = currentPlayer === 1;
  const isNextP1 = nextPlayer === 1;

  const svgWidth = 320;

  return (
    <div
      className="relative bg-white rounded border border-gray-200 overflow-hidden"
      style={{ height: MINIMAP_HEIGHT }}
    >
      {/* Nav buttons */}
      <div className="absolute bottom-1.5 left-1.5 z-10 flex gap-1">
        <button
          onClick={goToRoot}
          className="w-5 h-5 flex items-center justify-center rounded bg-gray-100 text-gray-400 hover:bg-gray-200 hover:text-gray-600 transition-colors"
          title="Root"
        >
          <svg width="8" height="8" viewBox="0 0 8 8">
            <polygon points="0,4 8,0 8,8" fill="currentColor" />
          </svg>
        </button>
        {currentPath.length > 0 && (
          <button
            onClick={goBack}
            className="w-5 h-5 flex items-center justify-center rounded bg-gray-100 text-gray-400 hover:bg-gray-200 hover:text-gray-600 transition-colors"
            title="Back"
          >
            <svg width="8" height="8" viewBox="0 0 8 8">
              <polygon points="8,4 0,0 0,8" fill="currentColor" />
            </svg>
          </button>
        )}
      </div>

      {/* Path breadcrumb */}
      {currentPath.length > 0 && (
        <div className="absolute top-1 right-1 z-10 flex items-center gap-0.5 text-[8px] font-mono text-gray-400">
          <span>Root</span>
          {currentPath.map((seg, i) => (
            <span key={i}>
              <span className="mx-0.5">&gt;</span>
              <span style={{ color: getActionColor(seg) }}>{formatActionLabel(seg)}</span>
            </span>
          ))}
        </div>
      )}

      <svg width={svgWidth} height={MINIMAP_HEIGHT}>
        {/* Edges */}
        {children.map(({ action, x, y, freq, color }) => {
          const isHovered = hoveredAction === action;
          const elbowX = parentX + NODE_R + 8;
          const pathD =
            Math.abs(y - parentY) < 3
              ? `M ${parentX + NODE_R} ${parentY} L ${x - NODE_R} ${y}`
              : `M ${parentX + NODE_R} ${parentY} H ${elbowX} V ${y} H ${x - NODE_R}`;

          const strokeWidth = isHovered ? 3 : 2;

          // Label position on the horizontal segment to the child
          const labelX = elbowX + (x - NODE_R - elbowX) * 0.35;
          const freqX = elbowX + (x - NODE_R - elbowX) * 0.72;

          return (
            <g
              key={action}
              className="cursor-pointer"
              onMouseEnter={() => setHoveredAction(action)}
              onMouseLeave={() => setHoveredAction(null)}
              onClick={() => handleActionClick(action)}
            >
              {/* Hit area */}
              <path d={pathD} stroke="transparent" strokeWidth={16} fill="none" />
              {/* Visible edge */}
              <path
                d={pathD}
                stroke={color}
                strokeWidth={strokeWidth}
                fill="none"
                opacity={isHovered ? 1 : 0.75}
              />
              {/* Arrow marker */}
              <polygon
                points={`${x - NODE_R - 6} ${y - 3}, ${x - NODE_R} ${y}, ${x - NODE_R - 6} ${y + 3}`}
                fill={color}
                opacity={isHovered ? 1 : 0.75}
              />
              {/* Action label */}
              <text
                x={labelX}
                y={y - 5}
                textAnchor="start"
                fill={isHovered ? '#111' : '#444'}
                fontSize="9"
                fontFamily="system-ui, sans-serif"
                fontWeight={isHovered ? '600' : '500'}
              >
                {formatActionLabel(action)}
              </text>
              {/* Frequency */}
              <text
                x={freqX}
                y={y - 5}
                textAnchor="start"
                fill={isHovered ? '#333' : '#888'}
                fontSize="9"
                fontFamily="JetBrains Mono, monospace"
                fontWeight="500"
              >
                {freq.toFixed(1)}%
              </text>
            </g>
          );
        })}

        {/* Parent node */}
        <g>
          <circle
            cx={parentX}
            cy={parentY}
            r={NODE_R}
            fill="#ffffff"
            stroke={isCurrentP1 ? '#00bcd4' : '#4caf50'}
            strokeWidth={2}
          />
          <text
            x={parentX}
            y={parentY + 4}
            textAnchor="middle"
            fill={isCurrentP1 ? '#00bcd4' : '#4caf50'}
            fontSize="11"
            fontWeight="bold"
            fontFamily="Arial, sans-serif"
          >
            {currentPlayer}
          </text>
        </g>

        {/* Child nodes */}
        {children.map(({ action, x, y }) => (
          <g
            key={`node-${action}`}
            className="cursor-pointer"
            onMouseEnter={() => setHoveredAction(action)}
            onMouseLeave={() => setHoveredAction(null)}
            onClick={() => handleActionClick(action)}
          >
            <circle
              cx={x}
              cy={y}
              r={NODE_R - 2}
              fill="#ffffff"
              stroke={isNextP1 ? '#00bcd4' : '#4caf50'}
              strokeWidth={1.5}
            />
            <text
              x={x}
              y={y + 3.5}
              textAnchor="middle"
              fill={isNextP1 ? '#00bcd4' : '#4caf50'}
              fontSize="9"
              fontWeight="bold"
              fontFamily="Arial, sans-serif"
            >
              {nextPlayer}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
