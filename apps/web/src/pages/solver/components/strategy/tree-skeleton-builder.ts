// Build a VizTree directly from a TreeConfig, without strategy/solver data.
// All frequencies are uniform (1/numActions).

import type { VizNode, VizEdge, VizTree, TreeConfig } from './game-tree-layout';
import { calcBetAmount, calcRaiseAmount } from './game-tree-layout';

type Street = 'FLOP' | 'TURN' | 'RIVER';

const NEXT_STREET: Record<Street, Street | null> = {
  FLOP: 'TURN',
  TURN: 'RIVER',
  RIVER: null,
};

const ACTION_LABELS: Record<string, string> = {
  check: 'Check',
  bet: 'Bet',
  call: 'Call',
  fold: 'Fold',
  raise: 'Raise',
  allin: 'All-in',
};

interface SkeletonState {
  history: string;
  player: number;
  pot: number;
  stacks: [number, number];
  facingBet: number;
  raiseCount: number;
  isFirstAction: boolean;
  street: Street;
  roundStartStacks: [number, number];
}

interface ActionInfo {
  action: string; // internal: 'check', 'bet_0', 'fold', 'call', 'raise_0', 'allin'
  semantic: string; // 'check', 'bet', 'fold', 'call', 'raise', 'allin'
  amount: number | null;
  char: string; // history encoding char
}

function getBetSizesForStreet(config: TreeConfig, street: Street): number[] {
  switch (street) {
    case 'FLOP':
      return config.betSizes.flop;
    case 'TURN':
      return config.betSizes.turn;
    case 'RIVER':
      return config.betSizes.river;
  }
}

function getLegalActions(config: SkeletonTreeConfig, state: SkeletonState): ActionInfo[] {
  const actions: ActionInfo[] = [];
  const playerStack = state.stacks[state.player];

  // Per-level geometric mode: one bet/raise per level
  if (config.perLevelBetFractions) {
    const fracs = config.perLevelBetFractions;

    if (state.facingBet > 0) {
      // Facing a bet/raise — offer raise (if within cap), call, fold
      const opponentStack = state.stacks[1 - state.player];
      const invested = state.roundStartStacks[state.player] - state.stacks[state.player];
      const raiseLevel = state.raiseCount + 1;
      if (
        state.raiseCount < config.raiseCapPerStreet &&
        raiseLevel < fracs.length &&
        opponentStack > 0
      ) {
        const additional = calcRaiseAmount(
          state.pot,
          state.facingBet,
          fracs[raiseLevel],
          playerStack,
          invested,
        );
        const totalBetLevel = invested + additional;
        if (totalBetLevel > state.facingBet) {
          actions.push({
            action: `raise_${raiseLevel}`,
            semantic: 'raise',
            amount: totalBetLevel,
            char: String(raiseLevel + 1),
          });
        }
      }
      actions.push({ action: 'call', semantic: 'call', amount: null, char: 'c' });
      actions.push({ action: 'fold', semantic: 'fold', amount: null, char: 'f' });
    } else {
      // No bet to face — offer bet (level 0), check
      if (playerStack > 0) {
        const amount = calcBetAmount(state.pot, fracs[0], playerStack);
        actions.push({
          action: 'bet_0',
          semantic: 'bet',
          amount,
          char: '1',
        });
      }
      actions.push({ action: 'check', semantic: 'check', amount: null, char: 'x' });
    }
    return actions;
  }

  // Standard mode: multiple bet sizes per street
  const sizes = getBetSizesForStreet(config, state.street);

  if (state.facingBet > 0) {
    // Facing a bet/raise — GTO+ order: raise first (stays horizontal), call, fold last
    const opponentStack = state.stacks[1 - state.player];
    const invested = state.roundStartStacks[state.player] - state.stacks[state.player];
    if (state.raiseCount < config.raiseCapPerStreet && opponentStack > 0) {
      for (let i = 0; i < sizes.length; i++) {
        const additional = calcRaiseAmount(
          state.pot,
          state.facingBet,
          sizes[i],
          playerStack,
          invested,
        );
        const totalBetLevel = invested + additional;
        if (additional >= playerStack) {
          if (totalBetLevel > state.facingBet) {
            actions.push({
              action: `raise_${i}`,
              semantic: 'raise',
              amount: totalBetLevel,
              char: String(i + 1),
            });
          }
          break;
        }
        if (totalBetLevel > state.facingBet) {
          actions.push({
            action: `raise_${i}`,
            semantic: 'raise',
            amount: totalBetLevel,
            char: String(i + 1),
          });
        }
      }
    }
    actions.push({ action: 'call', semantic: 'call', amount: null, char: 'c' });
    actions.push({ action: 'fold', semantic: 'fold', amount: null, char: 'f' });
  } else {
    // No bet to face — GTO+ order: bet first (stays horizontal), check last
    if (playerStack > 0) {
      for (let i = 0; i < sizes.length; i++) {
        const amount = calcBetAmount(state.pot, sizes[i], playerStack);
        if (amount >= playerStack) {
          actions.push({
            action: `bet_${i}`,
            semantic: 'bet',
            amount,
            char: String(i + 1),
          });
          break;
        }
        actions.push({
          action: `bet_${i}`,
          semantic: 'bet',
          amount,
          char: String(i + 1),
        });
      }
    }
    actions.push({ action: 'check', semantic: 'check', amount: null, char: 'x' });
  }

  return actions;
}

function fmtAmount(amount: number): string {
  if (amount === Math.floor(amount)) return amount.toString();
  const s = amount.toFixed(2);
  return s.replace(/\.?0+$/, '') || '0';
}

function formatLabel(semantic: string, amount: number | null): string {
  const base = ACTION_LABELS[semantic] ?? semantic;
  if (amount != null && (semantic === 'bet' || semantic === 'raise' || semantic === 'allin')) {
    return `${base} ${fmtAmount(amount)}`;
  }
  return base;
}

export interface SkeletonTreeConfig extends TreeConfig {
  singleStreet?: boolean;
  includeAllin?: boolean; // default false for visualization
  startStreet?: 'FLOP' | 'TURN' | 'RIVER';
}

export function buildSkeletonTree(config: SkeletonTreeConfig): VizTree {
  const nodes: VizNode[] = [];
  const edges: VizEdge[] = [];

  const initialState: SkeletonState = {
    history: '',
    player: 0,
    pot: config.startingPot,
    stacks: [config.effectiveStack, config.effectiveStack],
    facingBet: 0,
    raiseCount: 0,
    isFirstAction: true,
    street: config.startStreet ?? 'FLOP',
    roundStartStacks: [config.effectiveStack, config.effectiveStack],
  };

  buildRecursive(config, initialState, nodes, edges);
  return compactLayout(nodes, edges);
}

function buildRecursive(
  config: SkeletonTreeConfig,
  state: SkeletonState,
  nodes: VizNode[],
  edges: VizEdge[],
): void {
  const actions = getLegalActions(config, state);
  if (actions.length === 0) return;

  const nodeId = state.history || 'root';
  nodes.push({
    id: nodeId,
    type: 'action',
    player: state.player,
    pot: state.pot,
    stack: Math.min(state.stacks[0], state.stacks[1]),
    x: 0,
    y: 0,
  });

  const freq = 1 / actions.length;

  for (const actionInfo of actions) {
    const childHistory = state.history + actionInfo.char;
    const label = formatLabel(actionInfo.semantic, actionInfo.amount);

    const edge: VizEdge = {
      fromId: nodeId,
      toId: '',
      actionKey: actionInfo.char,
      action: actionInfo.semantic,
      amount: actionInfo.amount,
      frequency: freq,
      label,
    };

    if (actionInfo.semantic === 'fold') {
      const termId = childHistory + '_fold';
      edge.toId = termId;
      edges.push(edge);
      nodes.push({
        id: termId,
        type: 'fold',
        player: state.player,
        pot: state.pot,
        stack: Math.min(state.stacks[0], state.stacks[1]),
        x: 0,
        y: 0,
      });
      continue;
    }

    if (actionInfo.semantic === 'call') {
      const invested = state.roundStartStacks[state.player] - state.stacks[state.player];
      const callAmount = Math.min(state.facingBet - invested, state.stacks[state.player]);
      const newStacks: [number, number] = [...state.stacks];
      newStacks[state.player] -= callAmount;
      const newPot = state.pot + callAmount;

      // All-in → showdown
      if (newStacks[0] <= 0 || newStacks[1] <= 0) {
        const termId = childHistory + '_showdown';
        edge.toId = termId;
        edges.push(edge);
        nodes.push({
          id: termId,
          type: 'showdown',
          player: state.player,
          pot: newPot,
          stack: 0,
          x: 0,
          y: 0,
        });
        continue;
      }

      // Advance street
      const nextStreet = NEXT_STREET[state.street];
      if (!nextStreet) {
        // River ended → real showdown
        const termId = childHistory + '_showdown';
        edge.toId = termId;
        edges.push(edge);
        nodes.push({
          id: termId,
          type: 'showdown',
          player: state.player,
          pot: newPot,
          stack: Math.min(newStacks[0], newStacks[1]),
          x: 0,
          y: 0,
        });
      } else if (config.singleStreet) {
        // Street transition → chance node (deal next card)
        const termId = childHistory + '_chance';
        edge.toId = termId;
        edges.push(edge);
        nodes.push({
          id: termId,
          type: 'chance',
          player: state.player,
          pot: newPot,
          stack: Math.min(newStacks[0], newStacks[1]),
          x: 0,
          y: 0,
        });
      } else {
        const advHistory = childHistory + '/';
        edge.toId = advHistory;
        edges.push(edge);
        buildRecursive(
          config,
          {
            history: advHistory,
            player: 0,
            pot: newPot,
            stacks: newStacks,
            facingBet: 0,
            raiseCount: 0,
            isFirstAction: true,
            street: nextStreet,
            roundStartStacks: [...newStacks],
          },
          nodes,
          edges,
        );
      }
      continue;
    }

    if (actionInfo.semantic === 'check') {
      if (!state.isFirstAction) {
        // Both checked → advance street or showdown
        const nextStreet = NEXT_STREET[state.street];
        if (!nextStreet) {
          // River ended → real showdown
          const termId = childHistory + '_showdown';
          edge.toId = termId;
          edges.push(edge);
          nodes.push({
            id: termId,
            type: 'showdown',
            player: state.player,
            pot: state.pot,
            stack: Math.min(state.stacks[0], state.stacks[1]),
            x: 0,
            y: 0,
          });
        } else if (config.singleStreet) {
          // Street transition → chance node
          const termId = childHistory + '_chance';
          edge.toId = termId;
          edges.push(edge);
          nodes.push({
            id: termId,
            type: 'chance',
            player: state.player,
            pot: state.pot,
            stack: Math.min(state.stacks[0], state.stacks[1]),
            x: 0,
            y: 0,
          });
        } else {
          const advHistory = childHistory + '/';
          edge.toId = advHistory;
          edges.push(edge);
          buildRecursive(
            config,
            {
              history: advHistory,
              player: 0,
              pot: state.pot,
              stacks: [...state.stacks],
              facingBet: 0,
              raiseCount: 0,
              isFirstAction: true,
              street: nextStreet,
              roundStartStacks: [...state.stacks],
            },
            nodes,
            edges,
          );
        }
      } else {
        // First check → opponent acts
        edge.toId = childHistory;
        edges.push(edge);
        buildRecursive(
          config,
          {
            history: childHistory,
            player: 1 - state.player,
            pot: state.pot,
            stacks: [...state.stacks],
            facingBet: 0,
            raiseCount: 0,
            isFirstAction: false,
            street: state.street,
            roundStartStacks: [...state.roundStartStacks],
          },
          nodes,
          edges,
        );
      }
      continue;
    }

    // Bet / Raise / All-in
    // For raises, actionInfo.amount is the total bet level; compute additional for state
    const invested = state.roundStartStacks[state.player] - state.stacks[state.player];
    const displayAmount = actionInfo.amount ?? state.stacks[state.player];
    const additionalFromStack =
      actionInfo.semantic === 'raise' && actionInfo.amount != null
        ? Math.min(displayAmount - invested, state.stacks[state.player])
        : Math.min(displayAmount, state.stacks[state.player]);
    const newStacks: [number, number] = [...state.stacks];
    newStacks[state.player] -= additionalFromStack;
    const newPot = state.pot + additionalFromStack;
    const isRaise = state.facingBet > 0;

    // Total bet level for the opponent to match
    const totalBetLevel = invested + additionalFromStack;

    edge.toId = childHistory;
    edges.push(edge);
    buildRecursive(
      config,
      {
        history: childHistory,
        player: 1 - state.player,
        pot: newPot,
        stacks: newStacks,
        facingBet: totalBetLevel,
        raiseCount: state.raiseCount + (isRaise ? 1 : 0),
        isFirstAction: false,
        street: state.street,
        roundStartStacks: [...state.roundStartStacks],
      },
      nodes,
      edges,
    );
  }
}

// ── GTO+ Layout ────────────────────────────────────────────────
// First child (raise/bet) stays horizontal at same Y as parent.
// Terminal siblings (call/fold) are placed in tight rows just below.
// Each raise level's terminals cascade slightly further down.
// Subtree siblings (e.g. check branch) go after everything above.

const COMPACT_COL = 240;
const ROW_GAP = 26;
const COMPACT_PAD = 15;

function compactLayout(nodes: VizNode[], edges: VizEdge[]): VizTree {
  if (nodes.length === 0) return { nodes, edges, width: 0, height: 0 };

  const childrenOf = new Map<string, string[]>();
  const parentOf = new Map<string, string>();
  for (const e of edges) {
    const kids = childrenOf.get(e.fromId) || [];
    kids.push(e.toId);
    childrenOf.set(e.fromId, kids);
    parentOf.set(e.toId, e.fromId);
  }

  const nodeMap = new Map<string, VizNode>();
  for (const n of nodes) nodeMap.set(n.id, n);

  const rootId = nodes.find((n) => !parentOf.has(n.id))?.id;
  if (!rootId) return { nodes, edges, width: 0, height: 0 };

  // BFS depth for X positions
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

  // GTO+ layout: returns max Y used by this subtree.
  // Terminal children at fixed offsets below parent (equal spacing).
  // All raise-chain nodes share the same Y → Call/Fold form horizontal bands.
  // Subtree siblings (check branch) placed below the full extent.
  function assign(id: string, y: number): number {
    const node = nodeMap.get(id);
    if (!node) return y;
    node.x = COMPACT_PAD + (depthMap.get(id) ?? 0) * COMPACT_COL;
    node.y = y;

    const children = childrenOf.get(id) || [];
    if (children.length === 0) return y;

    // Classify non-first children: terminal (no grandchildren) vs subtree
    const terminalSiblings: string[] = [];
    const subtreeSiblings: string[] = [];
    for (let i = 1; i < children.length; i++) {
      const gc = childrenOf.get(children[i]) || [];
      if (gc.length === 0) {
        terminalSiblings.push(children[i]);
      } else {
        subtreeSiblings.push(children[i]);
      }
    }

    // Place terminal siblings at fixed offsets below parent (equal spacing)
    let maxTerminalY = y;
    for (let i = 0; i < terminalSiblings.length; i++) {
      const tn = nodeMap.get(terminalSiblings[i]);
      if (tn) {
        tn.x = COMPACT_PAD + (depthMap.get(terminalSiblings[i]) ?? 0) * COMPACT_COL;
        tn.y = y + (i + 1) * ROW_GAP;
        maxTerminalY = tn.y;
      }
    }

    // First child: stays at same Y (horizontal continuation)
    const firstMaxY = assign(children[0], y);

    let maxY = Math.max(maxTerminalY, firstMaxY);

    // Subtree siblings (e.g. check branch): placed below everything above
    for (const sid of subtreeSiblings) {
      const startY = maxY + ROW_GAP;
      maxY = assign(sid, startY);
    }

    return maxY;
  }

  assign(rootId, COMPACT_PAD);

  let maxX = 0,
    maxY = 0;
  for (const n of nodes) {
    maxX = Math.max(maxX, n.x);
    maxY = Math.max(maxY, n.y);
  }

  return { nodes, edges, width: maxX + COMPACT_COL, height: maxY + COMPACT_PAD * 2 };
}
