import {
  useMemo,
  useRef,
  useState,
  useCallback,
  useEffect,
  type MouseEvent as ReactMouseEvent,
} from 'react';
import {
  buildVizTree,
  type TreeConfig,
  type VizTree,
  type VizNode,
  type VizEdge,
} from './game-tree-layout';

// ── Colors (GTO+ style: edges cyan, purple on hover) ──
// P1(OOP) = cyan outlined, P2(IP) = green filled

const EDGE_COLOR = '#00bcd4';
const HOVER_COLOR = '#9c27b0';

const NODE_RADIUS = 18;
const TERMINAL_SIZE = 12;

// ── Props ──────────────────────────────────────────────────────

interface GameTreeViewProps {
  strategies: Array<{ key: string; probs: number[] }>;
  treeConfig: TreeConfig;
  selectedNodeId?: string;
  onSelectNode?: (nodeId: string) => void;
}

export function GameTreeView({
  strategies,
  treeConfig,
  selectedNodeId,
  onSelectNode,
}: GameTreeViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 });
  const [hoveredEdge, setHoveredEdge] = useState<string | null>(null);
  const dragRef = useRef({ dragging: false, startX: 0, startY: 0, txAtStart: 0, tyAtStart: 0 });

  // Build the visualization tree
  const vizTree = useMemo<VizTree>(() => {
    if (!strategies.length) return { nodes: [], edges: [], width: 0, height: 0 };
    return buildVizTree(strategies, treeConfig);
  }, [strategies, treeConfig]);

  // Auto fit-to-view when tree changes
  useEffect(() => {
    if (vizTree.width > 0 && containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      const scaleX = rect.width / vizTree.width;
      const scaleY = rect.height / vizTree.height;
      const scale = Math.min(scaleX, scaleY, 1) * 0.9;
      setTransform({
        x: (rect.width - vizTree.width * scale) / 2,
        y: (rect.height - vizTree.height * scale) / 2,
        scale,
      });
    }
  }, [vizTree]);

  // Wheel zoom (native event to allow preventDefault)
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      const delta = e.deltaY > 0 ? 0.9 : 1.1;
      setTransform((t) => {
        const newScale = Math.max(0.15, Math.min(4, t.scale * delta));
        const rect = el.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        return {
          x: mx - (mx - t.x) * (newScale / t.scale),
          y: my - (my - t.y) * (newScale / t.scale),
          scale: newScale,
        };
      });
    };
    el.addEventListener('wheel', handler, { passive: false });
    return () => el.removeEventListener('wheel', handler);
  }, []);

  // ── Pan handlers ────────────────────────────────────────────

  const handleMouseDown = useCallback(
    (e: ReactMouseEvent) => {
      if (e.button !== 0) return;
      const target = e.target as Element;
      if (target.closest('.tree-node')) return;
      dragRef.current = {
        dragging: true,
        startX: e.clientX,
        startY: e.clientY,
        txAtStart: transform.x,
        tyAtStart: transform.y,
      };
    },
    [transform.x, transform.y],
  );

  const handleMouseMove = useCallback((e: ReactMouseEvent) => {
    const d = dragRef.current;
    if (!d.dragging) return;
    setTransform((t) => ({
      ...t,
      x: d.txAtStart + (e.clientX - d.startX),
      y: d.tyAtStart + (e.clientY - d.startY),
    }));
  }, []);

  const handleMouseUp = useCallback(() => {
    dragRef.current.dragging = false;
  }, []);

  // ── Fit to view ─────────────────────────────────────────────

  const fitToView = useCallback(() => {
    if (!containerRef.current || vizTree.width === 0) return;
    const rect = containerRef.current.getBoundingClientRect();
    const scaleX = rect.width / vizTree.width;
    const scaleY = rect.height / vizTree.height;
    const scale = Math.min(scaleX, scaleY, 1) * 0.9;
    setTransform({
      x: (rect.width - vizTree.width * scale) / 2,
      y: (rect.height - vizTree.height * scale) / 2,
      scale,
    });
  }, [vizTree]);

  if (vizTree.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground">
        No tree data available
      </div>
    );
  }

  // Build node lookup for edge rendering
  const nodeMap = useMemo(() => {
    const m = new Map<string, VizNode>();
    for (const n of vizTree.nodes) m.set(n.id, n);
    return m;
  }, [vizTree.nodes]);

  return (
    <div
      ref={containerRef}
      className="relative w-full bg-background border border-border rounded-lg overflow-hidden"
      style={{ height: Math.max(500, Math.min(vizTree.height * 0.8, 800)) }}
    >
      {/* Controls */}
      <div className="absolute top-2 right-2 z-10 flex gap-1">
        <button
          onClick={fitToView}
          className="px-2 py-1 text-xs bg-secondary text-secondary-foreground rounded hover:bg-secondary/80 transition-colors"
          title="Fit to view"
        >
          Fit
        </button>
        <button
          onClick={() => setTransform((t) => ({ ...t, scale: Math.min(4, t.scale * 1.25) }))}
          className="px-2 py-1 text-xs bg-secondary text-secondary-foreground rounded hover:bg-secondary/80 transition-colors"
        >
          +
        </button>
        <button
          onClick={() => setTransform((t) => ({ ...t, scale: Math.max(0.15, t.scale / 1.25) }))}
          className="px-2 py-1 text-xs bg-secondary text-secondary-foreground rounded hover:bg-secondary/80 transition-colors"
        >
          -
        </button>
      </div>

      {/* Scale indicator */}
      <div className="absolute bottom-2 left-2 z-10 text-[10px] text-muted-foreground font-mono">
        {Math.round(transform.scale * 100)}%
      </div>

      {/* SVG Canvas */}
      <svg
        width="100%"
        height="100%"
        style={{ cursor: dragRef.current.dragging ? 'grabbing' : 'grab' }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <defs>
          <marker
            id="arrow-default"
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
            id="arrow-hover"
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

        <g transform={`translate(${transform.x}, ${transform.y}) scale(${transform.scale})`}>
          {/* Edges (behind nodes) */}
          {vizTree.edges.map((edge) => {
            const edgeKey = `${edge.fromId}-${edge.toId}`;
            return (
              <TreeEdge
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
            <TreeNodeEl
              key={node.id}
              node={node}
              selected={node.id === selectedNodeId}
              onClick={() => onSelectNode?.(node.id)}
            />
          ))}
        </g>
      </svg>
    </div>
  );
}

// ── Edge Component (90-degree orthogonal routing, GTO+ style) ──
// All edges cyan by default, purple on hover.

function TreeEdge({
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
  const x2 = toNode.x - (toNode.type === 'action' ? NODE_RADIUS : TERMINAL_SIZE);
  const y2 = toNode.y;

  const color = hovered ? HOVER_COLOR : EDGE_COLOR;
  const freq = (edge.frequency * 100).toFixed(1);

  // GTO+ style: thicker for high-freq actions
  const baseWidth = Math.max(1.5, Math.min(4.5, edge.frequency * 8));
  const strokeWidth = hovered ? baseWidth + 0.5 : baseWidth;
  const opacity = hovered ? 1 : edge.frequency < 0.005 ? 0.25 : 0.85;

  // 90-degree orthogonal path
  const isHorizontal = Math.abs(y2 - y1) < 3;
  const elbowX = x1 + Math.min(20, (x2 - x1) * 0.08);
  const pathD = isHorizontal
    ? `M ${x1} ${y1} L ${x2} ${y2}`
    : `M ${x1} ${y1} H ${elbowX} V ${y2} H ${x2}`;

  // Labels above horizontal segment: action left, freq right
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
      {/* Hit area */}
      <path d={pathD} stroke="transparent" strokeWidth={16} fill="none" />
      {/* Visible edge */}
      <path
        d={pathD}
        stroke={color}
        strokeWidth={strokeWidth}
        fill="none"
        markerEnd={hovered ? 'url(#arrow-hover)' : 'url(#arrow-default)'}
        opacity={opacity}
      />

      {/* Action label */}
      <text
        x={labelX}
        y={y2 - 6}
        textAnchor="middle"
        fill={hovered ? '#ffffff' : '#e0e0e0'}
        fontSize="11"
        fontFamily="system-ui, sans-serif"
        fontWeight={hovered ? '600' : '500'}
      >
        {edge.label}
      </text>

      {/* Frequency */}
      <text
        x={freqX}
        y={y2 - 6}
        textAnchor="middle"
        fill={hovered ? '#ce93d8' : '#90caf9'}
        fontSize="10"
        fontFamily="JetBrains Mono, monospace"
        fontWeight="600"
      >
        {freq}%
      </text>
    </g>
  );
}

// ── Node Component ─────────────────────────────────────────────

function TreeNodeEl({
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
          stroke={selected ? '#ab47bc' : '#283593'}
          strokeWidth={selected ? 2 : 1}
          rx={2}
        />
      </g>
    );
  }

  if (node.type === 'showdown') {
    return (
      <g className="tree-node" onClick={onClick} style={{ cursor: 'pointer' }}>
        <rect
          x={node.x - 10}
          y={node.y - 8}
          width={12}
          height={16}
          fill="#263238"
          stroke={selected ? '#ab47bc' : '#546e7a'}
          strokeWidth={1}
          rx={2}
        />
        <rect
          x={node.x - 4}
          y={node.y - 6}
          width={12}
          height={16}
          fill="#37474f"
          stroke={selected ? '#ab47bc' : '#546e7a'}
          strokeWidth={1}
          rx={2}
        />
        <text
          x={node.x + 2}
          y={node.y + 5}
          textAnchor="middle"
          fill="#e74c3c"
          fontSize="8"
          fontWeight="bold"
        >
          ♥
        </text>
      </g>
    );
  }

  if (node.type === 'chance') {
    return (
      <g className="tree-node" onClick={onClick} style={{ cursor: 'pointer' }}>
        <rect
          x={node.x - 6}
          y={node.y - 8}
          width={12}
          height={16}
          fill="hsl(222, 47%, 11%)"
          stroke={selected ? '#ab47bc' : '#e74c3c'}
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

  // GTO+: P1=cyan outlined, P2=green outlined, both same fill
  const playerNum = node.player + 1;
  const pColor = node.player === 0 ? '#00bcd4' : '#4caf50';
  return (
    <g className="tree-node" onClick={onClick} style={{ cursor: 'pointer' }}>
      <circle
        cx={node.x}
        cy={node.y}
        r={NODE_RADIUS}
        fill="hsl(222, 47%, 11%)"
        stroke={selected ? '#ab47bc' : pColor}
        strokeWidth={selected ? 3 : 2}
      />
      <text
        x={node.x}
        y={node.y + 5}
        textAnchor="middle"
        fill={pColor}
        fontSize="14"
        fontWeight="bold"
        fontFamily="JetBrains Mono, monospace"
      >
        {playerNum}
      </text>
    </g>
  );
}
