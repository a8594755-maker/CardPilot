import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type WorkspaceMode = 'configure' | 'analyze' | 'play';
export type DataSource = 'none' | 'solver' | 'gtoplus';

interface WorkspaceStore {
  // Board — THE single source of truth
  boardCards: string[];
  boardSelectorOpen: boolean;

  // Mode
  mode: WorkspaceMode;

  // Panel visibility
  leftPanelOpen: boolean;
  rightPanelOpen: boolean;

  // Data source for current board
  dataSource: DataSource;
  activeJobId: string | null;

  // Board actions
  setBoardCards: (cards: string[]) => void;
  toggleBoardCard: (card: string) => void;
  clearBoard: () => void;
  randomBoard: (count: number) => void;
  openBoardSelector: () => void;
  closeBoardSelector: () => void;

  // Mode actions
  setMode: (mode: WorkspaceMode) => void;

  // Panel actions
  toggleLeftPanel: () => void;
  toggleRightPanel: () => void;

  // Data source actions
  setDataSource: (source: DataSource) => void;
  setActiveJobId: (id: string | null) => void;
}

const RANKS = 'AKQJT98765432';
const SUITS = 'shdc';

function buildDeck(): string[] {
  const deck: string[] = [];
  for (const r of RANKS) {
    for (const s of SUITS) {
      deck.push(`${r}${s}`);
    }
  }
  return deck;
}

function shuffledDeck(): string[] {
  const deck = buildDeck();
  for (let i = deck.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [deck[i], deck[j]] = [deck[j], deck[i]];
  }
  return deck;
}

export const useWorkspace = create<WorkspaceStore>()(
  persist(
    (set) => ({
      boardCards: [],
      boardSelectorOpen: false,
      mode: 'configure',
      leftPanelOpen: true,
      rightPanelOpen: true,
      dataSource: 'none',
      activeJobId: null,

      setBoardCards: (boardCards) => set({ boardCards }),
      toggleBoardCard: (card) =>
        set((s) => {
          if (s.boardCards.includes(card)) {
            return { boardCards: s.boardCards.filter((c) => c !== card) };
          }
          if (s.boardCards.length >= 5) return s;
          return { boardCards: [...s.boardCards, card] };
        }),
      clearBoard: () => set({ boardCards: [] }),
      randomBoard: (count) => set({ boardCards: shuffledDeck().slice(0, count) }),
      openBoardSelector: () => set({ boardSelectorOpen: true }),
      closeBoardSelector: () => set({ boardSelectorOpen: false }),

      setMode: (mode) => set({ mode }),

      toggleLeftPanel: () => set((s) => ({ leftPanelOpen: !s.leftPanelOpen })),
      toggleRightPanel: () => set((s) => ({ rightPanelOpen: !s.rightPanelOpen })),

      setDataSource: (dataSource) => set({ dataSource }),
      setActiveJobId: (activeJobId) => set({ activeJobId }),
    }),
    {
      name: 'cardpilot-solver-workspace',
      partialize: (state) => ({
        boardCards: state.boardCards,
        mode: state.mode,
        leftPanelOpen: state.leftPanelOpen,
        rightPanelOpen: state.rightPanelOpen,
      }),
    },
  ),
);
