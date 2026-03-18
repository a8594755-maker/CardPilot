import { useState, useCallback, useRef } from 'react';
import { getActionColor, formatActionLabel } from '../../lib/strategy-utils';

interface TreeNode {
  id: string;
  label: string;
  player: number; // 0 = OOP, 1 = IP
  actions: string[];
  path: string[];
  depth: number;
  x: number;
  y: number;
  grid?: Record<string, Record<string, number>>;
}

interface FullTreeViewProps {
  actions: string[];
  onNavigateTo: (path: string[]) => void;
  currentPath: string[];
}

const NODE_WIDTH = 60;
const NODE_HEIGHT = 30;
const LEVEL_HEIGHT = 60;

/**
 * Interactive 2D tree visualization.
 * Shows game tree structure with action labels on edges.
 * Hover shows a quickview; click navigates to that node.
 */
export function FullTreeView({ actions, onNavigateTo, currentPath }: FullTreeViewProps) {
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const containerRef = useRef<HTMLDivElement>(null);

  // Build a simple demonstration tree from the available actions
  const tree = buildDemoTree(actions, 3);
  const { width: treeWidth, height: treeHeight } = getTreeDimensions(tree);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    setZoom((z) => Math.max(0.3, Math.min(2, z + (e.deltaY > 0 ? -0.1 : 0.1))));
  }, []);

  return (
    <div
      ref={containerRef}
      className="w-full h-full overflow-auto bg-background"
      onWheel={handleWheel}
    >
      <svg width={treeWidth * zoom + 40} height={treeHeight * zoom + 40} className="block">
        <g transform={`scale(${zoom}) translate(20, 20)`}>
          {/* Edges (90-degree orthogonal) */}
          {tree.map((node) =>
            node.actions.map((action) => {
              const childId = `${node.id}-${action}`;
              const child = tree.find((n) => n.id === childId);
              if (!child) return null;

              const x1 = node.x + NODE_WIDTH / 2;
              const y1 = node.y + NODE_HEIGHT;
              const x2 = child.x + NODE_WIDTH / 2;
              const y2 = child.y;
              const color = getActionColor(action);

              // 90-degree orthogonal path: vertical → horizontal → vertical
              const elbowY = y1 + (y2 - y1) * 0.4;
              const isVertical = Math.abs(x2 - x1) < 3;
              const pathD = isVertical
                ? `M ${x1} ${y1} L ${x2} ${y2}`
                : `M ${x1} ${y1} V ${elbowY} H ${x2} V ${y2}`;

              // Label on the vertical segment near the parent
              const labelX = x1 + (x2 - x1) * 0.5;
              const labelY = elbowY - 3;

              return (
                <g key={`edge-${childId}`}>
                  <path d={pathD} stroke={color} strokeWidth={2} fill="none" opacity={0.8} />
                  {/* Edge label */}
                  <text
                    x={labelX}
                    y={labelY}
                    fontSize={8}
                    fill={color}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fontFamily="'Microsoft YaHei', system-ui, sans-serif"
                  >
                    {formatActionLabel(action)}
                  </text>
                </g>
              );
            }),
          )}

          {/* Nodes */}
          {tree.map((node) => {
            const isHovered = hoveredNode === node.id;
            const isCurrent = JSON.stringify(node.path) === JSON.stringify(currentPath);

            return (
              <g
                key={node.id}
                onMouseEnter={() => setHoveredNode(node.id)}
                onMouseLeave={() => setHoveredNode(null)}
                onClick={() => onNavigateTo(node.path)}
                className="cursor-pointer"
              >
                <rect
                  x={node.x}
                  y={node.y}
                  width={NODE_WIDTH}
                  height={NODE_HEIGHT}
                  rx={4}
                  fill={isCurrent ? '#3b82f6' : isHovered ? '#1e293b' : '#0f172a'}
                  stroke={isCurrent ? '#60a5fa' : isHovered ? '#475569' : '#334155'}
                  strokeWidth={isCurrent ? 2 : 1}
                />
                <text
                  x={node.x + NODE_WIDTH / 2}
                  y={node.y + NODE_HEIGHT / 2}
                  fontSize={9}
                  fill={isCurrent ? 'white' : '#94a3b8'}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fontFamily="monospace"
                >
                  {node.label}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      {/* Zoom controls */}
      <div className="absolute bottom-2 right-2 flex gap-1">
        <button
          onClick={() => setZoom((z) => Math.min(2, z + 0.2))}
          className="w-6 h-6 rounded bg-secondary text-xs flex items-center justify-center hover:bg-secondary/80"
        >
          +
        </button>
        <button
          onClick={() => setZoom((z) => Math.max(0.3, z - 0.2))}
          className="w-6 h-6 rounded bg-secondary text-xs flex items-center justify-center hover:bg-secondary/80"
        >
          -
        </button>
        <button
          onClick={() => setZoom(1)}
          className="px-2 h-6 rounded bg-secondary text-[10px] flex items-center justify-center hover:bg-secondary/80"
        >
          1:1
        </button>
      </div>
    </div>
  );
}

function buildDemoTree(actions: string[], maxDepth: number): TreeNode[] {
  const nodes: TreeNode[] = [];
  let xOffset = 0;

  function addNode(path: string[], depth: number, player: number): number {
    const id = path.length === 0 ? 'root' : path.join('-');
    const label = path.length === 0 ? 'Root' : `P${player + 1}`;
    const x = xOffset;
    const y = depth * LEVEL_HEIGHT;

    const nodeActions = depth < maxDepth ? actions.slice(0, Math.min(actions.length, 3)) : [];

    nodes.push({
      id,
      label,
      player,
      actions: nodeActions,
      path: [...path],
      depth,
      x,
      y,
    });

    if (nodeActions.length === 0) {
      xOffset += NODE_WIDTH + 10;
      return x;
    }

    let firstChildX = 0;
    let lastChildX = 0;

    for (let i = 0; i < nodeActions.length; i++) {
      const action = nodeActions[i];
      const childPath = [...path, action];
      const childX = addNode(childPath, depth + 1, (player + 1) % 2);
      if (i === 0) firstChildX = childX;
      lastChildX = childX;
    }

    // Center parent above children
    const centerX = (firstChildX + lastChildX) / 2;
    const nodeIdx = nodes.findIndex((n) => n.id === id);
    if (nodeIdx >= 0) {
      nodes[nodeIdx].x = centerX;
    }

    return centerX;
  }

  addNode([], 0, 0);
  return nodes;
}

function getTreeDimensions(tree: TreeNode[]): { width: number; height: number } {
  let maxX = 0;
  let maxY = 0;
  for (const node of tree) {
    maxX = Math.max(maxX, node.x + NODE_WIDTH);
    maxY = Math.max(maxY, node.y + NODE_HEIGHT);
  }
  return { width: maxX, height: maxY };
}
