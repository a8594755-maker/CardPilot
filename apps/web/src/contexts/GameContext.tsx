import {
  createContext,
  useContext,
  useEffect,
  useState,
  useRef,
  type MutableRefObject,
  type ReactNode,
} from 'react';
import type {
  TableState,
  RoomFullState,
  AdvicePayload,
  SettlementResult,
  SevenTwoBountyInfo,
  TimerState,
} from '@cardpilot/shared-types';
import { useSocket } from './SocketContext';
import { useRoom } from './RoomContext';
import { useToast } from './ToastContext';
import { useAuth } from './AuthContext';
import { useGameSocketEvents } from '../hooks/useGameSocketEvents';
import type { PreAction } from '../lib/action-derivations';

export type AllInLockState = {
  handId: string;
  eligiblePlayers: Array<{ seat: number; name: string }>;
  maxRunCountAllowed: 3;
  submittedPlayerIds: number[];
  underdogSeat: number | null;
  targetRunCount: 1 | 2 | 3 | null;
  equities?: Array<{ seat: number; winRate: number; tieRate: number; equityRate: number }>;
};

export type BoardRevealState = {
  street: string;
  equities: Array<{ seat: number; winRate: number; tieRate: number; equityRate: number }>;
  hints?: Array<{ seat: number; label: string }>;
};

export type GameContextType = {
  // Core State
  snapshot: TableState | null;
  roomState: RoomFullState | null;
  seat: number;
  holeCards: string[];

  // Game Actions & Status
  advice: AdvicePayload | null;
  deviation: { deviation: number; playerAction: string } | null;
  actionPending: boolean;
  winners: Array<{ seat: number; amount: number; handName?: string }> | null;
  settlement: SettlementResult | null;
  allInLock: AllInLockState | null;
  myRunPreference: 1 | 2 | 3 | null;
  boardReveal: BoardRevealState | null;
  lastActionBySeat: Record<number, { action: string; amount: number }>;
  preAction: PreAction | null;

  // Timer
  actionTimer: TimerState | null;

  // Features / Side Games
  postHandShowAvailable: boolean;
  sevenTwoBountyPrompt: { bountyPerPlayer: number; totalBounty: number } | null;
  sevenTwoBountyResult: SevenTwoBountyInfo | null;
  sevenTwoRevealActive: SevenTwoBountyInfo | null;
  postHandRevealedCards: Record<number, [string, string]>;
  bombPotOverlayActive: { anteAmount: number } | null;

  // Setters
  setSeat: (seat: number) => void;
  setActionPending: (pending: boolean) => void;
  setMyRunPreference: (run: 1 | 2 | 3 | null) => void;
  setPreAction: (action: PreAction | null) => void;
  setSnapshot: (s: TableState | null) => void;
  setHoleCards: (cards: string[]) => void;
  setRoomState: (s: RoomFullState | null) => void;
  setAdvice: (a: AdvicePayload | null) => void;
  setDeviation: (d: { deviation: number; playerAction: string } | null) => void;
  setWinners: (w: Array<{ seat: number; amount: number; handName?: string }> | null) => void;
  setSettlement: (s: SettlementResult | null) => void;
  setAllInLock: (s: AllInLockState | null) => void;
  setBoardReveal: (s: BoardRevealState | null) => void;
  setLastActionBySeat: (
    update: (
      prev: Record<number, { action: string; amount: number }>,
    ) => Record<number, { action: string; amount: number }>,
  ) => void;
  setPostHandShowAvailable: (a: boolean) => void;
  setSevenTwoBountyPrompt: (p: { bountyPerPlayer: number; totalBounty: number } | null) => void;
  setSevenTwoBountyResult: (r: SevenTwoBountyInfo | null) => void;
  setSevenTwoRevealActive: (r: SevenTwoBountyInfo | null) => void;
  setPostHandRevealedCards: (
    update: (prev: Record<number, [string, string]>) => Record<number, [string, string]>,
  ) => void;
  setBombPotOverlayActive: (s: { anteAmount: number } | null) => void;

  // Refs (exposed for hooks that need current value without re-rendering or stale closures)
  snapshotRef: MutableRefObject<TableState | null>;
  seatRef: MutableRefObject<number>;
  holeCardsRef: MutableRefObject<string[]>;
};

const GameContext = createContext<GameContextType | null>(null);

export function useGame() {
  const context = useContext(GameContext);
  if (!context) {
    throw new Error('useGame must be used within a GameProvider');
  }
  return context;
}

export function GameProvider({ children }: { children: ReactNode }) {
  const { socket } = useSocket();
  const { tableId, currentRoomCode, currentRoomName } = useRoom();
  const { showToast } = useToast();
  const { authSession } = useAuth();

  // ── Core State ──
  const [snapshot, setSnapshot] = useState<TableState | null>(null);
  const [roomState, setRoomState] = useState<RoomFullState | null>(null);
  const [seat, setSeat] = useState(0);
  const [holeCards, setHoleCards] = useState<string[]>([]);

  // ── Game Status ──
  const [advice, setAdvice] = useState<AdvicePayload | null>(null);
  const [deviation, setDeviation] = useState<{ deviation: number; playerAction: string } | null>(
    null,
  );
  const [actionPending, setActionPending] = useState(false);
  const [winners, setWinners] = useState<Array<{
    seat: number;
    amount: number;
    handName?: string;
  }> | null>(null);
  const [settlement, setSettlement] = useState<SettlementResult | null>(null);
  const [allInLock, setAllInLock] = useState<AllInLockState | null>(null);
  const [myRunPreference, setMyRunPreference] = useState<1 | 2 | 3 | null>(null);
  const [boardReveal, setBoardReveal] = useState<BoardRevealState | null>(null);
  const [lastActionBySeat, setLastActionBySeat] = useState<
    Record<number, { action: string; amount: number }>
  >({});
  const [preAction, setPreAction] = useState<PreAction | null>(null);

  // ── Timer ──
  const serverTimerRef = useRef<TimerState | null>(null);
  const [actionTimer, setActionTimer] = useState<TimerState | null>(null);

  // Local tick: compute remaining from startedAt every 250ms
  useEffect(() => {
    if (!serverTimerRef.current) return;
    const tick = () => {
      const st = serverTimerRef.current;
      if (!st) {
        setActionTimer(null);
        return;
      }
      const elapsed = (Date.now() - st.startedAt) / 1000;
      if (st.usingTimeBank) {
        const tbRemaining = Math.max(0, st.timeBankRemaining - elapsed);
        setActionTimer({ ...st, timeBankRemaining: tbRemaining });
      } else {
        const remaining = Math.max(0, st.remaining - elapsed);
        setActionTimer({ ...st, remaining });
      }
    };
    tick();
    const id = setInterval(tick, 250);
    return () => clearInterval(id);
  }, [serverTimerRef.current]);

  const handleTimerUpdate = (t: TimerState | null) => {
    serverTimerRef.current = t;
    if (!t) {
      setActionTimer(null);
    } else {
      // Immediately compute from startedAt
      const elapsed = (Date.now() - t.startedAt) / 1000;
      if (t.usingTimeBank) {
        setActionTimer({ ...t, timeBankRemaining: Math.max(0, t.timeBankRemaining - elapsed) });
      } else {
        setActionTimer({ ...t, remaining: Math.max(0, t.remaining - elapsed) });
      }
    }
  };

  // ── Features ──
  const [postHandShowAvailable, setPostHandShowAvailable] = useState(false);
  const [sevenTwoBountyPrompt, setSevenTwoBountyPrompt] = useState<{
    bountyPerPlayer: number;
    totalBounty: number;
  } | null>(null);
  const [sevenTwoBountyResult, setSevenTwoBountyResult] = useState<SevenTwoBountyInfo | null>(null);
  const [sevenTwoRevealActive, setSevenTwoRevealActive] = useState<SevenTwoBountyInfo | null>(null);
  const [postHandRevealedCards, setPostHandRevealedCards] = useState<
    Record<number, [string, string]>
  >({});
  const [bombPotOverlayActive, setBombPotOverlayActive] = useState<{ anteAmount: number } | null>(
    null,
  );

  // ── Refs ──
  const snapshotRef = useRef(snapshot);
  const seatRef = useRef(seat);
  const holeCardsRef = useRef(holeCards);
  const latestSnapshotVersionRef = useRef(-1);
  const currentRoomCodeRef = useRef(currentRoomCode);
  const currentRoomNameRef = useRef(currentRoomName);

  // Sync refs
  useEffect(() => {
    snapshotRef.current = snapshot;
  }, [snapshot]);
  useEffect(() => {
    seatRef.current = seat;
  }, [seat]);
  useEffect(() => {
    holeCardsRef.current = holeCards;
  }, [holeCards]);
  useEffect(() => {
    currentRoomCodeRef.current = currentRoomCode;
  }, [currentRoomCode]);
  useEffect(() => {
    currentRoomNameRef.current = currentRoomName;
  }, [currentRoomName]);

  // ── Socket Events ──
  // We pass all state setters to the hook
  useGameSocketEvents({
    socket,
    tableId,
    authUserId: authSession?.userId,
    showToast,
    setSnapshot,
    setRoomState,
    setSeat,
    setHoleCards,
    setAdvice,
    setDeviation,
    setActionPending,
    setWinners,
    setSettlement,
    setAllInLock,
    setMyRunPreference,
    setBoardReveal,
    setLastActionBySeat,
    setPostHandShowAvailable,
    setSevenTwoBountyPrompt,
    setSevenTwoBountyResult,
    setSevenTwoRevealActive,
    setPostHandRevealedCards,
    setBombPotOverlayActive,
    setPreAction,
    onTimerUpdate: handleTimerUpdate,
    snapshotRef,
    seatRef,
    holeCardsRef,
    latestSnapshotVersionRef,
    currentRoomCodeRef,
    currentRoomNameRef,
  });

  return (
    <GameContext.Provider
      value={{
        snapshot,
        roomState,
        seat,
        holeCards,
        advice,
        deviation,
        actionPending,
        winners,
        settlement,
        allInLock,
        myRunPreference,
        boardReveal,
        lastActionBySeat,
        preAction,
        actionTimer,
        postHandShowAvailable,
        sevenTwoBountyPrompt,
        sevenTwoBountyResult,
        sevenTwoRevealActive,
        postHandRevealedCards,
        bombPotOverlayActive,
        setSeat,
        setActionPending,
        setMyRunPreference,
        setPreAction,
        setSnapshot,
        setHoleCards,
        setRoomState,
        setAdvice,
        setDeviation,
        setWinners,
        setSettlement,
        setAllInLock,
        setBoardReveal,
        setLastActionBySeat,
        setPostHandShowAvailable,
        setSevenTwoBountyPrompt,
        setSevenTwoBountyResult,
        setSevenTwoRevealActive,
        setPostHandRevealedCards,
        setBombPotOverlayActive,
        snapshotRef,
        seatRef,
        holeCardsRef,
      }}
    >
      {children}
    </GameContext.Provider>
  );
}
