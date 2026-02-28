import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { io, type Socket } from "socket.io-client";
import { useLocation, useNavigate } from "react-router-dom";
import type {
  AdvicePayload,
  LobbyRoomSummary,
  RoomFullState,
  RoomLogEntry,
  SettlementResult,
  SevenTwoBountyInfo,
  TablePlayer,
  TableState,
  TimerState
} from "@cardpilot/shared-types";
import { getClockwiseSeatsFromButton } from "@cardpilot/shared-types";
import { getExistingSession, ensureGuestSession, signOut, supabase, isUuid, normalizeClientUserId, resetInvalidRefreshGuard, type AuthSession } from "./supabase";
// NOTE: useAuthSession hook is ready at ./hooks/useAuthSession.ts
// Integration deferred to dedicated refactoring session to avoid hook-ordering risks
import { preloadCardImages } from "./lib/card-images.js";
// SettlementOverlay removed — replaced by non-blocking linger feedback + HandSummaryDrawer
import { PokerCard } from "./components/PokerCard";
import { AppLegalFooter } from "./legal-pages";
import { ClubsPage } from "./pages/clubs/ClubsPage";
import { HistoryByRoomPage } from "./pages/HistoryByRoomPage";
import { ProfilePage } from "./pages/ProfilePage";
import type { ClubListItem, ClubDetailPayload } from "@cardpilot/shared-types";
import { saveHand, autoTag, classifyStartingHandBucket, type HandRecord, type HandActionRecord } from "./lib/hand-history.js";
import { ChipAnimationLayer } from "./components/ChipAnimationLayer";
import { SevenTwoRevealOverlay } from "./components/SevenTwoRevealOverlay";
import { BombPotOverlay } from "./components/BombPotOverlay";
import { useChipAnimationDriver, type ChipAnimationAnchors } from "./hooks/useChipAnimationDriver";
import { type AnimationSpeed, loadAnimationSpeed, saveAnimationSpeed } from "./lib/chip-animation.js";
import { formatChips, makeChipFormatter } from "./lib/format-chips";
import { describeHandStrength } from "@cardpilot/shared-types";
import { TrainingDashboard } from "./pages/TrainingDashboard";
import { PreflopTrainer } from "./pages/PreflopTrainer";
import { useAuditEvents } from "./hooks/useAuditEvents";
import { BottomActionBar } from "./components/ui/BottomActionBar";
import { LeftOptionsRail, OptionsDrawer, type RailAction, type DrawerSection } from "./components/ui/LeftOptionsRail";
import { FoldConfirmModal } from "./components/ui/FoldConfirmModal";
import { HandSummaryDrawer } from "./components/ui/HandSummaryDrawer";
import { InGameHandHistory } from "./components/ui/InGameHandHistory";
import { SessionScoreboard, type SessionStatsEntry } from "./components/ui/SessionScoreboard";
import { AuthScreen } from "./components/AuthScreen";
import { OnboardingModal } from "./components/OnboardingModal";
import { RoomSettingsPanel } from "./components/RoomSettingsPanel";
import { SeatChip, InfoCell, Bar } from "./components/SeatChip";
import { Lobby, type CreateRoomSettings } from "./components/lobby";
import { useUserRole } from "./hooks/useUserRole";
import { OPTIONS_ITEMS, GROUP_LABELS, type SettingsTab } from "./config/optionsMenuItems";
import { useOverlayManager } from "./hooks/useOverlayManager";
import { useIsMobile } from "./hooks/useIsMobile";
import { useTableScale } from "./hooks/useTableScale";
import { MobileTopBar, MobileBottomTabs, MobileMoreMenu } from "./components/mobile-nav";
import {
  type PreAction,
  type PreActionType,
  deriveActionBar,
  derivePreActionUI,
  shouldAutoFirePreAction,
  shouldConfirmUnnecessaryFold,
} from "./lib/action-derivations";
import { haptic } from "./lib/haptic";
import { type UiSfx, playUiSfxTone } from "./lib/audio";
import { getSeatLayout, getPortraitSeatLayout, mapSeatToVisualIndex } from "./lib/seat-layout";
import { debugLog } from "./lib/debug";

// Use VITE_SERVER_URL if explicitly set; in dev mode use relative URL to go through Vite proxy
const SERVER = import.meta.env.VITE_SERVER_URL || (import.meta.env.DEV ? "/" : "http://127.0.0.1:4000");
const APP_VERSION = "v0.4.1";
const NETLIFY_COMMIT_REF = import.meta.env.VITE_NETLIFY_COMMIT_REF || "";
const NETLIFY_DEPLOY_ID = import.meta.env.VITE_NETLIFY_DEPLOY_ID || "";
const BUILD_TIME = new Date().toISOString().slice(0, 16).replace("T", " ");
const SOUND_PREF_KEY = "cardpilot_sound_muted";
const RECENT_NON_CLUB_TABLE_KEY = "cardpilot_recent_non_club_table";

/* ═══════════════════ MAIN APP ═══════════════════ */
export function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const isMobile = useIsMobile();
  const [isMobilePortrait, setIsMobilePortrait] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia("(max-width: 768px) and (orientation: portrait) and (pointer: coarse)").matches;
  });
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 768px) and (orientation: portrait) and (pointer: coarse)");
    const handler = (e: MediaQueryListEvent) => setIsMobilePortrait(e.matches);
    setIsMobilePortrait(mq.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  const [showMoreMenu, setShowMoreMenu] = useState(false);

  /* ── Auth state ── */
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState<string>("Guest");

  /* ── Game state ── */
  const [socket, setSocket] = useState<Socket | null>(null);
  const [tableId, setTableId] = useState("table-1");
  const [seat, setSeat] = useState(1);
  const [name, setName] = useState(displayName);
  const [snapshot, setSnapshot] = useState<TableState | null>(null);
  const [holeCards, setHoleCards] = useState<string[]>([]);
  const [advice, setAdvice] = useState<AdvicePayload | null>(null);
  const [deviation, setDeviation] = useState<{ deviation: number; playerAction: string } | null>(null);
  const [raiseTo, setRaiseTo] = useState(0);
  // message state removed — replaced by toast system (showToast)
  const [actionPending, setActionPending] = useState(false);
  const [winners, setWinners] = useState<Array<{ seat: number; amount: number; handName?: string }> | null>(null);
  const [settlement, setSettlement] = useState<SettlementResult | null>(null);
  const [settlementCountdown, setSettlementCountdown] = useState(0);
  const [settlementEndsAtMs, setSettlementEndsAtMs] = useState(0);
  const [settlementRevealedHoles, setSettlementRevealedHoles] = useState<Record<number, [string, string]> | undefined>(undefined);
  const [settlementWinnerHandNames, setSettlementWinnerHandNames] = useState<Record<number, string> | undefined>(undefined);
  type AllInLockState = {
    handId: string;
    eligiblePlayers: Array<{ seat: number; name: string }>;
    maxRunCountAllowed: 3;
    submittedPlayerIds: number[];
    underdogSeat: number | null;
    targetRunCount: 1 | 2 | 3 | null;
    equities?: Array<{ seat: number; winRate: number; tieRate: number; equityRate: number }>;
  };
  const [allInLock, setAllInLock] = useState<AllInLockState | null>(null);
  const [myRunPreference, setMyRunPreference] = useState<1 | 2 | 3 | null>(null);
  type BoardRevealState = {
    street: string;
    equities: Array<{ seat: number; winRate: number; tieRate: number; equityRate: number }>;
    hints?: Array<{ seat: number; label: string }>;
  };
  const [boardReveal, setBoardReveal] = useState<BoardRevealState | null>(null);
  const [showHandConfirm, setShowHandConfirm] = useState(false);
  const [lastActionBySeat, setLastActionBySeat] = useState<Record<number, { action: string; amount: number }>>({});

  const [lobbyRooms, setLobbyRooms] = useState<LobbyRoomSummary[]>([]);
  const [createSettings, setCreateSettings] = useState<CreateRoomSettings>({
    sb: 1, bb: 3, buyInMin: 40, buyInMax: 300, maxPlayers: 6, visibility: "public",
  });
  const [displayBB, setDisplayBB] = useState(false);
  const [showBuyInModal, setShowBuyInModal] = useState(false);
  const [pendingSitSeat, setPendingSitSeat] = useState(1);
  const [buyInAmount, setBuyInAmount] = useState(10000);
  const [currentRoomCode, setCurrentRoomCode] = useState("");
  const [currentRoomName, setCurrentRoomName] = useState("");
  const [clubRoomHintCode, setClubRoomHintCode] = useState("");
  type RecentNonClubTable = { tableId: string; roomCode: string; roomName?: string };
  const recentNonClubTableRef = useRef<RecentNonClubTable | null>(null);

  type AppView = "lobby" | "table" | "profile" | "history" | "clubs" | "training" | "preflop";
  const view = useMemo<AppView>(() => {
    const path = location.pathname;
    if (path === "/" || path.startsWith("/lobby")) return "lobby";
    if (path.startsWith("/table")) return "table";
    if (path.startsWith("/history")) return "history";
    if (path.startsWith("/clubs")) return "clubs";
    if (path.startsWith("/training")) return "training";
    if (path.startsWith("/preflop")) return "preflop";
    if (path.startsWith("/profile")) return "profile";
    return "lobby";
  }, [location.pathname]);
  const canAccessClubs = Boolean(authSession && !authSession.isGuest);

  const goToTable = useCallback((nextTableId?: string, replace = false) => {
    const resolvedTableId = (nextTableId ?? tableId ?? "table-1").trim() || "table-1";
    navigate(`/table/${encodeURIComponent(resolvedTableId)}`, { replace });
  }, [navigate, tableId]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(RECENT_NON_CLUB_TABLE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as RecentNonClubTable;
      if (!parsed?.tableId || !parsed?.roomCode) return;
      recentNonClubTableRef.current = parsed;
    } catch {
      // ignore malformed cache
    }
  }, []);

  useEffect(() => {
    if (location.pathname === "/") {
      navigate("/lobby", { replace: true });
      return;
    }

    if (location.pathname.startsWith("/clubs/")) {
      navigate("/clubs", { replace: true });
      return;
    }

    if (location.pathname === "/table") {
      goToTable(undefined, true);
      return;
    }

    const tableMatch = location.pathname.match(/^\/table\/([^/]+)$/);
    if (tableMatch) {
      const routeTableId = decodeURIComponent(tableMatch[1]);
      // Guard: skip sync if pathnameRef already points away (user is leaving the table
      // but React Router hasn't propagated the navigation yet)
      if (routeTableId && routeTableId !== tableId && pathnameRef.current.startsWith("/table")) {
        setTableId(routeTableId);
      }
      return;
    }

    const supportedPaths = ["/lobby", "/history", "/profile", "/training", "/preflop"];
    if (!(location.pathname.startsWith("/clubs") || location.pathname.startsWith("/history/") || supportedPaths.includes(location.pathname))) {
      navigate("/lobby", { replace: true });
    }
  }, [goToTable, location.pathname, navigate, tableId]);

  /* ── Clubs state ── */
  const [clubList, setClubList] = useState<ClubListItem[]>([]);
  const [clubDetail, setClubDetail] = useState<ClubDetailPayload | null>(null);
  const [selectedClubId, setSelectedClubId] = useState<string>("");
  const [clubsLoading, setClubsLoading] = useState(false);
  const selectedClubIdRef = useRef(selectedClubId);
  useEffect(() => { selectedClubIdRef.current = selectedClubId; }, [selectedClubId]);

  /* ── Room management state ── */
  const [roomState, setRoomState] = useState<RoomFullState | null>(null);
  const [timerState, setTimerState] = useState<TimerState | null>(null);
  const [roomLog, setRoomLog] = useState<RoomLogEntry[]>([]);
  const [kicked, setKicked] = useState<{ reason: string; banned: boolean } | null>(null);
  const [settingsTab, setSettingsTab] = useState<SettingsTab>("game");
  const [seatRequests, setSeatRequests] = useState<Array<{ orderId: string; userId: string; userName: string; seat: number; buyIn: number }>>([]);
  const [showRoomLog, setShowRoomLog] = useState(false);
  const [showSessionStats, setShowSessionStats] = useState(false);
  const [showInGameHistory, setShowInGameHistory] = useState(false);
  const [sessionStatsData, setSessionStatsData] = useState<SessionStatsEntry[]>([]);
  const [showRebuyModal, setShowRebuyModal] = useState(false);
  const [rebuyAmount, setRebuyAmount] = useState(0);
  type RebuyNotification = { orderId: string; userId: string; userName: string; seat: number; amount: number };
  const [rebuyRequests, setRebuyRequests] = useState<RebuyNotification[]>([]);
  const [rejoinStackInfo, setRejoinStackInfo] = useState<{ tableId: string; stack: number | null; loading: boolean } | null>(null);
  const [revealedZoom, setRevealedZoom] = useState<{ seat: number; name: string; cards: [string, string]; handName?: string } | null>(null);
  const [socketConnected, setSocketConnected] = useState(false);
  const [socketReconnecting, setSocketReconnecting] = useState(false);
  const [disconnectedSeats, setDisconnectedSeats] = useState<Map<number, { userId: string; graceSeconds: number; disconnectedAt: number }>>(new Map());
  const [supabaseEnabled, setSupabaseEnabled] = useState(true);
  const [showGtoSidebar, setShowGtoSidebar] = useState(() => {
    try { return localStorage.getItem("cardpilot_show_gto") !== "false"; } catch { return true; }
  });
  const [showMobileGto, setShowMobileGto] = useState(false);

  /* ── UI Redesign state ── */
  const [preAction, setPreAction] = useState<PreAction | null>(null);
  const [showFoldConfirm, setShowFoldConfirm] = useState(false);
  const [suppressFoldConfirm, setSuppressFoldConfirm] = useState(false);

  /* ── Overlay Manager (single source of truth for stacking) ── */
  const overlays = useOverlayManager();
  const showOptionsDrawer = overlays.isOpen("optionsDrawer");
  const setShowOptionsDrawer = useCallback((open: boolean) => {
    if (open) overlays.open("optionsDrawer");
    else overlays.close("optionsDrawer");
  }, [overlays]);
  const showSettings = overlays.isOpen("roomSettings");
  const setShowSettings = useCallback((open: boolean) => {
    if (open) overlays.open("roomSettings"); // auto-closes drawer (lower priority)
    else overlays.close("roomSettings");
  }, [overlays]);

  /* ── Hand-end linger state (non-blocking winner feedback) ── */
  const [lingerActive, setLingerActive] = useState(false);
  const [lingerWinnerSeats, setLingerWinnerSeats] = useState<Set<number>>(new Set());
  const [lingerSeatDeltas, setLingerSeatDeltas] = useState<Record<number, number>>({});
  const [lingerIsAllIn, setLingerIsAllIn] = useState(false);
  const [showHandSummaryDrawer, setShowHandSummaryDrawer] = useState(false);
  const lingerTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSettlementRef = useRef<SettlementResult | null>(null);

  /* ── Post-hand show & 7-2 bounty state ── */
  const [postHandShowAvailable, setPostHandShowAvailable] = useState(false);
  const [sevenTwoBountyPrompt, setSevenTwoBountyPrompt] = useState<{
    bountyPerPlayer: number; totalBounty: number;
  } | null>(null);
  const [sevenTwoBountyResult, setSevenTwoBountyResult] = useState<SevenTwoBountyInfo | null>(null);
  const [sevenTwoRevealActive, setSevenTwoRevealActive] = useState<SevenTwoBountyInfo | null>(null);
  const [postHandRevealedCards, setPostHandRevealedCards] = useState<Record<number, [string, string]>>({});

  /* ── Bomb pot overlay state ── */
  const [bombPotOverlayActive, setBombPotOverlayActive] = useState<{ anteAmount: number } | null>(null);
  const lastBombPotOverlayHandIdRef = useRef<string | null>(null);

  /* ── Table theme ── */
  type TableTheme = "green" | "blue";
  const [tableTheme, setTableTheme] = useState<TableTheme>(() => {
    try { const v = localStorage.getItem("cardpilot_table_theme"); return v === "blue" ? "blue" : "green"; } catch { return "green"; }
  });
  const [soundMuted, setSoundMuted] = useState(() => {
    try { return localStorage.getItem(SOUND_PREF_KEY) === "true"; } catch { return false; }
  });
  const [holeDealEpoch, setHoleDealEpoch] = useState(0);
  const [potPulseActive, setPotPulseActive] = useState(false);
  const [winnerFlareActive, setWinnerFlareActive] = useState(false);
  const [winnerSeatPulse, setWinnerSeatPulse] = useState<number | null>(null);
  const [resultRunFocus, setResultRunFocus] = useState<{ run: 1 | 2 | 3; seats: number[] } | null>(null);
  const [boardRevealTokens, setBoardRevealTokens] = useState<Record<string, number>>({});

  /* ── Chip animation state ── */
  const [chipAnimSpeed, setChipAnimSpeed] = useState<AnimationSpeed>(loadAnimationSpeed);
  const tableContainerRef = useRef<HTMLDivElement>(null);
  // tableStageRef: the scale-stage div — observed by useTableScale to compute canvas scale
  const tableStageRef = useRef<HTMLDivElement>(null);
  const potRef = useRef<HTMLDivElement>(null);
  const seatRefs = useRef<Record<number, HTMLElement | null>>({});
  const prevHoleSigRef = useRef("");
  const prevBoardTotalRef = useRef(0);
  const prevBoardHandRef = useRef<string | null>(null);
  const prevBoardRevealHandRef = useRef<string | null>(null);
  const prevBoardSlotKeysRef = useRef<Set<string>>(new Set());
  const boardRevealSeqRef = useRef(0);
  const lastChipSfxTransferIdRef = useRef<string | null>(null);
  const potPulseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const winnerFlareTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const winnerSeatPulseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const resultRunTimersRef = useRef<Array<ReturnType<typeof setTimeout>>>([]);
  // Re-create anchors object on each render so driver reads live DOM refs
  const chipAnchorsLive: ChipAnimationAnchors = {
    container: tableContainerRef.current,
    pot: potRef.current,
    seats: seatRefs.current,
  };
  const { transfers: chipTransfers, removeTransfer: removeChipTransfer, onSnapshot: chipOnSnapshot, onSettlement: chipOnSettlement, onBountyClaim: chipOnBountyClaim } = useChipAnimationDriver(chipAnchorsLive, chipAnimSpeed);
  const chipOnSnapshotRef = useRef(chipOnSnapshot);
  chipOnSnapshotRef.current = chipOnSnapshot;
  const chipOnSettlementRef = useRef(chipOnSettlement);
  chipOnSettlementRef.current = chipOnSettlement;
  const chipOnBountyClaimRef = useRef(chipOnBountyClaim);
  chipOnBountyClaimRef.current = chipOnBountyClaim;

  /* ── Table canvas scale (prevents clipping by fitting canvas into available space) ── */
  /* Portrait mode uses PokerNow's 1/1.8 tall canvas (500×900); desktop uses 16:9 (1600×900) */
  const { scale: tableScale } = useTableScale({
    container: tableStageRef.current,
    baseWidth: isMobilePortrait ? 500 : 1600,
    baseHeight: 900,
    minScale: 0.28,
    maxScale: isMobilePortrait ? 1.0 : 1.4,
    enabled: view === "table",
  });

  /* ── GTO Audit state ── */
  const auditState = useAuditEvents(socket, authSession?.userId ?? null);

  /* ── Toast state (replaces permanent status bar) ── */
  const [toast, setToast] = useState<{ text: string; isError: boolean; id: number } | null>(null);
  const [toastExiting, setToastExiting] = useState(false);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((text: string) => {
    if (!text) return;
    const isError = /^error:/i.test(text) || /fail|denied|kicked|banned/i.test(text);
    // Clear previous dismiss timer
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToastExiting(false);
    setToast({ text, isError, id: Date.now() });
    // Auto-dismiss non-error toasts after 5s
    if (!isError) {
      toastTimerRef.current = setTimeout(() => {
        setToastExiting(true);
        setTimeout(() => setToast(null), 250);
      }, 5000);
    }
  }, []);

  const quickJoinNonClub = useCallback((trigger: "table_tab" | "quick_play") => {
    if (!socket) {
      showToast("Not connected to server");
      return;
    }

    const openRoom = lobbyRooms.find((r) => r.status === "OPEN" && r.playerCount < r.maxPlayers && !r.isClubTable);
    if (openRoom) {
      setClubRoomHintCode("");
      goToTable(openRoom.tableId || "table-1");
      socket.emit("join_room_code", { roomCode: openRoom.roomCode });
      showToast(trigger === "table_tab" ? "Joining quick table..." : "Quick-matching into room...");
      return;
    }

    debugLog("[CREATE_ROOM] table-tab fallback create_room", { clientUserId: authSession?.userId, settings: createSettings, trigger });
    goToTable("table-1");
    socket.emit("create_room", {
      roomName: `${createSettings.sb}/${createSettings.bb} NLH`,
      maxPlayers: createSettings.maxPlayers,
      smallBlind: createSettings.sb,
      bigBlind: createSettings.bb,
      buyInMin: createSettings.buyInMin,
      buyInMax: createSettings.buyInMax,
      visibility: "public",
    });
    showToast(trigger === "table_tab" ? "No recent table. Creating a new table..." : "Creating a new table...");
  }, [socket, lobbyRooms, createSettings, authSession?.userId, goToTable, showToast]);

  const setView = useCallback((nextView: AppView) => {
    debugLog("[nav] setView", { from: location.pathname, to: nextView, tableId, currentRoomCode });
    if (nextView === "table") {
      const isCurrentRoomClub = Boolean(currentRoomCode && currentRoomCode === clubRoomHintCode);
      const hasActiveNonClubRoom = Boolean(tableId && currentRoomCode && !isCurrentRoomClub);
      if (hasActiveNonClubRoom) {
        goToTable(tableId);
        return;
      }

      const recent = recentNonClubTableRef.current;
      if (recent?.roomCode) {
        setClubRoomHintCode("");
        goToTable(recent.tableId || "table-1");
        if (socket) {
          socket.emit("join_room_code", { roomCode: recent.roomCode });
          showToast(`Returning to ${recent.roomName || recent.roomCode}...`);
        }
        return;
      }

      quickJoinNonClub("table_tab");
      return;
    }
    if (nextView === "lobby") {
      navigate("/lobby");
      return;
    }
    navigate(`/${nextView}`);
  }, [goToTable, navigate, location.pathname, tableId, currentRoomCode, clubRoomHintCode, socket, quickJoinNonClub, showToast]);

  useEffect(() => {
    if (!tableId || !currentRoomCode) return;
    if (roomState?.isClubTable) return;
    const recent: RecentNonClubTable = {
      tableId,
      roomCode: currentRoomCode,
      roomName: currentRoomName || undefined,
    };
    recentNonClubTableRef.current = recent;
    try {
      localStorage.setItem(RECENT_NON_CLUB_TABLE_KEY, JSON.stringify(recent));
    } catch {
      // ignore storage failures
    }
  }, [tableId, currentRoomCode, currentRoomName, roomState?.isClubTable]);

  const playUiSfx = useCallback((kind: UiSfx) => {
    playUiSfxTone(kind, soundMuted);
  }, [soundMuted]);

  const clearLinger = useCallback(() => {
    if (lingerTimerRef.current) { clearTimeout(lingerTimerRef.current); lingerTimerRef.current = null; }
    resultRunTimersRef.current.forEach((timer) => clearTimeout(timer));
    resultRunTimersRef.current = [];
    setLingerActive(false);
    setLingerWinnerSeats(new Set());
    setLingerSeatDeltas({});
    setLingerIsAllIn(false);
    setResultRunFocus(null);
  }, []);

  useEffect(() => { preloadCardImages(); }, []);

  // Persist GTO sidebar preference
  useEffect(() => {
    try { localStorage.setItem("cardpilot_show_gto", String(showGtoSidebar)); } catch {}
  }, [showGtoSidebar]);
  useEffect(() => {
    try { localStorage.setItem(SOUND_PREF_KEY, String(soundMuted)); } catch {}
  }, [soundMuted]);

  /* ── Refs for latest state (avoid stale closures in socket handlers) ── */
  const seatRef = useRef(seat);
  const holeCardsRef = useRef(holeCards);
  const snapshotRef = useRef(snapshot);
  const tableIdRef = useRef(tableId);
  const pathnameRef = useRef(location.pathname);
  const currentRoomCodeRef = useRef(currentRoomCode);
  const currentRoomNameRef = useRef(currentRoomName);
  const roomStateRef = useRef(roomState);
  const latestSnapshotVersionRef = useRef(-1);
  const latestSnapshotHashRef = useRef("");
  const snapshotResyncTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const snapshotResyncReasonRef = useRef<string | null>(null);
  const lastSocketConnectErrorToastRef = useRef(0);

  const resetSnapshotSyncState = useCallback(() => {
    if (snapshotResyncTimerRef.current) {
      clearTimeout(snapshotResyncTimerRef.current);
      snapshotResyncTimerRef.current = null;
    }
    latestSnapshotVersionRef.current = -1;
    latestSnapshotHashRef.current = "";
    snapshotResyncReasonRef.current = null;
  }, []);

  const snapshotHash = useCallback((s: TableState) => {
    const board = s.board.join(",");
    const players = s.players
      .map((p) => `${p.seat}:${p.stack}:${p.inHand ? 1 : 0}:${p.folded ? 1 : 0}:${p.allIn ? 1 : 0}:${p.streetCommitted}`)
      .join("|");
    return [
      s.tableId,
      String(s.stateVersion),
      s.handId ?? "-",
      s.street,
      String(s.pot),
      String(s.currentBet),
      String(s.actorSeat ?? -1),
      board,
      players,
    ].join(";");
  }, []);

  useEffect(() => { setName(displayName); }, [displayName]);
  useEffect(() => { seatRef.current = seat; }, [seat]);
  useEffect(() => { holeCardsRef.current = holeCards; }, [holeCards]);
  useEffect(() => { snapshotRef.current = snapshot; }, [snapshot]);
  useEffect(() => { tableIdRef.current = tableId; }, [tableId]);
  useEffect(() => { pathnameRef.current = location.pathname; }, [location.pathname]);
  useEffect(() => { currentRoomCodeRef.current = currentRoomCode; }, [currentRoomCode]);
  useEffect(() => { roomStateRef.current = roomState; }, [roomState]);
  useEffect(() => { currentRoomNameRef.current = currentRoomName; }, [currentRoomName]);

  const totalVisibleBoardCards = useMemo(() => {
    if (!snapshot?.handId) return 0;
    if (snapshot.runoutBoards && snapshot.runoutBoards.length > 1) {
      return snapshot.runoutBoards.reduce((sum, row) => sum + row.length, 0);
    }
    return snapshot.board?.length ?? 0;
  }, [snapshot?.handId, snapshot?.board, snapshot?.runoutBoards]);

  const visibleBoardSlotKeys = useMemo(() => {
    if (!snapshot?.handId) return [] as string[];
    if (snapshot.runoutBoards && snapshot.runoutBoards.length > 1) {
      return snapshot.runoutBoards.flatMap((row, runIdx) =>
        row.map((_, cardIdx) => `run-${runIdx}-card-${cardIdx}`)
      );
    }
    return (snapshot.board ?? []).map((_, cardIdx) => `main-${cardIdx}`);
  }, [snapshot?.handId, snapshot?.board, snapshot?.runoutBoards]);

  useEffect(() => {
    const handId = snapshot?.handId ?? "";
    const holeSig = handId ? `${handId}:${holeCards.join(",")}` : "";
    if (holeCards.length >= 2 && holeSig && holeSig !== prevHoleSigRef.current) {
      setHoleDealEpoch((v) => v + 1);
      playUiSfx("deal");
    }
    prevHoleSigRef.current = holeSig;
  }, [snapshot?.handId, holeCards, playUiSfx]);

  useEffect(() => {
    const handId = snapshot?.handId ?? null;
    if (!handId) {
      prevBoardHandRef.current = null;
      prevBoardTotalRef.current = 0;
      return;
    }
    if (prevBoardHandRef.current !== handId) {
      prevBoardHandRef.current = handId;
      prevBoardTotalRef.current = 0;
    }
    if (totalVisibleBoardCards > prevBoardTotalRef.current) {
      playUiSfx("flip");
    }
    prevBoardTotalRef.current = totalVisibleBoardCards;
  }, [snapshot?.handId, totalVisibleBoardCards, playUiSfx]);

  useEffect(() => {
    const handId = snapshot?.handId ?? null;
    if (!handId) {
      prevBoardRevealHandRef.current = null;
      prevBoardSlotKeysRef.current = new Set();
      setBoardRevealTokens({});
      return;
    }

    if (prevBoardRevealHandRef.current !== handId) {
      prevBoardRevealHandRef.current = handId;
      prevBoardSlotKeysRef.current = new Set();
      setBoardRevealTokens({});
    }

    const previous = prevBoardSlotKeysRef.current;
    const next = new Set(visibleBoardSlotKeys);
    const newlyVisible = visibleBoardSlotKeys.filter((slotKey) => !previous.has(slotKey));

    if (newlyVisible.length > 0) {
      setBoardRevealTokens((current) => {
        const updated = { ...current };
        for (const slotKey of newlyVisible) {
          boardRevealSeqRef.current += 1;
          updated[slotKey] = boardRevealSeqRef.current;
        }
        return updated;
      });
    }

    prevBoardSlotKeysRef.current = next;
  }, [snapshot?.handId, visibleBoardSlotKeys]);

  useEffect(() => {
    if (chipTransfers.length === 0) return;
    const latest = chipTransfers[chipTransfers.length - 1];
    if (latest.id === lastChipSfxTransferIdRef.current) return;
    lastChipSfxTransferIdRef.current = latest.id;

    if (latest.kind === "toWinner") {
      playUiSfx("chipWin");
      if (typeof latest.seat === "number" && latest.seat === seat) {
        haptic("win");
      }
      setWinnerFlareActive(true);
      if (winnerFlareTimerRef.current) clearTimeout(winnerFlareTimerRef.current);
      winnerFlareTimerRef.current = setTimeout(() => setWinnerFlareActive(false), 420);
      if (typeof latest.seat === "number") {
        setWinnerSeatPulse(latest.seat);
        if (winnerSeatPulseTimerRef.current) clearTimeout(winnerSeatPulseTimerRef.current);
        winnerSeatPulseTimerRef.current = setTimeout(() => setWinnerSeatPulse(null), 520);
      }
      return;
    }

    playUiSfx("chipBet");
    setPotPulseActive(true);
    if (potPulseTimerRef.current) clearTimeout(potPulseTimerRef.current);
    potPulseTimerRef.current = setTimeout(() => setPotPulseActive(false), 320);
  }, [chipTransfers, playUiSfx]);

  useEffect(() => {
    return () => {
      if (potPulseTimerRef.current) clearTimeout(potPulseTimerRef.current);
      if (winnerFlareTimerRef.current) clearTimeout(winnerFlareTimerRef.current);
      if (winnerSeatPulseTimerRef.current) clearTimeout(winnerSeatPulseTimerRef.current);
      resultRunTimersRef.current.forEach((timer) => clearTimeout(timer));
    };
  }, []);

  /* ── Client-side timer tick: smooth countdown using ref to avoid jumps ── */
  const [timerDisplay, setTimerDisplay] = useState<TimerState | null>(null);
  const timerRef = useRef<TimerState | null>(null);

  // Keep ref in sync with server updates (no interval recreation)
  // Replace server startedAt with client-local Date.now() to eliminate clock-skew jitter
  useEffect(() => {
    timerRef.current = timerState ? { ...timerState, startedAt: Date.now() } : null;
    if (!timerState) setTimerDisplay(null);
  }, [timerState]);

  // Single stable interval that reads from ref
  useEffect(() => {
    const interval = setInterval(() => {
      const ts = timerRef.current;
      if (!ts) { setTimerDisplay(null); return; }
      const elapsed = (Date.now() - ts.startedAt) / 1000;
      if (ts.usingTimeBank) {
        const bankLeft = Math.max(0, ts.timeBankRemaining - elapsed);
        setTimerDisplay({
          ...ts,
          remaining: 0,
          timeBankRemaining: bankLeft,
          usingTimeBank: true,
        });
      } else {
        const left = Math.max(0, ts.remaining - elapsed);
        setTimerDisplay({
          ...ts,
          remaining: left,
          usingTimeBank: left <= 0,
        });
      }
    }, 250);
    return () => clearInterval(interval);
  }, []); // ← stable: never recreated

  // Defensive clear: if no active hand/actor, hide local timer immediately
  useEffect(() => {
    if (!snapshot?.handId || snapshot.actorSeat == null) {
      setTimerState(null);
    }
  }, [snapshot?.handId, snapshot?.actorSeat]);

  /* ── Check existing session on mount (no network call) ── */
  useEffect(() => {
    let alive = true;
    getExistingSession()
      .then((session) => {
        if (!alive) return;
        if (session) {
          setAuthSession(session);
          setUserEmail(session.email ?? null);
          setDisplayName(session.displayName || session.email?.split("@")[0] || "Guest");
          showToast("Signed in");
        }
        setAuthLoading(false);
      })
      .catch(() => {
        if (!alive) return;
        setAuthLoading(false);
      });
    return () => { alive = false; };
  }, []);

  /* ── Listen for Supabase auth changes ── */
  useEffect(() => {
    if (!supabase) return;
    const { data } = supabase.auth.onAuthStateChange((_ev, session) => {
      if (session) {
        const meta = session.user.user_metadata;
        const dn = (typeof meta?.display_name === "string" && meta.display_name) || (typeof meta?.name === "string" && meta.name) || null;
        const isGuest = Boolean((session.user as { is_anonymous?: boolean }).is_anonymous);
        const s: AuthSession = {
          accessToken: session.access_token,
          userId: normalizeClientUserId(session.user.id, isGuest),
          email: session.user.email,
          displayName: dn,
          isGuest,
        };
        setAuthSession(s);
        setUserEmail(session.user.email ?? null);
        if (dn) setDisplayName(dn);
        resetInvalidRefreshGuard();
      } else {
        setAuthSession(null);
        setUserEmail(null);
      }
    });
    return () => { data.subscription.unsubscribe(); };
  }, []);

  const socketAuthUserId = authSession?.userId;
  const socketAuthTokenRef = useRef(authSession?.accessToken);
  useEffect(() => { socketAuthTokenRef.current = authSession?.accessToken; }, [authSession?.accessToken]);

  /* ── Socket: connect only when authenticated ── */
  useEffect(() => {
    if (!socketAuthUserId) return;
    debugLog("[SOCKET] Connecting with userId:", socketAuthUserId);
    // Use same-origin in dev (via Vite proxy) to avoid CORS; explicit URL in prod
    const serverUrl = import.meta.env.DEV ? window.location.origin : SERVER;
    const s = io(serverUrl, {
      auth: {
        accessToken: socketAuthTokenRef.current,
        displayName,
        userId: socketAuthUserId // Send userId to server
      }
    });
    setSocket(s);

    const requestSnapshotResync = (reason: string, requestedTableId?: string) => {
      const targetTableId = (requestedTableId ?? tableIdRef.current ?? "").trim();
      if (!targetTableId) return;
      if (snapshotResyncTimerRef.current) return;
      snapshotResyncReasonRef.current = reason;
      debugLog("[sync] schedule resync", { tableId: targetTableId, reason });
      snapshotResyncTimerRef.current = setTimeout(() => {
        snapshotResyncTimerRef.current = null;
        s.emit("request_table_snapshot", { tableId: targetTableId });
        s.emit("request_room_state", { tableId: targetTableId });
      }, 120);
    };

    const applyAuthoritativeSnapshot = (d: TableState, source: "table_snapshot" | "hand_ended"): boolean => {
      if (!d) return false;
      const activeTableId = (tableIdRef.current ?? "").trim();
      if (!activeTableId || d.tableId !== activeTableId) return false;
      const incomingVersion = Number.isFinite(d.stateVersion) ? d.stateVersion : 0;
      const currentVersion = latestSnapshotVersionRef.current;
      const incomingHash = snapshotHash(d);

      if (incomingVersion < currentVersion) {
        debugLog("[sync] drop stale snapshot", {
          source,
          tableId: d.tableId,
          incomingVersion,
          currentVersion,
          handId: d.handId,
          street: d.street,
        });
        requestSnapshotResync("stale_snapshot", d.tableId);
        return false;
      }

      if (incomingVersion === currentVersion) {
        const previousHash = latestSnapshotHashRef.current;
        if (previousHash && previousHash !== incomingHash) {
          debugLog("[sync] same-version payload mismatch", {
            source,
            tableId: d.tableId,
            stateVersion: incomingVersion,
            handId: d.handId,
            street: d.street,
          });
          requestSnapshotResync("same_version_mismatch", d.tableId);
        }
        return false;
      }

      if (currentVersion >= 0 && incomingVersion > currentVersion + 1) {
        debugLog("[sync] snapshot version gap detected", {
          source,
          tableId: d.tableId,
          incomingVersion,
          currentVersion,
          handId: d.handId,
          street: d.street,
        });
        requestSnapshotResync("version_gap", d.tableId);
      }

      latestSnapshotVersionRef.current = incomingVersion;
      latestSnapshotHashRef.current = incomingHash;
      snapshotResyncReasonRef.current = null;

      debugLog("[sync] apply snapshot", {
        source,
        tableId: d.tableId,
        stateVersion: d.stateVersion,
        handId: d.handId,
        street: d.street,
      });

      chipOnSnapshotRef.current(d);
      setSnapshot(d);

      // Bomb pot overlay: show dramatic announcement when a new bomb pot hand starts
      if (
        d.isBombPotHand &&
        d.handId &&
        d.handId !== lastBombPotOverlayHandIdRef.current
      ) {
        lastBombPotOverlayHandIdRef.current = d.handId;
        const anteAction = d.actions?.find((a: { type: string; amount: number }) => a.type === "ante");
        const anteAmount = anteAction?.amount ?? 0;
        setBombPotOverlayActive({ anteAmount });
      }

      if (d.winners) setWinners(d.winners);
      setAllInLock((prev) => (prev && prev.handId !== d.handId ? null : prev));
      if (!d.handId) {
        setMyRunPreference(null);
      }

      // Restore hero seat from snapshot (fixes desync after reconnect / page refresh)
      if (socketAuthUserId && d.players) {
        const heroPlayer = d.players.find((p) => p.userId === socketAuthUserId);
        if (heroPlayer && heroPlayer.seat !== seatRef.current) {
          setSeat(heroPlayer.seat);
        }
      }

      return true;
    };

    const handleReconnect = () => {
      const curPath = pathnameRef.current;
      let routeTableId = "";
      const tableRouteMatch = curPath.match(/^\/table\/([^/]+)$/);
      if (tableRouteMatch) {
        try {
          routeTableId = decodeURIComponent(tableRouteMatch[1]);
        } catch {
          routeTableId = "";
        }
      }
      const reconnectTableId = routeTableId || tableIdRef.current;
      const reconnectRoomCode = currentRoomCodeRef.current;
      const looksAuthoritativeTableId = /^tbl_[a-z0-9]+$/i.test(reconnectTableId);
      // Only resync if user is on table/lobby (not history/profile/etc.)
      const shouldResync = curPath === "/" || curPath.startsWith("/lobby") || curPath.startsWith("/table");
      if (shouldResync && reconnectRoomCode) {
        debugLog("[reconnect] resync room", { reconnectRoomCode, curPath });
        requestSnapshotResync("socket_reconnect", reconnectTableId);
      } else if (shouldResync && looksAuthoritativeTableId) {
        debugLog("[reconnect] resync table", { reconnectTableId, curPath });
        requestSnapshotResync("socket_reconnect_table_id", reconnectTableId);
      } else {
        debugLog("[reconnect] skipped resync, user on", curPath);
      }
      // Club re-fetch on reconnect is handled by the connect handler below
    };

    s.io.on("reconnect", handleReconnect);
    s.io.on("reconnect_attempt", () => {
      setSocketReconnecting(true);
    });
    s.on("connect_error", (err) => {
      setSocketConnected(false);
      setSocketReconnecting(true);

      const now = Date.now();
      if (now - lastSocketConnectErrorToastRef.current < 10_000) return;
      lastSocketConnectErrorToastRef.current = now;

      const message = err?.message ?? "unknown connection error";
      if (import.meta.env.DEV) {
        showToast("Server unavailable at http://127.0.0.1:4000. Start @cardpilot/game-server.");
        console.warn("[socket] connect_error", { message, target: "http://127.0.0.1:4000" });
      } else {
        showToast(`Connection failed: ${message}`);
      }
    });

    s.on("connect", () => {
      setSocketConnected(true);
      setSocketReconnecting(false);
      showToast("Connected");
      s.emit("request_lobby");
      if (!authSession?.isGuest) {
        setClubsLoading(true);
        s.emit("club_list_my_clubs");
        // Retry once after 5s if no response, then failsafe at 10s
        const retryTimer = setTimeout(() => {
          setClubsLoading((prev) => {
            if (prev) {
              debugLog("[clubs] no club_list response after 5s, retrying");
              s.emit("club_list_my_clubs");
            }
            return prev;
          });
        }, 5_000);
        const failsafeTimer = setTimeout(() => {
          setClubsLoading((prev) => {
            if (prev) console.warn("[clubs] clubsLoading failsafe timeout triggered");
            return false;
          });
        }, 10_000);
        // Clear timers when response arrives (via club_list or club_error handlers)
        const clearClubTimers = () => { clearTimeout(retryTimer); clearTimeout(failsafeTimer); };
        s.once("club_list", clearClubTimers);
        s.once("club_error", clearClubTimers);
      } else {
        setClubsLoading(false);
      }

      const curPath = pathnameRef.current;
      let routeTableId = "";
      const tableRouteMatch = curPath.match(/^\/table\/([^/]+)$/);
      if (tableRouteMatch) {
        try {
          routeTableId = decodeURIComponent(tableRouteMatch[1]);
        } catch {
          routeTableId = "";
        }
      }
      const activeTableId = routeTableId || tableIdRef.current;
      const roomCode = currentRoomCodeRef.current;
      const looksAuthoritativeTableId = /^tbl_[a-z0-9]+$/i.test(activeTableId);
      // Only rejoin room if user is on table or lobby page (not history/profile/etc.)
      const shouldRejoin = curPath === "/" || curPath.startsWith("/lobby") || curPath.startsWith("/table");
      if (shouldRejoin && roomCode) {
        debugLog("[connect] rejoining room", { roomCode, curPath });
        s.emit("join_room_code", { roomCode });
      } else if (shouldRejoin && looksAuthoritativeTableId) {
        debugLog("[connect] rejoining table", { activeTableId, curPath });
        s.emit("join_table", { tableId: activeTableId });
        requestSnapshotResync("socket_connect_table_id", activeTableId);
      } else if (roomCode || looksAuthoritativeTableId) {
        debugLog("[connect] skipped room rejoin, user on", curPath);
      }
    });
    s.on("connected", (d: { userId: string; displayName?: string; supabaseEnabled: boolean }) => {
      debugLog("[client] connected, server userId:", d.userId, "client userId:", socketAuthUserId);
      setSupabaseEnabled(d.supabaseEnabled);
      if (!d.supabaseEnabled) showToast("Connected (no Supabase persistence)");
    });
    s.on("disconnect", () => {
      setSocketConnected(false);
      setSocketReconnecting(true);
    });

    // ── Disconnect grace tracking ──
    s.on("player_disconnected", (d: { seat: number; userId: string; graceSeconds: number }) => {
      setDisconnectedSeats((prev) => {
        const next = new Map(prev);
        next.set(d.seat, { userId: d.userId, graceSeconds: d.graceSeconds, disconnectedAt: Date.now() });
        return next;
      });
    });
    s.on("player_reconnected", (d: { seat: number; userId: string }) => {
      setDisconnectedSeats((prev) => {
        const next = new Map(prev);
        next.delete(d.seat);
        return next;
      });
    });
    s.on("player_auto_sitout", (d: { seat: number; userId: string; reason: string }) => {
      setDisconnectedSeats((prev) => {
        const next = new Map(prev);
        next.delete(d.seat);
        return next;
      });
    });

    s.on("lobby_snapshot", (d: { rooms: LobbyRoomSummary[] }) => setLobbyRooms(d.rooms ?? []));
    s.on("room_created", (d: { tableId: string; roomCode: string; roomName: string }) => {
      resetSnapshotSyncState();
      tableIdRef.current = d.tableId;
      setTableId(d.tableId); setCurrentRoomCode(d.roomCode); setCurrentRoomName(d.roomName);
      showToast(`Room created: ${d.roomName} (${d.roomCode})`);
      // Only navigate to table if user is on lobby/table/root (not history/profile/etc.)
      const curPath = pathnameRef.current;
      if (curPath === "/" || curPath.startsWith("/lobby") || curPath.startsWith("/table")) {
        navigate(`/table/${encodeURIComponent(d.tableId)}`);
      } else {
        debugLog("[nav-guard] room_created: skipped navigate, user on", curPath);
      }
      s.emit("request_table_snapshot", { tableId: d.tableId });
      s.emit("request_room_state", { tableId: d.tableId });
      s.emit("request_session_stats", { tableId: d.tableId });
    });
    s.on("room_joined", (d: { tableId: string; roomCode: string; roomName: string }) => {
      resetSnapshotSyncState();
      tableIdRef.current = d.tableId;
      setTableId(d.tableId); setCurrentRoomCode(d.roomCode); setCurrentRoomName(d.roomName);
      // Only navigate to table if user is on lobby/table/root (not history/profile/etc.)
      const curPath = pathnameRef.current;
      if (curPath === "/" || curPath.startsWith("/lobby") || curPath.startsWith("/table")) {
        showToast(`Joined room: ${d.roomName} (${d.roomCode})`);
        navigate(`/table/${encodeURIComponent(d.tableId)}`);
      } else {
        debugLog("[nav-guard] room_joined: skipped navigate, user on", curPath);
      }
      s.emit("request_table_snapshot", { tableId: d.tableId });
      s.emit("request_room_state", { tableId: d.tableId });
      s.emit("request_session_stats", { tableId: d.tableId });
    });
    s.on("table_snapshot", (d: TableState) => {
      applyAuthoritativeSnapshot(d, "table_snapshot");
    });
    s.on("left_table", (d: { tableId: string }) => {
      const activeTableId = (tableIdRef.current ?? "").trim();
      if (!activeTableId || d.tableId !== activeTableId) return;
      resetSnapshotSyncState();
      // Clear refs synchronously to prevent reconnection handlers from auto-rejoining
      tableIdRef.current = "";
      currentRoomCodeRef.current = "";
      currentRoomNameRef.current = "";
      pathnameRef.current = "/lobby";
      setTableId("");
      setClubRoomHintCode("");
      setCurrentRoomCode(""); setCurrentRoomName("");
      setRoomState(null);
      setSnapshot(null);
      setHoleCards([]);
      setSeatRequests([]);
      overlays.closeAll();
      setShowRoomLog(false);
      setShowSessionStats(false);
      setKicked(null);
      setWinners(null);
      setSettlement(null);
      setSettlementCountdown(0);
      setAllInLock(null);
      setMyRunPreference(null);
      setAdvice(null);
      setDeviation(null);
      const curPath = pathnameRef.current;
      if (curPath.startsWith("/table")) {
        navigate("/lobby");
      }
      showToast("Left table");
      s.emit("request_lobby");
    });
    s.on("hole_cards", (d: { cards: string[]; seat: number }) => {
      setHoleCards(d.cards);
      setSeat(d.seat);
    });
    s.on("hand_started", () => {
      setActionPending(false);
      setAdvice(null); setDeviation(null); setWinners(null); setAllInLock(null); setMyRunPreference(null); setBoardReveal(null); setHoleCards([]);
      setSettlement(null); setSettlementCountdown(0); setSettlementEndsAtMs(0);
      setSettlementRevealedHoles(undefined); setSettlementWinnerHandNames(undefined);
      clearLinger(); setShowHandSummaryDrawer(false);
      setShowFoldConfirm(false);
      setPreAction(null);
      setLastActionBySeat({});
      setDisconnectedSeats(new Map());
      setPostHandShowAvailable(false);
      setSevenTwoBountyPrompt(null);
      setSevenTwoBountyResult(null);
      setPostHandRevealedCards({});
    });
    s.on("board_reveal", (d: {
      handId: string;
      street: string;
      newCards: string[];
      board: string[];
      equities: Array<{ seat: number; winRate: number; tieRate: number; equityRate: number }>;
      hints?: Array<{ seat: number; label: string }>;
    }) => {
      setBoardReveal({ street: d.street, equities: d.equities, hints: d.hints });
    });
    s.on("run_twice_reveal", (d: {
      handId: string;
      street: string;
      phase?: "top" | "both";
      run1: { newCards: string[]; board: string[] };
      run2?: { newCards: string[]; board: string[] };
      equities?: Array<{ seat: number; winRate: number; tieRate: number; equityRate: number }>;
      hints?: Array<{ seat: number; label: string }>;
    }) => {
      setBoardReveal((prev: BoardRevealState | null) => ({
        street: d.street,
        equities: d.equities ?? prev?.equities ?? [],
        hints: d.hints ?? prev?.hints,
      }));
      setSnapshot((prev) => {
        if (!prev || prev.handId !== d.handId) return prev;
        // Sequential reveal: "top" phase shows run1 only, "both" shows both boards
        if (d.phase === "top") {
          // Show top board; keep previous run2 board or empty
          const prevRun2 = prev.runoutBoards?.[1] ?? d.run2?.board ?? [];
          return { ...prev, runoutBoards: [d.run1.board, prevRun2] };
        }
        // "both" or legacy (no phase): show both boards
        return { ...prev, runoutBoards: [d.run1.board, d.run2?.board ?? []] };
      });
    });
    s.on("allin_locked", (d: {
      handId: string;
      eligiblePlayers: Array<{ seat: number; name: string }>;
      maxRunCountAllowed: 3;
      submittedPlayerIds?: number[];
      underdogSeat?: number;
      targetRunCount?: 1 | 2 | 3 | null;
      equities?: Array<{ seat: number; winRate: number; tieRate: number; equityRate: number }>;
    }) => {
      const liveHandId = snapshotRef.current?.handId;
      if (liveHandId && d.handId !== liveHandId) return;
      setAllInLock({
        handId: d.handId,
        eligiblePlayers: d.eligiblePlayers ?? [],
        maxRunCountAllowed: 3,
        submittedPlayerIds: d.submittedPlayerIds ?? [],
        underdogSeat: d.underdogSeat ?? null,
        targetRunCount: d.targetRunCount ?? null,
        equities: d.equities,
      });
      if (seatRef.current != null && !(d.submittedPlayerIds ?? []).includes(seatRef.current)) {
        setMyRunPreference(null);
      }
    });
    s.on("run_count_confirmed", (d: { handId: string; runCount: 1 | 2 | 3 }) => {
      const liveHandId = snapshotRef.current?.handId;
      if (liveHandId && d.handId !== liveHandId) return;
      setMyRunPreference(null);
    });
    s.on("run_count_chosen", () => {
      setMyRunPreference(null);
    });
    s.on("reveal_hole_cards", (d: { handId: string; revealed: Record<number, [string, string]> }) => {
      setSnapshot((prev) => {
        if (!prev || prev.handId !== d.handId) return prev;
        return { ...prev, revealedHoles: { ...(prev.revealedHoles ?? {}), ...(d.revealed ?? {}) } };
      });
    });
    s.on("post_hand_reveal", (d: { tableId: string; seat: number; cards: [string, string] }) => {
      setPostHandRevealedCards((prev) => ({ ...prev, [d.seat]: d.cards }));
      // Auto-clear after 8s so revealed cards stay visible long enough
      setTimeout(() => {
        setPostHandRevealedCards((prev: Record<number, [string, string]>) => {
          const next = { ...prev };
          delete next[d.seat];
          return next;
        });
      }, 8000);
    });
    s.on("seven_two_bounty_claimed", (d: { tableId: string; handId: string; bounty: SevenTwoBountyInfo }) => {
      setSevenTwoBountyResult(d.bounty);
      setSevenTwoBountyPrompt(null);
      const winnerName = snapshotRef.current?.players.find((p) => p.seat === d.bounty.winnerSeat)?.name ?? `Seat ${d.bounty.winnerSeat}`;
      showToast(`7-2 Bounty! ${winnerName} collected +${d.bounty.totalBounty}`);
      // Trigger 7-2 reveal overlay + bounty chip animations + SFX
      setSevenTwoRevealActive(d.bounty);
      chipOnBountyClaimRef.current(d.bounty);
      playUiSfx("bounty72");
      haptic("bounty");
    });
    s.on("reveal_board_card", (d: {
      handId: string;
      runIndex: 1 | 2 | 3;
      card: string;
      boardSizeNow: number;
      board: string[];
      street: string;
      equities?: Array<{ seat: number; winRate: number; tieRate: number; equityRate: number }>;
      hints?: Array<{ seat: number; label: string }>;
    }) => {
      setBoardReveal((prev: BoardRevealState | null) => ({
        street: `R${d.runIndex} ${d.street}`,
        equities: d.equities ?? prev?.equities ?? [],
        hints: d.hints ?? prev?.hints,
      }));
      setSnapshot((prev) => {
        if (!prev || prev.handId !== d.handId) return prev;
        const currentBoards = prev.runoutBoards ? prev.runoutBoards.map((board) => [...board]) : [];
        while (currentBoards.length < d.runIndex) currentBoards.push([]);
        currentBoards[d.runIndex - 1] = [...d.board];
        return {
          ...prev,
          board: d.runIndex === 1 ? [...d.board] : prev.board,
          runoutBoards: currentBoards,
        };
      });
    });
    s.on("showdown_results", (d: {
      handId: string;
      totalPayouts: Record<number, number>;
    }) => {
      if (snapshotRef.current?.handId && d.handId !== snapshotRef.current.handId) return;
      const winnersFromPayouts = Object.entries(d.totalPayouts ?? {})
        .map(([seatNum, amount]) => ({ seat: Number(seatNum), amount: Number(amount) || 0 }))
        .filter((winner) => winner.amount > 0);
      if (winnersFromPayouts.length > 0) {
        setWinners(winnersFromPayouts);
      }
    });
    s.on("stood_up", (d: { seat: number; reason: string }) => {
      showToast(d.reason);
    });
    s.on("action_applied", (d: { seat: number; action: string; amount: number; pot: number; auto?: boolean }) => {
      if (d.seat === seatRef.current) setActionPending(false);
      setLastActionBySeat((prev) => ({
        ...prev,
        [d.seat]: { action: d.action, amount: d.amount ?? 0 },
      }));
      // Show action confirmation for the local player
      if (d.seat === seatRef.current && !d.auto) {
        const actionLabel = d.action === "fold" ? "Fold" : d.action === "check" ? "Check" : d.action === "call" ? `Call ${d.amount.toLocaleString()}` : d.action === "raise" ? `Raise to ${d.amount.toLocaleString()}` : d.action === "all_in" ? "All-In" : d.action;
        showToast(`You: ${actionLabel} · Pot: ${d.pot.toLocaleString()}`);
      }
    });
    s.on("advice_payload", (d: AdvicePayload) => setAdvice(d));
    s.on("advice_deviation", (d: AdvicePayload & { playerAction: string }) => {
      setDeviation({ deviation: d.deviation ?? 0, playerAction: d.playerAction });
    });
    s.on("hand_ended", (d: { handId?: string; finalState?: TableState; winners?: Array<{ seat: number; amount: number; handName?: string }>; settlement?: SettlementResult }) => {
      setActionPending(false);
      setMyRunPreference(null);
      setBoardReveal(null);
      setPreAction(null);
      if (d.winners) setWinners(d.winners);
      if (d.finalState) {
        applyAuthoritativeSnapshot(d.finalState, "hand_ended");
      }

      // Chip animation: animate pot→winner payouts
      if (d.settlement) chipOnSettlementRef.current(d.settlement);

      // Non-blocking hand-end feedback: seat highlights + delta tags + toast
      if (d.settlement) {
        lastSettlementRef.current = d.settlement;

        // Capture revealed hole cards from the final table state (for drawer access)
        const fs = d.finalState;
        if (fs?.revealedHoles) {
          const holes: Record<number, [string, string]> = {};
          for (const [s, cards] of Object.entries(fs.revealedHoles)) {
            if (Array.isArray(cards) && cards.length === 2) holes[Number(s)] = cards as [string, string];
          }
          setSettlementRevealedHoles(Object.keys(holes).length > 0 ? holes : undefined);
        } else {
          setSettlementRevealedHoles(undefined);
        }
        if (fs?.winners) {
          const names: Record<number, string> = {};
          for (const w of fs.winners) {
            if (w.handName) names[w.seat] = w.handName;
          }
          setSettlementWinnerHandNames(Object.keys(names).length > 0 ? names : undefined);
        } else {
          setSettlementWinnerHandNames(undefined);
        }

        // Compute per-seat net deltas from ledger
        const deltas: Record<number, number> = {};
        for (const entry of d.settlement.ledger) {
          deltas[entry.seat] = entry.net;
        }
        setLingerSeatDeltas(deltas);

        // Identify winner seats
        const winSeats = new Set(d.settlement.winnersByRun.flatMap((r) => r.winners.map((w) => w.seat)));
        setLingerWinnerSeats(winSeats);

        // Detect all-in showdown (any player was all-in)
        const wasAllIn = d.finalState?.players.some((p) => p.allIn) ?? false;
        setLingerIsAllIn(wasAllIn);

        // Activate linger (non-blocking seat highlights + deltas)
        setLingerActive(true);

        // Explicit per-run result focus animation (clearer for multi-run showdowns)
        resultRunTimersRef.current.forEach((timer) => clearTimeout(timer));
        resultRunTimersRef.current = [];
        const runs = d.settlement.winnersByRun ?? [];
        if (runs.length > 0) {
          runs.forEach((run, idx) => {
            const timer = setTimeout(() => {
              const seatsForRun = run.winners.map((winner) => winner.seat);
              setResultRunFocus({ run: run.run, seats: seatsForRun });
              if (seatsForRun.length > 0) {
                setWinnerSeatPulse(seatsForRun[0]);
                if (winnerSeatPulseTimerRef.current) clearTimeout(winnerSeatPulseTimerRef.current);
                winnerSeatPulseTimerRef.current = setTimeout(() => setWinnerSeatPulse(null), 520);
              }
            }, idx * 720);
            resultRunTimersRef.current.push(timer);
          });
          const clearTimer = setTimeout(() => setResultRunFocus(null), runs.length * 720 + 520);
          resultRunTimersRef.current.push(clearTimer);
        }

        // Toast: lightweight winner summary
        const winnerNames = d.settlement.winnersByRun.flatMap((r) => r.winners).map((w) => {
          const p = d.finalState?.players.find((pl) => pl.seat === w.seat);
          return `${p?.name ?? `Seat ${w.seat}`} +${w.amount.toLocaleString()}`;
        });
        if (winnerNames.length > 0) {
          showToast(winnerNames.length === 1 ? `Winner: ${winnerNames[0]}` : `Winners: ${winnerNames.join(", ")}`);
        }

        // Auto-advance timer: 4s normal, 6s all-in
        const lingerMs = wasAllIn ? 6000 : 4000;
        if (lingerTimerRef.current) clearTimeout(lingerTimerRef.current);
        lingerTimerRef.current = setTimeout(() => {
          setLingerActive(false);
          setLingerWinnerSeats(new Set());
          setLingerSeatDeltas({});
          setLingerIsAllIn(false);
          setResultRunFocus(null);
          setWinners(null);
          setSettlement(null);
        }, lingerMs);

        // 7-2 bounty: if auto-applied at showdown, display result immediately
        if (d.settlement.sevenTwoBounty) {
          setSevenTwoBountyResult(d.settlement.sevenTwoBounty);
          setSevenTwoRevealActive(d.settlement.sevenTwoBounty);
          chipOnBountyClaimRef.current(d.settlement.sevenTwoBounty);
        } else {
          // Hero won with unrevealed 7-2 → server has pending claim, show prompt
          const heroSeatNow = seatRef.current;
          const heroWon = winSeats.has(heroSeatNow);
          const cards = holeCardsRef.current;
          if (heroWon && cards.length >= 2) {
            const r0 = cards[0][0], r1 = cards[1][0];
            const heroHas72 = (r0 === "7" && r1 === "2") || (r0 === "2" && r1 === "7");
            const bountyAmount = roomStateRef.current?.settings.sevenTwoBounty ?? 0;
            if (heroHas72 && bountyAmount > 0) {
              const dealtIn = d.finalState?.players.filter((p) => p.inHand && p.seat !== heroSeatNow).length ?? 0;
              setSevenTwoBountyPrompt({ bountyPerPlayer: bountyAmount, totalBounty: bountyAmount * dealtIn });
            }
          }
        }
      }

      // Enable post-hand show if hero had hole cards
      if (holeCardsRef.current.length >= 2) {
        setPostHandShowAvailable(true);
        setPostHandRevealedCards({});
      }

      // Save to local hand history (localStorage fallback)
      try {
        const st = d.finalState ?? snapshotRef.current;
        const cards = holeCardsRef.current;
        const heroSeat = seatRef.current;
        if (st && d.settlement) {
          const gameType = st.gameType === "omaha" ? "PLO" : "NLH";
          const actionRecords: HandActionRecord[] = st.actions.map((a) => ({
            seat: a.seat,
            street: a.street ?? st.street,
            type: a.type,
            amount: a.amount ?? 0,
          }));
          const playerNames: Record<number, string> = {};
          const showdownHands: Record<number, [string, string] | "mucked"> = {};
          for (const p of st.players) {
            playerNames[p.seat] = p.name;
            const revealed = st.revealedHoles?.[p.seat] as [string, string] | undefined;
            if (revealed) showdownHands[p.seat] = revealed;
            else if (st.muckedSeats?.includes(p.seat)) showdownHands[p.seat] = "mucked";
          }

          if (cards.length >= 2) {
            // Hero was seated — full detail record
            const heroPos = st.positions?.[heroSeat] ?? "?";
            const heroLedger = d.settlement.ledger.find((e) => e.seat === heroSeat);
            const didWinAnyRun = d.settlement.winnersByRun.some((run) => run.winners.some((winner) => winner.seat === heroSeat));
            const netByPosition: Record<string, number> = {};
            for (const entry of d.settlement.ledger) {
              const pos = st.positions?.[entry.seat] ?? `Seat ${entry.seat}`;
              netByPosition[pos] = (netByPosition[pos] ?? 0) + entry.net;
            }
            saveHand({
              gameType,
              stakes: `${st.smallBlind}/${st.bigBlind}`,
              tableSize: st.players.length,
              position: heroPos,
              heroCards: [...cards],
              startingHandBucket: classifyStartingHandBucket(cards, gameType),
              board: st.board,
              runoutBoards: st.runoutBoards,
              doubleBoardPayouts: d.settlement.doubleBoardPayouts
                ?? (d.settlement.runCount > 1 && d.settlement.winnersByRun.length > 1
                  ? d.settlement.winnersByRun.map((r) => ({
                      run: r.run as 1 | 2 | 3,
                      board: [...r.board],
                      winners: r.winners.map((w) => ({ seat: w.seat, amount: w.amount, handName: w.handName })),
                    }))
                  : undefined),
              actions: actionRecords,
              potSize: d.settlement.totalPot,
              stackSize: heroLedger?.endStack ?? 0,
              result: heroLedger?.net ?? 0,
              netByPosition,
              isBombPotHand: st.isBombPotHand,
              isDoubleBoardHand: st.isDoubleBoardHand,
              tags: autoTag(actionRecords),
              roomCode: currentRoomCodeRef.current || undefined,
              roomName: currentRoomNameRef.current || undefined,
              tableId: tableId || undefined,
              handId: d.handId || undefined,
              endedAt: new Date().toISOString(),
              heroSeat,
              heroName: name || displayName || "Hero",
              smallBlind: st.smallBlind,
              bigBlind: st.bigBlind,
              playersCount: st.players.length,
              didWinAnyRun,
              showdownHands,
              playerNames,
            });
          } else {
            // Spectator — save summary record without hero cards
            saveHand({
              gameType,
              stakes: `${st.smallBlind}/${st.bigBlind}`,
              tableSize: st.players.length,
              position: "OBS",
              heroCards: [],
              board: st.board,
              runoutBoards: st.runoutBoards,
              actions: actionRecords,
              potSize: d.settlement.totalPot,
              stackSize: 0,
              result: 0,
              isBombPotHand: st.isBombPotHand,
              isDoubleBoardHand: st.isDoubleBoardHand,
              tags: autoTag(actionRecords),
              roomCode: currentRoomCodeRef.current || undefined,
              roomName: currentRoomNameRef.current || undefined,
              tableId: tableId || undefined,
              handId: d.handId || undefined,
              endedAt: new Date().toISOString(),
              smallBlind: st.smallBlind,
              bigBlind: st.bigBlind,
              playersCount: st.players.length,
              didWinAnyRun: false,
              showdownHands,
              playerNames,
            });
          }
        }
      } catch (err) {
        debugLog("[local-history] failed to save hand:", err);
      }

      setTimeout(() => setHoleCards([]), 800);
    });
    s.on("error_event", (d: { message: string }) => {
      setActionPending(false);
      showToast(`Error: ${d.message}`);
    });
    s.on("session_stats", (d: { tableId: string; entries: Array<{ seat: number | null; userId: string; name: string; totalBuyIn: number; totalCashOut: number; currentStack: number; net: number; handsPlayed: number; status: string }> }) => {
      setSessionStatsData(d.entries);
    });
    s.on("rejoin_stack_info", (d: { tableId: string; stack: number | null }) => {
      setRejoinStackInfo({ tableId: d.tableId, stack: d.stack, loading: false });
    });
    s.on("deposit_request_pending", (d: { orderId: string; userId: string; userName: string; seat: number; amount: number }) => {
      setRebuyRequests((prev) => [...prev, d]);
    });

    // Room management events
    s.on("room_state_update", (d: RoomFullState) => {
      if (!d) return;
      debugLog("[client] room_state_update identity check", {
        clientUserId: socketAuthUserId,
        ownerId: d.ownership?.ownerId,
        isHost: d.ownership?.ownerId === socketAuthUserId,
      });
      setRoomState(d);
      if (d.log) setRoomLog(d.log);
    });
    s.on("timer_update", (d: TimerState) => setTimerState(d));
    s.on("room_log", (d: RoomLogEntry) => setRoomLog((prev) => [...prev.slice(-99), d]));
    s.on("kicked", (d: { reason: string; banned: boolean }) => {
      resetSnapshotSyncState();
      // Clear refs synchronously to prevent reconnection handlers from auto-rejoining
      tableIdRef.current = "";
      currentRoomCodeRef.current = "";
      currentRoomNameRef.current = "";
      pathnameRef.current = "/lobby";
      setKicked(d);
      setView("lobby");
      setTableId("");
      setClubRoomHintCode("");
      setCurrentRoomCode(""); setCurrentRoomName("");
      setRoomState(null);
      overlays.closeAll();
      showToast(`You were ${d.banned ? "banned" : "kicked"}: ${d.reason}`);
    });
    s.on("room_closed", (d?: { reason?: string }) => {
      resetSnapshotSyncState();
      setActionPending(false);
      // Clear refs synchronously to prevent reconnection handlers from auto-rejoining
      tableIdRef.current = "";
      currentRoomCodeRef.current = "";
      currentRoomNameRef.current = "";
      pathnameRef.current = "/lobby";
      setView("lobby");
      setTableId("");
      setClubRoomHintCode("");
      setCurrentRoomCode(""); setCurrentRoomName("");
      setRoomState(null);
      setTimerState(null);
      setSnapshot(null);
      setHoleCards([]);
      setSeatRequests([]);
      setWinners(null);
      setAllInLock(null);
      setMyRunPreference(null);
      setAdvice(null);
      setDeviation(null);
      setBoardReveal(null);
      overlays.closeAll(); // clears optionsDrawer + roomSettings + any other overlay
      setShowRoomLog(false);
      setShowSessionStats(false);
      clearLinger(); setShowHandSummaryDrawer(false);
      showToast(d?.reason ?? "Room closed. Returned to lobby.");
    });
    s.on("hand_aborted", (d: { reason: string }) => {
      setActionPending(false);
      setHoleCards([]);
      setWinners(null);
      setSettlement(null);
      setSettlementCountdown(0);
      setSettlementEndsAtMs(0);
      setSettlementRevealedHoles(undefined);
      setSettlementWinnerHandNames(undefined);
      setAllInLock(null);
      setMyRunPreference(null);
      setAdvice(null);
      setDeviation(null);
      setBoardReveal(null);
      clearLinger(); setShowHandSummaryDrawer(false);
      showToast(d.reason);
    });
    s.on("system_message", (d: { message: string }) => showToast(d.message));
    s.on("bomb_pot_queued", (d: { queuedBy: string }) => {
      showToast(`\u{1F4A3} Bomb Pot queued for next hand by ${d.queuedBy}`);
    });
    s.on("settings_updated", (d: { applied: Record<string, unknown>; deferred: Record<string, unknown> }) => {
      const keys = [...Object.keys(d.applied), ...Object.keys(d.deferred)];
      if (keys.length > 0) showToast(`Settings updated: ${keys.join(", ")}`);
    });
    s.on("think_extension_result", (d: { addedSeconds: number; remainingUses: number }) => {
      showToast(`Extended +${d.addedSeconds}s · Remaining this hour: ${d.remainingUses}`);
    });

    // Seat request flow
    s.on("seat_request_sent", (d: { orderId: string; seat: number }) => {
      showToast(`Seat request sent for seat #${d.seat} — waiting for host approval…`);
    });
    s.on("seat_approved", (d: { seat: number; buyIn: number }) => {
      setSeat(d.seat);
      showToast(`Seat #${d.seat} approved! You're in with ${d.buyIn.toLocaleString()}`);
    });
    s.on("seat_rejected", (d: { seat: number; reason: string }) => {
      showToast(`Seat request rejected: ${d.reason}`);
    });
    s.on("seat_request_pending", (d: { orderId: string; userId: string; userName: string; seat: number; buyIn: number }) => {
      debugLog("[SEAT_REQUEST] Received pending request:", d);
      setSeatRequests((prev) => [...prev.filter(r => r.orderId !== d.orderId), { orderId: d.orderId, userId: d.userId, userName: d.userName, seat: d.seat, buyIn: d.buyIn }]);
    });

    // ── Club events ──
    s.on("club_list", (d: { clubs: ClubListItem[] }) => {
      setClubList(d.clubs ?? []);
      setClubsLoading(false);
    });
    s.on("club_detail", (d: ClubDetailPayload) => {
      setClubDetail(d);
    });
    s.on("club_created", (d: { club: unknown }) => {
      showToast("Club created!");
      s.emit("club_list_my_clubs");
    });
    s.on("club_updated", () => {
      showToast("Club updated");
    });
    s.on("club_join_result", (d: { clubId: string; status: string; message: string }) => {
      showToast(d.message);
      if (d.status === "joined") s.emit("club_list_my_clubs");
    });
    s.on("club_member_update", () => {
      // Refresh detail if viewing a club
      const cid = selectedClubIdRef.current;
      if (cid) s.emit("club_get_detail", { clubId: cid });
    });
    s.on("club_table_created", (d: { clubId: string; table: unknown }) => {
      showToast("Club table created!");
    });
    s.on("club_table_updated", (d: { clubId: string }) => {
      const cid = selectedClubIdRef.current;
      if (cid && cid === d.clubId) {
        s.emit("club_get_detail", { clubId: cid });
      }
    });
    // Wallet error feedback: all wallet operation failures (admin_deposit, admin_adjust,
    // balance_get, buy-in insufficient funds, etc.) are surfaced through club_error.
    // The error_event handler covers game-level buy-in failures, and seat_rejected covers
    // seat request denials. All error paths already show user-facing toasts.
    s.on("club_error", (d: { code: string; message: string }) => {
      setClubsLoading(false);
      const isWalletError = d.code.startsWith("WALLET_") || d.code.startsWith("wallet_") || d.code === "INSUFFICIENT_FUNDS";
      showToast(isWalletError ? `Wallet error: ${d.message}` : `Error: ${d.message}`);
    });
    return () => {
      s.io.off("reconnect", handleReconnect);
      if (snapshotResyncTimerRef.current) {
        clearTimeout(snapshotResyncTimerRef.current);
        snapshotResyncTimerRef.current = null;
      }
      s.disconnect();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps -- socketAuthTokenRef is a ref, token updates are handled below without reconnecting
  }, [socketAuthUserId, displayName, navigate, resetSnapshotSyncState, snapshotHash, authSession?.isGuest]);

  // Update socket auth credentials on token refresh without tearing down the connection
  useEffect(() => {
    if (!socket || !authSession?.accessToken) return;
    (socket as unknown as { auth: Record<string, unknown> }).auth = {
      ...(socket as unknown as { auth: Record<string, unknown> }).auth,
      accessToken: authSession.accessToken,
    };
  }, [socket, authSession?.accessToken]);

  const canAct = useMemo(() => snapshot?.actorSeat === seat && snapshot?.handId, [snapshot, seat]);

  const derivedActionBar = useMemo(
    () => deriveActionBar(snapshot, authSession?.userId ?? null),
    [snapshot, authSession?.userId]
  );
  const derivedPreActionUI = useMemo(
    () => derivePreActionUI(snapshot, authSession?.userId ?? null),
    [snapshot, authSession?.userId]
  );

  const setPreActionType = useCallback((actionType: PreActionType | null) => {
    const uid = authSession?.userId;
    const hid = snapshotRef.current?.handId;
    if (!actionType) {
      setPreAction(null);
      return;
    }
    if (!uid || !hid) return;
    if (!derivedPreActionUI.enabled) return;

    setPreAction({ handId: hid, playerId: uid, actionType, createdAt: Date.now() });
  }, [authSession?.userId, derivedPreActionUI.enabled]);

  const attemptFold = useCallback(() => {
    const hid = snapshotRef.current?.handId;
    const legal = snapshotRef.current?.legalActions;
    if (!hid || actionPending) return;
    if (shouldConfirmUnnecessaryFold(legal ?? null, suppressFoldConfirm)) {
      setShowFoldConfirm(true);
      return;
    }
    setActionPending(true);
    setPreAction(null);
    socket?.emit("action_submit", { tableId, handId: hid, action: "fold" });
  }, [actionPending, socket, tableId, suppressFoldConfirm]);
  // Reset raiseTo to minRaise whenever legal actions change
  useEffect(() => {
    const minR = snapshot?.legalActions?.minRaise;
    if (minR && minR > 0) setRaiseTo(minR);
  }, [snapshot?.legalActions?.minRaise]);

  // Reset action pending when turn/street/hand changes
  useEffect(() => { setActionPending(false); }, [snapshot?.actorSeat, snapshot?.street, snapshot?.handId]);

  const wasMyTurnRef = useRef(false);
  useEffect(() => {
    const requiredHole = snapshot?.holeCardCount ?? 2;
    const isPlayersTurn = Boolean(snapshot?.handId && snapshot?.actorSeat === seat);
    const becameMyTurn = isPlayersTurn && !wasMyTurnRef.current;
    wasMyTurnRef.current = isPlayersTurn;
    if (!becameMyTurn) return;
    playUiSfx("turn");

    const decision = shouldAutoFirePreAction({
      preAction,
      gameState: snapshot,
      playerId: authSession?.userId ?? null,
      holeCardsCount: holeCards.length,
      isPlayersTurn,
      actionPending,
    });

    if (!preAction) return;
    if (!snapshot?.handId || preAction.handId !== snapshot.handId) {
      setPreAction(null);
      return;
    }

    if (!decision) {
      setPreAction(null);
      return;
    }

    if (holeCards.length < requiredHole) return;

    setActionPending(true);
    setPreAction(null);
    socket?.emit("action_submit", { tableId, handId: snapshot.handId, action: decision.action, amount: decision.amount });
  }, [snapshot?.handId, snapshot?.actorSeat, snapshot?.street, snapshot?.showdownPhase, seat, preAction, actionPending, socket, tableId, authSession?.userId, holeCards.length, holeCards, playUiSfx]);

  useEffect(() => {
    if (!preAction) return;
    if (!snapshot?.handId || preAction.handId !== snapshot.handId) {
      setPreAction(null);
      return;
    }
    if (!derivedPreActionUI.enabled) {
      setPreAction(null);
      return;
    }
  }, [preAction, snapshot?.handId, derivedPreActionUI.enabled]);
  const isConnected = socketConnected;
  const connectionLabel = isConnected ? "Online" : socketReconnecting ? "Reconnecting..." : "Offline";
  const connectionColor = isConnected ? "emerald" : socketReconnecting ? "yellow" : "red";
  const isHost = useMemo(() => roomState?.ownership.ownerId === authSession?.userId, [roomState, authSession]);
  const isCoHost = useMemo(() => roomState?.ownership.coHostIds.includes(authSession?.userId ?? "") ?? false, [roomState, authSession]);
  const isHostOrCoHost = isHost || isCoHost;
  const isClubTable = Boolean(roomState?.isClubTable);
  const isClubTableContext = isClubTable || Boolean(currentRoomCode && currentRoomCode === clubRoomHintCode);
  const userRole = useUserRole(roomState, authSession?.userId, seat);
  const handInProgress = useMemo(
    () => (roomState?.status === "PLAYING") || Boolean(snapshot?.handId && (snapshot.actorSeat != null || snapshot.showdownPhase === "decision")),
    [roomState?.status, snapshot?.handId, snapshot?.actorSeat, snapshot?.showdownPhase]
  );
  const minPlayersToStart = useMemo(
    () => Math.max(2, roomState?.settings.minPlayersToStart ?? 2),
    [roomState?.settings.minPlayersToStart]
  );
  const eligiblePlayerCount = useMemo(
    () => snapshot?.players.filter((p: TablePlayer) => p.status === "active" && p.stack > 0).length ?? 0,
    [snapshot?.players]
  );
  const dealDisabledReason = useMemo(() => {
    if (!isConnected) return "Server disconnected";
    if (!isHostOrCoHost && seat == null) return "Sit down to deal";
    if (roomState?.status === "PAUSED") return "Game is paused";
    if (handInProgress) return "Current hand is still in progress";
    if (eligiblePlayerCount < minPlayersToStart) {
      return `Need at least ${minPlayersToStart} players with chips (currently ${eligiblePlayerCount})`;
    }
    return null;
  }, [isConnected, isHostOrCoHost, seat, roomState?.status, handInProgress, eligiblePlayerCount, minPlayersToStart]);
  const myOwnedRoomCode = useMemo(
    () => (roomState?.ownership.ownerId === authSession?.userId ? currentRoomCode : ""),
    [roomState, authSession, currentRoomCode]
  );
  const myThinkExtensionUsage = useMemo(() => {
    const uid = authSession?.userId;
    if (!uid) return null;
    return roomState?.thinkExtensionUsageByUser?.[uid] ?? null;
  }, [roomState, authSession]);
  const thinkExtensionRemainingUses = myThinkExtensionUsage?.remaining ?? roomState?.settings.thinkExtensionQuotaPerHour ?? 0;
  const myPlayer = useMemo(
    () => snapshot?.players.find((p) => p.seat === seat) ?? null,
    [snapshot?.players, seat]
  );
  const myRevealedCards = (snapshot?.revealedHoles?.[seat] as [string, string] | undefined) ?? undefined;
  const myIsMucked = snapshot?.muckedSeats?.includes(seat) ?? false;
  const myIsWinner = snapshot?.winners?.some((w) => w.seat === seat) ?? false;
  const isMyShowdownDecision = useMemo(() => {
    if (snapshot?.showdownPhase !== "decision") return false;
    if (!myPlayer) return false;
    return myPlayer.inHand && !myPlayer.folded;
  }, [snapshot?.showdownPhase, myPlayer]);
  const canVoluntaryShow = useMemo(() => {
    if (!snapshot?.handId || !myPlayer || holeCards.length !== 2) return false;
    if (snapshot.showdownPhase === "decision" && myPlayer.inHand && !myPlayer.folded) return true;
    if (roomState?.settings.allowShowAfterFold !== true) return false;
    if (roomState?.status !== "PLAYING") return false;
    return myPlayer.folded;
  }, [snapshot?.handId, snapshot?.showdownPhase, myPlayer, holeCards.length, roomState?.settings.allowShowAfterFold, roomState?.status]);
  const allInLockForCurrentHand = allInLock && snapshot?.handId === allInLock.handId ? allInLock : null;
  const resolvedSeat = useMemo(() => {
    const uid = authSession?.userId;
    if (uid && snapshot?.players) {
      const me = snapshot.players.find((player) => player.userId === uid);
      if (me) return me.seat;
    }
    return seat;
  }, [authSession?.userId, snapshot?.players, seat]);
  const resolvedPlayer = useMemo(
    () => snapshot?.players.find((player) => player.seat === resolvedSeat) ?? null,
    [snapshot?.players, resolvedSeat]
  );
  const underdogSeat = allInLockForCurrentHand?.underdogSeat ?? null;
  const underdogUserId = useMemo(
    () => (underdogSeat != null ? snapshot?.players.find((player) => player.seat === underdogSeat)?.userId ?? null : null),
    [snapshot?.players, underdogSeat]
  );
  const isUnderdogUser = Boolean(
    underdogSeat != null
    && (
      (resolvedSeat != null && resolvedSeat === underdogSeat)
      || (authSession?.userId && underdogUserId === authSession.userId)
    )
  );
  const myRunSeat = (isUnderdogUser && underdogSeat != null) ? underdogSeat : resolvedSeat;
  const runChoiceEligible = Boolean(
    (allInLockForCurrentHand?.eligiblePlayers.some((player) => player.seat === resolvedSeat)
      && (!resolvedPlayer || (resolvedPlayer.inHand && !resolvedPlayer.folded)))
    || isUnderdogUser
  );
  const myIsUnderdog = isUnderdogUser;
  const underdogWinRate = useMemo(() => {
    if (!allInLockForCurrentHand?.equities || underdogSeat == null) return null;
    const entry = allInLockForCurrentHand.equities.find((e) => e.seat === underdogSeat);
    return entry ? Math.round(entry.equityRate * 1000) / 10 : null;
  }, [allInLockForCurrentHand?.equities, underdogSeat]);
  const runTarget = allInLockForCurrentHand?.targetRunCount ?? null;
  const runTargetNeedsApproval = Boolean(runTarget && runTarget > 1);
  const runApprovalEligible = Boolean(runChoiceEligible && !myIsUnderdog && runTargetNeedsApproval);
  const submittedRunSeats = allInLockForCurrentHand?.submittedPlayerIds ?? [];
  const hasSubmittedRunPreference = myRunSeat != null && submittedRunSeats.includes(myRunSeat);
  const pendingRunPlayers = (allInLockForCurrentHand?.eligiblePlayers ?? []).filter((player) => !submittedRunSeats.includes(player.seat));
  const runChoiceWaitingCount = pendingRunPlayers.length;
  const showInitialStartPrompt = Boolean(
    !isClubTableContext
    && roomState
    && roomState.hasStartedHand === false
    && !handInProgress
  );
  useEffect(() => {
    if (!canVoluntaryShow) setShowHandConfirm(false);
  }, [canVoluntaryShow]);
  useEffect(() => {
    if (!isHostOrCoHost || isClubTable) {
      setRebuyRequests([]);
      return;
    }
    const pending = snapshot?.pendingRebuys ?? [];
    setRebuyRequests(
      pending.map((deposit) => ({
        orderId: deposit.orderId,
        userId: deposit.userId,
        userName: deposit.userName,
        seat: deposit.seat,
        amount: deposit.amount,
      }))
    );
  }, [isHostOrCoHost, isClubTable, snapshot?.pendingRebuys]);
  useEffect(() => {
    if (!isClubTable) return;
    setSeatRequests([]);
    setRebuyRequests([]);
  }, [isClubTable]);
  useEffect(() => {
    if (!socket || !snapshot?.handId) return;
    if (!isMyShowdownDecision) return;
    if (myIsWinner) return;
    if (myRevealedCards || myIsMucked) return;
    if ((roomState?.settings.autoMuckLosingHands ?? true) !== true) return;

    const timeout = setTimeout(() => {
      socket.emit("muck_hand", { tableId, handId: snapshot.handId, seat });
    }, 4000);
    return () => clearTimeout(timeout);
  }, [
    socket,
    tableId,
    seat,
    snapshot?.handId,
    isMyShowdownDecision,
    myIsWinner,
    myRevealedCards,
    myIsMucked,
    roomState?.settings.autoMuckLosingHands,
  ]);
  // Skip interaction: Space/Enter during linger period immediately clears it
  useEffect(() => {
    if (!lingerActive) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === " " || e.key === "Enter" || e.key === "Escape") {
        e.preventDefault();
        clearLinger();
        setWinners(null);
        setSettlement(null);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [lingerActive, clearLinger]);

  // Escape key closes Room Settings modal (highest priority overlay)
  useEffect(() => {
    if (!showSettings) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        setShowSettings(false);
      }
    };
    window.addEventListener("keydown", handler, true); // capture phase
    return () => window.removeEventListener("keydown", handler, true);
  }, [showSettings, setShowSettings]);

  useEffect(() => {
    setLastActionBySeat({});
  }, [snapshot?.handId]);

  const seatPositions = useMemo(() => {
    const n = roomState?.settings.maxPlayers ?? 6;
    return isMobilePortrait ? getPortraitSeatLayout(n) : getSeatLayout(n);
  }, [roomState?.settings.maxPlayers, isMobilePortrait]);
  const heroSeatForLayout = useMemo(() => {
    if (!snapshot?.players?.some((p: TablePlayer) => p.seat === seat)) return null;
    return seat;
  }, [snapshot?.players, seat]);
  const potNumbers = useMemo(() => {
    const totalPot = snapshot?.pot ?? 0;
    const currentStreetCommitted = snapshot?.players?.reduce((sum: number, player: TablePlayer) => sum + (player.streetCommitted ?? 0), 0) ?? 0;
    return {
      totalPot,
      pushedPot: Math.max(0, totalPot - currentStreetCommitted),
    };
  }, [snapshot?.pot, snapshot?.players]);

  const handleSeatClick = useCallback((seatNum: number) => {
    if (socket && tableId) {
      setRejoinStackInfo({ tableId, stack: null, loading: true });
      socket.emit("request_rejoin_stack", { tableId });
    }
    const settings = roomState?.settings;
    const min = settings?.buyInMin ?? 40;
    const max = settings?.buyInMax ?? 300;
    const step = Math.max(100, settings?.bigBlind ?? 100);
    // Sticky rebuy: load last buy-in for this room, fallback to midpoint
    let initial: number | null = null;
    try {
      if (currentRoomCode) {
        const saved = localStorage.getItem(`cardpilot_buyin_${currentRoomCode}`);
        if (saved) { const n = Number(saved); if (n >= min && n <= max) initial = n; }
      }
    } catch { /* ignore */ }
    const raw = initial ?? (min + max) / 2;
    const snapped = Math.round(raw / step) * step;
    setBuyInAmount(Math.min(max, Math.max(min, snapped)));
    setPendingSitSeat(seatNum);
    setShowBuyInModal(true);
  }, [roomState?.settings, currentRoomCode, socket, tableId]);

  const seatElements = useMemo(() => {
    const maxP = roomState?.settings.maxPlayers ?? 6;
    return Array.from({ length: maxP }, (_, i) => i + 1).map((seatNum) => {
      const visualSeatNum = heroSeatForLayout == null
        ? seatNum
        : mapSeatToVisualIndex(seatNum, heroSeatForLayout, maxP);
      const pos = seatPositions[visualSeatNum];
      const player = snapshot?.players.find((p) => p.seat === seatNum);
      const isActor = snapshot?.actorSeat === seatNum;
      const isMe = seatNum === seat;
      const isOwner = player && roomState?.ownership.ownerId === player.userId;
      const isCo = player && roomState?.ownership.coHostIds.includes(player.userId);
      const seatTimer = isActor && timerDisplay?.seat === seatNum ? timerDisplay : null;
      const posLabel = snapshot?.positions?.[seatNum] ?? "";
      const isButton = snapshot?.buttonSeat === seatNum && !!snapshot?.handId;
      const equity = boardReveal?.equities.find((e) => e.seat === seatNum)
        ?? allInLockForCurrentHand?.equities?.find((e) => e.seat === seatNum)
        ?? null;
      const isAllInLocked = Boolean(allInLockForCurrentHand);
      const handHint = boardReveal?.hints?.find((h) => h.seat === seatNum)?.label;
      const isPendingLeave = snapshot?.pendingStandUp?.includes(seatNum) ?? false;
      const revealedCards = snapshot?.revealedHoles?.[seatNum] as [string, string] | undefined;
      const isMucked = snapshot?.muckedSeats?.includes(seatNum) ?? false;
      // Get hand name from winners, or compute it for non-winners with revealed cards
      const winnerHandName = snapshot?.winners?.find((w) => w.seat === seatNum)?.handName;
      const computedHandName = revealedCards && snapshot?.board && snapshot.board.length >= 3 && !winnerHandName
        ? describeHandStrength(revealedCards, snapshot.board)
        : undefined;
      const revealedHandName = winnerHandName ?? computedHandName;
      return (
        <div key={seatNum} ref={(el) => { seatRefs.current[seatNum] = el; }} className="absolute -translate-x-1/2 -translate-y-1/2" style={{ top: pos.top, left: pos.left }}>
          <SeatChip player={player} seatNum={seatNum} isActor={isActor} isMe={isMe}
            isOwner={!!isOwner} isCoHost={!!isCo} isBot={player?.isBot} timer={seatTimer} timerTotal={roomState?.settings.actionTimerSeconds ?? 15}
            posLabel={posLabel} isButton={isButton} displayBB={displayBB} bigBlind={snapshot?.bigBlind ?? 3}
            lastAction={lastActionBySeat[seatNum] ?? null}
            equity={equity} isAllInLocked={isAllInLocked} handHint={handHint} pendingLeave={isPendingLeave} revealedCards={revealedCards} revealedHandName={revealedHandName} isMucked={isMucked}
            isWinner={lingerActive && lingerWinnerSeats.has(seatNum)}
            isWinnerPulse={winnerSeatPulse === seatNum}
            netDelta={lingerActive ? lingerSeatDeltas[seatNum] : undefined}
            isDisconnected={disconnectedSeats.has(seatNum)}
            onClickRevealed={revealedCards ? () => {
              setRevealedZoom({
                seat: seatNum,
                name: player?.name ?? `Seat ${seatNum}`,
                cards: revealedCards,
                handName: revealedHandName ?? undefined,
              });
            } : undefined}
            onClickEmpty={handleSeatClick} />
        </div>
      );
    });
  }, [snapshot, seat, roomState, timerDisplay, boardReveal, displayBB, seatPositions, heroSeatForLayout, handleSeatClick, lastActionBySeat, lingerActive, lingerWinnerSeats, lingerSeatDeltas, winnerSeatPulse, allInLockForCurrentHand]);

  // Debug seat requests
  useEffect(() => {
    debugLog("[SEAT_REQUESTS] Current requests:", seatRequests.length, seatRequests);
    debugLog("[SEAT_REQUESTS] isHostOrCoHost:", isHostOrCoHost, "isHost:", isHost, "isCoHost:", isCoHost);
  }, [seatRequests, isHostOrCoHost, isHost, isCoHost]);

  function copyCode() {
    if (!currentRoomCode) return;
    void navigator.clipboard.writeText(currentRoomCode);
    showToast(`Copied room code: ${currentRoomCode}`);
  }

  function leaveRoom() {
    debugLog("[nav] leaveRoom()", { tableId, currentRoomCode, seat, pathname: location.pathname });
    if (socket && tableId) {
      socket.emit("stand_up", { tableId, seat });
      socket.emit("leave_table", { tableId });
    }
    resetSnapshotSyncState();
    // Clear refs synchronously to prevent reconnection handlers from auto-rejoining
    tableIdRef.current = "";
    currentRoomCodeRef.current = "";
    currentRoomNameRef.current = "";
    pathnameRef.current = "/lobby";
    setTableId("");
    setClubRoomHintCode("");
    setCurrentRoomCode(""); setCurrentRoomName("");
    setRoomState(null);
    setSnapshot(null);
    setHoleCards([]);
    setSeatRequests([]);
    overlays.closeAll();
    setShowRoomLog(false);
    setShowSessionStats(false);
    setKicked(null);
    setWinners(null);
    setSettlement(null);
    setSettlementCountdown(0);
    setAllInLock(null);
    setMyRunPreference(null);
    setAdvice(null);
    setDeviation(null);
    setView("lobby");
    navigate("/lobby");
    showToast("Left room");
    socket?.emit("request_lobby");
  }

  async function handleLogout() {
    resetSnapshotSyncState();
    overlays.closeAll();
    socket?.disconnect();
    setSocket(null);
    await signOut();
    setAuthSession(null);
    setUserEmail(null);
    setDisplayName("Guest");
    setSnapshot(null);
    setHoleCards([]);
    setView("lobby");
    showToast("Signed out");
  }

  const handleAuthSuccess = useCallback((s: AuthSession) => {
    setAuthSession(s);
    setUserEmail(s.email ?? null);
    const dn = s.displayName || s.email?.split("@")[0] || "Guest";
    setDisplayName(dn);
    setName(dn);
    showToast("Signed in");
  }, [showToast]);

  /* ── Onboarding state ── */
  const [showOnboarding, setShowOnboarding] = useState(() => {
    try { return !localStorage.getItem("cardpilot_onboarded"); } catch { return true; }
  });

  function completeOnboarding() {
    try { localStorage.setItem("cardpilot_onboarded", "1"); } catch { /* ignore */ }
    setShowOnboarding(false);
  }

  /* ═══════════════ AUTH SCREEN ═══════════════ */
  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-2xl font-extrabold text-slate-900 shadow-lg mx-auto mb-4">C</div>
          <p className="text-slate-400 text-sm">Loading...</p>
        </div>
      </div>
    );
  }

  if (!authSession) {
    return (
      <AuthScreen
        onAuth={handleAuthSuccess}
        disableGuest={location.pathname.startsWith("/clubs")}
        gateMessage={location.pathname.startsWith("/clubs") ? "Club access requires a logged-in account." : undefined}
      />
    );
  }

  if (view === "clubs" && !canAccessClubs) {
    return (
      <AuthScreen
        onAuth={handleAuthSuccess}
        disableGuest
        gateMessage="Club access requires a logged-in account."
      />
    );
  }

  /* ═══════════════════ RENDER ═══════════════════ */
  const PAGE_TITLES: Record<string, string> = {
    lobby: "Lobby", table: "Table", profile: "Profile",
    history: "History", clubs: "Clubs", training: "Training",
  };
  const mobilePageTitle = PAGE_TITLES[view] ?? "CardPilot";

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* ── Onboarding Modal ── */}
      {showOnboarding && authSession && (
        <OnboardingModal onComplete={completeOnboarding} />
      )}

      {/* ── DESKTOP NAV — code-gated: NOT rendered in TABLE view ── */}
      {view !== "table" ? (
        <header className="flex items-center justify-between px-4 py-1.5 border-b border-white/5 shrink-0 cp-desktop-only">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-sm font-extrabold text-slate-900 shadow-lg">C</div>
            <h1 className="text-base font-bold tracking-tight text-white">Card<span className="text-amber-400">Pilot</span></h1>
          </div>
          <nav className="flex items-center gap-1 bg-white/5 rounded-xl p-1">
            {(["lobby", "clubs", "table", "history", "training", "profile"] as const).map((v) => (
              <button key={v} onClick={() => {
                setView(v);
                if (v === "clubs" && socket && canAccessClubs) { socket.emit("club_list_my_clubs"); }
              }}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${view === v ? "bg-white/10 text-white shadow-sm" : "text-slate-400 hover:text-slate-200"}`}>
                {v === "lobby" ? "Lobby" : v === "clubs" ? "Clubs" : v === "table" ? "Table" : v === "history" ? "History" : v === "training" ? "Training" : "Profile"}
              </button>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-[10px] font-medium ${isConnected ? "bg-emerald-500/10 text-emerald-400" : socketReconnecting ? "bg-yellow-500/10 text-yellow-400 animate-pulse" : "bg-red-500/10 text-red-400 animate-pulse"}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? "bg-emerald-400" : socketReconnecting ? "bg-yellow-400" : "bg-red-400"}`} />
              {connectionLabel}
            </span>
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-[11px] font-bold text-white uppercase">{displayName[0]}</div>
            <span className="text-xs text-slate-200 font-medium max-w-[140px] truncate">Hi, {displayName}</span>
            <button onClick={handleLogout} className="text-xs text-slate-500 hover:text-red-400 transition-colors px-2 py-1 rounded-lg hover:bg-white/5">Sign Out</button>
            <span className="text-[8px] text-slate-600 font-mono" title={`Build: ${BUILD_TIME}`}>{APP_VERSION}{NETLIFY_COMMIT_REF ? `@${NETLIFY_COMMIT_REF.slice(0, 7)}` : ""}{NETLIFY_DEPLOY_ID ? `#${NETLIFY_DEPLOY_ID.slice(0, 6)}` : ""}</span>
          </div>
        </header>
      ) : !isMobilePortrait ? (
        /* ── Compact TableTopBar for TABLE view (desktop + mobile landscape) ── */
        <header className="cp-table-topbar">
          <div className="flex items-center gap-2">
            <button onClick={leaveRoom} className="cp-table-exit-btn" title="Exit to Lobby">← Lobby</button>
            <div className="w-px h-5 bg-white/10" />
            {currentRoomName && <span className="text-xs font-semibold text-white truncate max-w-[180px]">{currentRoomName}</span>}
            {currentRoomCode && (
              <button onClick={copyCode} className="text-[10px] font-mono text-amber-400 tracking-wider hover:text-amber-300 transition-colors" title="Copy room code">{currentRoomCode} 📋</button>
            )}
          </div>
          <div className="flex items-center gap-2">
            {roomState && <span className="text-[10px] text-slate-500">{roomState.settings.smallBlind}/{roomState.settings.bigBlind} · {roomState.settings.maxPlayers}-max</span>}
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-medium ${isConnected ? "bg-emerald-500/10 text-emerald-400" : socketReconnecting ? "bg-yellow-500/10 text-yellow-400 animate-pulse" : "bg-red-500/10 text-red-400 animate-pulse"}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? "bg-emerald-400" : socketReconnecting ? "bg-yellow-400" : "bg-red-400"}`} />
              {connectionLabel}
            </span>
            <button onClick={() => setShowInGameHistory(true)} className="text-sm text-slate-400 hover:text-white px-1.5 py-1 rounded-lg hover:bg-white/5 transition-colors" title="Hand History">📜</button>
            <button onClick={() => setShowOptionsDrawer(!showOptionsDrawer)} className="text-sm text-slate-400 hover:text-white px-1.5 py-1 rounded-lg hover:bg-white/5 transition-colors" title="Options">☰</button>
          </div>
        </header>
      ) : null}

      {/* ── MOBILE NAV: Top Bar (shown on mobile, NEVER in TABLE view) ── */}
      {isMobile && view !== "table" && (
        <MobileTopBar
          title={mobilePageTitle}
          isConnected={isConnected}
          onMenuOpen={() => setShowMoreMenu(true)}
          displayName={displayName}
        />
      )}

      {/* ── Toast overlay ── */}
      {toast && (
        <div className={`fixed z-[100] pointer-events-none ${isMobile ? "top-[calc(52px+env(safe-area-inset-top,0px))] left-1/2 -translate-x-1/2" : "bottom-4 left-4 lg:bottom-4 lg:left-4 max-lg:bottom-auto max-lg:top-14 max-lg:left-1/2 max-lg:-translate-x-1/2"}`}
          role="status" aria-live="polite">
          <div className={`toast ${toast.isError ? "toast-error" : "toast-info"} ${toastExiting ? "toast-exit" : ""}`}>
            {toast.text}
          </div>
        </div>
      )}

      {/* ── CONTENT ── */}
      <div className={`flex-1 flex flex-col overflow-hidden ${isMobile && view !== "table" ? "pt-[calc(48px+env(safe-area-inset-top,0px))]" : ""} ${isMobile && view !== "table" ? "pb-[calc(56px+env(safe-area-inset-bottom,0px))]" : ""}`}>
      <div className="flex-1 flex overflow-hidden">
        {view === "profile" ? (
          /* ═══════ PROFILE ═══════ */
          <ProfilePage
            displayName={displayName}
            setDisplayName={(n) => { setDisplayName(n); setName(n); }}
            email={userEmail}
            authSession={authSession}
          />
        ) : view === "history" ? (
          /* ═══════ HISTORY ═══════ */
          <HistoryByRoomPage
            socket={socket}
            isConnected={isConnected}
            userId={authSession?.userId ?? ""}
            supabaseEnabled={supabaseEnabled}
          />
        ) : view === "training" ? (
          /* ═══════ TRAINING ═══════ */
          <TrainingDashboard
            handAudits={auditState.handAudits}
            sessionLeak={auditState.sessionLeak}
            hasData={auditState.hasData}
          />
        ) : view === "preflop" ? (
          /* ═══════ PREFLOP GTO ═══════ */
          <PreflopTrainer />
        ) : view === "clubs" ? (
          /* ═══════ CLUBS ═══════ */
          <ClubsPage
            socket={socket}
            isConnected={isConnected}
            userId={authSession?.userId ?? ""}
            clubs={clubList}
            clubsLoading={clubsLoading}
            clubDetail={selectedClubId ? clubDetail : null}
            onSelectClub={(clubId) => {
              setSelectedClubId(clubId);
              if (clubId && socket) {
                socket.emit("club_get_detail", { clubId });
              } else {
                setClubDetail(null);
              }
            }}
            onRefreshClubs={() => {
              if (socket) {
                setClubsLoading(true);
                socket.emit("club_list_my_clubs");
              }
            }}
            onJoinClubTable={(clubId, tableId) => {
              if (socket) {
                setClubRoomHintCode(tableId);
                socket.emit("club_table_join", { clubId, tableId });
                setView("table");
              }
            }}
            showToast={showToast}
          />
        ) : view === "lobby" ? (
          /* ═══════ LOBBY ═══════ */
          <Lobby
            connected={socketConnected}
            currentRoomCode={currentRoomCode}
            currentRoomName={currentRoomName}
            isOwner={!!myOwnedRoomCode}
            lobbyRooms={lobbyRooms}
            createSettings={createSettings}
            onCreateSettingsChange={setCreateSettings}
            onQuickPlay={() => {
              quickJoinNonClub("quick_play");
            }}
            onJoinByCode={(code: string) => {
              setClubRoomHintCode("");
              socket?.emit("join_room_code", { roomCode: code });
              showToast("Joining room...");
            }}
            onCreateRoom={(s: CreateRoomSettings) => {
              if (!socket) { showToast("Not connected to server"); return; }
              debugLog("[CREATE_ROOM] Emitting create_room", { clientUserId: authSession?.userId, settings: s });
              socket.emit("create_room", {
                roomName: `${s.sb}/${s.bb} NLH`,
                maxPlayers: s.maxPlayers,
                smallBlind: s.sb,
                bigBlind: s.bb,
                buyInMin: s.buyInMin,
                buyInMax: s.buyInMax,
                visibility: s.visibility,
              });
              showToast("Creating room...");
            }}
            onJoinRoom={(roomCode: string) => {
              setClubRoomHintCode("");
              socket?.emit("join_room_code", { roomCode });
              showToast("Joining room...");
            }}
            onRefreshLobby={() => socket?.emit("request_lobby")}
            onCopyCode={copyCode}
            onGoToTable={() => setView("table")}
            onLeaveRoom={leaveRoom}
          />
        ) : (
          /* ═══════ TABLE VIEW ═══════ */
          <>
            {/* ── Left Options Rail (desktop + landscape only — code-gated out for mobile portrait) ── */}
            {!isMobilePortrait && <LeftOptionsRail
              drawerOpen={showOptionsDrawer}
              onOpenDrawer={() => {
                setShowOptionsDrawer(true);
                debugLog("[OPTIONS_DRAWER] opened", {
                  tableId, userId: authSession?.userId, isHost: userRole.isHost,
                  isSeated: userRole.isSeated, canEditGame: userRole.canEditGame,
                  canEditPlayers: userRole.canEditPlayers,
                  renderedItemIds: OPTIONS_ITEMS.map(i => i.id),
                });
              }}
              actions={[
                ...(myPlayer ? [
                  { id: "away", icon: "💤", label: "Away", onClick: () => {
                    if (myPlayer.status === "sitting_out") socket?.emit("sit_in", { tableId });
                    else socket?.emit("sit_out", { tableId });
                  }, active: myPlayer.status === "sitting_out" },
                ] : []),
                { id: "leave", icon: "🚪", label: "Leave", onClick: () => {
                  if (handInProgress && !confirm("A hand is in progress. Leave the table?")) return;
                  debugLog("[nav] Leave rail clicked", { tableId, currentRoomCode });
                  leaveRoom();
                }, danger: true, hidden: !myPlayer },
                { id: "theme", icon: tableTheme === "green" ? "🟢" : "🔵", label: "Theme", onClick: () => {
                  const next: TableTheme = tableTheme === "green" ? "blue" : "green";
                  setTableTheme(next);
                  try { localStorage.setItem("cardpilot_table_theme", next); } catch {}
                }},
                { id: "bb", icon: displayBB ? "BB" : "$", label: displayBB ? "Chips" : "BB", onClick: () => setDisplayBB(!displayBB) },
              ]}
            />}

            {/* ── Options Drawer (all TABLE views — mobile portrait opens via hamburger) ── */}
            <OptionsDrawer
              open={showOptionsDrawer}
              onClose={() => setShowOptionsDrawer(false)}
              roomName={currentRoomName || undefined}
              roomCode={currentRoomCode || undefined}
              blinds={roomState ? `${roomState.settings.smallBlind}/${roomState.settings.bigBlind}` : undefined}
              isHost={!!isHost}
              onCopyCode={() => {
                if (currentRoomCode) {
                  navigator.clipboard.writeText(currentRoomCode).then(() => showToast("Room code copied!")).catch(() => {});
                }
              }}
              sections={OPTIONS_ITEMS.map((item): DrawerSection => {
                const isHostOnly = item.requiresHost && !userRole.isHostOrCoHost;
                const isSeatedOnly = item.requiresSeated && !userRole.isSeated;
                const isDisabled = isHostOnly || isSeatedOnly;

                // Dynamic labels for stateful toggles
                let dynamicLabel = item.label;
                let dynamicIcon = item.icon;
                if (item.id === "sit_toggle") {
                  dynamicLabel = myPlayer?.status === "sitting_out" ? "Sit In" : "Sit Out";
                  dynamicIcon = myPlayer?.status === "sitting_out" ? "✅" : "💤";
                }
                if (item.id === "display_bb") { dynamicLabel = displayBB ? "Show Chips ($)" : "Show BB"; dynamicIcon = displayBB ? "$" : "BB"; }
                if (item.id === "anim_speed") { dynamicLabel = `Animations: ${chipAnimSpeed}`; }
                if (item.id === "sound") { dynamicLabel = soundMuted ? "Unmute Sound" : "Mute Sound"; dynamicIcon = soundMuted ? "🔇" : "🔊"; }
                if (item.id === "theme") { dynamicLabel = `Felt: ${tableTheme === "green" ? "Green" : "Blue"}`; dynamicIcon = tableTheme === "green" ? "🟢" : "🔵"; }
                if (item.id === "pause_resume") { dynamicLabel = roomState?.status === "PAUSED" ? "Resume Game" : "Pause Game"; dynamicIcon = roomState?.status === "PAUSED" ? "▶️" : "⏸️"; }
                // Hide bomb pot if not enabled
                if (item.id === "bomb_pot" && !roomState?.settings?.bombPotEnabled) return null!;
                // Hide rebuy if not allowed
                if (item.id === "rebuy" && !roomState?.settings?.rebuyAllowed) return null!;
                // Hide close_room for non-host
                if (item.id === "close_room" && !isHost) return null!;

                const handleAction = () => {
                  if (item.settingsTab) {
                    setSettingsTab(item.settingsTab);
                    setShowSettings(true);
                    setShowOptionsDrawer(false);
                  } else if (item.action === "deal_hand") {
                    if (dealDisabledReason) { showToast(dealDisabledReason); return; }
                    socket?.emit("start_hand", { tableId });
                    setShowOptionsDrawer(false);
                  } else if (item.action === "stand_up") {
                    socket?.emit("stand_up", { tableId, seat });
                    setShowOptionsDrawer(false);
                  } else if (item.action === "sit_toggle") {
                    if (myPlayer?.status === "sitting_out") socket?.emit("sit_in", { tableId });
                    else socket?.emit("sit_out", { tableId });
                    setShowOptionsDrawer(false);
                  } else if (item.action === "rebuy") {
                    const bb = roomState?.settings.bigBlind ?? 100;
                    setRebuyAmount(bb * 100);
                    setShowRebuyModal(true);
                    setShowOptionsDrawer(false);
                  } else if (item.action === "queue_bomb_pot") {
                    socket?.emit("queue_bomb_pot", { tableId });
                    setShowOptionsDrawer(false);
                  } else if (item.action === "toggle_display_bb") {
                    setDisplayBB(!displayBB);
                    setShowOptionsDrawer(false);
                  } else if (item.action === "cycle_anim_speed") {
                    const next: AnimationSpeed = chipAnimSpeed === "normal" ? "slow" : chipAnimSpeed === "slow" ? "off" : "normal";
                    setChipAnimSpeed(next);
                    saveAnimationSpeed(next);
                    setShowOptionsDrawer(false);
                  } else if (item.action === "toggle_sound") {
                    setSoundMuted((m) => !m);
                    setShowOptionsDrawer(false);
                  } else if (item.action === "cycle_theme") {
                    const next: TableTheme = tableTheme === "green" ? "blue" : "green";
                    setTableTheme(next);
                    try { localStorage.setItem("cardpilot_table_theme", next); } catch {}
                    setShowOptionsDrawer(false);
                  } else if (item.action === "pause_resume") {
                    socket?.emit("game_control", { tableId, action: roomState?.status === "PAUSED" ? "resume" : "pause" });
                    setShowOptionsDrawer(false);
                  } else if (item.action === "end_game") {
                    socket?.emit("game_control", { tableId, action: "end" });
                    setShowOptionsDrawer(false);
                  } else if (item.action === "close_room") {
                    if (!confirm("Are you sure you want to close the room? All players will be returned to the lobby.")) return;
                    if (!socket || !isConnected) { showToast("Error: Cannot close room — not connected"); return; }
                    socket.emit("close_room", { tableId });
                    showToast("Closing room...");
                    const closeTimeout = setTimeout(() => { leaveRoom(); }, 5000);
                    socket.once("room_closed", () => clearTimeout(closeTimeout));
                    socket.once("error_event", (err: { message: string }) => { clearTimeout(closeTimeout); showToast(`Error: ${err.message}`); });
                    setShowOptionsDrawer(false);
                  } else if (item.action === "toggle_gto") {
                    setShowGtoSidebar(!showGtoSidebar); setShowOptionsDrawer(false);
                  } else if (item.action === "toggle_hand_history") {
                    setShowInGameHistory(!showInGameHistory); setShowOptionsDrawer(false);
                  } else if (item.action === "toggle_stats") {
                    setShowSessionStats(!showSessionStats);
                    if (!showSessionStats) socket?.emit("request_session_stats", { tableId });
                    setShowOptionsDrawer(false);
                  } else if (item.action === "toggle_log") {
                    setShowRoomLog(!showRoomLog); setShowOptionsDrawer(false);
                  } else if (item.action === "open_profile") {
                    setView("profile"); setShowOptionsDrawer(false);
                  } else if (item.action === "back_to_lobby") {
                    if (handInProgress && !confirm("A hand is in progress. Leave the table?")) return;
                    debugLog("[nav] Back to Lobby drawer clicked", { tableId, currentRoomCode });
                    leaveRoom();
                  }
                  debugLog("[OPTIONS_DRAWER] click:", item.analyticsName, { tableId, isHost: userRole.isHost, isSeated: userRole.isSeated });
                };
                return {
                  id: item.id,
                  icon: dynamicIcon,
                  label: dynamicLabel,
                  group: item.group,
                  groupLabel: GROUP_LABELS[item.group],
                  onClick: handleAction,
                  disabled: isDisabled,
                  disabledLabel: isHostOnly ? "Host only" : isSeatedOnly ? "Sit down first" : undefined,
                  badge: item.id === "gto" ? advice?.recommended?.toUpperCase()
                       : item.id === "deal" && dealDisabledReason ? "⏳"
                       : item.id === "bomb_pot" && snapshot?.bombPotQueued ? "Queued"
                       : undefined,
                };
              }).filter(Boolean)}
            />

            <main className="flex-1 flex flex-col overflow-hidden relative">
              {/* §6: Floating panels — overlay on table, don't push layout (anti-breathing) */}
              <div className="cp-table-float-panels">
              {/* Kicked overlay */}
              {kicked && (
                <div className="mx-3 mt-2 glass-card p-3 text-center border-red-500/30 bg-red-500/5 shrink-0">
                  <h3 className="text-sm font-bold text-red-400">{kicked.banned ? "You were banned" : "You were kicked"}: {kicked.reason}</h3>
                  <button onClick={() => { setKicked(null); setView("lobby"); }} className="btn-primary mt-2 text-xs !py-1.5 !px-4">Back to Lobby</button>
                </div>
              )}

              {/* Disconnected warning */}
              {!isConnected && (
                <div className="mx-3 mt-2 glass-card p-2 border-red-500/20 bg-red-500/5 flex items-center gap-2 shrink-0">
                  <span className="text-red-400 text-sm">⚠</span>
                  <p className="text-xs text-red-400">Server not connected — run <code className="bg-white/10 px-1 rounded">npm run dev</code></p>
                </div>
              )}

              {/* Controls Strip removed — all controls moved to OptionsDrawer (§1 code-gate) */}

              {/* ── Buy-in Modal ── */}
              {showBuyInModal && (() => {
                const settings = roomState?.settings;
                const biMin = settings?.buyInMin ?? 2000;
                const biMax = settings?.buyInMax ?? 20000;
                const bb = settings?.bigBlind ?? 100;
                const buyInStep = Math.max(100, bb);
                const snapBuyIn = (value: number) => {
                  const snapped = Math.round(value / buyInStep) * buyInStep;
                  return Math.min(biMax, Math.max(biMin, snapped));
                };
                debugLog("[BUY_IN_MODAL] isHostOrCoHost:", isHostOrCoHost, "isHost:", isHost, "isCoHost:", isCoHost);
                debugLog("[BUY_IN_MODAL] roomState.ownership:", roomState?.ownership);
                return (
                  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65" onClick={() => setShowBuyInModal(false)}>
                    <div className="glass-card p-6 w-80 space-y-4" onClick={(e) => e.stopPropagation()}>
                      <h3 className="text-sm font-bold text-white text-center">Choose Buy-in</h3>
                      {rejoinStackInfo?.tableId === tableId && rejoinStackInfo.stack != null && (
                        <div className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 p-2 text-center">
                          <div className="text-[10px] uppercase tracking-wider text-cyan-300">Returning Stack</div>
                          <div className="text-lg font-bold text-cyan-200 font-mono">{rejoinStackInfo.stack.toLocaleString()}</div>
                          <div className="text-[9px] text-cyan-400/80">Same room-session balance (anti-ratholing)</div>
                        </div>
                      )}
                      <div className="text-center">
                        <span className="text-3xl font-bold text-amber-400 font-mono">{(rejoinStackInfo?.tableId === tableId && rejoinStackInfo.stack != null ? rejoinStackInfo.stack : buyInAmount).toLocaleString()}</span>
                        <div className="text-[10px] text-slate-500 mt-1">{((rejoinStackInfo?.tableId === tableId && rejoinStackInfo.stack != null ? rejoinStackInfo.stack : buyInAmount) / bb).toFixed(0)} BB</div>
                      </div>
                      {!(rejoinStackInfo?.tableId === tableId && rejoinStackInfo.stack != null) && (
                        <input type="range" min={biMin} max={biMax} step={buyInStep} value={buyInAmount}
                          onChange={(e) => setBuyInAmount(snapBuyIn(Number(e.target.value)))}
                          className="w-full h-2 rounded-full appearance-none bg-white/10 accent-amber-500 cursor-pointer" />
                      )}
                      <div className="flex justify-between text-[10px] text-slate-500">
                        <span>{biMin.toLocaleString()}</span>
                        <span>{biMax.toLocaleString()}</span>
                      </div>
                      {/* Quick presets */}
                      {!(rejoinStackInfo?.tableId === tableId && rejoinStackInfo.stack != null) && (
                        <div className="flex gap-1.5 justify-center flex-wrap">
                          {(() => {
                            const presets = Array.from(new Set([
                              snapBuyIn(biMin),
                              snapBuyIn(biMin + (biMax - biMin) * 0.25),
                              snapBuyIn((biMin + biMax) / 2),
                              snapBuyIn(biMin + (biMax - biMin) * 0.75),
                              snapBuyIn(biMax)
                            ]));
                            return presets.map((v) => (
                              <button key={v} onClick={() => setBuyInAmount(v)}
                                className={`px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all ${
                                  buyInAmount === v
                                    ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                                    : "bg-white/5 text-slate-400 border border-white/10 hover:border-white/20"
                                }`}>{v.toLocaleString()}</button>
                            ));
                          })()}
                        </div>
                      )}
                      <div className="flex gap-2">
                        <button onClick={() => setShowBuyInModal(false)}
                          className="flex-1 py-2 rounded-lg text-xs font-medium bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10 transition-all">Cancel</button>
                        <button onClick={() => {
                          const canSitDirectly = isHostOrCoHost || isClubTableContext;
                          debugLog("[BUY_IN_MODAL] Sit button clicked. canSitDirectly:", canSitDirectly, "isHostOrCoHost:", isHostOrCoHost);
                          
                          if (canSitDirectly) {
                            debugLog("[BUY_IN_MODAL] Emitting sit_down (direct)");
                            socket?.emit("sit_down", { tableId, seat: pendingSitSeat, buyIn: (rejoinStackInfo?.tableId === tableId && rejoinStackInfo.stack != null ? rejoinStackInfo.stack : buyInAmount), name });
                          } else {
                            debugLog("[BUY_IN_MODAL] Emitting seat_request (guest)");
                            socket?.emit("seat_request", { tableId, seat: pendingSitSeat, buyIn: (rejoinStackInfo?.tableId === tableId && rejoinStackInfo.stack != null ? rejoinStackInfo.stack : buyInAmount), name });
                          }
                          // Sticky rebuy: remember buy-in per room
                          try { if (currentRoomCode) localStorage.setItem(`cardpilot_buyin_${currentRoomCode}`, String(buyInAmount)); } catch { /* ignore */ }
                          setShowBuyInModal(false);
                        }} className="flex-1 py-2 rounded-lg text-xs font-semibold bg-gradient-to-r from-emerald-500 to-emerald-600 text-white shadow-lg shadow-emerald-900/30 hover:from-emerald-400 hover:to-emerald-500 transition-all">
                          {isClubTableContext || isHostOrCoHost ? "Sit Down" : "Request Seat"}
                        </button>
                      </div>
                      <p className="text-[9px] text-slate-600 text-center">
                        Seat #{pendingSitSeat} · Blinds {settings?.smallBlind ?? 1}/{bb}
                        {!isClubTableContext && !isHostOrCoHost && " · Requires host approval"}
                      </p>
                    </div>
                  </div>
                );
              })()}

              {/* ── Rebuy Modal ── */}
              {showRebuyModal && (() => {
                const settings = roomState?.settings;
                const bb = settings?.bigBlind ?? 100;
                const myPlayer = snapshot?.players.find((p) => p.seat === seat);
                const maxRebuy = Math.max(0, (settings?.buyInMax ?? 20000) - (myPlayer?.stack ?? 0));
                const minRebuy = Math.max(bb, 1);
                return (
                  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65" onClick={() => setShowRebuyModal(false)}>
                    <div className="glass-card p-5 w-72 space-y-3" onClick={(e) => e.stopPropagation()}>
                      <h3 className="text-sm font-bold text-emerald-400 text-center">{isClubTable ? "Top Up Stack" : "Request Rebuy"}</h3>
                      <div className="text-center">
                        <span className="text-2xl font-bold text-emerald-400 font-mono">{rebuyAmount.toLocaleString()}</span>
                        <div className="text-[10px] text-slate-500 mt-0.5">{(rebuyAmount / bb).toFixed(0)} BB</div>
                      </div>
                      <input type="range" min={minRebuy} max={maxRebuy} step={bb} value={Math.min(rebuyAmount, maxRebuy)}
                        onChange={(e) => setRebuyAmount(Number(e.target.value))}
                        className="w-full h-2 rounded-full appearance-none bg-white/10 accent-emerald-500 cursor-pointer" />
                      <div className="flex justify-between text-[10px] text-slate-500">
                        <span>{minRebuy.toLocaleString()}</span>
                        <span>{maxRebuy.toLocaleString()}</span>
                      </div>
                      <div className="flex gap-2">
                        <button onClick={() => setShowRebuyModal(false)}
                          className="flex-1 py-2 rounded-lg text-xs font-medium bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10 transition-all">Cancel</button>
                        <button disabled={rebuyAmount <= 0 || rebuyAmount > maxRebuy} onClick={() => {
                          socket?.emit("deposit_request", { tableId, amount: rebuyAmount });
                          setShowRebuyModal(false);
                        }} className="flex-1 py-2 rounded-lg text-xs font-semibold bg-gradient-to-r from-emerald-500 to-emerald-600 text-white shadow-lg shadow-emerald-900/30 hover:from-emerald-400 hover:to-emerald-500 transition-all disabled:opacity-40">
                          {isClubTable || isHostOrCoHost ? "Top Up" : "Request"}
                        </button>
                      </div>
                      <p className="text-[9px] text-slate-600 text-center">
                        {isClubTable
                          ? "Instantly approved for club tables · Credited at next hand start"
                          : isHostOrCoHost
                            ? "Auto-approved · Credited at next hand start"
                            : "Host must approve · Credited at next hand start"}
                      </p>
                    </div>
                  </div>
                );
              })()}

              {/* ── Rebuy Requests (Host Only) ── */}
              {!isClubTable && isHostOrCoHost && rebuyRequests.length > 0 && (
                <div className="mx-3 mt-1 shrink-0">
                  <div className="glass-card p-3 border border-cyan-500/30 bg-cyan-500/5">
                    <h3 className="text-xs font-bold text-cyan-400 mb-2">Rebuy Requests ({rebuyRequests.length})</h3>
                    <div className="space-y-1.5">
                      {rebuyRequests.map((d) => (
                        <div key={d.orderId} className="flex items-center gap-2 p-2 rounded-lg bg-black/20 border border-cyan-500/10">
                          <div className="flex-1 text-[10px]">
                            <span className="text-white font-medium">{d.userName}</span>
                            <span className="text-slate-500"> (Seat {d.seat})</span>
                            <span className="text-cyan-400 font-mono ml-1">+{d.amount.toLocaleString()}</span>
                          </div>
                          <button onClick={() => {
                            socket?.emit("approve_deposit", { tableId, orderId: d.orderId });
                            setRebuyRequests((prev) => prev.filter((x) => x.orderId !== d.orderId));
                          }} className="px-2 py-1 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30">✓</button>
                          <button onClick={() => {
                            socket?.emit("reject_deposit", { tableId, orderId: d.orderId });
                            setRebuyRequests((prev) => prev.filter((x) => x.orderId !== d.orderId));
                          }} className="px-2 py-1 rounded text-[10px] font-semibold bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30">✗</button>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* ── Seat Request Panel (Host Only) ── */}
              {!isClubTable && isHostOrCoHost && seatRequests.length > 0 && (
                <div className="mx-3 mt-2 shrink-0 animate-pulse">
                  <div className="glass-card p-4 border-2 border-emerald-500/50 bg-gradient-to-r from-emerald-500/10 to-emerald-600/10 shadow-lg shadow-emerald-500/20">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-bold text-emerald-400 flex items-center gap-2">
                        <span className="text-lg">🎫</span>
                        Seat Requests ({seatRequests.length})
                      </h3>
                    </div>
                    <div className="space-y-2">
                      {seatRequests.map((req) => (
                        <div key={req.orderId} className="flex items-center gap-3 p-3 rounded-lg bg-black/30 border border-emerald-500/20">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-sm font-bold text-white">{req.userName}</span>
                              <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-semibold">Seat #{req.seat}</span>
                            </div>
                            <div className="text-[10px] text-slate-400">
                              Buy-in: <span className="text-amber-400 font-semibold">{formatChips(req.buyIn, { mode: displayBB ? "bb" : "chips", bbSize: snapshot?.bigBlind ?? 3 })}</span>
                            </div>
                          </div>
                          <div className="flex gap-2">
                            <button 
                              onClick={() => { 
                                socket?.emit("approve_seat", { tableId, orderId: req.orderId }); 
                                setSeatRequests(prev => prev.filter(r => r.orderId !== req.orderId)); 
                              }}
                              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 transition-all">
                              ✓ Approve
                            </button>
                            <button 
                              onClick={() => { 
                                socket?.emit("reject_seat", { tableId, orderId: req.orderId }); 
                                setSeatRequests(prev => prev.filter(r => r.orderId !== req.orderId)); 
                              }}
                              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 transition-all">
                              ✗ Reject
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Settings / Log panels */}
              {showRoomLog && (
                <div className="mx-3 mt-1 glass-card p-3 max-h-36 overflow-y-auto shrink-0">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-xs font-bold text-slate-400">Room Log</h3>
                    <button onClick={() => setShowRoomLog(false)} className="text-xs text-slate-500 hover:text-white">✕</button>
                  </div>
                  {roomLog.length === 0 ? (
                    <p className="text-[10px] text-slate-500 text-center py-2">No events yet</p>
                  ) : (
                    <div className="space-y-0.5">
                      {roomLog.slice().reverse().map((entry) => (
                        <div key={entry.id} className="flex items-start gap-2 text-[10px] py-0.5 border-b border-white/5 last:border-0">
                          <span className="text-slate-600 w-14 shrink-0">{new Date(entry.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
                          <span className={`px-1 py-0.5 rounded text-[9px] font-medium shrink-0 ${
                            entry.type === "OWNER_CHANGED" ? "bg-amber-500/10 text-amber-400" :
                            entry.type === "PLAYER_KICKED" || entry.type === "PLAYER_BANNED" ? "bg-red-500/10 text-red-400" :
                            entry.type === "SETTINGS_CHANGED" ? "bg-blue-500/10 text-blue-400" :
                            entry.type === "PLAYER_TIMED_OUT" || entry.type === "PLAYER_SAT_OUT" ? "bg-orange-500/10 text-orange-400" :
                            entry.type === "GAME_PAUSED" || entry.type === "GAME_RESUMED" ? "bg-purple-500/10 text-purple-400" :
                            "bg-white/5 text-slate-400"
                          }`}>{entry.type.replace(/_/g, " ")}</span>
                          <span className="text-slate-300">{entry.message}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}


              </div>{/* end cp-table-float-panels */}

              {/* ── CENTER: TABLE + SIDEBAR ── */}
              <div className={`cp-table-layout cp-scene-bg${isMobilePortrait ? " cp-table-layout--mobilePortrait" : ""}`}>
                <section className="cp-table-region-header">
                  {isMobilePortrait ? (
                    /* Compact mobile portrait top bar: Exit | Name/Code | Online dot + menu */
                    <div className="cp-mp-table-topbar">
                      <button
                        onClick={leaveRoom}
                        className="text-sm px-3 py-1 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-all shrink-0"
                        title="Leave table"
                      >
                        ← Exit
                      </button>
                      <div className="flex flex-col items-center min-w-0 flex-1 px-2">
                        {currentRoomName && (
                          <span className="text-xs font-semibold text-white truncate">{currentRoomName}</span>
                        )}
                        {currentRoomCode && (
                          <span className="text-[10px] font-mono text-amber-400 tracking-wider">{currentRoomCode}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 shrink-0 ml-auto pl-2">
                        <span
                          className={`w-2 h-2 rounded-full ${isConnected ? "bg-emerald-400" : "bg-red-400 animate-pulse"}`}
                          title={isConnected ? "Online" : "Offline"}
                        />
                        <button
                          onClick={() => setShowInGameHistory(true)}
                          className="text-lg text-slate-300 hover:text-white px-1"
                          title="Hand History"
                        >
                          📜
                        </button>
                        <button
                          onClick={() => setShowOptionsDrawer(true)}
                          className="text-lg text-slate-300 hover:text-white px-1"
                          title="Options"
                        >
                          ☰
                        </button>
                      </div>
                    </div>
                  ) : (
                  /* Info strip — improved numeric hierarchy */
                  <div className="cp-table-info-strip">
                    <div className="flex items-center gap-3">
                      <InfoCell label="Hand" value={snapshot?.handId ? snapshot.handId.slice(0, 8) : "—"} />
                      <div className="w-px h-5 bg-white/10" />
                      <InfoCell label="Street" value={snapshot?.street ?? "—"} highlight />
                      {snapshot?.isBombPotHand && (
                        <>
                          <div className="w-px h-5 bg-white/10" />
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-orange-500/15 text-orange-400 border border-orange-500/25 font-bold uppercase tracking-wider">
                            <span className="cp-bomb-icon">💣</span> Bomb Pot
                          </span>
                        </>
                      )}
                      {snapshot?.bombPotQueued && !snapshot?.isBombPotHand && (
                        <>
                          <div className="w-px h-5 bg-white/10" />
                          <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-orange-500/10 text-orange-300/70 border border-orange-500/15 font-medium">
                            💣 Next hand
                          </span>
                        </>
                      )}
                      <div className="w-px h-5 bg-white/10" />
                      <InfoCell label="Action" value={
                        snapshot?.actorSeat != null
                          ? (snapshot.actorSeat === seat ? "▶ Your turn" : `Seat ${snapshot.actorSeat} (${snapshot.players.find(p => p.seat === snapshot.actorSeat)?.name ?? "?"})`)
                          : "—"
                      } cyan />
                    </div>
                    <div className="flex items-center gap-5">
                      {/* Hero bet this street */}
                      {snapshot?.handId && (() => {
                        const me = snapshot.players.find(p => p.seat === seat);
                        return me && me.streetCommitted > 0 ? (
                          <div className="text-right">
                            <span className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">Your Bet</span>
                            <div className="text-base font-bold text-sky-400 cp-num">{formatChips(me.streetCommitted, { mode: displayBB ? "bb" : "chips", bbSize: snapshot.bigBlind ?? 3 })}</div>
                          </div>
                        ) : null;
                      })()}
                      <div className="text-right">
                        <span className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">Total Pot</span>
                        <div className="text-xl font-extrabold text-amber-400 cp-num">{formatChips(potNumbers.totalPot, { mode: displayBB ? "bb" : "chips", bbSize: snapshot?.bigBlind ?? 3 })}</div>
                      </div>
                    </div>
                  </div>
                  )}{/* end isMobilePortrait ternary */}
                </section>

                {/* Table area — maximized viewport usage */}
                <section className="cp-table-region-table" style={{ zIndex: 2 }}>

                  {/* Scale stage: fills available height; ref observed by useTableScale */}
                  <div className="cp-table-scale-stage" ref={tableStageRef}>
                    {/* Scale frame: sized to baseW*scale × baseH*scale, clips scaled content */}
                    <div
                      className="cp-table-scale-frame"
                      style={{ "--cp-table-scale": tableScale } as React.CSSProperties}
                    >
                      {/* Scale layer: always 1600×900, transform:scale() applied via CSS var */}
                      <div className="cp-table-scale-layer">

                  {/* Table surface + overlays — CSS green felt, wider */}
                  <div
                    ref={tableContainerRef}
                    className={`cp-table-canvas ${lingerActive ? "cursor-pointer" : ""} ${winnerFlareActive ? "cp-table-canvas--winner-flare" : ""} ${snapshot?.isBombPotHand ? "cp-table-canvas--bomb-pot" : ""}`}
                    onClick={lingerActive ? () => { clearLinger(); setWinners(null); setSettlement(null); } : undefined}>
                    <div className={`cp-table-felt ${tableTheme === "blue" ? "cp-table-felt--blue" : "cp-table-felt--green"}`} />

                    {/* Active game mode badges on table surface */}
                    {(roomState?.settings.bombPotEnabled || (roomState?.settings.sevenTwoBounty ?? 0) > 0) && (
                      <div className="cp-game-mode-badges">
                        {roomState?.settings.bombPotEnabled && (
                          <span className="cp-game-mode-badge cp-game-mode-badge--bomb">
                            💣 Bomb Pot
                          </span>
                        )}
                        {(roomState?.settings.sevenTwoBounty ?? 0) > 0 && (
                          <span className="cp-game-mode-badge cp-game-mode-badge--72">
                            🃏 7-2 Bounty
                          </span>
                        )}
                      </div>
                    )}

                    {/* Community cards — centered on table (supports up to 3 runout boards) */}
                    <div className="cp-table-center">
                      {snapshot?.runoutBoards && snapshot.runoutBoards.length > 1 ? (
                        /* Multi-run: show shared cards once, then branch for diverging cards */
                        (() => {
                          const boards = snapshot.runoutBoards;
                          // Compute common prefix length
                          let commonLen = 0;
                          const minLen = Math.min(...boards.map((b) => b.length));
                          for (let i = 0; i < minLen; i++) {
                            if (boards.every((b) => b[i] === boards[0][i])) commonLen = i + 1;
                            else break;
                          }
                          const commonCards = boards[0].slice(0, commonLen);
                          const hasBranches = boards.some((b) => b.length > commonLen);
                          return (
                            <div className={hasBranches ? "cp-board-branched" : "cp-board-row cp-board-row--single"}>
                              {/* Common cards shown once */}
                              {commonCards.length > 0 && (
                                <div className="cp-board-common">
                                  {commonCards.map((c: string, i: number) => {
                                    const slotKey = `run-0-card-${i}`;
                                    const revealToken = boardRevealTokens[slotKey] ?? 0;
                                    return (
                                      <div
                                        key={`${snapshot?.handId ?? "h"}-common-${i}-${revealToken}`}
                                        className={revealToken > 0 ? "cp-card-flip-in" : ""}
                                        style={revealToken > 0 ? { animationDelay: `${i * 140}ms` } : undefined}
                                      >
                                        <PokerCard card={c} variant="table" />
                                      </div>
                                    );
                                  })}
                                </div>
                              )}
                              {/* Branching cards per run */}
                              {hasBranches && (
                                <div className="cp-board-fork">
                                  {boards.map((board, runIdx) => {
                                    const unique = board.slice(commonLen);
                                    if (unique.length === 0) return null;
                                    return (
                                      <div key={runIdx} className={`cp-board-branch transition-all duration-200 ${board.length === 0 ? "opacity-0 scale-95" : "opacity-100 scale-100"}`}>
                                        <span className={`cp-board-run-badge shrink-0 ${
                                          runIdx === 0 ? "text-cyan-400" : runIdx === 1 ? "text-amber-400" : "text-emerald-400"
                                        } ${resultRunFocus?.run === (runIdx + 1) ? "ring-1 ring-amber-300/60 bg-amber-500/10 animate-pulse" : ""}`}>
                                          R{runIdx + 1}
                                        </span>
                                        {unique.map((c: string, i: number) => {
                                          const absIdx = commonLen + i;
                                          const slotKey = `run-${runIdx}-card-${absIdx}`;
                                          const revealToken = boardRevealTokens[slotKey] ?? 0;
                                          return (
                                            <div
                                              key={`${snapshot?.handId ?? "h"}-${slotKey}-${revealToken}`}
                                              className={revealToken > 0 ? "cp-card-flip-in" : ""}
                                              style={revealToken > 0 ? { animationDelay: `${(commonLen + runIdx * 2 + i) * 140}ms` } : undefined}
                                            >
                                              <PokerCard card={c} variant="table" />
                                            </div>
                                          );
                                        })}
                                      </div>
                                    );
                                  })}
                                </div>
                              )}
                            </div>
                          );
                        })()
                      ) : (
                        /* Standard single board */
                        <div className="cp-board-row cp-board-row--single">
                          {snapshot?.board && snapshot.board.length > 0
                            ? snapshot.board.map((c: string, i: number) => {
                                const slotKey = `main-${i}`;
                                const revealToken = boardRevealTokens[slotKey] ?? 0;
                                return (
                                  <div
                                    key={`${snapshot.handId ?? "h"}-${slotKey}-${revealToken}`}
                                    className={revealToken > 0 ? "cp-card-flip-in" : ""}
                                    style={revealToken > 0 ? { animationDelay: `${i * 140}ms` } : undefined}
                                  >
                                    <PokerCard card={c} variant="table" />
                                  </div>
                                );
                              })
                            : Array.from({ length: 5 }).map((_, i) => (
                                <div key={i} className="cp-board-slot" />
                              ))}
                        </div>
                      )}
                    </div>

                    {/* Runout street badge — positioned above pot summary */}
                    {boardReveal && (
                      <div className="cp-board-badge">
                        Runout: {boardReveal.street}
                      </div>
                    )}
                    {lingerActive && resultRunFocus && (
                      <div className="cp-board-badge mt-1 border border-amber-400/30 bg-amber-500/10 text-amber-300 animate-pulse">
                        Result Run {resultRunFocus.run}: {resultRunFocus.seats.length > 0 ? resultRunFocus.seats.map((seatNum) => `Seat ${seatNum}`).join(", ") : "Pending"}
                      </div>
                    )}

                    {/* Pot chip on table (always render anchor ref for animations) */}
                    <div ref={potRef} className="cp-pot-anchor">
                      {potNumbers.totalPot > 0 && (
                        <div className={`cp-pot-pill ${potPulseActive ? "cp-pot-pill--pulse" : ""}`}>
                          <div className="flex items-center justify-between gap-4 text-slate-300 uppercase tracking-wider text-base">
                            <span className="font-semibold">Pushed</span>
                            <span className="text-emerald-300 font-bold cp-num normal-case text-xl">{formatChips(potNumbers.pushedPot, { mode: displayBB ? "bb" : "chips", bbSize: snapshot?.bigBlind ?? 3 })}</span>
                          </div>
                          <div className="mt-1 flex items-center justify-between gap-4 text-slate-300 uppercase tracking-wider text-base">
                            <span className="font-semibold">Total</span>
                            <span className="text-amber-400 font-bold cp-num normal-case text-xl">{formatChips(potNumbers.totalPot, { mode: displayBB ? "bb" : "chips", bbSize: snapshot?.bigBlind ?? 3 })}</span>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Player seats */}
                    <div className="cp-seat-ring">{seatElements}</div>

                    {/* Chip animation overlay */}
                    <ChipAnimationLayer transfers={chipTransfers} onTransferDone={removeChipTransfer} speed={chipAnimSpeed} />
                  </div>{/* end cp-table-canvas */}
                      </div>{/* end cp-table-scale-layer */}
                    </div>{/* end cp-table-scale-frame */}
                  </div>{/* end cp-table-scale-stage */}

                  {/* Hole cards — rendered in normal flow below the table image to avoid overlapping timer/buttons */}
                  {holeCards.length > 0 && (
                    <div className="cp-hero-strip cp-hero-strip--deal-origin">
                      <span className="text-[9px] text-slate-500 uppercase tracking-wider mr-1">Your Hand</span>
                      {canVoluntaryShow && !myRevealedCards && !showHandConfirm && (
                        <button
                          onClick={() => setShowHandConfirm(true)}
                          className="text-[10px] px-2 py-1 rounded-md bg-white/5 text-amber-300 border border-amber-500/30 hover:bg-amber-500/15"
                          title="Show your hand to the entire table"
                        >
                          👁 SHOW
                        </button>
                      )}
                      {canVoluntaryShow && !myRevealedCards && showHandConfirm && (
                        <>
                          <button
                            onClick={() => {
                              if (!snapshot?.handId) return;
                              socket?.emit("show_hand", { tableId, handId: snapshot.handId, seat, scope: "table" });
                              setShowHandConfirm(false);
                            }}
                            className="text-[10px] px-2 py-1 rounded-md bg-amber-500/20 text-amber-200 border border-amber-500/40 hover:bg-amber-500/30"
                          >
                            Confirm
                          </button>
                          <button
                            onClick={() => setShowHandConfirm(false)}
                            className="text-[10px] px-2 py-1 rounded-md bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10"
                          >
                            Cancel
                          </button>
                        </>
                      )}
                      {myRevealedCards && (
                        <span className="text-[9px] px-2 py-1 rounded-md bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 uppercase tracking-wider">
                          Revealed
                        </span>
                      )}
                      {holeCards.map((c: string, i: number) => (
                        <div
                          key={`${snapshot?.handId ?? "h"}-${holeDealEpoch}-${i}-${c}`}
                          className="cp-card-deal-in"
                          style={{
                            animationDelay: `${i * 90}ms`,
                            ["--cp-deal-from-x" as string]: `${(i - (holeCards.length - 1) / 2) * 32}px`,
                            ["--cp-deal-from-y" as string]: "-220px",
                            ["--cp-deal-from-rot" as string]: `${i % 2 === 0 ? -10 : 10}deg`,
                          }}
                        >
                          <PokerCard card={c} variant="table" />
                        </div>
                      ))}
                      {/* Hand strength display — updates by street */}
                      {snapshot?.board && snapshot.board.length >= 3 && holeCards.length >= 2 && (() => {
                        const boardCards = snapshot.runoutBoards && snapshot.runoutBoards.length > 1
                          ? snapshot.runoutBoards
                          : [snapshot.board];
                        return boardCards.map((b, bIdx) => {
                          const desc = describeHandStrength(holeCards, b);
                          if (!desc || desc === "No board yet" || desc === "No hand data") return null;
                          return (
                            <span key={bIdx} className="text-[9px] px-2 py-0.5 rounded-md bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 ml-1" title={boardCards.length > 1 ? `Board ${bIdx + 1}` : "Made hand"}>
                              {boardCards.length > 1 && <span className="text-[7px] text-cyan-400/60 mr-1">R{bIdx + 1}</span>}
                              {desc}
                            </span>
                          );
                        });
                      })()}
                    </div>
                  )}

                  {/* Non-blocking hand-end linger: skip hint + hand summary access */}
                  {lingerActive && (
                    <div className="cp-hero-linger animate-[cpFadeSlideUp_0.3s_ease-out]">
                      <button
                        onClick={() => setShowHandSummaryDrawer(true)}
                        className="text-[10px] px-3 py-1.5 rounded-lg bg-white/5 text-slate-300 border border-white/10 hover:bg-white/10 transition-all"
                      >
                        Hand Summary
                      </button>
                      {seat != null && (
                        <button
                          onClick={() => { socket?.emit("start_hand", { tableId }); clearLinger(); setWinners(null); setSettlement(null); }}
                          className="text-[10px] px-3 py-1.5 rounded-lg bg-blue-500/20 text-blue-300 border border-blue-500/30 hover:bg-blue-500/30 transition-all font-semibold"
                        >
                          Deal Now
                        </button>
                      )}
                      <span className="text-[9px] text-slate-600 ml-1">
                        Press Space to skip
                      </span>
                    </div>
                  )}

                  {/* Post-hand show cards & 7-2 bounty claim */}
                  {postHandShowAvailable && !snapshot?.handId && seat != null && (
                    <div className="cp-hero-linger animate-[cpFadeSlideUp_0.3s_ease-out]">
                      {sevenTwoBountyPrompt && !sevenTwoBountyResult ? (
                        <button
                          onClick={() => {
                            socket?.emit("claim_seven_two_bounty", { tableId, seat });
                            setPostHandShowAvailable(false);
                          }}
                          className="text-base px-6 py-3 rounded-lg bg-amber-500/25 text-amber-200 border-2 border-amber-400/50 ring-2 ring-amber-400/60 hover:bg-amber-500/40 transition-all font-extrabold animate-pulse min-h-[48px]"
                        >
                          SHOW 7-2 &amp; Collect Bounty (+{sevenTwoBountyPrompt.totalBounty})
                        </button>
                      ) : (
                        !postHandRevealedCards[seat] && (
                          <button
                            onClick={() => {
                              socket?.emit("show_hand_post", { tableId, seat });
                              setPostHandShowAvailable(false);
                            }}
                            className="text-sm px-5 py-2.5 rounded-lg bg-white/5 text-amber-300 border border-amber-500/30 hover:bg-amber-500/15 transition-all font-semibold min-h-[44px]"
                          >
                            SHOW
                          </button>
                        )
                      )}
                    </div>
                  )}

                  {/* 7-2 bounty result banner */}
                  {sevenTwoBountyResult && (
                    <div className="cp-hero-linger animate-[cpFadeSlideUp_0.3s_ease-out]">
                      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-500/15 border border-amber-500/30">
                        <span className="text-xs font-bold text-amber-300 uppercase tracking-wider">7-2 Bounty</span>
                        <span className="text-sm text-amber-100">
                          {snapshot?.players.find((p) => p.seat === sevenTwoBountyResult.winnerSeat)?.name ?? `Seat ${sevenTwoBountyResult.winnerSeat}`}
                          {" "}collected +{sevenTwoBountyResult.totalBounty}
                        </span>
                      </div>
                    </div>
                  )}

                  {/* 7-2 bounty reveal overlay animation */}
                  {sevenTwoRevealActive && (
                    <SevenTwoRevealOverlay
                      winnerName={snapshot?.players.find((p) => p.seat === sevenTwoRevealActive.winnerSeat)?.name ?? `Seat ${sevenTwoRevealActive.winnerSeat}`}
                      winnerCards={sevenTwoRevealActive.winnerCards}
                      totalBounty={sevenTwoRevealActive.totalBounty}
                      onDismiss={() => setSevenTwoRevealActive(null)}
                    />
                  )}

                  {/* Bomb Pot announcement overlay */}
                  {bombPotOverlayActive && (
                    <BombPotOverlay
                      anteAmount={bombPotOverlayActive.anteAmount}
                      onDismiss={() => setBombPotOverlayActive(null)}
                    />
                  )}

                  {/* First-hand manual start gate (normal tables only). Club tables stay auto-start. */}
                  {showInitialStartPrompt && (
                    <div className="cp-hero-linger animate-[cpFadeSlideUp_0.3s_ease-out]">
                      <span className="text-[10px] text-amber-200/90">Ready to start this table?</span>
                      <button
                        onClick={() => {
                          if (dealDisabledReason) { showToast(dealDisabledReason); return; }
                          socket?.emit("start_hand", { tableId });
                        }}
                        className="text-[11px] px-4 py-2 rounded-lg bg-amber-500/20 text-amber-200 border border-amber-400/40 hover:bg-amber-500/30 transition-all font-semibold"
                      >
                        Start Game
                      </button>
                    </div>
                  )}
                </section>

                {/* ── GTO SIDEBAR — collapsible ── */}
                <aside className={`cp-table-region-side-panel overflow-y-auto ${showGtoSidebar ? "w-72 xl:w-80 p-2" : "w-8 p-1"}`}>
                  <button onClick={() => setShowGtoSidebar(!showGtoSidebar)}
                    className="flex items-center gap-1.5 mb-1 hover:opacity-80 transition-opacity"
                    aria-label={showGtoSidebar ? "Collapse GTO panel" : "Expand GTO panel"}
                    title={showGtoSidebar ? "Collapse" : "Expand GTO Coach"}>
                    <div className="w-5 h-5 rounded-md bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-[9px] font-extrabold text-slate-900 shrink-0">G</div>
                    {showGtoSidebar && <h2 className="text-[10px] font-bold text-white uppercase tracking-wider">GTO Coach</h2>}
                    <span className="text-[10px] text-slate-500 ml-auto">{showGtoSidebar ? "◂" : "▸"}</span>
                  </button>
                  {showGtoSidebar && (
                    <div className="space-y-2">
                    {advice ? (
                      <div className="space-y-2">
                        <div className="text-[9px] text-slate-500 font-mono truncate">{advice.spotKey}</div>
                        <div className="flex items-center gap-1.5 py-1 px-2 rounded-lg bg-white/[0.05]">
                          <span className="text-[9px] text-slate-500">Hand</span>
                          <span className="text-sm font-extrabold text-white tracking-wide">{advice.heroHand}</span>
                        </div>

                        {advice.recommended && (
                          <div className={`p-1.5 rounded-lg border text-center ${
                            advice.recommended === "raise" ? "bg-red-500/10 border-red-500/30 text-red-400"
                            : advice.recommended === "call" ? "bg-blue-500/10 border-blue-500/30 text-blue-400"
                            : "bg-slate-500/10 border-slate-500/30 text-slate-400"
                          }`}>
                            <div className="text-[8px] uppercase tracking-wider opacity-70">Recommendation</div>
                            <div className="text-sm font-extrabold uppercase">{advice.recommended}</div>
                          </div>
                        )}

                        <div className="space-y-1">
                          <Bar label="Raise" pct={advice.mix.raise} color="from-red-500 to-red-600" />
                          <Bar label="Call" pct={advice.mix.call} color="from-blue-500 to-blue-600" />
                          <Bar label="Fold" pct={advice.mix.fold} color="from-slate-500 to-slate-600" />
                        </div>
                        <div className="p-1.5 rounded-lg bg-white/[0.03] border border-white/5 text-[10px] text-slate-300 leading-relaxed">{advice.explanation}</div>

                        {deviation && (
                          <div className={`p-1.5 rounded-lg border ${
                            deviation.deviation <= 0.2 ? "bg-emerald-500/10 border-emerald-500/30"
                            : deviation.deviation <= 0.5 ? "bg-amber-500/10 border-amber-500/30"
                            : "bg-red-500/10 border-red-500/30"
                          }`}>
                            <div className="text-[8px] uppercase tracking-wider text-slate-400">Deviation</div>
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] text-white">You: <span className="font-bold uppercase">{deviation.playerAction}</span></span>
                              <span className={`text-xs font-extrabold ${
                                deviation.deviation <= 0.2 ? "text-emerald-400"
                                : deviation.deviation <= 0.5 ? "text-amber-400"
                                : "text-red-400"
                              }`}>{deviation.deviation <= 0.2 ? "GTO ✓" : `${Math.round(deviation.deviation * 100)}%`}</span>
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="text-center py-6">
                        <div className="text-xl mb-1 opacity-20">🎯</div>
                        <p className="text-slate-500 text-[10px]">Advice on your turn…</p>
                      </div>
                    )}
                    </div>
                  )}
                </aside>

                <section className="cp-table-region-overlays">
                {revealedZoom && (
                  <div className="fixed inset-0 z-[100] bg-black/75 flex items-end md:items-center justify-center" onClick={() => setRevealedZoom(null)}>
                    <div
                      className="w-full md:w-auto md:min-w-[360px] rounded-t-2xl md:rounded-2xl border border-white/15 bg-slate-900/95 p-4 md:p-6"
                      style={{ paddingBottom: "max(16px, env(safe-area-inset-bottom))" }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="flex items-center justify-between mb-3">
                        <div>
                          <div className="text-sm font-semibold text-white">{revealedZoom.name}</div>
                          <div className="text-xs text-slate-400">Seat {revealedZoom.seat}{revealedZoom.handName ? ` · ${revealedZoom.handName}` : " · Revealed hand"}</div>
                        </div>
                        <button className="text-slate-400 hover:text-white" onClick={() => setRevealedZoom(null)}>✕</button>
                      </div>
                      <div className="flex items-center justify-center gap-2">
                        <PokerCard card={revealedZoom.cards[0]} variant="modal" />
                        <PokerCard card={revealedZoom.cards[1]} variant="modal" />
                      </div>
                    </div>
                  </div>
                )}

                {/* ── Mobile GTO: Floating pill (landscape only) + Bottom Sheet ── */}
                {/* C2: In mobile portrait, GTO entry is inside ActionBar — no floating pill here */}
                <div className="lg:hidden" style={{ pointerEvents: "none" }}>
                  {/* Floating GTO pill — only for NON-portrait mobile (landscape phones/tablets) */}
                  {!isMobilePortrait && !showMobileGto && (
                    <button
                      onClick={() => setShowMobileGto(true)}
                      aria-label="Open GTO Coach"
                      style={{ pointerEvents: "auto" }}
                      className={`fixed z-40 flex items-center gap-1.5 px-3 py-2 rounded-full shadow-lg transition-all bottom-24 right-3 ${
                        advice ? "bg-gradient-to-r from-amber-500 to-orange-500 text-white animate-[pulse_2s_ease-in-out_infinite]" : "bg-slate-800 text-slate-400 border border-white/10"
                      }`}
                    >
                      <div className="w-5 h-5 rounded-md bg-white/20 flex items-center justify-center text-[9px] font-extrabold shrink-0">G</div>
                      <span className="text-xs font-semibold">GTO</span>
                      {advice?.recommended && <span className="text-[10px] font-bold uppercase bg-white/20 px-1.5 py-0.5 rounded-full">{advice.recommended}</span>}
                    </button>
                  )}

                  {/* GTO Bottom sheet (portrait) or right drawer (landscape) */}
                  {showMobileGto && (
                    <div
                      className={isMobilePortrait
                        ? "fixed inset-0 z-50"
                        : "fixed inset-0 z-50"
                      }
                      style={{ pointerEvents: "auto" }}
                      onClick={() => setShowMobileGto(false)}
                    >
                      {/* C3: Backdrop — in portrait, only cover the table area, NOT the action bar */}
                      <div
                        className="absolute inset-0 bg-black/50"
                        style={isMobilePortrait ? { bottom: "var(--cp-reserved-action-h-mobile)" } : undefined}
                      />
                      <div
                        className={isMobilePortrait
                          ? "cp-coach-mobile-sheet absolute left-0 right-0"
                          : "gto-drawer absolute right-0 top-0 bottom-0 w-72 max-w-[85vw] bg-[#0f1724] border-l border-white/10 p-4 overflow-y-auto"
                        }
                        style={isMobilePortrait ? {
                          bottom: "var(--cp-reserved-action-h-mobile)",
                          maxHeight: "min(60vh, 520px)",
                        } : undefined}
                        onClick={(e) => e.stopPropagation()}
                      >
                        {isMobilePortrait && <div className="cp-coach-mobile-handle" />}
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-2">
                            <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-xs font-extrabold text-slate-900">G</div>
                            <h3 className="text-sm font-bold text-white">GTO Coach</h3>
                          </div>
                          <button onClick={() => setShowMobileGto(false)} className="text-slate-400 hover:text-white text-sm px-2 py-1">✕</button>
                        </div>

                        {advice ? (
                          <div className="space-y-3">
                            <div className="text-[10px] text-slate-500 font-mono truncate">{advice.spotKey}</div>
                            <div className="flex items-center gap-2 py-2 px-3 rounded-xl bg-white/[0.05]">
                              <span className="text-xs text-slate-400">Hand</span>
                              <span className="text-lg font-extrabold text-white tracking-wide">{advice.heroHand}</span>
                            </div>

                            {advice.recommended && (
                              <div className={`p-3 rounded-xl border text-center ${
                                advice.recommended === "raise" ? "bg-red-500/10 border-red-500/30 text-red-400"
                                : advice.recommended === "call" ? "bg-blue-500/10 border-blue-500/30 text-blue-400"
                                : "bg-slate-500/10 border-slate-500/30 text-slate-400"
                              }`}>
                                <div className="text-[10px] uppercase tracking-wider opacity-70 mb-1">Recommendation</div>
                                <div className="text-xl font-extrabold uppercase">{advice.recommended}</div>
                              </div>
                            )}

                            <div className="space-y-1.5">
                              <Bar label="Raise" pct={advice.mix.raise} color="from-red-500 to-red-600" />
                              <Bar label="Call" pct={advice.mix.call} color="from-blue-500 to-blue-600" />
                              <Bar label="Fold" pct={advice.mix.fold} color="from-slate-500 to-slate-600" />
                            </div>
                            <div className="p-3 rounded-xl bg-white/[0.03] border border-white/5 text-xs text-slate-300 leading-relaxed">{advice.explanation}</div>

                            {deviation && (
                              <div className={`p-3 rounded-xl border ${
                                deviation.deviation <= 0.2 ? "bg-emerald-500/10 border-emerald-500/30"
                                : deviation.deviation <= 0.5 ? "bg-amber-500/10 border-amber-500/30"
                                : "bg-red-500/10 border-red-500/30"
                              }`}>
                                <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">Deviation</div>
                                <div className="flex items-center justify-between">
                                  <span className="text-xs text-white">You: <span className="font-bold uppercase">{deviation.playerAction}</span></span>
                                  <span className={`text-sm font-extrabold ${
                                    deviation.deviation <= 0.2 ? "text-emerald-400"
                                    : deviation.deviation <= 0.5 ? "text-amber-400"
                                    : "text-red-400"
                                  }`}>{deviation.deviation <= 0.2 ? "GTO ✓" : `${Math.round(deviation.deviation * 100)}%`}</span>
                                </div>
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="text-center py-8">
                            <div className="text-3xl mb-2 opacity-20">🎯</div>
                            <p className="text-slate-400 text-sm">GTO advice will appear on your turn</p>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
                </section>

                <section className="cp-table-region-action">
              {/* ── ACTIONS (pinned to bottom) — only when seated & hand active ── */}
              {snapshot?.handId && snapshot.players.some((p: TablePlayer) => p.seat === seat) && (
              <>
                <BottomActionBar
                  canAct={!!canAct}
                  legal={snapshot?.legalActions ?? null}
                  pot={snapshot?.pot ?? 0}
                  bigBlind={snapshot?.bigBlind ?? 100}
                  currentBet={snapshot?.currentBet ?? 0}
                  raiseTo={raiseTo}
                  setRaiseTo={setRaiseTo}
                  street={snapshot?.street ?? "PREFLOP"}
                  board={snapshot?.board ?? []}
                  heroStack={snapshot?.players.find((p) => p.seat === seat)?.stack ?? 10000}
                  numPlayers={snapshot?.players.filter((p: TablePlayer) => p.inHand && !p.folded).length ?? 2}
                  advice={advice}
                  thinkExtensionEnabled={(roomState?.settings.thinkExtensionQuotaPerHour ?? 0) > 0}
                  thinkExtensionRemainingUses={thinkExtensionRemainingUses}
                  onThinkExtension={() => socket?.emit("request_think_extension", { tableId })}
                  actionPending={actionPending}
                  displayBB={displayBB}
                  preAction={preAction}
                  onSetPreAction={setPreActionType}
                  derivedActionBar={derivedActionBar}
                  derivedPreActionUI={derivedPreActionUI}
                  isMyTurn={!!canAct}
                  onFoldAttempt={attemptFold}
                  onOpenGto={() => setShowMobileGto(true)}
                  isMobilePortrait={isMobilePortrait}
                  onAction={(action, amount) => {
                    if (!snapshot?.handId) return;
                    if (actionPending) return;
                    if (action === "fold") {
                      attemptFold();
                      return;
                    }
                    setActionPending(true);
                    setPreAction(null);

                    const legal = snapshot.legalActions;
                    if (action === "all_in") {
                      socket?.emit("action_submit", { tableId, handId: snapshot.handId, action: "all_in" });
                      return;
                    }
                    if (action === "raise") {
                      if (!legal?.canRaise) {
                        setActionPending(false);
                        return;
                      }
                      const minRaise = legal.minRaise;
                      const maxRaise = legal.maxRaise;
                      const requested = typeof amount === "number" ? amount : minRaise;
                      const normalized = Math.max(minRaise, Math.min(maxRaise, Math.round(requested)));
                      socket?.emit("action_submit", {
                        tableId,
                        handId: snapshot.handId,
                        action: "raise",
                        amount: normalized,
                      });
                      return;
                    }

                    socket?.emit("action_submit", { tableId, handId: snapshot.handId, action, amount });
                  }}
                />

                {/* Unnecessary fold confirmation modal */}
                <FoldConfirmModal
                  open={showFoldConfirm}
                  onConfirmFold={() => {
                    setShowFoldConfirm(false);
                    if (!snapshot?.handId || actionPending) return;
                    setActionPending(true);
                    setPreAction(null);
                    socket?.emit("action_submit", { tableId, handId: snapshot.handId, action: "fold" });
                  }}
                  onCancel={() => {
                    setShowFoldConfirm(false);
                    // Auto-check instead
                    if (snapshot?.legalActions?.canCheck && snapshot?.handId && !actionPending) {
                      setActionPending(true);
                      socket?.emit("action_submit", { tableId, handId: snapshot.handId, action: "check" });
                    }
                  }}
                  suppressedThisSession={suppressFoldConfirm}
                  onSuppressChange={setSuppressFoldConfirm}
                />

                {isMyShowdownDecision && snapshot?.handId && (
                  <div className="mt-2 p-4 rounded-xl border-2 border-indigo-400/50 bg-indigo-500/15 shadow-lg shadow-indigo-500/10">
                    <div className="flex items-center justify-between gap-2 mb-3">
                      <div className="text-xs uppercase tracking-wider text-indigo-200 font-semibold">Showdown Decision</div>
                      {!myIsWinner && (roomState?.settings.autoMuckLosingHands ?? true) && !myRevealedCards && !myIsMucked && (
                        <div className="text-xs text-slate-300 font-mono tabular-nums">Auto-muck in ~4s</div>
                      )}
                    </div>
                    {myRevealedCards ? (
                      <div className="text-sm text-emerald-300 font-semibold">Your hand is revealed to the table.</div>
                    ) : myIsMucked ? (
                      <div className="text-sm text-slate-300">You mucked your hand.</div>
                    ) : (
                      <div className="flex gap-3">
                        <button
                          onClick={() => socket?.emit("show_hand", { tableId, handId: snapshot.handId!, seat, scope: "table" })}
                          className="cp-btn cp-action-btn cp-btn-call flex-1 text-sm font-bold min-h-[48px]"
                        >
                          SHOW
                        </button>
                        <button
                          onClick={() => socket?.emit("muck_hand", { tableId, handId: snapshot.handId!, seat })}
                          className="cp-btn cp-action-btn cp-btn-fold flex-1 text-sm font-bold min-h-[48px]"
                        >
                          MUCK
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {allInLockForCurrentHand && runChoiceEligible && (
                  <div className="mt-2 p-3 rounded-xl border border-orange-500/30 bg-orange-500/10">
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div>
                        <div className="text-[10px] uppercase tracking-wider text-orange-300">All-In Run Count</div>
                        <div className="text-xs text-slate-200">
                          {myIsUnderdog
                            ? `You are the underdog${underdogWinRate != null ? ` (~${underdogWinRate}% equity)` : ""}. Choose run once, twice, or three times.`
                            : runTargetNeedsApproval
                              ? `Underdog chose run ${runTarget}. Agree to continue ${runTarget} runs or reject to run once.`
                              : "Waiting for underdog to choose run count."}
                        </div>
                        {hasSubmittedRunPreference && runChoiceWaitingCount > 0 && (
                          <div className="text-[10px] text-slate-300 mt-0.5">
                            Submitted. Waiting for {runChoiceWaitingCount} player{runChoiceWaitingCount === 1 ? "" : "s"}.
                          </div>
                        )}
                      </div>
                      <div className="text-[10px] text-slate-400 text-right">
                        {submittedRunSeats.length}/{allInLockForCurrentHand.eligiblePlayers.length} responded
                      </div>
                    </div>

                    {myIsUnderdog ? (
                      <div className="grid grid-cols-3 gap-2">
                        {[
                          { runCount: 1 as const, label: "Once" },
                          { runCount: 2 as const, label: "Twice" },
                          { runCount: 3 as const, label: "Three times" },
                        ].map((choice) => {
                          const selected = myRunPreference === choice.runCount;
                          const disabled = hasSubmittedRunPreference || choice.runCount > allInLockForCurrentHand.maxRunCountAllowed;
                          return (
                            <button
                              key={choice.runCount}
                              disabled={disabled}
                              onClick={() => {
                                if (!snapshot?.handId || !allInLockForCurrentHand) return;
                                socket?.emit("submit_run_preference", {
                                  tableId,
                                  handId: snapshot.handId,
                                  runCount: choice.runCount,
                                });
                                setMyRunPreference(choice.runCount);
                              }}
                              className={`btn-action ${
                                selected
                                  ? "bg-gradient-to-r from-amber-500 to-orange-500 text-slate-900 border border-amber-300/60"
                                  : "bg-gradient-to-r from-orange-600 to-orange-700 hover:from-orange-500 hover:to-orange-600"
                              } disabled:opacity-50`}
                            >
                              {choice.label}
                            </button>
                          );
                        })}
                      </div>
                    ) : runApprovalEligible && runTarget ? (
                      <div className="grid grid-cols-2 gap-2">
                        <button
                          disabled={hasSubmittedRunPreference}
                          onClick={() => {
                            if (!snapshot?.handId || !allInLockForCurrentHand) return;
                            socket?.emit("submit_run_preference", {
                              tableId,
                              handId: snapshot.handId,
                              runCount: runTarget,
                            });
                            setMyRunPreference(runTarget);
                          }}
                          className={`btn-action ${
                            myRunPreference === runTarget
                              ? "bg-gradient-to-r from-emerald-500 to-emerald-600 text-white border border-emerald-300/60"
                              : "bg-gradient-to-r from-emerald-700 to-emerald-800 hover:from-emerald-600 hover:to-emerald-700"
                          } disabled:opacity-50`}
                        >
                          Agree ({runTarget} runs)
                        </button>
                        <button
                          disabled={hasSubmittedRunPreference}
                          onClick={() => {
                            if (!snapshot?.handId || !allInLockForCurrentHand) return;
                            socket?.emit("submit_run_preference", {
                              tableId,
                              handId: snapshot.handId,
                              runCount: 1,
                            });
                            setMyRunPreference(1);
                          }}
                          className={`btn-action ${
                            myRunPreference === 1
                              ? "bg-gradient-to-r from-rose-500 to-red-500 text-white border border-rose-300/60"
                              : "bg-gradient-to-r from-rose-700 to-red-700 hover:from-rose-600 hover:to-red-600"
                          } disabled:opacity-50`}
                        >
                          Reject (Run once)
                        </button>
                      </div>
                    ) : (
                      <div className="text-[10px] text-slate-300">Waiting for underdog choice…</div>
                    )}
                  </div>
                )}

                {allInLockForCurrentHand && !runChoiceEligible && seat != null && snapshot.players.some((p: TablePlayer) => p.seat === seat && p.inHand) && (
                  <div className="mt-2 px-3 py-2 rounded-xl border border-amber-500/20 bg-amber-500/5 text-center">
                    <span className="text-[10px] text-amber-300 animate-pulse">
                      Waiting for run-count choices from {pendingRunPlayers.length > 0
                        ? pendingRunPlayers.map((player) => `Seat ${player.seat}`).join(", ")
                        : "all players"}…
                    </span>
                  </div>
                )}
              </>
              )}
                </section>
              </div>

              {/* Hand Summary Drawer (non-blocking, outside hand-active guard for linger access) */}
              <HandSummaryDrawer
                open={showHandSummaryDrawer}
                onClose={() => setShowHandSummaryDrawer(false)}
                settlement={lastSettlementRef.current}
                playerName={(s: number) => {
                  const p = snapshot?.players.find((pl) => pl.seat === s);
                  return p?.name ?? `Seat ${s}`;
                }}
                revealedHoles={settlementRevealedHoles}
                winnerHandNames={settlementWinnerHandNames}
              />

              {/* In-Game Hand History Drawer */}
              <InGameHandHistory
                open={showInGameHistory}
                onClose={() => setShowInGameHistory(false)}
                currentRoomCode={currentRoomCode}
                socket={socket}
                tableId={tableId}
              />

              {/* Session Scoreboard Drawer */}
              <SessionScoreboard
                open={showSessionStats}
                onClose={() => setShowSessionStats(false)}
                entries={sessionStatsData}
                currentUserId={socketAuthUserId}
                displayBB={displayBB}
                bigBlind={snapshot?.bigBlind ?? 3}
                onRefresh={() => socket?.emit("request_session_stats", { tableId })}
              />
            </main>

            {/* ── Room Settings Full-Screen Modal ── */}
            {showSettings && roomState && (
              <div
                className="cp-room-settings-backdrop"
                onClick={() => setShowSettings(false)}
                onKeyDown={(e) => { if (e.key === "Escape") setShowSettings(false); }}
                role="dialog"
                aria-modal="true"
                aria-label="Room Settings"
                data-testid="room-settings-modal"
              >
                <div
                  className="cp-room-settings-surface"
                  onClick={(e) => e.stopPropagation()}
                >
                  <RoomSettingsPanel
                    roomState={roomState}
                    isHost={!!isHost}
                    readOnly={!userRole.isHostOrCoHost}
                    initialTab={settingsTab}
                    players={snapshot?.players ?? []}
                    authUserId={authSession?.userId ?? ""}
                    onUpdateSettings={(settings: Record<string, unknown>) => socket?.emit("update_settings", { tableId, settings })}
                    onKick={(targetUserId: string, reason: string, ban: boolean) => socket?.emit("kick_player", { tableId, targetUserId, reason, ban })}
                    onTransfer={(newOwnerId: string) => socket?.emit("transfer_ownership", { tableId, newOwnerId })}
                    onSetCoHost={(userId: string, add: boolean) => socket?.emit("set_cohost", { tableId, userId, add })}
                    onBotAddChips={(seat: number, amount: number) => socket?.emit("bot_add_chips", { tableId, seat, amount })}
                    onClose={() => setShowSettings(false)}
                  />
                </div>
              </div>
            )}
          </>
        )}
      </div>
      {view !== "table" && !isMobile && <AppLegalFooter />}

      {/* ── MOBILE NAV: Bottom Tabs + More Menu (shown on mobile, hidden on table view) ── */}
      {isMobile && view !== "table" && (
        <MobileBottomTabs
          activeView={view}
          onNavigate={(v) => {
            setView(v);
            if (v === "clubs" && socket && canAccessClubs) { socket.emit("club_list_my_clubs"); }
            setShowMoreMenu(false);
          }}
          onMoreOpen={() => setShowMoreMenu((prev) => !prev)}
          moreOpen={showMoreMenu}
        />
      )}
      {isMobile && view !== "table" && (
        <MobileMoreMenu
          open={showMoreMenu}
          onClose={() => setShowMoreMenu(false)}
          activeView={view}
          onNavigate={(v) => {
            setView(v);
            if (v === "clubs" && socket && canAccessClubs) { socket.emit("club_list_my_clubs"); }
          }}
          onSignOut={handleLogout}
        />
      )}
      </div>
    </div>
  );
}


export default App;
