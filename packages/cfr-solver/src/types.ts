// Core type definitions for the CFR solver

export type Street = 'FLOP' | 'TURN' | 'RIVER';
export type Player = 0 | 1; // 0 = OOP (BB), 1 = IP (BTN)

// Actions available at each street
// Format: 'fold', 'check', 'call', 'allin', 'bet_0'..'bet_N', 'raise_0'..'raise_N'
// Indexed by position in the street's bet size array from TreeConfig.
export type Action = string;

// Game tree node types
export interface TerminalNode {
  type: 'terminal';
  pot: number;       // total chips in pot (in bb)
  showdown: boolean; // true = showdown, false = someone folded
  lastToAct: Player; // who took the last action (for fold: the folder)
  playerStacks: [number, number]; // remaining stack for each player
}

export interface ActionNode {
  type: 'action';
  player: Player;
  street: Street;
  pot: number;
  stacks: [number, number]; // remaining stacks
  actions: Action[];
  children: Map<Action, GameNode>;
  historyKey: string;   // encoded action history for info-set lookup
  raiseCount: number;   // raises on current street (cap = 1 for V1)
}

export type GameNode = TerminalNode | ActionNode;

// Bet sizing configuration
export interface BetSizeConfig {
  flop: number[];   // fractions of pot
  turn: number[];
  river: number[];
}

// Tree building configuration
export interface TreeConfig {
  startingPot: number;       // in bb (e.g., 5 for HU SRP)
  effectiveStack: number;    // in bb (e.g., 47.5 for 50bb game)
  betSizes: BetSizeConfig;
  raiseCapPerStreet: number; // max raises per street (1 for V1)
}

// Solver configuration
export interface SolveConfig {
  tree: TreeConfig;
  iterations: number;
  boardId: number;
  board: number[];           // 3 card indices for flop
  oopRange: number[][];      // list of [card1, card2] pairs
  ipRange: number[][];       // list of [card1, card2] pairs
}

// Solved info-set result
export interface SolvedInfoSet {
  key: string;         // "F|42|0|xbc|137"
  actions: string[];   // action names
  probs: number[];     // average strategy probabilities
  ev?: number;
}
