import { create } from 'zustand';
import type {
  GtoPlusCombo,
  GtoPlusContext,
  GtoPlusSummary,
  SolverGridResult,
} from '../lib/api-client';

interface StrategyEntry {
  key: string;
  probs: number[];
}

type DataSource = 'cfr' | 'gtoplus';

interface StrategyBrowserStore {
  // Existing fields
  config: string;
  flopFile: string;
  flopCards: string[];
  currentPath: string[];
  strategies: StrategyEntry[];
  selectedHandClass: string | null;
  player: number;

  // GTO+ data (OOP / primary player)
  dataSource: DataSource;
  nodeGrid: Record<string, Record<string, number>>;
  nodeActions: string[];
  nodeCombos: GtoPlusCombo[];
  nodeContext: GtoPlusContext | null;
  nodeSummary: GtoPlusSummary | null;

  // IP (secondary player) data
  ipFile: string;
  ipGrid: Record<string, Record<string, number>>;
  ipActions: string[];
  ipCombos: GtoPlusCombo[];
  ipContext: GtoPlusContext | null;
  ipSummary: GtoPlusSummary | null;

  // Hover & interaction state (Phase 1A/1E)
  hoveredCategory: string | null;
  fixedCategory: string | null;
  hoveredCombo: string | null;
  hoveredHandClass: string | null;
  selectedAction: string | null;

  // Solver tree navigation (history-based)
  currentHistory: string;
  solverChildNodes: SolverGridResult['childNodes'];

  // Strategy clipboard (Phase 1G)
  clipboard: {
    grid: Record<string, Record<string, number>>;
    actions: string[];
  } | null;

  // Methods
  setConfig: (config: string) => void;
  setFlop: (file: string, cards: string[]) => void;
  setStrategies: (entries: StrategyEntry[]) => void;
  navigateTo: (action: string) => void;
  setPath: (path: string[]) => void;
  goBack: () => void;
  goToRoot: () => void;
  selectHand: (handClass: string | null) => void;
  setPlayer: (p: number) => void;
  setDataSource: (source: DataSource) => void;
  setNodeData: (data: {
    grid: Record<string, Record<string, number>>;
    actions: string[];
    combos: GtoPlusCombo[];
    context: GtoPlusContext;
    summary: GtoPlusSummary;
  }) => void;
  setIpFile: (file: string) => void;
  setIpData: (data: {
    grid: Record<string, Record<string, number>>;
    actions: string[];
    combos: GtoPlusCombo[];
    context: GtoPlusContext;
    summary: GtoPlusSummary;
  }) => void;
  clearIpData: () => void;
  clearNodeData: () => void;
  setHoveredCategory: (key: string | null) => void;
  setFixedCategory: (key: string | null) => void;
  setHoveredCombo: (combo: string | null) => void;
  setHoveredHandClass: (handClass: string | null) => void;
  setSelectedAction: (action: string | null) => void;
  setClipboard: (
    data: { grid: Record<string, Record<string, number>>; actions: string[] } | null,
  ) => void;
  setSolverChildNodes: (nodes: SolverGridResult['childNodes']) => void;
  navigateToHistory: (history: string) => void;
  goToRootHistory: () => void;
}

export const useStrategyBrowser = create<StrategyBrowserStore>((set) => ({
  config: '',
  flopFile: '',
  flopCards: [],
  currentPath: [],
  strategies: [],
  selectedHandClass: null,
  player: 0,
  dataSource: 'gtoplus',
  nodeGrid: {},
  nodeActions: [],
  nodeCombos: [],
  nodeContext: null,
  nodeSummary: null,
  ipFile: '',
  ipGrid: {},
  ipActions: [],
  ipCombos: [],
  ipContext: null,
  ipSummary: null,

  currentHistory: '',
  solverChildNodes: [],

  hoveredCategory: null,
  fixedCategory: null,
  hoveredCombo: null,
  hoveredHandClass: null,
  selectedAction: null,
  clipboard: null,

  setConfig: (config) => set({ config }),
  setFlop: (flopFile, flopCards) =>
    set({ flopFile, flopCards, currentPath: [], strategies: [], selectedHandClass: null }),
  setStrategies: (strategies) => set({ strategies }),
  navigateTo: (action) => set((s) => ({ currentPath: [...s.currentPath, action] })),
  setPath: (currentPath) => set({ currentPath }),
  goBack: () => set((s) => ({ currentPath: s.currentPath.slice(0, -1) })),
  goToRoot: () => set({ currentPath: [] }),
  selectHand: (selectedHandClass) => set({ selectedHandClass }),
  setPlayer: (player) => set({ player }),
  setDataSource: (dataSource) => set({ dataSource }),
  setNodeData: ({ grid, actions, combos, context, summary }) =>
    set({
      nodeGrid: grid,
      nodeActions: actions,
      nodeCombos: combos,
      nodeContext: context,
      nodeSummary: summary,
    }),
  setIpFile: (ipFile) => set({ ipFile }),
  setIpData: ({ grid, actions, combos, context, summary }) =>
    set({
      ipGrid: grid,
      ipActions: actions,
      ipCombos: combos,
      ipContext: context,
      ipSummary: summary,
    }),
  clearIpData: () =>
    set({
      ipFile: '',
      ipGrid: {},
      ipActions: [],
      ipCombos: [],
      ipContext: null,
      ipSummary: null,
    }),
  clearNodeData: () =>
    set({
      nodeGrid: {},
      nodeActions: [],
      nodeCombos: [],
      nodeContext: null,
      nodeSummary: null,
    }),
  setHoveredCategory: (hoveredCategory) => set({ hoveredCategory }),
  setFixedCategory: (fixedCategory) => set({ fixedCategory }),
  setHoveredCombo: (hoveredCombo) => set({ hoveredCombo }),
  setHoveredHandClass: (hoveredHandClass) => set({ hoveredHandClass }),
  setSelectedAction: (selectedAction) => set({ selectedAction }),
  setClipboard: (clipboard) => set({ clipboard }),
  setSolverChildNodes: (solverChildNodes) => set({ solverChildNodes }),
  navigateToHistory: (currentHistory) => set({ currentHistory, selectedHandClass: null }),
  goToRootHistory: () => set({ currentHistory: '', selectedHandClass: null }),
}));
