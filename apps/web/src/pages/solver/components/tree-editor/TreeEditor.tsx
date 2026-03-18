import { useState, useMemo, useCallback } from 'react';

/**
 * Visual tree editor - SVG-based interactive game tree builder.
 * Allows right-click to add/remove/modify actions at any node.
 */

export interface TreeEditorNode {
  id: string;
  label: string;
  player: number;
  street: string;
  pot: number;
  actions: TreeEditorAction[];
}

export interface TreeEditorAction {
  name: string;
  label: string;
  color: string;
  child?: TreeEditorNode;
}

interface TreeEditorProps {
  root: TreeEditorNode;
  onModify?: (nodeId: string, modifications: NodeModification) => void;
}

export type NodeModification =
  | { type: 'add_action'; action: string; betSize?: number }
  | { type: 'remove_action'; action: string }
  | { type: 'modify_action'; action: string; newBetSize: number };

interface LayoutNode {
  node: TreeEditorNode;
  x: number;
  y: number;
  children: Array<{ action: TreeEditorAction; child: LayoutNode }>;
}

const NODE_WIDTH = 80;
const NODE_HEIGHT = 30;
const LEVEL_HEIGHT = 90;
const MIN_SIBLING_GAP = 20;

const PLAYER_COLORS = ['#3b82f6', '#ef4444', '#22c55e'];

function layoutTree(node: TreeEditorNode, depth: number = 0): LayoutNode {
  const childLayouts = node.actions
    .filter((a) => a.child)
    .map((a) => ({
      action: a,
      child: layoutTree(a.child!, depth + 1),
    }));

  const totalWidth =
    childLayouts.length > 0
      ? childLayouts.reduce((s, c) => s + getWidth(c.child), 0) +
        (childLayouts.length - 1) * MIN_SIBLING_GAP
      : NODE_WIDTH;

  let xOffset = -totalWidth / 2;
  for (const cl of childLayouts) {
    const w = getWidth(cl.child);
    cl.child.x = xOffset + w / 2;
    xOffset += w + MIN_SIBLING_GAP;
  }

  return {
    node,
    x: 0,
    y: depth * LEVEL_HEIGHT,
    children: childLayouts,
  };
}

function getWidth(layout: LayoutNode): number {
  if (layout.children.length === 0) return NODE_WIDTH;
  const first = layout.children[0].child;
  const last = layout.children[layout.children.length - 1].child;
  return last.x + NODE_WIDTH / 2 - (first.x - NODE_WIDTH / 2);
}

function getTreeBounds(layout: LayoutNode): { minX: number; maxX: number; maxY: number } {
  let minX = layout.x - NODE_WIDTH / 2;
  let maxX = layout.x + NODE_WIDTH / 2;
  let maxY = layout.y + NODE_HEIGHT;

  for (const child of layout.children) {
    const bounds = getTreeBounds(child.child);
    minX = Math.min(minX, layout.x + bounds.minX);
    maxX = Math.max(maxX, layout.x + bounds.maxX);
    maxY = Math.max(maxY, bounds.maxY);
  }

  return { minX, maxX, maxY };
}

export function TreeEditor({ root, onModify }: TreeEditorProps) {
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; nodeId: string } | null>(
    null,
  );
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });

  const layout = useMemo(() => layoutTree(root), [root]);
  const bounds = useMemo(() => getTreeBounds(layout), [layout]);

  const viewWidth = bounds.maxX - bounds.minX + 100;
  const viewHeight = bounds.maxY + 60;

  const handleContextMenu = useCallback((e: React.MouseEvent, nodeId: string) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, nodeId });
  }, []);

  const handleAddAction = useCallback(
    (nodeId: string, action: string) => {
      onModify?.(nodeId, { type: 'add_action', action });
      setContextMenu(null);
    },
    [onModify],
  );

  const handleRemoveAction = useCallback(
    (nodeId: string, action: string) => {
      onModify?.(nodeId, { type: 'remove_action', action });
      setContextMenu(null);
    },
    [onModify],
  );

  function renderNode(ln: LayoutNode, parentX: number, parentY: number) {
    const absX = parentX + ln.x;
    const absY = ln.y;
    const isSelected = selectedNode === ln.node.id;
    const playerColor = PLAYER_COLORS[ln.node.player % PLAYER_COLORS.length];

    return (
      <g key={ln.node.id}>
        {/* Connection from parent */}
        {parentY < absY && (
          <line
            x1={parentX}
            y1={parentY + NODE_HEIGHT}
            x2={absX}
            y2={absY}
            stroke="#444"
            strokeWidth={1.5}
          />
        )}

        {/* Node rectangle */}
        <rect
          x={absX - NODE_WIDTH / 2}
          y={absY}
          width={NODE_WIDTH}
          height={NODE_HEIGHT}
          rx={4}
          fill={isSelected ? playerColor : '#1a1a2e'}
          stroke={playerColor}
          strokeWidth={isSelected ? 2 : 1}
          className="cursor-pointer"
          onClick={() => setSelectedNode(ln.node.id === selectedNode ? null : ln.node.id)}
          onContextMenu={(e) => handleContextMenu(e, ln.node.id)}
        />

        {/* Node label */}
        <text
          x={absX}
          y={absY + NODE_HEIGHT / 2 + 4}
          textAnchor="middle"
          fill="white"
          fontSize={10}
          className="pointer-events-none"
        >
          {ln.node.label}
        </text>

        {/* Action labels on edges */}
        {ln.children.map(({ action, child }) => {
          const childAbsX = absX + child.x;
          const midX = (absX + childAbsX) / 2;
          const midY = (absY + NODE_HEIGHT + child.y) / 2;

          return (
            <g key={action.name}>
              <text
                x={midX}
                y={midY}
                textAnchor="middle"
                fill={action.color || '#888'}
                fontSize={9}
                className="pointer-events-none"
              >
                {action.label}
              </text>
              {renderNode(child, absX, absY)}
            </g>
          );
        })}
      </g>
    );
  }

  return (
    <div className="relative w-full h-full bg-background rounded-lg border border-border overflow-hidden">
      {/* Toolbar */}
      <div className="absolute top-2 right-2 flex gap-1 z-10">
        <button
          onClick={() => setZoom((z) => Math.min(z + 0.2, 3))}
          className="w-7 h-7 flex items-center justify-center bg-secondary border border-border rounded text-sm"
        >
          +
        </button>
        <button
          onClick={() => setZoom((z) => Math.max(z - 0.2, 0.3))}
          className="w-7 h-7 flex items-center justify-center bg-secondary border border-border rounded text-sm"
        >
          -
        </button>
        <button
          onClick={() => {
            setZoom(1);
            setPan({ x: 0, y: 0 });
          }}
          className="px-2 h-7 flex items-center justify-center bg-secondary border border-border rounded text-xs"
        >
          Reset
        </button>
      </div>

      {/* SVG tree */}
      <svg
        width="100%"
        height="100%"
        viewBox={`${bounds.minX - 50 + pan.x} ${-20 + pan.y} ${viewWidth / zoom} ${viewHeight / zoom}`}
        onWheel={(e) => {
          if (e.ctrlKey) {
            e.preventDefault();
            setZoom((z) => Math.max(0.3, Math.min(3, z - e.deltaY * 0.001)));
          } else {
            setPan((p) => ({ x: p.x + e.deltaX * 0.5, y: p.y + e.deltaY * 0.5 }));
          }
        }}
      >
        {renderNode(layout, 0, 0)}
      </svg>

      {/* Context menu */}
      {contextMenu && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setContextMenu(null)} />
          <div
            className="fixed z-50 bg-card border border-border rounded shadow-lg py-1 min-w-[150px]"
            style={{ left: contextMenu.x, top: contextMenu.y }}
          >
            <button
              onClick={() => handleAddAction(contextMenu.nodeId, 'check')}
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-secondary"
            >
              Add Check
            </button>
            <button
              onClick={() => handleAddAction(contextMenu.nodeId, 'bet')}
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-secondary"
            >
              Add Bet...
            </button>
            <button
              onClick={() => handleAddAction(contextMenu.nodeId, 'fold')}
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-secondary"
            >
              Add Fold
            </button>
            <div className="border-t border-border my-1" />
            <button
              onClick={() => handleRemoveAction(contextMenu.nodeId, 'last')}
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-secondary text-destructive"
            >
              Remove Last Action
            </button>
          </div>
        </>
      )}
    </div>
  );
}
