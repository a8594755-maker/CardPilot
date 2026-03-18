// Pure logic for building and laying out the game tree visualization.
// No React — just data structures and algorithms.

// ── Types ──────────────────────────────────────────────────────

export interface TreeConfig {
  startingPot: number;
  effectiveStack: number;
  betSizes: { flop: number[]; turn: number[]; river: number[] };
  raiseCapPerStreet: number;
  numPlayers?: number;
  perLevelBetFractions?: number[];
}

export interface VizNode {
  id: string; // history key (e.g., "", "1", "1f", "x", "x1")
  type: 'action' | 'fold' | 'showdown' | 'chance';
  player: number; // 0=OOP(P1), 1=IP(P2)
  pot: number;
  stack: number; // effective stack remaining (min of both players)
  x: number;
  y: number;
}

export interface VizEdge {
  fromId: string;
  toId: string;
  actionKey: string; // raw action char (e.g., "1", "f", "c", "x")
  action: string; // semantic action: 'check', 'bet', 'call', 'fold', 'raise', 'allin'
  amount: number | null;
  frequency: number; // 0-1
  label: string; // display (e.g., "Bet 1.65")
}

export interface VizTree {
  nodes: VizNode[];
  edges: VizEdge[];
  width: number;
  height: number;
}

// ── Bet math (ported from cfr-solver) ──────────────────────────

export function calcBetAmount(pot: number, fraction: number, stack: number): number {
  const bet = Math.round(pot * fraction * 100) / 100;
  return Math.min(bet, stack);
}

export function calcRaiseAmount(
  pot: number,
  facingBet: number,
  fraction: number,
  stack: number,
  invested: number = 0,
): number {
  const callAmount = facingBet - invested;
  const potAfterCall = pot + callAmount;
  const raiseOverBet = Math.round(potAfterCall * fraction * 100) / 100;
  const additional = callAmount + raiseOverBet;
  return Math.min(additional, stack);
}

// ── Action char mapping (matches tree-builder.ts) ──────────────

// action char → semantic meaning depends on context (facing bet or not)
// 'f' = fold, 'x' = check, 'c' = call, 'A' = allin
// '1','2','3',... = bet_0/raise_0, bet_1/raise_1, ...

function actionCharToSemantic(ch: string, facingBet: boolean): string {
  if (ch === 'f') return 'fold';
  if (ch === 'x') return 'check';
  if (ch === 'c') return 'call';
  if (ch === 'A') return 'allin';
  // digit: bet or raise depending on context
  if (/^\d+$/.test(ch)) {
    return facingBet ? 'raise' : 'bet';
  }
  return 'unknown';
}

// ── Build visualization tree from strategy data ────────────────

interface BuildContext {
  config: TreeConfig;
  histories: Set<string>; // all unique history strings from strategy keys
  freqMap: Map<string, number[]>; // history → aggregated probs for that node
  actionCountMap: Map<string, number>; // history → number of actions at that node
}

/**
 * Parse strategy keys to extract unique history strings and aggregate frequencies.
 * Strategy key format: "{bucket}|{boardId}|{player}|{history}|{infoSet}"
 * We only care about the history (index 3) and probs.
 */
function parseStrategies(strategies: Array<{ key: string; probs: number[] }>): {
  histories: Set<string>;
  freqMap: Map<string, number[]>;
  actionCountMap: Map<string, number>;
} {
  const histories = new Set<string>();
  // Group by (player, history) and aggregate probs
  const grouped = new Map<string, { probs: number[][]; numActions: number }>();

  for (const s of strategies) {
    const parts = s.key.split('|');
    const player = parts[2] || '0';
    const history = parts[3] || '';
    histories.add(history);

    const groupKey = `${player}|${history}`;
    const existing = grouped.get(groupKey);
    if (existing) {
      existing.probs.push(s.probs);
    } else {
      grouped.set(groupKey, { probs: [s.probs], numActions: s.probs.length });
    }
  }

  // Aggregate: average across buckets, keyed by history (combine both players)
  // Actually we want per-node, so key by history (the acting player's probs)
  const freqMap = new Map<string, number[]>();
  const actionCountMap = new Map<string, number>();

  for (const [groupKey, { probs, numActions }] of grouped) {
    const history = groupKey.split('|').slice(1).join('|');
    if (freqMap.has(history)) continue; // already processed

    // Average all prob vectors for this history
    const allProbs = probs;
    const avgProbs = new Array(numActions).fill(0);
    for (const p of allProbs) {
      for (let i = 0; i < numActions; i++) {
        avgProbs[i] += (p[i] ?? 0) / allProbs.length;
      }
    }
    freqMap.set(history, avgProbs);
    actionCountMap.set(history, numActions);
  }

  return { histories, freqMap, actionCountMap };
}

interface NodeState {
  history: string;
  player: number;
  pot: number;
  stacks: [number, number];
  facingBet: number;
  raiseCount: number;
  isFirstAction: boolean;
  depth: number;
  roundStartStacks: [number, number];
}

/**
 * Build the full visualization tree from strategies + config.
 */
export function buildVizTree(
  strategies: Array<{ key: string; probs: number[] }>,
  config: TreeConfig,
): VizTree {
  const { histories, freqMap, actionCountMap } = parseStrategies(strategies);
  const ctx: BuildContext = { config, histories, freqMap, actionCountMap };

  const nodes: VizNode[] = [];
  const edges: VizEdge[] = [];

  const rootState: NodeState = {
    history: '',
    player: 0,
    pot: config.startingPot,
    stacks: [config.effectiveStack, config.effectiveStack],
    facingBet: 0,
    raiseCount: 0,
    isFirstAction: true,
    depth: 0,
    roundStartStacks: [config.effectiveStack, config.effectiveStack],
  };

  buildNodeRecursive(ctx, rootState, nodes, edges);

  // Layout
  return layoutTree(nodes, edges);
}

function buildNodeRecursive(
  ctx: BuildContext,
  state: NodeState,
  nodes: VizNode[],
  edges: VizEdge[],
): void {
  const { history, player, pot, stacks } = state;

  // Find children: look for histories that extend current by exactly one char
  const childActions = findChildActions(ctx, history);

  if (childActions.length === 0) {
    // This shouldn't happen for a valid root/action node (the leaves are terminals)
    // But just in case, treat as terminal
    return;
  }

  // Create action node
  const node: VizNode = {
    id: history || 'root',
    type: 'action',
    player,
    pot,
    stack: Math.min(stacks[0], stacks[1]),
    x: 0,
    y: 0, // layout fills these
  };
  nodes.push(node);

  // Get aggregated frequencies for this node
  const freqs = ctx.freqMap.get(history);

  // Generate action labels matching tree-builder convention
  const actionLabels = generateActionOrder(childActions, state.facingBet > 0);

  for (let i = 0; i < actionLabels.length; i++) {
    const actionChar = actionLabels[i].char;
    const semantic = actionLabels[i].semantic;
    const freq = freqs ? (freqs[i] ?? 0) : 0;

    const childHistory = history + actionChar;
    const amount = computeAmount(ctx.config, semantic, actionChar, state);

    // Create edge
    const label = formatActionLabel(semantic, amount);
    const edge: VizEdge = {
      fromId: history || 'root',
      toId: '', // filled below
      actionKey: actionChar,
      action: semantic,
      amount,
      frequency: freq,
      label,
    };

    // Determine child type
    if (semantic === 'fold') {
      const terminalId = childHistory + '_fold';
      edge.toId = terminalId;
      edges.push(edge);
      nodes.push({
        id: terminalId,
        type: 'fold',
        player,
        pot,
        stack: Math.min(stacks[0], stacks[1]),
        x: 0,
        y: 0,
      });
    } else if (semantic === 'call') {
      const callInvested = state.roundStartStacks[player] - stacks[player];
      const callAmount = Math.min(state.facingBet - callInvested, stacks[player]);
      const newStacks: [number, number] = [...stacks];
      newStacks[player] -= callAmount;
      const newPot = pot + callAmount;

      // Check if this leads to more actions (next street) or is terminal
      const hasChildren = findChildActions(ctx, childHistory).length > 0;
      // Also check for street advance (history contains '/')
      const advanceHistory = childHistory + '/';
      const hasNextStreet = findChildActions(ctx, advanceHistory).length > 0;

      if (hasNextStreet) {
        // Street advance — recurse into next street
        edge.toId = advanceHistory || 'root';
        edges.push(edge);
        buildNodeRecursive(
          ctx,
          {
            history: advanceHistory,
            player: 0, // OOP acts first on new street
            pot: newPot,
            stacks: newStacks,
            facingBet: 0,
            raiseCount: 0,
            isFirstAction: true,
            depth: state.depth + 1,
            roundStartStacks: [...newStacks],
          },
          nodes,
          edges,
        );
      } else if (hasChildren) {
        edge.toId = childHistory;
        edges.push(edge);
        buildNodeRecursive(
          ctx,
          {
            history: childHistory,
            player: 1 - player,
            pot: newPot,
            stacks: newStacks,
            facingBet: 0,
            raiseCount: 0,
            isFirstAction: true,
            depth: state.depth + 1,
            roundStartStacks: [...newStacks],
          },
          nodes,
          edges,
        );
      } else {
        // Terminal showdown
        const terminalId = childHistory + '_showdown';
        edge.toId = terminalId;
        edges.push(edge);
        nodes.push({
          id: terminalId,
          type: 'showdown',
          player,
          pot: newPot,
          stack: Math.min(newStacks[0], newStacks[1]),
          x: 0,
          y: 0,
        });
      }
    } else if (semantic === 'check') {
      // Check: pass to opponent (or if both checked, advance street)
      const hasChildren = findChildActions(ctx, childHistory).length > 0;
      const advanceHistory = childHistory + '/';
      const hasNextStreet = findChildActions(ctx, advanceHistory).length > 0;

      if (!state.isFirstAction) {
        // Both players checked — advance or terminal
        if (hasNextStreet) {
          edge.toId = advanceHistory;
          edges.push(edge);
          buildNodeRecursive(
            ctx,
            {
              history: advanceHistory,
              player: 0,
              pot,
              stacks: [...stacks],
              facingBet: 0,
              raiseCount: 0,
              isFirstAction: true,
              depth: state.depth + 1,
              roundStartStacks: [...stacks],
            },
            nodes,
            edges,
          );
        } else {
          const terminalId = childHistory + '_showdown';
          edge.toId = terminalId;
          edges.push(edge);
          nodes.push({
            id: terminalId,
            type: 'showdown',
            player,
            pot,
            stack: Math.min(stacks[0], stacks[1]),
            x: 0,
            y: 0,
          });
        }
      } else {
        // First check — opponent acts
        if (hasChildren) {
          edge.toId = childHistory;
          edges.push(edge);
          buildNodeRecursive(
            ctx,
            {
              history: childHistory,
              player: 1 - player,
              pot,
              stacks: [...stacks],
              facingBet: 0,
              raiseCount: 0,
              isFirstAction: false,
              depth: state.depth + 1,
              roundStartStacks: [...state.roundStartStacks],
            },
            nodes,
            edges,
          );
        } else if (hasNextStreet) {
          edge.toId = advanceHistory;
          edges.push(edge);
          buildNodeRecursive(
            ctx,
            {
              history: advanceHistory,
              player: 0,
              pot,
              stacks: [...stacks],
              facingBet: 0,
              raiseCount: 0,
              isFirstAction: true,
              depth: state.depth + 1,
              roundStartStacks: [...stacks],
            },
            nodes,
            edges,
          );
        }
      }
    } else {
      // Bet / Raise / All-in
      // amount = total bet level for raises, additional for bets/all-in
      const invested = state.roundStartStacks[player] - stacks[player];
      const displayAmount = amount ?? stacks[player];
      // For raises, amount is total bet level; additional = amount - invested
      // For bets/all-in, amount IS the additional chips
      const additionalFromStack =
        semantic === 'raise' && amount != null
          ? Math.min(displayAmount - invested, stacks[player])
          : Math.min(displayAmount, stacks[player]);
      const newStacks: [number, number] = [...stacks];
      newStacks[player] -= additionalFromStack;
      const newPot = pot + additionalFromStack;
      const totalBetLevel = invested + additionalFromStack;

      const hasChildren = findChildActions(ctx, childHistory).length > 0;
      if (hasChildren) {
        edge.toId = childHistory;
        edges.push(edge);
        buildNodeRecursive(
          ctx,
          {
            history: childHistory,
            player: 1 - player,
            pot: newPot,
            stacks: newStacks,
            facingBet: totalBetLevel,
            raiseCount: state.raiseCount + (state.facingBet > 0 ? 1 : 0),
            isFirstAction: false,
            depth: state.depth + 1,
            roundStartStacks: [...state.roundStartStacks],
          },
          nodes,
          edges,
        );
      } else {
        // Terminal (all-in with no response possible?)
        const terminalId = childHistory + '_showdown';
        edge.toId = terminalId;
        edges.push(edge);
        nodes.push({
          id: terminalId,
          type: 'showdown',
          player,
          pot: newPot,
          stack: 0,
          x: 0,
          y: 0,
        });
      }
    }
  }
}

/**
 * Find all single-char action extensions of a history prefix.
 * Returns unique action characters sorted for consistent ordering.
 */
function findChildActions(ctx: BuildContext, history: string): string[] {
  const children = new Set<string>();
  for (const h of ctx.histories) {
    if (h.length > history.length && h.startsWith(history)) {
      const nextChar = h[history.length];
      // Skip '/' (street separator) — it's not an action
      if (nextChar !== '/') {
        children.add(nextChar);
      }
    }
  }
  return Array.from(children).sort(actionCharOrder);
}

/**
 * Sort action chars in a consistent order:
 * fold(f), check(x), call(c) first, then bet/raise digits ascending, then allin(A)
 */
function actionCharOrder(a: string, b: string): number {
  const order = (ch: string) => {
    if (ch === 'f') return 0;
    if (ch === 'x') return 1;
    if (ch === 'c') return 2;
    if (/^\d$/.test(ch)) return 10 + parseInt(ch);
    if (ch === 'A') return 100;
    return 50;
  };
  return order(a) - order(b);
}

interface ActionInfo {
  char: string;
  semantic: string;
}

/**
 * Generate ordered action info matching the tree-builder's action ordering.
 * The tree-builder generates actions as:
 *   Facing bet: [fold, call, raise_0, raise_1, ..., allin]
 *   No bet:     [check, bet_0, bet_1, ..., allin]
 */
function generateActionOrder(chars: string[], facingBet: boolean): ActionInfo[] {
  return chars.map((ch) => ({
    char: ch,
    semantic: actionCharToSemantic(ch, facingBet),
  }));
}

/**
 * Compute bet/raise amount for display.
 * For bets: returns the bet amount (= additional chips).
 * For raises: returns the total bet level (raise-to amount).
 */
function computeAmount(
  config: TreeConfig,
  semantic: string,
  actionChar: string,
  state: NodeState,
): number | null {
  if (semantic === 'fold' || semantic === 'check' || semantic === 'call') return null;
  if (semantic === 'allin') return state.stacks[state.player];

  const sizeIdx = parseInt(actionChar) - 1; // '1' → index 0, '2' → index 1, etc.
  const sizes = config.betSizes.flop; // TODO: support turn/river based on street
  if (sizeIdx < 0 || sizeIdx >= sizes.length) return state.stacks[state.player];

  if (semantic === 'bet') {
    return calcBetAmount(state.pot, sizes[sizeIdx], state.stacks[state.player]);
  }
  // raise: return total bet level for display
  const invested = state.roundStartStacks[state.player] - state.stacks[state.player];
  const additional = calcRaiseAmount(
    state.pot,
    state.facingBet,
    sizes[sizeIdx],
    state.stacks[state.player],
    invested,
  );
  return invested + additional;
}

function formatActionLabel(semantic: string, amount: number | null): string {
  switch (semantic) {
    case 'fold':
      return 'Fold';
    case 'check':
      return 'Check';
    case 'call':
      return 'Call';
    case 'allin':
      return `All-in${amount != null ? ' ' + fmtBB(amount) : ''}`;
    case 'bet':
      return `Bet${amount != null ? ' ' + fmtBB(amount) : ''}`;
    case 'raise':
      return `Raise${amount != null ? ' ' + fmtBB(amount) : ''}`;
    default:
      return semantic;
  }
}

function fmtBB(amount: number): string {
  if (amount === Math.floor(amount)) return amount.toString();
  // Show 1 decimal if fractional
  const s = amount.toFixed(2);
  // Trim trailing zeros: 3.50 → 3.5, 3.00 → 3
  return s.replace(/\.?0+$/, '') || '0';
}

// ── Layout Algorithm ───────────────────────────────────────────

export const COL_WIDTH = 280;
export const ROW_HEIGHT = 40;
export const PADDING = 30;

/**
 * Assign (x, y) coordinates to all nodes.
 * Strategy: BFS by depth to assign columns, then recursive subtree sizing for rows.
 */
export function layoutTree(nodes: VizNode[], edges: VizEdge[]): VizTree {
  if (nodes.length === 0) return { nodes, edges, width: 0, height: 0 };

  // Build adjacency: parent → children (ordered)
  const childrenOf = new Map<string, string[]>();
  const parentOf = new Map<string, string>();
  for (const e of edges) {
    const kids = childrenOf.get(e.fromId) || [];
    kids.push(e.toId);
    childrenOf.set(e.fromId, kids);
    parentOf.set(e.toId, e.fromId);
  }

  // Find root (node with no parent)
  const nodeMap = new Map<string, VizNode>();
  for (const n of nodes) nodeMap.set(n.id, n);

  const rootId = nodes.find((n) => !parentOf.has(n.id))?.id;
  if (!rootId) return { nodes, edges, width: 0, height: 0 };

  // Compute depth of each node (BFS)
  const depthMap = new Map<string, number>();
  const queue: string[] = [rootId];
  depthMap.set(rootId, 0);
  while (queue.length > 0) {
    const id = queue.shift()!;
    const depth = depthMap.get(id)!;
    for (const childId of childrenOf.get(id) || []) {
      depthMap.set(childId, depth + 1);
      queue.push(childId);
    }
  }

  // Compute subtree height for each node (bottom-up)
  const subtreeHeight = new Map<string, number>();
  function getSubtreeHeight(id: string): number {
    if (subtreeHeight.has(id)) return subtreeHeight.get(id)!;
    const children = childrenOf.get(id) || [];
    if (children.length === 0) {
      subtreeHeight.set(id, 1);
      return 1;
    }
    let total = 0;
    for (const child of children) {
      total += getSubtreeHeight(child);
    }
    subtreeHeight.set(id, total);
    return total;
  }
  getSubtreeHeight(rootId);

  // Assign Y coordinates recursively
  function assignPositions(id: string, yStart: number): void {
    const node = nodeMap.get(id);
    if (!node) return;

    const depth = depthMap.get(id) ?? 0;
    node.x = PADDING + depth * COL_WIDTH;

    const children = childrenOf.get(id) || [];
    if (children.length === 0) {
      node.y = yStart + ROW_HEIGHT / 2;
      return;
    }

    // Distribute children vertically
    let currentY = yStart;
    const childYCenters: number[] = [];
    for (const child of children) {
      const h = getSubtreeHeight(child) * ROW_HEIGHT;
      assignPositions(child, currentY);
      const childNode = nodeMap.get(child);
      if (childNode) childYCenters.push(childNode.y);
      currentY += h;
    }

    // Parent Y = average of children Y
    if (childYCenters.length > 0) {
      node.y = childYCenters[0]; // Align with first child (main line)
    }
  }

  assignPositions(rootId, PADDING);

  // Compute total dimensions
  let maxX = 0,
    maxY = 0;
  for (const n of nodes) {
    maxX = Math.max(maxX, n.x);
    maxY = Math.max(maxY, n.y);
  }

  return {
    nodes,
    edges,
    width: maxX + COL_WIDTH,
    height: maxY + PADDING * 2,
  };
}
