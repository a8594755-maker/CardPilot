// Flatten an ActionNode tree into contiguous TypedArrays for data-oriented CFR.
//
// The existing tree builder produces an object graph of ActionNode/TerminalNode
// linked by Maps. This module converts that into a flat array representation
// where every node has an integer ID and all data is stored in typed arrays
// for maximum cache locality and zero GC pressure.

import type { GameNode, ActionNode, TerminalNode } from '../types.js';

// Street encoding for flat arrays
const STREET_CODE: Record<string, number> = { FLOP: 0, TURN: 1, RIVER: 2 };

// Action type encoding
export const ACTION_FOLD = 0;
export const ACTION_CHECK = 1;
export const ACTION_CALL = 2;
export const ACTION_BET = 3;
export const ACTION_RAISE = 4;
export const ACTION_ALLIN = 5;

export interface FlatTree {
  // Tree topology (immutable after build)
  numNodes: number;
  numTerminals: number;
  numPlayers: number;
  totalActions: number;

  // Per action-node arrays (length = numNodes)
  nodePlayer: Uint8Array;
  nodeStreet: Uint8Array;
  nodeNumActions: Uint8Array;
  nodeActionOffset: Uint32Array;
  nodePot: Float32Array;
  nodeStacks: Float32Array; // interleaved: numNodes * numPlayers

  // Edge arrays (length = totalActions)
  // childNodeId >= 0 means action node, < 0 means terminal: -(terminalIndex + 1)
  childNodeId: Int32Array;
  actionType: Uint8Array;

  // Terminal node arrays (length = numTerminals)
  terminalPot: Float32Array;
  terminalIsShowdown: Uint8Array;
  terminalFolder: Int8Array;
  terminalStacks: Float32Array; // interleaved: numTerminals * numPlayers
  terminalWinner: Int8Array;
  terminalFolded: Uint8Array; // bitmask of folded players (bit i = player i folded)

  // String metadata for export (not used in CFR hot loop)
  nodeHistoryKey: string[]; // length = numNodes — action history key per node
  nodeActionLabels: string[]; // length = totalActions — action label per edge
}

function encodeActionType(action: string): number {
  if (action === 'fold') return ACTION_FOLD;
  if (action === 'check') return ACTION_CHECK;
  if (action === 'call') return ACTION_CALL;
  if (action === 'allin') return ACTION_ALLIN;
  if (action.startsWith('bet_')) return ACTION_BET;
  if (action.startsWith('raise_')) return ACTION_RAISE;
  return ACTION_BET; // fallback
}

/**
 * Count all action nodes and terminal nodes in the tree.
 */
function countAll(node: GameNode): { actions: number; terminals: number; totalEdges: number } {
  if (node.type === 'terminal') {
    return { actions: 0, terminals: 1, totalEdges: 0 };
  }
  let actions = 1;
  let terminals = 0;
  let totalEdges = node.actions.length;
  for (const child of node.children.values()) {
    const sub = countAll(child);
    actions += sub.actions;
    terminals += sub.terminals;
    totalEdges += sub.totalEdges;
  }
  return { actions, terminals, totalEdges };
}

/**
 * Flatten an ActionNode tree into a FlatTree of contiguous TypedArrays.
 *
 * The existing `buildTree()` / `buildTreeMultiWay()` output is the input.
 * After flattening, the original tree can be garbage collected.
 */
export function flattenTree(root: ActionNode, numPlayers: number = 2): FlatTree {
  const counts = countAll(root);
  const numNodes = counts.actions;
  const numTerminals = counts.terminals;
  const totalActions = counts.totalEdges;

  // Allocate all arrays
  const nodePlayer = new Uint8Array(numNodes);
  const nodeStreet = new Uint8Array(numNodes);
  const nodeNumActions = new Uint8Array(numNodes);
  const nodeActionOffset = new Uint32Array(numNodes);
  const nodePot = new Float32Array(numNodes);
  const nodeStacks = new Float32Array(numNodes * numPlayers);

  const childNodeId = new Int32Array(totalActions);
  const actionTypeArr = new Uint8Array(totalActions);

  const terminalPot = new Float32Array(numTerminals);
  const terminalIsShowdown = new Uint8Array(numTerminals);
  const terminalFolder = new Int8Array(numTerminals);
  const terminalStacks = new Float32Array(numTerminals * numPlayers);
  const terminalWinner = new Int8Array(numTerminals);
  const terminalFolded = new Uint8Array(numTerminals);

  // String metadata for export
  const nodeHistoryKey = new Array<string>(numNodes);
  const nodeActionLabels = new Array<string>(totalActions);

  // DFS pass 1: assign IDs to action nodes
  // We need two passes because children may reference nodes not yet seen
  let nextNodeId = 0;
  let nextTerminalId = 0;
  const nodeIdMap = new Map<GameNode, number>();

  function assignIds(node: GameNode): void {
    if (node.type === 'terminal') {
      nodeIdMap.set(node, -(nextTerminalId + 1));
      nextTerminalId++;
      return;
    }
    nodeIdMap.set(node, nextNodeId++);
    for (const action of node.actions) {
      const child = node.children.get(action)!;
      assignIds(child);
    }
  }
  assignIds(root);

  // DFS pass 2: fill arrays
  let edgeOffset = 0;
  let termIdx = 0;
  let actionNodeIdx = 0;

  function fillArrays(node: GameNode): void {
    if (node.type === 'terminal') {
      const tNode = node as TerminalNode;
      const ti = termIdx++;
      terminalPot[ti] = tNode.pot;
      terminalIsShowdown[ti] = tNode.showdown ? 1 : 0;
      terminalFolder[ti] = tNode.showdown ? -1 : tNode.lastToAct;
      for (let p = 0; p < numPlayers; p++) {
        terminalStacks[ti * numPlayers + p] = tNode.playerStacks[p] ?? 0;
      }
      terminalWinner[ti] = tNode.winner ?? -1;

      // Encode folded players bitmask
      let foldedBits = 0;
      if (tNode.foldedPlayers) {
        for (let p = 0; p < tNode.foldedPlayers.length; p++) {
          if (tNode.foldedPlayers[p]) foldedBits |= 1 << p;
        }
      }
      terminalFolded[ti] = foldedBits;
      return;
    }

    const actNode = node as ActionNode;
    const nid = actionNodeIdx++;
    const numActs = actNode.actions.length;

    nodePlayer[nid] = actNode.player;
    nodeStreet[nid] = STREET_CODE[actNode.street] ?? 0;
    nodeNumActions[nid] = numActs;
    nodeActionOffset[nid] = edgeOffset;
    nodePot[nid] = actNode.pot;
    nodeHistoryKey[nid] = actNode.historyKey;

    for (let p = 0; p < numPlayers; p++) {
      nodeStacks[nid * numPlayers + p] = actNode.stacks[p] ?? 0;
    }

    // Fill edge arrays
    for (let a = 0; a < numActs; a++) {
      const action = actNode.actions[a];
      const child = actNode.children.get(action)!;
      const childId = nodeIdMap.get(child)!;
      childNodeId[edgeOffset + a] = childId;
      actionTypeArr[edgeOffset + a] = encodeActionType(action);
      nodeActionLabels[edgeOffset + a] = action;
    }
    edgeOffset += numActs;

    // Recurse into children (same DFS order as assignIds)
    for (const action of actNode.actions) {
      const child = actNode.children.get(action)!;
      fillArrays(child);
    }
  }
  fillArrays(root);

  return {
    numNodes,
    numTerminals,
    numPlayers,
    totalActions,
    nodePlayer,
    nodeStreet,
    nodeNumActions,
    nodeActionOffset,
    nodePot,
    nodeStacks,
    childNodeId,
    actionType: actionTypeArr,
    terminalPot,
    terminalIsShowdown,
    terminalFolder,
    terminalStacks,
    terminalWinner,
    terminalFolded,
    nodeHistoryKey,
    nodeActionLabels,
  };
}

/**
 * Decode a terminal node ID to its index.
 * Terminal IDs are encoded as -(index + 1).
 */
export function decodeTerminalId(id: number): number {
  return -(id + 1);
}

/**
 * Check if a child ID refers to a terminal node.
 */
export function isTerminal(childId: number): boolean {
  return childId < 0;
}

/**
 * Apply rake to showdown terminal pots in a flat tree.
 * Rake is deducted from the pot before distribution:
 *   rakeAmount = min(pot * percentage, cap)
 *   effectivePot = pot - rakeAmount
 *
 * Fold terminals are NOT raked (pot goes to winner without deduction).
 */
export function applyRakeToTree(tree: FlatTree, rakePercentage: number, rakeCap: number): void {
  for (let ti = 0; ti < tree.numTerminals; ti++) {
    if (tree.terminalIsShowdown[ti]) {
      const pot = tree.terminalPot[ti];
      const rakeAmount = Math.min(pot * rakePercentage, rakeCap);
      tree.terminalPot[ti] = pot - rakeAmount;
    }
  }
}
