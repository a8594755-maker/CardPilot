import { useMemo, useState, useRef, useCallback } from 'react';
import type { VizTree, VizNode, VizEdge } from '../strategy/game-tree-layout';

// ── Colors matching GTO+ ────────────────────────────────────
const EDGE_COLOR = '#00bcd4';
const HOVER_COLOR = '#9c27b0';

const NODE_RADIUS = 16;
const TERMINAL_SIZE = 9;

const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'];
const SUITS = ['h', 'c', 'd', 's'];
const SUIT_COLORS: Record<string, string> = {
  h: '#e74c3c',
  c: '#27ae60',
  d: '#3498db',
  s: '#2c3e50',
};
const SUIT_SYMBOLS: Record<string, string> = { h: '\u2665', c: '\u2663', d: '\u2666', s: '\u2660' };

// ── Props ───────────────────────────────────────────────────

interface NavigationTreeViewProps {
  vizTree: VizTree;
  selectedNodeId?: string;
  onSelectNode?: (nodeId: string) => void;
  boardCards?: string[];
  onSelectCard?: (card: string) => void;
}

/**
 * Fixed-size navigation tree view (no zoom/pan).
 * Renders at natural pixel size with scroll.
 */
export function NavigationTreeView({
  vizTree,
  selectedNodeId,
  onSelectNode,
  boardCards = [],
  onSelectCard,
}: NavigationTreeViewProps) {
  const [hoveredEdge, setHoveredEdge] = useState<string | null>(null);
  const [chancePopup, setChancePopup] = useState<{ nodeId: string; x: number; y: number } | null>(
    null,
  );
  const containerRef = useRef<HTMLDivElement>(null);

  const nodeMap = useMemo(() => {
    const m = new Map<string, VizNode>();
    for (const n of vizTree.nodes) m.set(n.id, n);
    return m;
  }, [vizTree.nodes]);

  const usedCards = useMemo(() => new Set(boardCards.map((c) => c.toLowerCase())), [boardCards]);

  const handleChanceClick = useCallback(
    (node: VizNode) => {
      if (!onSelectCard || !containerRef.current) return;
      // Convert SVG coords to screen-relative position
      const svg = containerRef.current.querySelector('svg');
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const svgWidth = vizTree.width + 30; // padding*2
      const scale = rect.width / svgWidth;
      const x = (node.x + 15) * scale; // +15 for padding
      const y = (node.y + 15) * scale;
      setChancePopup((prev) => (prev?.nodeId === node.id ? null : { nodeId: node.id, x, y }));
    },
    [onSelectCard, vizTree.width],
  );

  const handleCardSelect = useCallback(
    (card: string) => {
      onSelectCard?.(card);
      setChancePopup(null);
    },
    [onSelectCard],
  );

  if (vizTree.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        Set config to generate tree
      </div>
    );
  }

  const padding = 15;
  const svgWidth = vizTree.width + padding * 2;
  const svgHeight = vizTree.height + padding * 2;

  return (
    <div
      ref={containerRef}
      className="relative w-full bg-white rounded-lg"
      style={{ border: '1px solid #e5e7eb' }}
    >
      <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} style={{ width: '100%', height: 'auto' }}>
        <defs>
          <marker
            id="nav-arrow-default"
            markerWidth="10"
            markerHeight="8"
            refX="9"
            refY="4"
            orient="auto"
            markerUnits="userSpaceOnUse"
          >
            <polygon points="0 0.5, 9 4, 0 7.5" fill={EDGE_COLOR} />
          </marker>
          <marker
            id="nav-arrow-hover"
            markerWidth="10"
            markerHeight="8"
            refX="9"
            refY="4"
            orient="auto"
            markerUnits="userSpaceOnUse"
          >
            <polygon points="0 0.5, 9 4, 0 7.5" fill={HOVER_COLOR} />
          </marker>
        </defs>

        <g transform={`translate(${padding}, ${padding})`}>
          {/* Edges */}
          {vizTree.edges.map((edge) => {
            const edgeKey = `${edge.fromId}-${edge.toId}`;
            return (
              <GtoEdge
                key={edgeKey}
                edge={edge}
                nodeMap={nodeMap}
                hovered={hoveredEdge === edgeKey}
                onHover={() => setHoveredEdge(edgeKey)}
                onLeave={() => setHoveredEdge(null)}
                onClick={() => onSelectNode?.(edge.toId)}
              />
            );
          })}

          {/* Nodes */}
          {vizTree.nodes.map((node) => (
            <GtoNode
              key={node.id}
              node={node}
              selected={node.id === selectedNodeId}
              onClick={() => {
                if (node.type === 'chance') {
                  handleChanceClick(node);
                } else {
                  onSelectNode?.(node.id);
                }
              }}
            />
          ))}
        </g>
      </svg>

      {/* Card picker popup for chance nodes */}
      {chancePopup && (
        <>
          {/* Backdrop to close popup */}
          <div className="fixed inset-0 z-40" onClick={() => setChancePopup(null)} />
          <div
            className="absolute z-50 bg-white rounded-lg shadow-xl border border-gray-300"
            style={{
              left: Math.min(chancePopup.x, (containerRef.current?.clientWidth ?? 300) - 200),
              top: chancePopup.y + 10,
              padding: '8px',
            }}
          >
            <div className="text-xs font-semibold text-gray-600 mb-1 text-center">Select Card</div>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: `repeat(${SUITS.length}, 1fr)`,
                gap: '2px',
              }}
            >
              {RANKS.map((rank) =>
                SUITS.map((suit) => {
                  const card = rank + suit;
                  const disabled = usedCards.has(card.toLowerCase());
                  return (
                    <button
                      key={card}
                      disabled={disabled}
                      onClick={() => handleCardSelect(card)}
                      style={{
                        width: 32,
                        height: 26,
                        fontSize: 11,
                        fontWeight: 600,
                        border: '1px solid #ddd',
                        borderRadius: 3,
                        background: disabled ? '#f0f0f0' : '#fff',
                        color: disabled ? '#ccc' : SUIT_COLORS[suit],
                        cursor: disabled ? 'default' : 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        padding: 0,
                      }}
                    >
                      {rank}
                      {SUIT_SYMBOLS[suit]}
                    </button>
                  );
                }),
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── Edge Component (90-degree orthogonal, GTO+ style) ────────

function GtoEdge({
  edge,
  nodeMap,
  hovered,
  onHover,
  onLeave,
  onClick,
}: {
  edge: VizEdge;
  nodeMap: Map<string, VizNode>;
  hovered: boolean;
  onHover: () => void;
  onLeave: () => void;
  onClick: () => void;
}) {
  const fromNode = nodeMap.get(edge.fromId);
  const toNode = nodeMap.get(edge.toId);
  if (!fromNode || !toNode) return null;

  const x1 = fromNode.x + NODE_RADIUS;
  const y1 = fromNode.y;
  const isTerminal = toNode.type !== 'action';
  const x2 = toNode.x - (isTerminal ? TERMINAL_SIZE / 2 : NODE_RADIUS);
  const y2 = toNode.y;

  const color = hovered ? HOVER_COLOR : EDGE_COLOR;
  const freq = (edge.frequency * 100).toFixed(1);

  const baseWidth = Math.max(1.5, Math.min(4, edge.frequency * 7));
  const strokeWidth = hovered ? baseWidth + 0.5 : baseWidth;
  const isHorizontal = Math.abs(y2 - y1) < 3;

  const elbowX = x1 + Math.min(14, (x2 - x1) * 0.08);
  const pathD = isHorizontal
    ? `M ${x1} ${y1} L ${x2} ${y2}`
    : `M ${x1} ${y1} H ${elbowX} V ${y2} H ${x2}`;

  const segStart = elbowX + 8;
  const segEnd = x2 - 12;
  const labelX = segStart + (segEnd - segStart) * 0.28;
  const freqX = segStart + (segEnd - segStart) * 0.72;

  return (
    <g
      className="tree-edge"
      style={{ cursor: 'pointer' }}
      onMouseEnter={onHover}
      onMouseLeave={onLeave}
      onClick={onClick}
    >
      <path d={pathD} stroke="transparent" strokeWidth={14} fill="none" />
      <path
        d={pathD}
        stroke={color}
        strokeWidth={strokeWidth}
        fill="none"
        markerEnd={hovered ? 'url(#nav-arrow-hover)' : 'url(#nav-arrow-default)'}
        opacity={hovered ? 1 : 0.85}
      />
      <text
        x={labelX}
        y={y2 - 7}
        textAnchor="middle"
        fill={hovered ? '#111' : '#333'}
        fontSize="12"
        fontFamily="system-ui, sans-serif"
        fontWeight={hovered ? '600' : '500'}
      >
        {edge.label}
      </text>
      <text
        x={freqX}
        y={y2 - 7}
        textAnchor="middle"
        fill={hovered ? '#333' : '#777'}
        fontSize="11"
        fontFamily="JetBrains Mono, monospace"
        fontWeight="500"
      >
        {freq}%
      </text>
    </g>
  );
}

// ── Node Component (GTO+ style) ─────────────────────────────

function GtoNode({
  node,
  selected,
  onClick,
}: {
  node: VizNode;
  selected: boolean;
  onClick: () => void;
}) {
  if (node.type === 'fold') {
    return (
      <g className="tree-node" onClick={onClick} style={{ cursor: 'pointer' }}>
        <rect
          x={node.x - TERMINAL_SIZE / 2}
          y={node.y - TERMINAL_SIZE / 2}
          width={TERMINAL_SIZE}
          height={TERMINAL_SIZE}
          fill="#1a237e"
          stroke={selected ? '#e91e63' : '#0d1450'}
          strokeWidth={selected ? 2 : 1}
          rx={1}
        />
      </g>
    );
  }

  if (node.type === 'showdown') {
    const s = 7;
    return (
      <g className="tree-node" onClick={onClick} style={{ cursor: 'pointer' }}>
        <polygon
          points={`${node.x - s * 0.4} ${node.y - s * 0.7}, ${node.x + s * 0.7} ${node.y}, ${node.x - s * 0.4} ${node.y + s * 0.7}`}
          fill="#4caf50"
          stroke={selected ? '#e91e63' : '#2e7d32'}
          strokeWidth={selected ? 1.5 : 0.5}
        />
      </g>
    );
  }

  if (node.type === 'chance') {
    // Card icon — small red heart card indicating "deal next card"
    return (
      <g className="tree-node" onClick={onClick} style={{ cursor: 'pointer' }}>
        <rect
          x={node.x - 6}
          y={node.y - 8}
          width={12}
          height={16}
          fill="#fff"
          stroke={selected ? '#e91e63' : '#e74c3c'}
          strokeWidth={selected ? 2 : 1}
          rx={2}
        />
        <text
          x={node.x}
          y={node.y + 4}
          textAnchor="middle"
          fill="#e74c3c"
          fontSize="10"
          fontWeight="bold"
        >
          ♥
        </text>
      </g>
    );
  }

  // Action node
  const playerNum = node.player + 1;
  const pColor = node.player === 0 ? '#00bcd4' : '#4caf50';
  return (
    <g className="tree-node" onClick={onClick} style={{ cursor: 'pointer' }}>
      <circle
        cx={node.x}
        cy={node.y}
        r={NODE_RADIUS}
        fill="#ffffff"
        stroke={selected ? '#e91e63' : pColor}
        strokeWidth={selected ? 3 : 2}
      />
      <text
        x={node.x}
        y={node.y + 5}
        textAnchor="middle"
        fill={pColor}
        fontSize="14"
        fontWeight="bold"
        fontFamily="Arial, sans-serif"
      >
        {playerNum}
      </text>
    </g>
  );
}
