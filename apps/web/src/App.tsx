import { useEffect, useMemo, useState, useCallback, useRef, memo } from "react";
import { io, type Socket } from "socket.io-client";
import type {
  AdvicePayload,
  AllInPrompt,
  HistoryHandDetail,
  HistoryHandSummary,
  HistoryRoomSummary,
  HistorySessionSummary,
  LegalActions,
  LobbyRoomSummary,
  RoomFullState,
  RoomLogEntry,
  SettlementResult,
  TablePlayer,
  TableState,
  TimerState
} from "@cardpilot/shared-types";
import { getExistingSession, ensureGuestSession, signUpWithEmail, signInWithEmail, signInWithGoogle, signOut, supabase, validateEmail, validatePassword, getRateLimitSecondsLeft, type AuthSession } from "./supabase";
import { preloadCardImages, getCardImagePath } from "./lib/card-images.js";
import { SettlementOverlay } from "./components/SettlementOverlay";
import { getSuggestedPresets, userPresetsToButtons, type BetPreset } from "./lib/bet-sizing.js";

const SERVER = import.meta.env.VITE_SERVER_URL || "http://127.0.0.1:4000";
const DEBUG_LOGS_ENABLED = import.meta.env.DEV;
const APP_VERSION = "v0.4.1";
const NETLIFY_COMMIT_REF = import.meta.env.VITE_NETLIFY_COMMIT_REF || "";
const NETLIFY_DEPLOY_ID = import.meta.env.VITE_NETLIFY_DEPLOY_ID || "";
const BUILD_TIME = new Date().toISOString().slice(0, 16).replace("T", " ");

const debugLog = (...args: unknown[]) => {
  if (DEBUG_LOGS_ENABLED) console.log(...args);
};

/** Compute evenly-spaced seat positions around an ellipse for the given player count.
 *  Seat 1 starts at bottom-center and proceeds clockwise. */
function getSeatLayout(n: number): Record<number, { top: string; left: string }> {
  const cx = 50;   // ellipse center X (%)
  const cy = 46;   // ellipse center Y (%) — slightly above visual center of table image
  const rx = 43;   // horizontal radius (%)
  const ry = 38;   // vertical radius (%)
  const result: Record<number, { top: string; left: string }> = {};
  for (let i = 0; i < n; i++) {
    // π/2 = bottom in screen coords; subtract to go clockwise
    const angle = Math.PI / 2 - (i * 2 * Math.PI) / n;
    result[i + 1] = {
      top:  `${(cy + ry * Math.sin(angle)).toFixed(1)}%`,
      left: `${(cx + rx * Math.cos(angle)).toFixed(1)}%`,
    };
  }
  return result;
}

/* ═══════════════════ MAIN APP ═══════════════════ */
export function App() {
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
  const [allInPrompt, setAllInPrompt] = useState<AllInPrompt | null>(null);
  const [boardReveal, setBoardReveal] = useState<{ street: string; equities: Array<{ seat: number; winRate: number; tieRate: number }> } | null>(null);
  const [showHandConfirm, setShowHandConfirm] = useState(false);

  const [lobbyRooms, setLobbyRooms] = useState<LobbyRoomSummary[]>([]);
  const [newRoomSB, setNewRoomSB] = useState(1);
  const [newRoomBB, setNewRoomBB] = useState(3);
  const [newRoomBuyInMin, setNewRoomBuyInMin] = useState(40);
  const [newRoomBuyInMax, setNewRoomBuyInMax] = useState(300);
  const [displayBB, setDisplayBB] = useState(false);
  const [newRoomMaxPlayers, setNewRoomMaxPlayers] = useState(6);
  const [newRoomVisibility, setNewRoomVisibility] = useState<"public" | "private">("public");
  const [roomCodeInput, setRoomCodeInput] = useState("");
  const [showBuyInModal, setShowBuyInModal] = useState(false);
  const [pendingSitSeat, setPendingSitSeat] = useState(1);
  const [buyInAmount, setBuyInAmount] = useState(10000);
  const [currentRoomCode, setCurrentRoomCode] = useState("");
  const [view, setView] = useState<"lobby" | "table" | "profile" | "history">("lobby");

  /* ── Room management state ── */
  const [roomState, setRoomState] = useState<RoomFullState | null>(null);
  const [timerState, setTimerState] = useState<TimerState | null>(null);
  const [roomLog, setRoomLog] = useState<RoomLogEntry[]>([]);
  const [kicked, setKicked] = useState<{ reason: string; banned: boolean } | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [seatRequests, setSeatRequests] = useState<Array<{ orderId: string; userId: string; userName: string; seat: number; buyIn: number }>>([]);
  const [showRoomLog, setShowRoomLog] = useState(false);
  const [showSessionStats, setShowSessionStats] = useState(false);
  type SessionStatsEntry = { seat: number | null; userId: string; name: string; totalBuyIn: number; currentStack: number; net: number; handsPlayed: number };
  const [sessionStatsData, setSessionStatsData] = useState<SessionStatsEntry[]>([]);
  const [showDepositModal, setShowDepositModal] = useState(false);
  const [depositAmount, setDepositAmount] = useState(0);
  type DepositNotification = { orderId: string; userId: string; userName: string; seat: number; amount: number };
  const [depositNotifications, setDepositNotifications] = useState<DepositNotification[]>([]);
  const [socketConnected, setSocketConnected] = useState(false);
  const [showGtoSidebar, setShowGtoSidebar] = useState(() => {
    try { return localStorage.getItem("cardpilot_show_gto") !== "false"; } catch { return true; }
  });
  const [showMobileGto, setShowMobileGto] = useState(false);

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

  useEffect(() => { preloadCardImages(); }, []);

  // Persist GTO sidebar preference
  useEffect(() => {
    try { localStorage.setItem("cardpilot_show_gto", String(showGtoSidebar)); } catch {}
  }, [showGtoSidebar]);

  /* ── Refs for latest state (avoid stale closures in socket handlers) ── */
  const seatRef = useRef(seat);
  const currentRoomCodeRef = useRef(currentRoomCode);
  useEffect(() => { setName(displayName); }, [displayName]);
  useEffect(() => { seatRef.current = seat; }, [seat]);
  useEffect(() => { currentRoomCodeRef.current = currentRoomCode; }, [currentRoomCode]);

  /* ── Client-side timer tick: count down remaining every second ── */
  const [timerDisplay, setTimerDisplay] = useState<TimerState | null>(null);
  useEffect(() => {
    if (!timerState) { setTimerDisplay(null); return; }
    // Initialize display from server state
    setTimerDisplay({ ...timerState });
    const interval = setInterval(() => {
      const elapsed = (Date.now() - timerState.startedAt) / 1000;
      if (timerState.usingTimeBank) {
        const bankLeft = Math.max(0, timerState.timeBankRemaining - elapsed);
        setTimerDisplay({
          ...timerState,
          remaining: 0,
          timeBankRemaining: bankLeft,
          usingTimeBank: true,
        });
      } else {
        const left = Math.max(0, timerState.remaining - elapsed);
        setTimerDisplay({
          ...timerState,
          remaining: left,
          usingTimeBank: left <= 0,
        });
      }
    }, 500);
    return () => clearInterval(interval);
  }, [timerState]);

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
        const s: AuthSession = { accessToken: session.access_token, userId: session.user.id, email: session.user.email, displayName: dn };
        setAuthSession(s);
        setUserEmail(session.user.email ?? null);
        if (dn) setDisplayName(dn);
      } else {
        setAuthSession(null);
        setUserEmail(null);
      }
    });
    return () => { data.subscription.unsubscribe(); };
  }, []);

  const socketAuthUserId = authSession?.userId;
  const socketAuthToken = authSession?.accessToken;

  /* ── Socket: connect only when authenticated ── */
  useEffect(() => {
    if (!socketAuthUserId) return;
    debugLog("[SOCKET] Connecting with userId:", socketAuthUserId);
    const s = io(SERVER, { 
      auth: { 
        accessToken: socketAuthToken, 
        displayName,
        userId: socketAuthUserId // Send userId to server
      } 
    });
    setSocket(s);

    s.on("connect", () => {
      setSocketConnected(true);
      showToast("Connected");
      s.emit("request_lobby");

      const roomCode = currentRoomCodeRef.current;
      if (roomCode) {
        s.emit("join_room_code", { roomCode });
      }
    });
    s.on("connected", (d: { userId: string; displayName?: string; supabaseEnabled: boolean }) => {
      debugLog("[client] connected, server userId:", d.userId, "client userId:", socketAuthUserId);
      if (!d.supabaseEnabled) showToast("Connected (no Supabase persistence)");
    });
    s.on("disconnect", () => { setSocketConnected(false); });
    s.on("lobby_snapshot", (d: { rooms: LobbyRoomSummary[] }) => setLobbyRooms(d.rooms ?? []));
    s.on("room_created", (d: { tableId: string; roomCode: string; roomName: string }) => {
      setTableId(d.tableId); setCurrentRoomCode(d.roomCode);
      showToast(`Room created: ${d.roomName} (${d.roomCode})`); setView("table");
    });
    s.on("room_joined", (d: { tableId: string; roomCode: string; roomName: string }) => {
      setTableId(d.tableId); setCurrentRoomCode(d.roomCode);
      showToast(`Joined room: ${d.roomName} (${d.roomCode})`); setView("table");
    });
    s.on("table_snapshot", (d: TableState) => {
      setSnapshot(d);
      if (d.winners) setWinners(d.winners);
      if (d.allInPrompt && d.allInPrompt.actorSeat === seatRef.current) {
        setAllInPrompt(d.allInPrompt);
      } else {
        setAllInPrompt(null);
      }
    });
    s.on("hole_cards", (d: { cards: string[]; seat: number }) => {
      setHoleCards(d.cards);
      setSeat(d.seat);
    });
    s.on("hand_started", () => {
      setActionPending(false);
      setAdvice(null); setDeviation(null); setWinners(null); setAllInPrompt(null); setBoardReveal(null); setHoleCards([]);
      setSettlement(null); setSettlementCountdown(0);
    });
    s.on("board_reveal", (d: { handId: string; street: string; newCards: string[]; board: string[]; equities: Array<{ seat: number; winRate: number; tieRate: number }> }) => {
      setBoardReveal({ street: d.street, equities: d.equities });
    });
    s.on("run_twice_reveal", (d: { handId: string; street: string; run1: { newCards: string[]; board: string[] }; run2: { newCards: string[]; board: string[] } }) => {
      setBoardReveal((prev) => ({ street: d.street, equities: prev?.equities ?? [] }));
      setSnapshot((prev) => {
        if (!prev || prev.handId !== d.handId) return prev;
        return { ...prev, runoutBoards: [d.run1.board, d.run2.board] };
      });
    });
    s.on("run_count_chosen", () => {
      setAllInPrompt(null);
    });
    s.on("stood_up", (d: { seat: number; reason: string }) => {
      showToast(d.reason);
    });
    s.on("action_applied", (d: { seat: number; action: string; amount: number; pot: number; auto?: boolean }) => {
      if (d.seat === seatRef.current) setActionPending(false);
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
      setAllInPrompt(null);
      setBoardReveal(null);
      if (d.winners) setWinners(d.winners);
      if (d.finalState) setSnapshot(d.finalState);

      // Settlement overlay: capture settlement data and start countdown
      if (d.settlement) {
        setSettlement(d.settlement);
        setSettlementCountdown(6);
      }
      setTimeout(() => setHoleCards([]), 800);
    });
    s.on("error_event", (d: { message: string }) => {
      setActionPending(false);
      showToast(`Error: ${d.message}`);
    });
    s.on("all_in_prompt", (d: AllInPrompt) => setAllInPrompt(d));
    s.on("session_stats", (d: { tableId: string; entries: Array<{ seat: number | null; userId: string; name: string; totalBuyIn: number; currentStack: number; net: number; handsPlayed: number }> }) => {
      setSessionStatsData(d.entries);
    });
    s.on("deposit_request_pending", (d: { orderId: string; userId: string; userName: string; seat: number; amount: number }) => {
      setDepositNotifications((prev) => [...prev, d]);
    });

    // Room management events
    s.on("room_state_update", (d: RoomFullState) => {
      if (!d) return;
      debugLog("[client] room_state_update received, owner:", d.ownership?.ownerId);
      setRoomState(d);
      if (d.log) setRoomLog(d.log);
    });
    s.on("timer_update", (d: TimerState) => setTimerState(d));
    s.on("room_log", (d: RoomLogEntry) => setRoomLog((prev) => [...prev.slice(-99), d]));
    s.on("kicked", (d: { reason: string; banned: boolean }) => {
      setKicked(d);
      setView("lobby");
      setCurrentRoomCode("");
      setRoomState(null);
      showToast(`You were ${d.banned ? "banned" : "kicked"}: ${d.reason}`);
    });
    s.on("room_closed", (d?: { reason?: string }) => {
      setActionPending(false);
      setView("lobby");
      setCurrentRoomCode("");
      setRoomState(null);
      setSnapshot(null);
      setHoleCards([]);
      setSeatRequests([]);
      setWinners(null);
      setAllInPrompt(null);
      setAdvice(null);
      setDeviation(null);
      setBoardReveal(null);
      setShowSettings(false);
      setShowRoomLog(false);
      showToast(d?.reason ?? "Room closed. Returned to lobby.");
    });
    s.on("hand_aborted", (d: { reason: string }) => {
      setActionPending(false);
      setHoleCards([]);
      setWinners(null);
      setSettlement(null);
      setSettlementCountdown(0);
      setAllInPrompt(null);
      setAdvice(null);
      setDeviation(null);
      setBoardReveal(null);
      showToast(d.reason);
    });
    s.on("system_message", (d: { message: string }) => showToast(d.message));
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

    return () => { s.disconnect(); };
  }, [socketAuthUserId, socketAuthToken, displayName]);

  const canAct = useMemo(() => snapshot?.actorSeat === seat && snapshot?.handId, [snapshot, seat]);
  // Reset raiseTo to minRaise whenever legal actions change
  useEffect(() => {
    const minR = snapshot?.legalActions?.minRaise;
    if (minR && minR > 0) setRaiseTo(minR);
  }, [snapshot?.legalActions?.minRaise]);

  // Reset action pending when turn/street/hand changes
  useEffect(() => { setActionPending(false); }, [snapshot?.actorSeat, snapshot?.street, snapshot?.handId]);
  const isConnected = socketConnected;
  const isHost = useMemo(() => roomState?.ownership.ownerId === authSession?.userId, [roomState, authSession]);
  const isCoHost = useMemo(() => roomState?.ownership.coHostIds.includes(authSession?.userId ?? "") ?? false, [roomState, authSession]);
  const isHostOrCoHost = isHost || isCoHost;
  const handInProgress = useMemo(
    () => (roomState?.status === "PLAYING") || Boolean(snapshot?.handId && (snapshot.actorSeat != null || snapshot.showdownPhase === "decision")),
    [roomState?.status, snapshot?.handId, snapshot?.actorSeat, snapshot?.showdownPhase]
  );
  const dealDisabledReason = useMemo(() => {
    if (!isConnected) return "Server disconnected";
    if (!isHost) return "Only host can deal";
    if (roomState?.status === "PAUSED") return "Game is paused";
    if (handInProgress) return "Current hand is still in progress";
    const eligibleCount = snapshot?.players.filter((p) => p.stack > 0).length ?? 0;
    if (eligibleCount < 2) return `Need at least 2 players with chips (currently ${eligibleCount})`;
    return null;
  }, [isConnected, isHost, roomState?.status, handInProgress, snapshot?.players]);
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
  useEffect(() => {
    if (!canVoluntaryShow) setShowHandConfirm(false);
  }, [canVoluntaryShow]);
  useEffect(() => {
    if (!isHostOrCoHost) {
      setDepositNotifications([]);
      return;
    }
    const pending = snapshot?.pendingDeposits ?? [];
    setDepositNotifications(
      pending.map((deposit) => ({
        orderId: deposit.orderId,
        userId: deposit.userId,
        userName: deposit.userName,
        seat: deposit.seat,
        amount: deposit.amount,
      }))
    );
  }, [isHostOrCoHost, snapshot?.pendingDeposits]);
  useEffect(() => {
    if (roomState?.settings.roomFundsTracking === false) {
      setShowSessionStats(false);
    }
  }, [roomState?.settings.roomFundsTracking]);
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
  // Settlement overlay countdown timer
  useEffect(() => {
    if (!settlement || settlementCountdown <= 0) return;
    const timer = setTimeout(() => {
      setSettlementCountdown((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearTimeout(timer);
  }, [settlement, settlementCountdown]);

  // Compute auto-start block reason for settlement overlay
  const autoStartBlockReason = useMemo(() => {
    if (!settlement) return null;
    if (roomState?.status === "PAUSED") return "Game is paused by host.";
    if (!roomState?.settings.autoStartNextHand) return "Auto-start is off.";
    const eligibleCount = snapshot?.players.filter((p) => p.stack > 0).length ?? 0;
    if (eligibleCount < 2) return `Waiting for 2+ eligible players (currently ${eligibleCount}).`;
    return null;
  }, [settlement, roomState, snapshot?.players]);

  const seatPositions = useMemo(() => getSeatLayout(roomState?.settings.maxPlayers ?? 6), [roomState?.settings.maxPlayers]);

  const handleSeatClick = useCallback((seatNum: number) => {
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
  }, [roomState?.settings, currentRoomCode]);

  const seatElements = useMemo(() => {
    const maxP = roomState?.settings.maxPlayers ?? 6;
    return Array.from({ length: maxP }, (_, i) => i + 1).map((seatNum) => {
      const pos = seatPositions[seatNum];
      const player = snapshot?.players.find((p) => p.seat === seatNum);
      const isActor = snapshot?.actorSeat === seatNum;
      const isMe = seatNum === seat;
      const isOwner = player && roomState?.ownership.ownerId === player.userId;
      const isCo = player && roomState?.ownership.coHostIds.includes(player.userId);
      const seatTimer = isActor && timerDisplay?.seat === seatNum ? timerDisplay : null;
      const posLabel = snapshot?.positions?.[seatNum] ?? "";
      const isButton = snapshot?.buttonSeat === seatNum && !!snapshot?.handId;
      const equity = boardReveal?.equities.find((e) => e.seat === seatNum) ?? null;
      const isPendingLeave = snapshot?.pendingStandUp?.includes(seatNum) ?? false;
      const revealedCards = snapshot?.revealedHoles?.[seatNum] as [string, string] | undefined;
      const isMucked = snapshot?.muckedSeats?.includes(seatNum) ?? false;
      return (
        <div key={seatNum} className="absolute -translate-x-1/2 -translate-y-1/2" style={{ top: pos.top, left: pos.left }}>
          <SeatChip player={player} seatNum={seatNum} isActor={isActor} isMe={isMe}
            isOwner={!!isOwner} isCoHost={!!isCo} timer={seatTimer}
            posLabel={posLabel} isButton={isButton} displayBB={displayBB} bigBlind={snapshot?.bigBlind ?? 3}
            equity={equity} pendingLeave={isPendingLeave} revealedCards={revealedCards} isMucked={isMucked}
            onClickEmpty={handleSeatClick} />
        </div>
      );
    });
  }, [snapshot, seat, roomState, timerDisplay, boardReveal, displayBB, seatPositions, handleSeatClick]);

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
    if (socket && tableId) {
      socket.emit("stand_up", { tableId, seat });
      socket.emit("leave_table", { tableId });
    }
    setCurrentRoomCode("");
    setRoomState(null);
    setSnapshot(null);
    setHoleCards([]);
    setSeatRequests([]);
    setShowSettings(false);
    setShowRoomLog(false);
    setKicked(null);
    setWinners(null);
    setSettlement(null);
    setSettlementCountdown(0);
    setAllInPrompt(null);
    setAdvice(null);
    setDeviation(null);
    setView("lobby");
    showToast("Left room");
    socket?.emit("request_lobby");
  }

  async function handleLogout() {
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
    return <AuthScreen onAuth={(s) => {
      setAuthSession(s);
      setUserEmail(s.email ?? null);
      const dn = s.displayName || s.email?.split("@")[0] || "Guest";
      setDisplayName(dn);
      setName(dn);
      showToast("Signed in");
    }} />;
  }

  /* ═══════════════════ RENDER ═══════════════════ */
  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* ── Onboarding Modal ── */}
      {showOnboarding && authSession && (
        <OnboardingModal onComplete={completeOnboarding} />
      )}

      {/* ── NAV ── */}
      <header className="flex items-center justify-between px-4 py-1.5 border-b border-white/5 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-sm font-extrabold text-slate-900 shadow-lg">C</div>
          <h1 className="text-base font-bold tracking-tight text-white">Card<span className="text-amber-400">Pilot</span></h1>
        </div>
        <nav className="flex items-center gap-1 bg-white/5 rounded-xl p-1">
          {(["lobby", "table", "history", "profile"] as const).map((v) => (
            <button key={v} onClick={() => setView(v)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${view === v ? "bg-white/10 text-white shadow-sm" : "text-slate-400 hover:text-slate-200"}`}>
              {v === "lobby" ? "Lobby" : v === "table" ? "Table" : v === "history" ? "History" : "Profile"}
            </button>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-[10px] font-medium ${isConnected ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400 animate-pulse"}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? "bg-emerald-400" : "bg-red-400"}`} />
            {isConnected ? "Online" : "Offline"}
          </span>
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-[11px] font-bold text-white uppercase">{displayName[0]}</div>
          <span className="text-xs text-slate-200 font-medium max-w-[140px] truncate">Hi, {displayName}</span>
          <button onClick={handleLogout} className="text-xs text-slate-500 hover:text-red-400 transition-colors px-2 py-1 rounded-lg hover:bg-white/5">Sign Out</button>
          <span className="text-[8px] text-slate-600 font-mono" title={`Build: ${BUILD_TIME}`}>{APP_VERSION}{NETLIFY_COMMIT_REF ? `@${NETLIFY_COMMIT_REF.slice(0, 7)}` : ""}{NETLIFY_DEPLOY_ID ? `#${NETLIFY_DEPLOY_ID.slice(0, 6)}` : ""}</span>
        </div>
      </header>

      {/* ── Toast overlay (replaces old status bar — no layout shift) ── */}
      {toast && (
        <div className="fixed bottom-4 left-4 z-[100] pointer-events-none lg:bottom-4 lg:left-4 max-lg:bottom-auto max-lg:top-14 max-lg:left-1/2 max-lg:-translate-x-1/2"
          role="status" aria-live="polite">
          <div className={`toast ${toast.isError ? "toast-error" : "toast-info"} ${toastExiting ? "toast-exit" : ""}`}>
            {toast.text}
          </div>
        </div>
      )}

      {/* ── CONTENT ── */}
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
          <HistoryPage socket={socket} isConnected={socketConnected} />
        ) : view === "lobby" ? (
          /* ═══════ LOBBY ═══════ */
          <main className="flex-1 p-6 overflow-y-auto">
            <div className="max-w-3xl mx-auto space-y-6">

              {/* ── Play Now Quick-Match ── */}
              {!currentRoomCode && (
                <div className="glass-card p-6 bg-gradient-to-r from-emerald-500/5 via-transparent to-amber-500/5 border-emerald-500/20">
                  <div className="flex flex-col sm:flex-row items-center gap-4">
                    <div className="flex-1 text-center sm:text-left">
                      <h2 className="text-xl font-bold text-white mb-1">Ready to play?</h2>
                      <p className="text-sm text-slate-400">Jump into a table instantly — no setup needed.</p>
                    </div>
                    <button
                      disabled={!socket || !socketConnected}
                      onClick={() => {
                        if (!socket) { showToast("Not connected to server"); return; }
                        // Try to join the first open public room with available seats
                        const openRoom = lobbyRooms.find(r => r.status === "OPEN" && r.playerCount < r.maxPlayers);
                        if (openRoom) {
                          socket.emit("join_room_code", { roomCode: openRoom.roomCode });
                          showToast("Quick-matching into room...");
                        } else {
                          // No open rooms — create a default one
                          socket.emit("create_room", {
                            roomName: "1/2 NLH",
                            maxPlayers: 6,
                            smallBlind: 1,
                            bigBlind: 2,
                            buyInMin: 40,
                            buyInMax: 200,
                            visibility: "public",
                          });
                          showToast("Creating a new table...");
                        }
                      }}
                      className="btn-success !py-4 !px-8 text-lg font-bold whitespace-nowrap shadow-xl shadow-emerald-900/40 hover:shadow-emerald-900/60 disabled:opacity-50 disabled:cursor-not-allowed transition-all active:scale-95"
                    >
                      ▶ Play Now
                    </button>
                  </div>
                  {lobbyRooms.length > 0 && (
                    <p className="text-[10px] text-slate-500 text-center sm:text-left mt-2">
                      {lobbyRooms.filter(r => r.status === "OPEN" && r.playerCount < r.maxPlayers).length} open table{lobbyRooms.filter(r => r.status === "OPEN" && r.playerCount < r.maxPlayers).length !== 1 ? "s" : ""} available
                    </p>
                  )}
                </div>
              )}

              {/* ── Current Room Banner ── */}
              {currentRoomCode && (
                <div className="glass-card p-5 border-amber-500/20 bg-gradient-to-r from-amber-500/5 to-transparent">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-11 h-11 rounded-xl bg-amber-500/15 border border-amber-500/25 flex items-center justify-center text-amber-400 text-lg">
                        {myOwnedRoomCode ? "👑" : "🎴"}
                      </div>
                      <div>
                        <div className="text-xs text-slate-400 uppercase tracking-wider mb-0.5">
                          {myOwnedRoomCode ? "Your Room" : "Current Room"}
                        </div>
                        <div className="font-mono font-bold text-amber-400 text-xl tracking-[0.2em]">{currentRoomCode}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={copyCode} className="px-3 py-2 rounded-lg text-xs font-medium bg-white/5 text-slate-300 border border-white/10 hover:bg-white/10 transition-all">Copy</button>
                      <button onClick={() => setView("table")} className="px-4 py-2 rounded-lg text-xs font-semibold bg-gradient-to-r from-emerald-500 to-emerald-600 text-white shadow-lg shadow-emerald-900/30 hover:from-emerald-400 hover:to-emerald-500 transition-all">Go to Table</button>
                      <button onClick={leaveRoom} className="px-3 py-2 rounded-lg text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-all">Leave</button>
                    </div>
                  </div>
                </div>
              )}

              {/* ── Create / Join ── */}
              <div className="glass-card p-6">
                <div className="flex items-center justify-between mb-5">
                  <h2 className="text-lg font-bold text-white">
                    {currentRoomCode ? "Switch Room" : "Create or Join a Room"}
                  </h2>
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${socketConnected ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`} />
                    <span className="text-xs text-slate-400">{socketConnected ? "Connected" : "Disconnected"}</span>
                  </div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                  {/* Create Room */}
                  <div className="space-y-3">
                    <label className="block text-xs font-medium text-slate-400 uppercase tracking-wider">Create Room</label>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-[10px] text-slate-500 mb-1">Small Blind</label>
                        <input type="number" value={newRoomSB} min={1} onChange={(e) => { const v = Math.max(1, Number(e.target.value)); setNewRoomSB(v); setNewRoomBB(Math.max(v + 1, v * 2)); setNewRoomBuyInMin(v * 40); setNewRoomBuyInMax(v * 300); }} className="input-field w-full text-xs !py-1.5 text-center" />
                      </div>
                      <div>
                        <label className="block text-[10px] text-slate-500 mb-1">Big Blind</label>
                        <input type="number" value={newRoomBB} min={newRoomSB + 1} onChange={(e) => setNewRoomBB(Math.max(newRoomSB + 1, Number(e.target.value)))} className="input-field w-full text-xs !py-1.5 text-center" />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-[10px] text-slate-500 mb-1">Buy-in Min</label>
                        <input type="number" value={newRoomBuyInMin} min={1} onChange={(e) => setNewRoomBuyInMin(Math.max(1, Number(e.target.value)))} className="input-field w-full text-xs !py-1.5 text-center" />
                      </div>
                      <div>
                        <label className="block text-[10px] text-slate-500 mb-1">Buy-in Max</label>
                        <input type="number" value={newRoomBuyInMax} min={newRoomBuyInMin} onChange={(e) => setNewRoomBuyInMax(Math.max(newRoomBuyInMin, Number(e.target.value)))} className="input-field w-full text-xs !py-1.5 text-center" />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-[10px] text-slate-500 mb-1">Max Players</label>
                        <select value={newRoomMaxPlayers} onChange={(e) => setNewRoomMaxPlayers(Number(e.target.value))} className="input-field w-full text-xs !py-1.5">
                          {[2,3,4,5,6,7,8,9].map(n => <option key={n} value={n}>{n} players</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="block text-[10px] text-slate-500 mb-1">Room Type</label>
                        <div className="flex gap-1">
                          <button onClick={() => setNewRoomVisibility("public")}
                            className={`flex-1 py-1.5 rounded-lg text-[10px] font-semibold transition-all ${
                              newRoomVisibility === "public"
                                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                                : "bg-white/5 text-slate-400 border border-white/10"
                            }`}>🌐 Public</button>
                          <button onClick={() => setNewRoomVisibility("private")}
                            className={`flex-1 py-1.5 rounded-lg text-[10px] font-semibold transition-all ${
                              newRoomVisibility === "private"
                                ? "bg-amber-500/20 text-amber-400 border border-amber-500/40"
                                : "bg-white/5 text-slate-400 border border-white/10"
                            }`}>🔒 Private</button>
                        </div>
                      </div>
                    </div>
                    <div className="text-[10px] text-slate-500 text-center py-1 rounded-lg bg-white/[0.02]">
                      {newRoomMaxPlayers}-max · Blinds {newRoomSB}/{newRoomBB} · Buy-in {newRoomBuyInMin.toLocaleString()}–{newRoomBuyInMax.toLocaleString()}
                    </div>
                    {newRoomBB <= newRoomSB && <p className="text-[10px] text-red-400 text-center">Big blind must be greater than small blind</p>}
                    {newRoomBuyInMax < newRoomBuyInMin && <p className="text-[10px] text-red-400 text-center">Max buy-in must be ≥ min buy-in</p>}
                    <button 
                      onClick={() => {
                        if (!socket) { showToast("Not connected to server"); return; }
                        if (newRoomBB <= newRoomSB) { showToast("Big blind must be greater than small blind"); return; }
                        if (newRoomBuyInMax < newRoomBuyInMin) { showToast("Max buy-in must be ≥ min buy-in"); return; }
                        socket.emit("create_room", {
                          roomName: `${newRoomSB}/${newRoomBB} NLH`,
                          maxPlayers: newRoomMaxPlayers,
                          smallBlind: newRoomSB,
                          bigBlind: newRoomBB,
                          buyInMin: newRoomBuyInMin,
                          buyInMax: newRoomBuyInMax,
                          visibility: newRoomVisibility,
                        });
                        showToast("Creating room...");
                      }} 
                      disabled={!socket || newRoomBB <= newRoomSB || newRoomBuyInMax < newRoomBuyInMin}
                      className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed">
                      Create Room
                    </button>
                  </div>

                  {/* Join by Code */}
                  <div className="space-y-3">
                    <label className="block text-xs font-medium text-slate-400 uppercase tracking-wider">Join by Code</label>
                    <input
                      value={roomCodeInput}
                      onChange={(e) => setRoomCodeInput(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ""))}
                      onKeyDown={(e) => { if (e.key === "Enter" && roomCodeInput.length >= 4) { socket?.emit("join_room_code", { roomCode: roomCodeInput }); showToast("Joining room..."); } }}
                      placeholder="Enter room code"
                      maxLength={8}
                      className="input-field w-full uppercase tracking-[0.3em] text-center font-mono text-lg !py-3" />
                    <button
                      onClick={() => {
                        if (!roomCodeInput.trim()) { showToast("Please enter a room code"); return; }
                        socket?.emit("join_room_code", { roomCode: roomCodeInput });
                        showToast("Joining room...");
                      }}
                      disabled={!socket || !roomCodeInput.trim()}
                      className="btn-success w-full disabled:opacity-50 disabled:cursor-not-allowed">
                      Join Room
                    </button>
                  </div>
                </div>
              </div>

              {/* ── Room List ── */}
              <div className="glass-card p-6">
                <div className="flex items-center justify-between mb-5">
                  <h2 className="text-lg font-bold text-white">Open Rooms</h2>
                  <button onClick={() => socket?.emit("request_lobby")} className="btn-ghost text-xs !py-1.5 !px-3">Refresh</button>
                </div>
                {lobbyRooms.length === 0 ? (
                  <div className="text-center py-12">
                    <div className="text-4xl mb-3 opacity-30">🎴</div>
                    <p className="text-slate-500 text-sm">No open rooms yet</p>
                    <p className="text-slate-600 text-xs mt-1">Create one to get started!</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {lobbyRooms.map((r) => (
                      <div key={r.tableId} className="flex items-center justify-between p-4 rounded-xl bg-white/[0.03] border border-white/5 hover:border-white/10 transition-all group">
                        <div className="flex items-center gap-4">
                          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-emerald-500/20 to-emerald-700/20 border border-emerald-500/20 flex items-center justify-center text-emerald-400 text-sm font-bold">{r.playerCount}</div>
                          <div>
                            <div className="font-medium text-white text-sm">{r.roomName}</div>
                            <div className="text-xs text-slate-500 mt-0.5">
                              <span className="font-mono text-amber-400/70">{r.roomCode}</span>
                              <span className="mx-2">·</span>{r.playerCount}/{r.maxPlayers} players
                              <span className="mx-2">·</span>Blinds {r.smallBlind}/{r.bigBlind}
                            </div>
                          </div>
                        </div>
                        <button onClick={() => { socket?.emit("join_room_code", { roomCode: r.roomCode }); showToast("Joining room..."); }} className="btn-primary text-xs !py-2 !px-4 opacity-70 group-hover:opacity-100">Join</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </main>
        ) : (
          /* ═══════ TABLE VIEW ═══════ */
          <>
            <main className="flex-1 flex flex-col overflow-hidden">
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
                  <p className="text-xs text-red-400">Server not connected — run <code className="bg-white/10 px-1 rounded">./dev.sh start</code></p>
                </div>
              )}

              {/* ── Controls Strip ── */}
              <div className="px-3 py-1.5 flex flex-wrap items-center gap-2 border-b border-white/5 shrink-0">
                <input value={name} onChange={(e) => setName(e.target.value)} className="input-field !py-1 !px-2 w-24 text-xs" placeholder="Name" />
                <button
                  disabled={dealDisabledReason != null}
                  onClick={() => {
                    if (dealDisabledReason) {
                      showToast(dealDisabledReason);
                      return;
                    }
                    socket?.emit("start_hand", { tableId });
                  }}
                  className="text-[11px] px-2.5 py-1 rounded-lg bg-blue-500/20 text-blue-400 border border-blue-500/30 hover:bg-blue-500/30 disabled:opacity-40 transition-all"
                  title={dealDisabledReason ?? "Deal a new hand"}
                >
                  {isHost ? "Deal" : "Deal (Host)"}
                </button>
                <button disabled={!isConnected} onClick={() => socket?.emit("stand_up", { tableId, seat })} className="text-[11px] px-2.5 py-1 rounded-lg bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10 disabled:opacity-40 transition-all" title="Stand up from seat">Stand</button>
                <button onClick={leaveRoom} className="text-[11px] px-2.5 py-1 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-all" title="Leave room entirely">Exit</button>
                {roomState?.settings.rebuyAllowed && (
                  <button disabled={!isConnected} onClick={() => {
                    const bb = roomState?.settings.bigBlind ?? 100;
                    setDepositAmount(bb * 100);
                    setShowDepositModal(true);
                  }} className="text-[11px] px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 disabled:opacity-40 transition-all" title="Request additional chips">Rebuy</button>
                )}

                <button onClick={() => setDisplayBB(!displayBB)}
                  className={`text-[10px] px-2 py-0.5 rounded-lg border transition-all ${displayBB ? "bg-amber-500/15 text-amber-400 border-amber-500/30" : "bg-white/5 text-slate-400 border-white/10 hover:bg-white/10"}`}>
                  {displayBB ? "BB" : "$"}
                </button>

                {roomState && (
                  <>
                    <div className="w-px h-4 bg-white/10" />
                    <span className="text-[10px] text-slate-500">{roomState.settings.smallBlind}/{roomState.settings.bigBlind} · {roomState.settings.maxPlayers}-max</span>
                    <span className="text-[10px] text-slate-500">Timer {roomState.settings.actionTimerSeconds}s</span>
                    {roomState.status === "PAUSED" && <span className="text-[10px] text-red-400 font-bold animate-pulse">PAUSED</span>}
                    {snapshot?.pendingPause && <span className="text-[10px] text-amber-400 font-semibold animate-pulse">Pausing after hand…</span>}
                  </>
                )}

                {currentRoomCode && (
                  <span className="ml-auto flex items-center gap-2 text-[10px] text-slate-500">
                    {roomState?.settings.visibility === "private" && <span className="text-amber-400">🔒</span>}
                    <span className="font-mono text-amber-400 font-bold tracking-wider">{currentRoomCode}</span>
                    <button onClick={copyCode} className="text-slate-500 hover:text-white transition-colors" title="Copy room code">📋</button>
                  </span>
                )}

                {/* Host Controls */}
                {isHostOrCoHost && (
                  <>
                    <div className="w-px h-4 bg-white/10" />
                    <span className="text-[9px] text-amber-400 font-bold uppercase">👑 {isHost ? "Host" : "Co-Host"}</span>
                    {roomState?.status === "PAUSED" ? (
                      <button onClick={() => socket?.emit("game_control", { tableId, action: "resume" })} className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20">▶</button>
                    ) : (
                      <button onClick={() => socket?.emit("game_control", { tableId, action: "pause" })} className="text-[10px] px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20">⏸</button>
                    )}
                    <button onClick={() => socket?.emit("game_control", { tableId, action: "end" })} className="text-[10px] px-2 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20" title="Stop auto-deal">■</button>
                    {isHost && (
                      <button onClick={() => { if (confirm("Are you sure you want to close the room? All players will be returned to the lobby.")) { socket?.emit("close_room", { tableId }); } }}
                        className="text-[10px] px-2 py-0.5 rounded bg-red-600/20 text-red-300 border border-red-500/30 hover:bg-red-600/30 font-semibold" title="Close room permanently">
                        Close Room
                      </button>
                    )}
                    <button onClick={() => setShowSettings(!showSettings)} className="text-[10px] px-2 py-0.5 rounded bg-white/5 text-slate-300 border border-white/10 hover:bg-white/10">⚙</button>
                    <button onClick={() => setShowRoomLog(!showRoomLog)} className="text-[10px] px-2 py-0.5 rounded bg-white/5 text-slate-300 border border-white/10 hover:bg-white/10">📋</button>
                    {roomState?.settings.roomFundsTracking ? (
                      <button onClick={() => { setShowSessionStats(!showSessionStats); if (!showSessionStats) socket?.emit("request_session_stats", { tableId }); }}
                        className={`text-[10px] px-2 py-0.5 rounded border hover:bg-white/10 ${showSessionStats ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/30" : "bg-white/5 text-slate-300 border-white/10"}`}
                        title="Session Stats">📊</button>
                    ) : (
                      <span className="text-[9px] text-slate-600" title="Enable Room funds tracking in settings to view stats">Funds tracking off</span>
                    )}
                    {seatRequests.length > 0 ? (
                      <button className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-bold animate-pulse">
                        🎫 {seatRequests.length} Request{seatRequests.length > 1 ? "s" : ""}
                      </button>
                    ) : (
                      <span className="text-[9px] text-slate-600">No requests</span>
                    )}
                  </>
                )}

              </div>

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
                  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setShowBuyInModal(false)}>
                    <div className="glass-card p-6 w-80 space-y-4" onClick={(e) => e.stopPropagation()}>
                      <h3 className="text-sm font-bold text-white text-center">Choose Buy-in</h3>
                      <div className="text-center">
                        <span className="text-3xl font-bold text-amber-400 font-mono">{buyInAmount.toLocaleString()}</span>
                        <div className="text-[10px] text-slate-500 mt-1">{(buyInAmount / bb).toFixed(0)} BB</div>
                      </div>
                      <input type="range" min={biMin} max={biMax} step={buyInStep} value={buyInAmount}
                        onChange={(e) => setBuyInAmount(snapBuyIn(Number(e.target.value)))}
                        className="w-full h-2 rounded-full appearance-none bg-white/10 accent-amber-500 cursor-pointer" />
                      <div className="flex justify-between text-[10px] text-slate-500">
                        <span>{biMin.toLocaleString()}</span>
                        <span>{biMax.toLocaleString()}</span>
                      </div>
                      {/* Quick presets */}
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
                      <div className="flex gap-2">
                        <button onClick={() => setShowBuyInModal(false)}
                          className="flex-1 py-2 rounded-lg text-xs font-medium bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10 transition-all">Cancel</button>
                        <button onClick={() => {
                          const canSitDirectly = isHostOrCoHost;
                          debugLog("[BUY_IN_MODAL] Sit button clicked. canSitDirectly:", canSitDirectly, "isHostOrCoHost:", isHostOrCoHost);
                          
                          if (canSitDirectly) {
                            // Host/Creator auto-sits directly
                            debugLog("[BUY_IN_MODAL] Emitting sit_down (host)");
                            socket?.emit("sit_down", { tableId, seat: pendingSitSeat, buyIn: buyInAmount, name });
                          } else {
                            // Non-host sends a request for host approval
                            debugLog("[BUY_IN_MODAL] Emitting seat_request (guest)");
                            socket?.emit("seat_request", { tableId, seat: pendingSitSeat, buyIn: buyInAmount, name });
                          }
                          // Sticky rebuy: remember buy-in per room
                          try { if (currentRoomCode) localStorage.setItem(`cardpilot_buyin_${currentRoomCode}`, String(buyInAmount)); } catch { /* ignore */ }
                          setShowBuyInModal(false);
                        }} className="flex-1 py-2 rounded-lg text-xs font-semibold bg-gradient-to-r from-emerald-500 to-emerald-600 text-white shadow-lg shadow-emerald-900/30 hover:from-emerald-400 hover:to-emerald-500 transition-all">
                          {isHostOrCoHost ? "Sit Down" : "Request Seat"}
                        </button>
                      </div>
                      <p className="text-[9px] text-slate-600 text-center">
                        Seat #{pendingSitSeat} · Blinds {settings?.smallBlind ?? 1}/{bb}
                        {!isHostOrCoHost && " · Requires host approval"}
                      </p>
                    </div>
                  </div>
                );
              })()}

              {/* ── Deposit Modal ── */}
              {showDepositModal && (() => {
                const settings = roomState?.settings;
                const bb = settings?.bigBlind ?? 100;
                const myPlayer = snapshot?.players.find((p) => p.seat === seat);
                const maxDeposit = Math.max(0, (settings?.buyInMax ?? 20000) - (myPlayer?.stack ?? 0));
                const minDeposit = Math.max(bb, 1);
                return (
                  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setShowDepositModal(false)}>
                    <div className="glass-card p-5 w-72 space-y-3" onClick={(e) => e.stopPropagation()}>
                      <h3 className="text-sm font-bold text-emerald-400 text-center">Request Deposit</h3>
                      <div className="text-center">
                        <span className="text-2xl font-bold text-emerald-400 font-mono">{depositAmount.toLocaleString()}</span>
                        <div className="text-[10px] text-slate-500 mt-0.5">{(depositAmount / bb).toFixed(0)} BB</div>
                      </div>
                      <input type="range" min={minDeposit} max={maxDeposit} step={bb} value={Math.min(depositAmount, maxDeposit)}
                        onChange={(e) => setDepositAmount(Number(e.target.value))}
                        className="w-full h-2 rounded-full appearance-none bg-white/10 accent-emerald-500 cursor-pointer" />
                      <div className="flex justify-between text-[10px] text-slate-500">
                        <span>{minDeposit.toLocaleString()}</span>
                        <span>{maxDeposit.toLocaleString()}</span>
                      </div>
                      <div className="flex gap-2">
                        <button onClick={() => setShowDepositModal(false)}
                          className="flex-1 py-2 rounded-lg text-xs font-medium bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10 transition-all">Cancel</button>
                        <button disabled={depositAmount <= 0 || depositAmount > maxDeposit} onClick={() => {
                          socket?.emit("deposit_request", { tableId, amount: depositAmount });
                          setShowDepositModal(false);
                        }} className="flex-1 py-2 rounded-lg text-xs font-semibold bg-gradient-to-r from-emerald-500 to-emerald-600 text-white shadow-lg shadow-emerald-900/30 hover:from-emerald-400 hover:to-emerald-500 transition-all disabled:opacity-40">
                          Request
                        </button>
                      </div>
                      <p className="text-[9px] text-slate-600 text-center">Host must approve · Credited at next hand start</p>
                    </div>
                  </div>
                );
              })()}

              {/* ── Deposit Notifications (Host Only) ── */}
              {isHostOrCoHost && depositNotifications.length > 0 && (
                <div className="mx-3 mt-1 shrink-0">
                  <div className="glass-card p-3 border border-cyan-500/30 bg-cyan-500/5">
                    <h3 className="text-xs font-bold text-cyan-400 mb-2">Deposit Requests ({depositNotifications.length})</h3>
                    <div className="space-y-1.5">
                      {depositNotifications.map((d) => (
                        <div key={d.orderId} className="flex items-center gap-2 p-2 rounded-lg bg-black/20 border border-cyan-500/10">
                          <div className="flex-1 text-[10px]">
                            <span className="text-white font-medium">{d.userName}</span>
                            <span className="text-slate-500"> (Seat {d.seat})</span>
                            <span className="text-cyan-400 font-mono ml-1">+{d.amount.toLocaleString()}</span>
                          </div>
                          <button onClick={() => {
                            socket?.emit("approve_deposit", { tableId, orderId: d.orderId });
                            setDepositNotifications((prev) => prev.filter((x) => x.orderId !== d.orderId));
                          }} className="px-2 py-1 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30">✓</button>
                          <button onClick={() => {
                            socket?.emit("reject_deposit", { tableId, orderId: d.orderId });
                            setDepositNotifications((prev) => prev.filter((x) => x.orderId !== d.orderId));
                          }} className="px-2 py-1 rounded text-[10px] font-semibold bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30">✗</button>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* ── Seat Request Panel (Host Only) ── */}
              {isHostOrCoHost && seatRequests.length > 0 && (
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
                              Buy-in: <span className="text-amber-400 font-semibold">{req.buyIn.toLocaleString()}</span>
                              {displayBB && <span className="text-slate-500 ml-1">({(req.buyIn / (snapshot?.bigBlind ?? 3)).toFixed(1)}bb)</span>}
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

              {/* Settings / Log panels (overlay-style, max-height constrained) */}
              {showSettings && isHostOrCoHost && roomState && (
                <div className="mx-3 mt-1 max-h-[70vh] overflow-y-auto shrink-0">
                  <RoomSettingsPanel
                    roomState={roomState}
                    isHost={!!isHost}
                    players={snapshot?.players ?? []}
                    authUserId={authSession?.userId ?? ""}
                    onUpdateSettings={(settings: Record<string, unknown>) => socket?.emit("update_settings", { tableId, settings })}
                    onKick={(targetUserId: string, reason: string, ban: boolean) => socket?.emit("kick_player", { tableId, targetUserId, reason, ban })}
                    onTransfer={(newOwnerId: string) => socket?.emit("transfer_ownership", { tableId, newOwnerId })}
                    onSetCoHost={(userId: string, add: boolean) => socket?.emit("set_cohost", { tableId, userId, add })}
                    onClose={() => setShowSettings(false)}
                  />
                </div>
              )}
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

              {/* ── Session Stats Panel ── */}
              {showSessionStats && roomState?.settings.roomFundsTracking && (
                <div className="mx-3 mt-1 glass-card p-3 max-h-48 overflow-y-auto shrink-0">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-xs font-bold text-cyan-400">Session Stats</h3>
                    <div className="flex items-center gap-2">
                      <button onClick={() => socket?.emit("request_session_stats", { tableId })} className="text-[9px] text-slate-400 hover:text-white">↻ Refresh</button>
                      <button onClick={() => setShowSessionStats(false)} className="text-xs text-slate-500 hover:text-white">✕</button>
                    </div>
                  </div>
                  {sessionStatsData.length === 0 ? (
                    <p className="text-[10px] text-slate-500 text-center py-2">No session data yet</p>
                  ) : (
                    <table className="w-full text-[10px]">
                      <thead>
                        <tr className="text-slate-500 border-b border-white/5">
                          <th className="text-left py-1 font-medium">Seat</th>
                          <th className="text-left py-1 font-medium">Player</th>
                          <th className="text-right py-1 font-medium">Deposited</th>
                          <th className="text-right py-1 font-medium">Stack</th>
                          <th className="text-right py-1 font-medium">Net</th>
                          <th className="text-right py-1 font-medium">Hands</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sessionStatsData.map((e) => (
                          <tr key={e.userId} className="border-b border-white/5 last:border-0">
                            <td className="py-1 text-slate-400">{e.seat ?? "—"}</td>
                            <td className="py-1 text-slate-200 font-medium truncate max-w-[100px]">{e.name}</td>
                            <td className="py-1 text-right text-slate-400 font-mono">{e.totalBuyIn.toLocaleString()}</td>
                            <td className="py-1 text-right text-slate-300 font-mono">{e.currentStack.toLocaleString()}</td>
                            <td className={`py-1 text-right font-mono font-semibold ${e.net > 0 ? "text-emerald-400" : e.net < 0 ? "text-red-400" : "text-slate-400"}`}>
                              {e.net > 0 ? "+" : ""}{e.net.toLocaleString()}
                            </td>
                            <td className="py-1 text-right text-slate-500">{e.handsPlayed}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}

              {/* ── CENTER: TABLE + SIDEBAR ── */}
              <div className="flex-1 flex overflow-hidden min-h-0">
                {/* Table area */}
                <div className="flex-1 flex flex-col items-center justify-center p-2 overflow-hidden">
                  {/* Info strip */}
                  <div className="w-full max-w-2xl flex items-center justify-between mb-1 px-1 shrink-0">
                    <div className="flex items-center gap-3">
                      <InfoCell label="Hand" value={snapshot?.handId ? snapshot.handId.slice(0, 8) : "—"} />
                      <div className="w-px h-5 bg-white/10" />
                      <InfoCell label="Street" value={snapshot?.street ?? "—"} highlight />
                      <div className="w-px h-5 bg-white/10" />
                      <InfoCell label="Action" value={
                        snapshot?.actorSeat != null
                          ? (snapshot.actorSeat === seat ? "▶ Your turn" : `Seat ${snapshot.actorSeat} (${snapshot.players.find(p => p.seat === snapshot.actorSeat)?.name ?? "?"})`)
                          : "—"
                      } cyan />
                    </div>
                    <div className="flex items-center gap-4">
                      {/* Hero bet this street */}
                      {snapshot?.handId && (() => {
                        const me = snapshot.players.find(p => p.seat === seat);
                        return me && me.streetCommitted > 0 ? (
                          <div className="text-right">
                            <span className="text-[9px] text-slate-500 uppercase tracking-wider">You Bet</span>
                            <div className="text-sm font-bold text-sky-400">{displayBB ? `${(me.streetCommitted / (snapshot.bigBlind ?? 3)).toFixed(1)}bb` : me.streetCommitted.toLocaleString()}</div>
                          </div>
                        ) : null;
                      })()}
                      <div className="text-right">
                        <span className="text-[9px] text-slate-500 uppercase tracking-wider">Pot</span>
                        <div className="text-lg font-extrabold text-amber-400">{displayBB ? `${((snapshot?.pot ?? 0) / (snapshot?.bigBlind ?? 3)).toFixed(1)}bb` : (snapshot?.pot ?? 0).toLocaleString()}</div>
                      </div>
                    </div>
                  </div>

                  {/* Table image + overlays — constrained size */}
                  <div className="relative w-full max-w-2xl select-none shrink" style={{ background: "#111827" }}>
                    <img src="/poker-table.png" alt="Table" className="w-full h-auto" style={{ mixBlendMode: "lighten" }} draggable={false} />

                    {/* Community cards — centered on table (supports run-it-twice dual boards) */}
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none" style={{ top: "-2%" }}>
                      {snapshot?.runoutBoards && snapshot.runoutBoards.length === 2 ? (
                        /* Run-it-twice: two rows of community cards */
                        <div className="flex flex-col gap-1 items-center pointer-events-auto" style={{ width: "36%" }}>
                          {snapshot.runoutBoards.map((board, runIdx) => (
                            <div key={runIdx} className="flex items-center gap-0.5 w-full">
                              <span className={`text-[7px] font-bold uppercase shrink-0 w-6 text-center ${runIdx === 0 ? "text-cyan-400" : "text-amber-400"}`}>
                                R{runIdx + 1}
                              </span>
                              <div className="flex gap-0.5 flex-1">
                                {board.map((c, i) => (
                                  <CardImg key={i} card={c} className="flex-1 min-w-0 max-w-[44px] rounded shadow-lg" />
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        /* Standard single board */
                        <div className="flex gap-1 pointer-events-auto" style={{ width: "32%" }}>
                          {snapshot?.board && snapshot.board.length > 0
                            ? snapshot.board.map((c, i) => <CardImg key={i} card={c} className="flex-1 min-w-0 max-w-[56px] rounded shadow-lg" />)
                            : Array.from({ length: 5 }).map((_, i) => (
                                <div key={i} className="flex-1 min-w-0 max-w-[56px] aspect-[2.5/3.5] rounded border border-dashed border-white/15 bg-white/[0.04]" />
                              ))}
                        </div>
                      )}
                    </div>

                    {/* Pot chip on table */}
                    {(snapshot?.pot ?? 0) > 0 && (
                      <div className="absolute top-[32%] left-1/2 -translate-x-1/2 pointer-events-none">
                        <div className="bg-black/70 px-2 py-0.5 rounded-full text-amber-400 font-bold text-[10px] shadow-lg">
                          {displayBB ? `${((snapshot?.pot ?? 0) / (snapshot?.bigBlind ?? 3)).toFixed(1)}bb` : (snapshot?.pot ?? 0).toLocaleString()}
                        </div>
                      </div>
                    )}

                    {/* Player seats */}
                    {seatElements}
                  </div>

                  {/* Hole cards — rendered in normal flow below the table image to avoid overlapping timer/buttons */}
                  {holeCards.length > 0 && (
                    <div className="flex items-center justify-center gap-1.5 py-1 flex-wrap">
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
                      {holeCards.map((c, i) => <CardImg key={i} card={c} className="w-14 rounded-lg shadow-lg border border-white/10" />)}
                    </div>
                  )}

                  {/* Settlement Overlay (replaces old winners overlay) */}
                  {settlement ? (
                    <SettlementOverlay
                      settlement={settlement}
                      players={snapshot?.players ?? []}
                      autoStartScheduled={!autoStartBlockReason && (roomState?.settings.autoStartNextHand ?? true)}
                      autoStartBlockReason={autoStartBlockReason}
                      countdownSeconds={settlementCountdown}
                      onDismiss={() => { setSettlement(null); setWinners(null); }}
                      onDealNow={isHost ? () => { socket?.emit("start_hand", { tableId }); setSettlement(null); setWinners(null); } : undefined}
                      isHost={!!isHost}
                      getCardImagePath={getCardImagePath}
                    />
                  ) : winners && winners.length > 0 && (
                    <div className="w-full max-w-2xl mt-2 shrink-0 animate-[fadeSlideUp_0.5s_ease-out]">
                      <div className="relative rounded-2xl border border-amber-500/30 bg-gradient-to-b from-amber-500/10 via-black/60 to-black/80 backdrop-blur-md px-6 py-4 shadow-[0_0_30px_rgba(245,158,11,0.15)]">
                        <div className="flex items-center justify-center gap-2 mb-3">
                          <span className="text-2xl">🏆</span>
                          <span className="text-amber-400 text-lg font-extrabold tracking-wide uppercase">
                            {winners.length > 1 ? "Winners" : "Winner"}
                          </span>
                          <span className="text-2xl">🏆</span>
                        </div>
                        <div className="flex flex-col items-center gap-2">
                          {winners.map((w) => {
                            const p = snapshot?.players.find((pl) => pl.seat === w.seat);
                            return (
                              <div key={w.seat} className="flex items-center gap-3 px-5 py-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 animate-[fadeSlideUp_0.6s_ease-out]">
                                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-sm font-extrabold text-slate-900 shadow-lg">
                                  {(p?.name ?? `S${w.seat}`)[0].toUpperCase()}
                                </div>
                                <div className="flex flex-col">
                                  <span className="text-white font-bold text-sm">{p?.name ?? `Seat ${w.seat}`}</span>
                                  {w.handName && <span className="text-slate-400 text-xs">{w.handName}</span>}
                                </div>
                                <span className="text-amber-400 font-extrabold text-xl ml-2 animate-[pulse_1.5s_ease-in-out_infinite]">
                                  +{w.amount.toLocaleString()}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                        <div className="text-center mt-3">
                          <span className="text-[10px] text-slate-500">Next hand in a few seconds...</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* ── GTO SIDEBAR — collapsible ── */}
                <aside className={`border-l border-white/5 overflow-y-auto hidden lg:flex flex-col shrink-0 transition-all duration-200 ${showGtoSidebar ? "w-72 xl:w-80 p-2" : "w-8 p-1"}`}>
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

                {/* ── Mobile GTO Pill + Drawer (visible on < lg only) ── */}
                <div className="lg:hidden">
                  {/* Floating GTO pill */}
                  {!showMobileGto && (
                    <button
                      onClick={() => setShowMobileGto(true)}
                      aria-label="Open GTO Coach"
                      className={`fixed bottom-24 right-3 z-40 flex items-center gap-1.5 px-3 py-2 rounded-full shadow-lg transition-all ${
                        advice ? "bg-gradient-to-r from-amber-500 to-orange-500 text-white animate-[pulse_2s_ease-in-out_infinite]" : "bg-slate-800 text-slate-400 border border-white/10"
                      }`}
                    >
                      <div className="w-5 h-5 rounded-md bg-white/20 flex items-center justify-center text-[9px] font-extrabold shrink-0">G</div>
                      <span className="text-xs font-semibold">GTO</span>
                      {advice?.recommended && <span className="text-[10px] font-bold uppercase bg-white/20 px-1.5 py-0.5 rounded-full">{advice.recommended}</span>}
                    </button>
                  )}

                  {/* Slide-in drawer from right */}
                  {showMobileGto && (
                    <div className="fixed inset-0 z-50 flex justify-end" onClick={() => setShowMobileGto(false)}>
                      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
                      <div
                        className="gto-drawer relative w-72 max-w-[85vw] bg-[#0f1724] border-l border-white/10 p-4 overflow-y-auto"
                        onClick={(e) => e.stopPropagation()}
                      >
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
              </div>

              {/* ── ACTIONS (pinned to bottom, compact) — only when seated & hand active ── */}
              {snapshot?.handId && snapshot.players.some((p) => p.seat === seat) && (
              <div className="shrink-0 px-3 pb-1.5 pt-1">
                <ActionBar
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
                  numPlayers={snapshot?.players.filter((p) => p.inHand && !p.folded).length ?? 2}
                  advice={advice}
                  thinkExtensionEnabled={(roomState?.settings.thinkExtensionQuotaPerHour ?? 0) > 0}
                  thinkExtensionRemainingUses={thinkExtensionRemainingUses}
                  onThinkExtension={() => socket?.emit("request_think_extension", { tableId })}
                  actionPending={actionPending}
                  onAction={(action, amount) => {
                    if (!snapshot?.handId) return;
                    if (actionPending) return;
                    setActionPending(true);
                    if (action === "all_in") {
                      socket?.emit("action_submit", { tableId, handId: snapshot.handId, action: "all_in" });
                      return;
                    }
                    socket?.emit("action_submit", { tableId, handId: snapshot.handId, action, amount });
                  }}
                />

                {isMyShowdownDecision && snapshot?.handId && (
                  <div className="mt-2 p-3 rounded-xl border border-indigo-500/30 bg-indigo-500/10">
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div className="text-[10px] uppercase tracking-wider text-indigo-200">Showdown Decision</div>
                      {!myIsWinner && (roomState?.settings.autoMuckLosingHands ?? true) && !myRevealedCards && !myIsMucked && (
                        <div className="text-[10px] text-slate-300">Auto-muck in ~4s</div>
                      )}
                    </div>
                    {myRevealedCards ? (
                      <div className="text-xs text-emerald-300">Your hand is revealed to the table.</div>
                    ) : myIsMucked ? (
                      <div className="text-xs text-slate-300">You mucked your hand.</div>
                    ) : (
                      <div className="flex gap-2">
                        <button
                          onClick={() => socket?.emit("show_hand", { tableId, handId: snapshot.handId!, seat, scope: "table" })}
                          className="btn-action flex-1 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600"
                        >
                          SHOW
                        </button>
                        <button
                          onClick={() => socket?.emit("muck_hand", { tableId, handId: snapshot.handId!, seat })}
                          className="btn-action flex-1 bg-white/10 border border-white/20 text-slate-200 hover:bg-white/15"
                        >
                          MUCK
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {allInPrompt && snapshot?.handId && allInPrompt.actorSeat === seat && (
                  <div className="mt-2 p-3 rounded-xl border border-orange-500/30 bg-orange-500/10">
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div>
                        <div className="text-[10px] uppercase tracking-wider text-orange-300">All-In Runout Choice</div>
                        <div className="text-xs text-slate-200">Your equity: <span className="font-mono text-orange-300 font-bold">{Math.round(allInPrompt.winRate * 100)}%</span></div>
                      </div>
                      <div className="text-[10px] text-slate-400 max-w-[60%] text-right">{allInPrompt.reason}</div>
                    </div>

                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          socket?.emit("run_count_submit", { tableId, handId: snapshot.handId, runCount: 1 });
                          setAllInPrompt(null);
                        }}
                        className="btn-action flex-1 bg-gradient-to-r from-orange-600 to-orange-700 hover:from-orange-500 hover:to-orange-600"
                      >
                        Run Once
                      </button>
                      <button
                        onClick={() => {
                          socket?.emit("run_count_submit", { tableId, handId: snapshot.handId, runCount: 2 });
                          setAllInPrompt(null);
                        }}
                        className="btn-action flex-1 bg-gradient-to-r from-amber-600 to-amber-700 hover:from-amber-500 hover:to-amber-600"
                      >
                        Run Twice
                      </button>
                    </div>
                  </div>
                )}

                {/* Waiting banner: shown to non-prompted players during all-in decision */}
                {snapshot?.allInPrompt && snapshot.allInPrompt.actorSeat !== seat && seat != null && snapshot.players.some((p) => p.seat === seat && p.inHand) && (
                  <div className="mt-2 px-3 py-2 rounded-xl border border-amber-500/20 bg-amber-500/5 text-center">
                    <span className="text-[10px] text-amber-300 animate-pulse">
                      Waiting for Seat {snapshot.allInPrompt.actorSeat} to choose run count…
                    </span>
                  </div>
                )}
              </div>
              )}
            </main>
          </>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════ PROFILE PAGE ═══════════════════ */
const AVATAR_COLORS = [
  "from-cyan-500 to-blue-600",
  "from-amber-400 to-orange-500",
  "from-emerald-400 to-green-600",
  "from-purple-400 to-violet-600",
  "from-rose-400 to-pink-600",
  "from-teal-400 to-cyan-600",
];

const PROFILE_STORAGE_KEY = "cardpilot_profile";

type UserPreferences = {
  gameType: "NLH" | "PLO";
  blindLevel: string;
  tableType: "6-max" | "9-max";
  currency: string;
  avatarColor: number;
  betPresets: {
    flop: [number, number, number];
    turn: [number, number, number];
    river: [number, number, number];
  };
  dataRetention: boolean;
};

const DEFAULT_PREFS: UserPreferences = {
  gameType: "NLH",
  blindLevel: "50/100",
  tableType: "6-max",
  currency: "Chips",
  avatarColor: 0,
  betPresets: {
    flop: [33, 66, 100],
    turn: [50, 75, 125],
    river: [50, 100, 200],
  },
  dataRetention: true,
};

function loadPrefs(): UserPreferences {
  try {
    const raw = localStorage.getItem(PROFILE_STORAGE_KEY);
    if (raw) return { ...DEFAULT_PREFS, ...JSON.parse(raw) };
  } catch { /* ignore */ }
  return { ...DEFAULT_PREFS };
}

function savePrefs(prefs: UserPreferences): void {
  try { localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(prefs)); } catch { /* ignore */ }
}

function ProfilePage({ displayName, setDisplayName, email, authSession }: {
  displayName: string;
  setDisplayName: (n: string) => void;
  email: string | null;
  authSession: AuthSession | null;
}) {
  const [prefs, setPrefs] = useState<UserPreferences>(loadPrefs);
  const [editName, setEditName] = useState(displayName);
  const [saved, setSaved] = useState(false);

  function updatePref<K extends keyof UserPreferences>(key: K, value: UserPreferences[K]) {
    const next = { ...prefs, [key]: value };
    setPrefs(next);
    savePrefs(next);
  }

  function handleSaveName() {
    const trimmed = editName.trim();
    if (!trimmed) return;
    setDisplayName(trimmed);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
    // Persist to Supabase in background
    if (supabase && authSession && !authSession.userId.startsWith("guest-")) {
      supabase.auth.updateUser({ data: { display_name: trimmed } }).catch(() => {});
    }
  }

  return (
    <main className="flex-1 p-6 overflow-y-auto">
      <div className="max-w-2xl mx-auto space-y-6">
        <h2 className="text-2xl font-bold text-white">Profile</h2>

        {/* Avatar + Name */}
        <div className="glass-card p-6">
          <div className="flex items-start gap-6">
            <div className="flex flex-col items-center gap-2">
              <div className={`w-20 h-20 rounded-full bg-gradient-to-br ${AVATAR_COLORS[prefs.avatarColor]} flex items-center justify-center text-3xl font-bold text-white uppercase shadow-lg`}>
                {displayName[0]}
              </div>
              <div className="flex gap-1 mt-1">
                {AVATAR_COLORS.map((c, i) => (
                  <button key={i} onClick={() => updatePref("avatarColor", i)}
                    className={`w-5 h-5 rounded-full bg-gradient-to-br ${c} border-2 transition-all ${
                      prefs.avatarColor === i ? "border-white scale-110" : "border-transparent opacity-60 hover:opacity-100"
                    }`} />
                ))}
              </div>
            </div>
            <div className="flex-1 space-y-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Display Name</label>
                <div className="flex gap-2">
                  <input value={editName} onChange={(e) => setEditName(e.target.value)} className="input-field flex-1" maxLength={32} />
                  <button onClick={handleSaveName} className="btn-primary text-sm !py-2 !px-4">Save</button>
                </div>
                {saved && <p className="text-xs text-emerald-400">Name updated!</p>}
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Email</label>
                <p className="text-sm text-slate-300">{email || "Guest account"}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Game Preferences */}
        <div className="glass-card p-6 space-y-5">
          <h3 className="text-lg font-bold text-white">Game Preferences</h3>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Game Type</label>
              <div className="flex gap-1 bg-white/5 rounded-xl p-1">
                {(["NLH", "PLO"] as const).map((g) => (
                  <button key={g} onClick={() => updatePref("gameType", g)}
                    className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all ${prefs.gameType === g ? "bg-white/10 text-white" : "text-slate-400 hover:text-slate-200"}`}>
                    {g}
                  </button>
                ))}
              </div>
            </div>
            {/* Table Type removed - host decides this when creating room */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Blind Level</label>
              <select value={prefs.blindLevel} onChange={(e) => updatePref("blindLevel", e.target.value)} className="input-field w-full">
                {["1/2", "2/5", "5/10", "10/20", "25/50", "50/100"].map((b) => <option key={b} value={b}>{b}</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Currency</label>
              <select value={prefs.currency} onChange={(e) => updatePref("currency", e.target.value)} className="input-field w-full">
                {["Chips", "USD", "EUR", "GBP", "TWD"].map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>
        </div>

        {/* Bet Size Presets */}
        <div className="glass-card p-6 space-y-4">
          <h3 className="text-lg font-bold text-white">Custom Bet Size Presets</h3>
          <p className="text-xs text-slate-400">Set your preferred bet sizes as % of pot for each street.</p>
          {(["flop", "turn", "river"] as const).map((street) => (
            <div key={street} className="space-y-1.5">
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">{street}</label>
              <div className="flex gap-2">
                {prefs.betPresets[street].map((val, i) => (
                  <div key={i} className="flex items-center gap-1">
                    <input type="number" value={val} min={1} max={500}
                      onChange={(e) => {
                        const next = [...prefs.betPresets[street]] as [number, number, number];
                        next[i] = Number(e.target.value) || 0;
                        updatePref("betPresets", { ...prefs.betPresets, [street]: next });
                      }}
                      className="input-field w-20 text-center text-sm" />
                    <span className="text-xs text-slate-500">%</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Data Retention */}
        <div className="glass-card p-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-bold text-white">Data Retention</h3>
              <p className="text-xs text-slate-400 mt-1">Hand history is server-authored and visible by room permissions. Toggle this to hide local preference data only.</p>
            </div>
            <button onClick={() => updatePref("dataRetention", !prefs.dataRetention)}
              className={`relative w-12 h-7 rounded-full transition-colors ${prefs.dataRetention ? "bg-emerald-500" : "bg-slate-600"}`}>
              <div className={`absolute top-0.5 w-6 h-6 rounded-full bg-white shadow transition-transform ${prefs.dataRetention ? "translate-x-5" : "translate-x-0.5"}`} />
            </button>
          </div>
          {prefs.dataRetention && (
            <div className="mt-3 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-400">
              Local client preferences are stored in your browser. Hand history is stored on the server and follows room visibility rules.
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

/* ═══════════════════ HISTORY PAGE ═══════════════════ */
function HistoryPage({ socket, isConnected }: { socket: Socket | null; isConnected: boolean }) {
  const [rooms, setRooms] = useState<HistoryRoomSummary[]>([]);
  const [sessions, setSessions] = useState<HistorySessionSummary[]>([]);
  const [hands, setHands] = useState<HistoryHandSummary[]>([]);
  const [selectedRoomId, setSelectedRoomId] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [selectedHandId, setSelectedHandId] = useState("");
  const [detailById, setDetailById] = useState<Record<string, HistoryHandDetail>>({});
  const [loadingRooms, setLoadingRooms] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingHands, setLoadingHands] = useState(false);
  const [loadingMoreHands, setLoadingMoreHands] = useState(false);
  const [loadingDetailId, setLoadingDetailId] = useState("");
  const [hasMoreHands, setHasMoreHands] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);

  const selectedRoomRef = useRef(selectedRoomId);
  const selectedSessionRef = useRef(selectedSessionId);
  const pendingHandsRequestRef = useRef<{ roomSessionId: string; beforeEndedAt?: string } | null>(null);

  useEffect(() => { selectedRoomRef.current = selectedRoomId; }, [selectedRoomId]);
  useEffect(() => { selectedSessionRef.current = selectedSessionId; }, [selectedSessionId]);

  const requestRooms = useCallback(() => {
    if (!socket) return;
    setLoadingRooms(true);
    socket.emit("request_history_rooms", { limit: 100 });
  }, [socket]);

  const requestSessions = useCallback((roomId: string) => {
    if (!socket || !roomId) return;
    setLoadingSessions(true);
    socket.emit("request_history_sessions", { roomId, limit: 200 });
  }, [socket]);

  const requestHands = useCallback((roomSessionId: string, beforeEndedAt?: string) => {
    if (!socket || !roomSessionId) return;
    if (beforeEndedAt) {
      setLoadingMoreHands(true);
    } else {
      setLoadingHands(true);
    }
    pendingHandsRequestRef.current = { roomSessionId, beforeEndedAt };
    socket.emit("request_history_hands", { roomSessionId, limit: 40, beforeEndedAt });
  }, [socket]);

  useEffect(() => {
    if (!socket) return;

    const onHistoryRooms = (payload: { rooms: HistoryRoomSummary[] }) => {
      setLoadingRooms(false);
      const nextRooms = payload.rooms ?? [];
      setRooms(nextRooms);
      setSelectedRoomId((current) => {
        if (current && nextRooms.some((room) => room.roomId === current)) return current;
        return nextRooms[0]?.roomId ?? "";
      });
    };

    const onHistorySessions = (payload: { roomId: string; sessions: HistorySessionSummary[] }) => {
      if (payload.roomId !== selectedRoomRef.current) return;
      setLoadingSessions(false);
      const nextSessions = payload.sessions ?? [];
      setSessions(nextSessions);
      setSelectedSessionId((current) => {
        if (current && nextSessions.some((session) => session.roomSessionId === current)) return current;
        return nextSessions[0]?.roomSessionId ?? "";
      });
    };

    const onHistoryHands = (payload: { roomSessionId: string; hands: HistoryHandSummary[]; hasMore: boolean; nextCursor?: string }) => {
      if (payload.roomSessionId !== selectedSessionRef.current) return;
      setLoadingHands(false);
      setLoadingMoreHands(false);

      const pending = pendingHandsRequestRef.current;
      const append = pending?.roomSessionId === payload.roomSessionId && !!pending.beforeEndedAt;

      setHands((current) => {
        if (!append) return payload.hands ?? [];
        const seen = new Set(current.map((hand) => hand.id));
        const merged = [...current];
        for (const hand of payload.hands ?? []) {
          if (!seen.has(hand.id)) {
            merged.push(hand);
            seen.add(hand.id);
          }
        }
        return merged;
      });
      setHasMoreHands(Boolean(payload.hasMore));
      setNextCursor(payload.nextCursor ?? null);
    };

    const onHistoryHandDetail = (payload: { handHistoryId: string; hand: HistoryHandDetail | null }) => {
      if (payload.hand) {
        setDetailById((current) => ({ ...current, [payload.handHistoryId]: payload.hand! }));
      }
      setLoadingDetailId((current) => (current === payload.handHistoryId ? "" : current));
    };

    socket.on("history_rooms", onHistoryRooms);
    socket.on("history_sessions", onHistorySessions);
    socket.on("history_hands", onHistoryHands);
    socket.on("history_hand_detail", onHistoryHandDetail);

    return () => {
      socket.off("history_rooms", onHistoryRooms);
      socket.off("history_sessions", onHistorySessions);
      socket.off("history_hands", onHistoryHands);
      socket.off("history_hand_detail", onHistoryHandDetail);
    };
  }, [socket]);

  useEffect(() => {
    if (!socket || !isConnected) return;
    requestRooms();
  }, [socket, isConnected, requestRooms]);

  useEffect(() => {
    setSessions([]);
    setSelectedSessionId("");
    setHands([]);
    setSelectedHandId("");
    setHasMoreHands(false);
    setNextCursor(null);
    if (!selectedRoomId) return;
    requestSessions(selectedRoomId);
  }, [selectedRoomId, requestSessions]);

  useEffect(() => {
    setHands([]);
    setSelectedHandId("");
    setHasMoreHands(false);
    setNextCursor(null);
    if (!selectedSessionId) return;
    requestHands(selectedSessionId);
  }, [selectedSessionId, requestHands]);

  const selectedHand = selectedHandId ? detailById[selectedHandId] ?? null : null;

  return (
    <main className="flex-1 p-4 overflow-hidden">
      <div className="h-full flex flex-col gap-3">
        <div className="glass-card p-4 flex items-center gap-3">
          <h2 className="text-xl font-bold text-white">Hand History by Room</h2>
          <span className="text-xs text-slate-500">Summary lists are lightweight; details load on demand.</span>
          <button onClick={requestRooms} className="btn-ghost text-xs !py-1.5 !px-3 ml-auto">Refresh</button>
        </div>

        {!isConnected || !socket ? (
          <div className="glass-card p-8 text-center text-slate-400 text-sm">Connect to the game server to load hand history.</div>
        ) : (
          <div className="min-h-0 flex-1 grid grid-cols-1 lg:grid-cols-[260px_320px_minmax(0,1fr)] gap-3">
            <section className="glass-card min-h-0 p-3 flex flex-col">
              <div className="text-xs text-slate-400 uppercase tracking-wider mb-2">Rooms</div>
              <div className="min-h-0 overflow-y-auto space-y-1.5">
                {loadingRooms ? (
                  <p className="text-xs text-slate-500 py-2">Loading rooms…</p>
                ) : rooms.length === 0 ? (
                  <p className="text-xs text-slate-500 py-2">No visible room history.</p>
                ) : (
                  rooms.map((room) => (
                    <button
                      key={room.roomId}
                      onClick={() => setSelectedRoomId(room.roomId)}
                      className={`w-full text-left p-2 rounded-lg border transition-all ${
                        selectedRoomId === room.roomId ? "bg-amber-500/10 border-amber-500/30" : "bg-white/[0.02] border-white/5 hover:border-white/20"
                      }`}
                    >
                      <div className="text-sm font-semibold text-white truncate">{room.roomName}</div>
                      <div className="text-[10px] text-slate-500 mt-0.5">
                        <span className="font-mono text-amber-400/80">{room.roomCode}</span>
                        <span className="mx-1.5">·</span>
                        {room.totalHands} hands
                      </div>
                      <div className="text-[10px] text-slate-600 mt-0.5">Last: {formatHistoryDateTime(room.lastPlayedAt)}</div>
                    </button>
                  ))
                )}
              </div>
            </section>

            <section className="glass-card min-h-0 p-3 flex flex-col">
              <div className="text-xs text-slate-400 uppercase tracking-wider mb-2">Sessions</div>
              <div className="min-h-0 overflow-y-auto space-y-1.5">
                {selectedRoomId.length === 0 ? (
                  <p className="text-xs text-slate-500 py-2">Select a room.</p>
                ) : loadingSessions ? (
                  <p className="text-xs text-slate-500 py-2">Loading sessions…</p>
                ) : sessions.length === 0 ? (
                  <p className="text-xs text-slate-500 py-2">No sessions available.</p>
                ) : (
                  sessions.map((session, idx) => {
                    const currentDay = historyDayKey(session.openedAt);
                    const prevDay = idx > 0 ? historyDayKey(sessions[idx - 1].openedAt) : "";
                    return (
                      <div key={session.roomSessionId}>
                        {idx === 0 || currentDay !== prevDay ? (
                          <div className="text-[10px] text-slate-600 uppercase tracking-wider mt-2 mb-1">
                            {new Date(session.openedAt).toLocaleDateString()}
                          </div>
                        ) : null}
                        <button
                          onClick={() => setSelectedSessionId(session.roomSessionId)}
                          className={`w-full text-left p-2 rounded-lg border transition-all ${
                            selectedSessionId === session.roomSessionId ? "bg-cyan-500/10 border-cyan-500/30" : "bg-white/[0.02] border-white/5 hover:border-white/20"
                          }`}
                        >
                          <div className="text-xs text-white font-medium">
                            {formatHistoryTime(session.openedAt)} - {session.closedAt ? formatHistoryTime(session.closedAt) : "Open"}
                          </div>
                          <div className="text-[10px] text-slate-500 mt-0.5">{session.handCount} visible hands</div>
                        </button>
                      </div>
                    );
                  })
                )}
              </div>
            </section>

            <section className="glass-card min-h-0 p-3 flex flex-col">
              <div className="text-xs text-slate-400 uppercase tracking-wider mb-2">Hands</div>
              <div className="min-h-0 overflow-y-auto space-y-1.5">
                {selectedSessionId.length === 0 ? (
                  <p className="text-xs text-slate-500 py-2">Select a session.</p>
                ) : loadingHands ? (
                  <p className="text-xs text-slate-500 py-2">Loading hands…</p>
                ) : hands.length === 0 ? (
                  <p className="text-xs text-slate-500 py-2">No hands in this session.</p>
                ) : (
                  hands.map((hand) => (
                    <button
                      key={hand.id}
                      onClick={() => {
                        setSelectedHandId(hand.id);
                        if (!detailById[hand.id] && socket) {
                          setLoadingDetailId(hand.id);
                          socket.emit("request_history_hand_detail", { handHistoryId: hand.id });
                        }
                      }}
                      className="w-full text-left p-2.5 rounded-lg border border-white/5 bg-white/[0.02] hover:border-amber-500/30 transition-all"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-sm text-white font-semibold">Hand #{hand.handNo}</div>
                        <div className="text-[10px] text-slate-500">{formatHistoryTime(hand.endedAt)}</div>
                      </div>
                      <div className="text-[11px] text-slate-400 mt-1">
                        Pot {hand.summary.totalPot.toLocaleString()} · Blinds {hand.blinds.sb}/{hand.blinds.bb}
                        <span className="mx-1.5">·</span>
                        {hand.summary.flags.runItTwice ? "Run it twice" : "Single run"}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-1 truncate">
                        {hand.summary.winners.length > 0
                          ? hand.summary.winners.map((winner) => {
                              const player = hand.players.find((p) => p.seat === winner.seat);
                              return `${player?.name ?? `Seat ${winner.seat}`} +${winner.amount}`;
                            }).join(" · ")
                          : "No winner data"}
                      </div>
                    </button>
                  ))
                )}
              </div>
              {selectedSessionId && hasMoreHands && (
                <button
                  onClick={() => nextCursor && requestHands(selectedSessionId, nextCursor)}
                  disabled={loadingMoreHands || !nextCursor}
                  className="mt-2 btn-ghost text-xs !py-1.5 disabled:opacity-50"
                >
                  {loadingMoreHands ? "Loading…" : "Load more"}
                </button>
              )}
            </section>
          </div>
        )}
      </div>

      {selectedHandId && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-3" onClick={() => setSelectedHandId("")}>
          <div className="glass-card w-full max-w-4xl max-h-[92vh] overflow-y-auto p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white">Hand Detail</h3>
              <button onClick={() => setSelectedHandId("")} className="btn-ghost text-xs !py-1 !px-2">Close</button>
            </div>
            {!selectedHand && loadingDetailId === selectedHandId ? (
              <p className="text-sm text-slate-400">Loading hand detail…</p>
            ) : selectedHand ? (
              <HistoryHandDetailView hand={selectedHand} />
            ) : (
              <p className="text-sm text-slate-400">Hand detail is not available.</p>
            )}
          </div>
        </div>
      )}
    </main>
  );
}

function HistoryHandDetailView({ hand }: { hand: HistoryHandDetail }) {
  return (
    <div className="space-y-4">
      <div className="glass-card p-3">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="font-semibold text-white">Hand #{hand.handNo}</span>
          <span className="text-slate-400">Ended {formatHistoryDateTime(hand.endedAt)}</span>
          <span className="text-slate-400">Pot {hand.summary.totalPot.toLocaleString()}</span>
          <span className="text-slate-400">Blinds {hand.blinds.sb}/{hand.blinds.bb}</span>
        </div>
      </div>

      <div className="glass-card p-3 space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Boards</h4>
        {(hand.detail.runoutBoards.length > 0 ? hand.detail.runoutBoards : [hand.detail.board]).map((board, idx) => (
          <div key={idx} className="flex items-center gap-2">
            {hand.detail.runoutBoards.length > 1 && <span className="text-[10px] text-slate-500 w-7">Run {idx + 1}</span>}
            <div className="flex gap-1.5">
              {board.map((card, cardIdx) => <CardImg key={cardIdx} card={card} className="w-9 h-13 rounded shadow" />)}
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="glass-card p-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Pot Breakdown</h4>
          <div className="space-y-1.5">
            {hand.detail.potLayers.map((layer, idx) => (
              <div key={idx} className="text-xs text-slate-300 flex items-center justify-between">
                <span>{layer.label}</span>
                <span className="font-mono text-amber-300">{layer.amount.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="glass-card p-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Payout Ledger</h4>
          <div className="space-y-1.5">
            {hand.detail.payoutLedger.map((entry) => (
              <div key={entry.seat} className="text-xs flex items-center justify-between">
                <span className="text-slate-300">{entry.playerName}</span>
                <span className={`font-mono ${entry.net >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                  {entry.net >= 0 ? "+" : ""}{entry.net.toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="glass-card p-3">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Action Timeline</h4>
        <div className="space-y-1.5 max-h-64 overflow-y-auto">
          {hand.detail.actionTimeline.map((action, idx) => (
            <div key={`${action.seat}-${action.at}-${idx}`} className="text-xs flex items-center gap-2">
              <span className="text-slate-500 w-10">{action.street}</span>
              <span className="text-slate-500 w-12">Seat {action.seat}</span>
              <span className={`uppercase font-semibold ${
                action.type === "fold" ? "text-slate-400" :
                action.type === "raise" || action.type === "all_in" ? "text-red-400" :
                action.type === "call" ? "text-blue-400" :
                action.type === "check" ? "text-emerald-400" :
                "text-slate-300"
              }`}>
                {action.type}
              </span>
              {action.amount > 0 && <span className="text-slate-400 font-mono">{action.amount.toLocaleString()}</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function historyDayKey(value: string): string {
  const d = new Date(value);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function formatHistoryDateTime(value: string): string {
  return new Date(value).toLocaleString([], { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatHistoryTime(value: string): string {
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/* ═══════════════════ ROOM SETTINGS PANEL (Host-only) ═══════════════════ */
function RoomSettingsPanel({ roomState, isHost, players, authUserId, onUpdateSettings, onKick, onTransfer, onSetCoHost, onClose }: {
  roomState: RoomFullState;
  isHost: boolean;
  players: TablePlayer[];
  authUserId: string;
  onUpdateSettings: (settings: Record<string, unknown>) => void;
  onKick: (targetUserId: string, reason: string, ban: boolean) => void;
  onTransfer: (newOwnerId: string) => void;
  onSetCoHost: (userId: string, add: boolean) => void;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<"game" | "rules" | "special" | "players" | "moderation">("game");
  const [kickReason, setKickReason] = useState("");

  const s = roomState.settings;

  function updateField(key: string, value: unknown) {
    onUpdateSettings({ [key]: value });
  }

  /* ── Blind structure helpers ── */
  const [blindLevels, setBlindLevels] = useState(
    s.blindStructure ?? [{ smallBlind: s.smallBlind, bigBlind: s.bigBlind, ante: s.ante, durationMinutes: 20 }]
  );

  function addBlindLevel() {
    const last = blindLevels[blindLevels.length - 1];
    const next = { smallBlind: last.smallBlind * 2, bigBlind: last.bigBlind * 2, ante: last.ante, durationMinutes: last.durationMinutes };
    const updated = [...blindLevels, next];
    setBlindLevels(updated);
    updateField("blindStructure", updated);
  }

  function removeBlindLevel(idx: number) {
    if (blindLevels.length <= 1) return;
    const updated = blindLevels.filter((_, i) => i !== idx);
    setBlindLevels(updated);
    updateField("blindStructure", updated);
  }

  function updateBlindLevel(idx: number, field: string, value: number) {
    const updated = blindLevels.map((lvl, i) => i === idx ? { ...lvl, [field]: value } : lvl);
    setBlindLevels(updated);
    updateField("blindStructure", updated);
    if (idx === 0) {
      if (field === "smallBlind") updateField("smallBlind", value);
      if (field === "bigBlind") updateField("bigBlind", value);
      if (field === "ante") updateField("ante", value);
    }
  }

  const SectionTitle = ({ children }: { children: React.ReactNode }) => (
    <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mt-2 mb-1">{children}</div>
  );

  const YesNo = ({ label, value, onChange, hint }: { label: string; value: boolean; onChange: (v: boolean) => void; hint?: string }) => (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-1.5 min-w-0">
        <span className="text-xs text-slate-400 truncate">{label}</span>
        {hint && <span className="text-[9px] text-slate-600 cursor-help" title={hint}>?</span>}
      </div>
      <div className="flex gap-1 shrink-0">
        <button onClick={() => onChange(true)}
          className={`text-xs px-3 py-1.5 rounded-l-md border transition-all ${value ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-400 font-semibold" : "bg-white/5 border-white/10 text-slate-500"}`}>
          Yes
        </button>
        <button onClick={() => onChange(false)}
          className={`text-xs px-3 py-1.5 rounded-r-md border transition-all ${!value ? "bg-red-500/10 border-red-500/20 text-red-400 font-semibold" : "bg-white/5 border-white/10 text-slate-500"}`}>
          No
        </button>
      </div>
    </div>
  );

  const TriToggle = ({ label, value, options, onChange }: { label: string; value: string; options: { value: string; label: string }[]; onChange: (v: string) => void }) => (
    <div className="space-y-1">
      <span className="text-xs text-slate-400">{label}</span>
      <div className="flex gap-1">
        {options.map((opt) => (
          <button key={opt.value} onClick={() => onChange(opt.value)}
            className={`flex-1 text-xs px-3 py-2 rounded-md border transition-all ${value === opt.value ? "bg-white/10 border-white/20 text-white font-semibold" : "bg-white/5 border-white/10 text-slate-500"}`}>
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <div className="glass-card p-6 space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-bold text-white">Room Settings <span className="text-xs text-amber-400 font-normal ml-1">(Host Only)</span></h3>
        <button onClick={onClose} className="text-xs text-slate-500 hover:text-white transition-colors">✕</button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-white/5 rounded-lg p-1 overflow-x-auto">
        {([
          { key: "game" as const, label: "Blinds" },
          { key: "rules" as const, label: "Rules" },
          { key: "special" as const, label: "Special" },
          { key: "players" as const, label: "Players" },
          { key: "moderation" as const, label: "Mod" },
        ]).map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`flex-1 px-3 py-2 rounded-md text-xs font-medium transition-all whitespace-nowrap ${tab === t.key ? "bg-white/10 text-white" : "text-slate-400 hover:text-white"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ══ BLINDS & STRUCTURE TAB ══ */}
      {tab === "game" && (
        <div className="space-y-3">
          <SectionTitle>Poker Variant</SectionTitle>
          <SettingRow label="Game Type">
            <select value={s.gameType} onChange={(e) => updateField("gameType", e.target.value)} className="input-field text-xs !py-1.5">
              <option value="texas">No Limit Texas Hold'em</option>
              <option value="omaha">Pot Limit Omaha</option>
            </select>
          </SettingRow>
          <SettingRow label="Max Players">
            <select value={s.maxPlayers} onChange={(e) => updateField("maxPlayers", Number(e.target.value))} className="input-field text-xs !py-1.5 w-20">
              {[2, 3, 4, 5, 6, 7, 8, 9].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </SettingRow>

          <SectionTitle>Blind Levels</SectionTitle>
          <div className="space-y-2">
            {/* Header row */}
            <div className="grid grid-cols-[2rem_1fr_1fr_1fr_1fr_1.5rem] gap-1 text-[9px] text-slate-500 uppercase tracking-wider px-1">
              <span>#</span><span>SB</span><span>BB</span><span>Ante</span><span>Min</span><span></span>
            </div>
            {blindLevels.map((lvl, i) => (
              <div key={i} className="grid grid-cols-[2rem_1fr_1fr_1fr_1fr_1.5rem] gap-1 items-center">
                <span className="text-[10px] text-slate-500 text-center">{i + 1}</span>
                <input type="number" value={lvl.smallBlind} min={1}
                  onChange={(e) => updateBlindLevel(i, "smallBlind", Number(e.target.value))}
                  className="input-field text-[11px] !py-1 w-full text-center" />
                <input type="number" value={lvl.bigBlind} min={2}
                  onChange={(e) => updateBlindLevel(i, "bigBlind", Number(e.target.value))}
                  className="input-field text-[11px] !py-1 w-full text-center" />
                <input type="number" value={lvl.ante} min={0}
                  onChange={(e) => updateBlindLevel(i, "ante", Number(e.target.value))}
                  className="input-field text-[11px] !py-1 w-full text-center" />
                <input type="number" value={lvl.durationMinutes} min={1}
                  onChange={(e) => updateBlindLevel(i, "durationMinutes", Number(e.target.value))}
                  className="input-field text-[11px] !py-1 w-full text-center" />
                <button onClick={() => removeBlindLevel(i)}
                  className="text-[10px] text-slate-600 hover:text-red-400 transition-colors text-center leading-none"
                  title="Remove level">×</button>
              </div>
            ))}
            <button onClick={addBlindLevel}
              className="w-full text-[10px] py-1.5 rounded-md border border-dashed border-white/10 text-slate-400 hover:text-white hover:border-white/20 transition-all">
              + Add Level
            </button>
          </div>

          <SectionTitle>Buy-in</SectionTitle>
          <div className="grid grid-cols-2 gap-3">
            <SettingRow label="Min">
              <input type="number" value={s.buyInMin} onChange={(e) => updateField("buyInMin", Number(e.target.value))} className="input-field text-xs !py-1.5 w-full" />
            </SettingRow>
            <SettingRow label="Max">
              <input type="number" value={s.buyInMax} onChange={(e) => updateField("buyInMax", Number(e.target.value))} className="input-field text-xs !py-1.5 w-full" />
            </SettingRow>
          </div>
        </div>
      )}

      {/* ══ GAME RULES TAB ══ */}
      {tab === "rules" && (
        <div className="space-y-3">
          <SectionTitle>Hand Flow</SectionTitle>
          <YesNo
            label="Auto-start next hand?"
            value={s.autoStartNextHand}
            onChange={(v) => updateField("autoStartNextHand", v)}
            hint="Automatically starts the next hand after showdown delay"
          />
          <TriToggle
            label="Showdown speed"
            value={s.showdownSpeed}
            options={[
              { value: "fast", label: "Fast (3s)" },
              { value: "normal", label: "Normal (6s)" },
              { value: "slow", label: "Slow (9s)" },
            ]}
            onChange={(v) => updateField("showdownSpeed", v)}
          />
          <YesNo
            label="Deal to away players?"
            value={s.dealToAwayPlayers}
            onChange={(v) => updateField("dealToAwayPlayers", v)}
            hint="When off, disconnected/away seats are excluded from auto-deal eligibility"
          />
          <YesNo
            label="Reveal all at showdown?"
            value={s.revealAllAtShowdown}
            onChange={(v) => updateField("revealAllAtShowdown", v)}
            hint="Force reveal on river-call or all-in runouts"
          />
          <YesNo
            label="Room funds tracking?"
            value={s.roomFundsTracking}
            onChange={(v) => updateField("roomFundsTracking", v)}
            hint="Tracks per-player buy-ins, net and stack restoration across rejoin"
          />

          <SectionTitle>Gameplay</SectionTitle>
          <TriToggle label="Allow Run It Twice?"
            value={s.runItTwiceMode}
            options={[
              { value: "always", label: "Always" },
              { value: "ask_players", label: "Ask Players" },
              { value: "off", label: "No" },
            ]}
            onChange={(v) => { updateField("runItTwiceMode", v); updateField("runItTwice", v !== "off"); }}
          />
          <YesNo
            label="Auto reveal on all-in + called?"
            value={s.autoRevealOnAllInCall}
            onChange={(v) => updateField("autoRevealOnAllInCall", v)}
            hint="Reveal live players' hole cards when no more betting decisions remain"
          />
          <YesNo
            label="Allow show after fold?"
            value={s.allowShowAfterFold}
            onChange={(v) => updateField("allowShowAfterFold", v)}
            hint="Folded players may voluntarily reveal before hand end"
          />
          <YesNo label="Allow UTG Straddle 2BB?" value={s.straddleAllowed} onChange={(v) => updateField("straddleAllowed", v)} />
          <YesNo label="Rebuy allowed?" value={s.rebuyAllowed} onChange={(v) => updateField("rebuyAllowed", v)} />

          <SectionTitle>Timers</SectionTitle>
          <div className="grid grid-cols-2 gap-3">
            <SettingRow label="Decision Time (sec)">
              <input type="number" value={s.actionTimerSeconds} onChange={(e) => updateField("actionTimerSeconds", Number(e.target.value))} className="input-field text-xs !py-1.5 w-full" min={5} max={120} />
            </SettingRow>
            <SettingRow label="Time Bank (sec)">
              <input type="number" value={s.timeBankSeconds} onChange={(e) => updateField("timeBankSeconds", Number(e.target.value))} className="input-field text-xs !py-1.5 w-full" min={0} max={300} />
            </SettingRow>
          </div>
          <SettingRow label="Hands to fill Time Bank">
            <input type="number" value={s.timeBankHandsToFill} onChange={(e) => updateField("timeBankHandsToFill", Number(e.target.value))} className="input-field text-xs !py-1.5 w-24" min={1} max={50} />
          </SettingRow>
          <div className="grid grid-cols-2 gap-3">
            <SettingRow label="Extension/Use (sec)">
              <input type="number" value={s.thinkExtensionSecondsPerUse} onChange={(e) => updateField("thinkExtensionSecondsPerUse", Number(e.target.value))} className="input-field text-xs !py-1.5 w-full" min={1} max={60} />
            </SettingRow>
            <SettingRow label="Extension Quota (/hr)">
              <input type="number" value={s.thinkExtensionQuotaPerHour} onChange={(e) => updateField("thinkExtensionQuotaPerHour", Number(e.target.value))} className="input-field text-xs !py-1.5 w-full" min={0} max={20} />
            </SettingRow>
          </div>
        </div>
      )}

      {/* ══ SPECIAL FEATURES TAB ══ */}
      {tab === "special" && (
        <div className="space-y-3">
          <SectionTitle>Bomb Pot</SectionTitle>
          <YesNo label="Bomb Pot enabled?" value={s.bombPotEnabled} onChange={(v) => updateField("bombPotEnabled", v)}
            hint="All players put in a set amount pre-flop with no betting" />
          {s.bombPotEnabled && (
            <SettingRow label="Frequency (every N hands, 0=manual)">
              <input type="number" value={s.bombPotFrequency} onChange={(e) => updateField("bombPotFrequency", Number(e.target.value))} className="input-field text-xs !py-1.5 w-20" min={0} max={100} />
            </SettingRow>
          )}

          <SectionTitle>Double Board</SectionTitle>
          <TriToggle label="Double Board?"
            value={s.doubleBoardMode}
            options={[
              { value: "always", label: "Always" },
              { value: "bomb_pot", label: "Bomb Pot Only" },
              { value: "off", label: "Off" },
            ]}
            onChange={(v) => updateField("doubleBoardMode", v)}
          />

          <SectionTitle>7-2 Bounty</SectionTitle>
          <SettingRow label="Bounty amount (0 = off)">
            <input type="number" value={s.sevenTwoBounty} onChange={(e) => updateField("sevenTwoBounty", Number(e.target.value))} className="input-field text-xs !py-1.5 w-24" min={0} />
          </SettingRow>
          {s.sevenTwoBounty > 0 && (
            <p className="text-[10px] text-slate-500">Each player pays {s.sevenTwoBounty} to the winner holding 7-2</p>
          )}
        </div>
      )}

      {/* ══ PLAYERS TAB ══ */}
      {tab === "players" && (
        <div className="space-y-2">
          <p className="text-[10px] text-slate-500">Owner: <span className="text-amber-400 font-medium">{roomState.ownership.ownerName}</span></p>
          {players.length === 0 ? (
            <p className="text-xs text-slate-500 text-center py-4">No players seated</p>
          ) : (
            players.map((p) => {
              const isMe = p.userId === authUserId;
              const isPlayerOwner = p.userId === roomState.ownership.ownerId;
              const isPlayerCoHost = roomState.ownership.coHostIds.includes(p.userId);
              return (
                <div key={p.seat} className="flex items-center gap-3 p-2 rounded-lg bg-white/[0.03] border border-white/5">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-slate-600 to-slate-700 flex items-center justify-center text-xs font-bold text-white">{p.seat}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-white truncate">{p.name}</span>
                      {isPlayerOwner && <span className="text-[9px] bg-amber-500/20 text-amber-400 px-1 rounded">👑 Host</span>}
                      {isPlayerCoHost && <span className="text-[9px] bg-blue-500/20 text-blue-400 px-1 rounded">⭐ Co-Host</span>}
                      {isMe && <span className="text-[9px] bg-cyan-500/20 text-cyan-400 px-1 rounded">You</span>}
                    </div>
                    <span className="text-[10px] text-slate-500">{p.stack.toLocaleString()} chips</span>
                  </div>
                  {!isMe && !isPlayerOwner && (
                    <div className="flex gap-1 shrink-0">
                      {isHost && (
                        <button onClick={() => onSetCoHost(p.userId, !isPlayerCoHost)}
                          className="text-[10px] px-2 py-1 rounded bg-white/5 text-slate-400 hover:text-white transition-colors">
                          {isPlayerCoHost ? "Remove Co-Host" : "Make Co-Host"}
                        </button>
                      )}
                      {isHost && (
                        <button onClick={() => onTransfer(p.userId)}
                          className="text-[10px] px-2 py-1 rounded bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 transition-colors">
                          Transfer Host
                        </button>
                      )}
                      <button onClick={() => onKick(p.userId, kickReason, false)}
                        className="text-[10px] px-2 py-1 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors">
                        Kick
                      </button>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}

      {/* ══ MODERATION TAB ══ */}
      {tab === "moderation" && (
        <div className="space-y-3">
          <SettingRow label="Room Visibility">
            <select value={s.visibility} onChange={(e) => updateField("visibility", e.target.value)} className="input-field text-xs !py-1.5">
              <option value="public">Public</option>
              <option value="private">Private</option>
            </select>
          </SettingRow>
          {s.visibility === "private" && (
            <SettingRow label="Password">
              <input type="text" value={s.password ?? ""} onChange={(e) => updateField("password", e.target.value || null)} className="input-field text-xs !py-1.5 w-40" placeholder="Set password..." />
            </SettingRow>
          )}
          <SettingRow label="Kick Reason">
            <input value={kickReason} onChange={(e) => setKickReason(e.target.value)} className="input-field text-xs !py-1.5 w-full" placeholder="Optional reason for kicks..." />
          </SettingRow>
          <SettingRow label="Max Consecutive Timeouts">
            <input type="number" value={s.maxConsecutiveTimeouts} onChange={(e) => updateField("maxConsecutiveTimeouts", Number(e.target.value))} className="input-field text-xs !py-1.5 w-20" min={1} max={10} />
          </SettingRow>
          <SettingRow label="Disconnect Grace (sec)">
            <input type="number" value={s.disconnectGracePeriod} onChange={(e) => updateField("disconnectGracePeriod", Number(e.target.value))} className="input-field text-xs !py-1.5 w-20" min={5} max={120} />
          </SettingRow>

          {/* Ban list */}
          {roomState.banList.length > 0 && (
            <div>
              <span className="text-[10px] text-slate-500 uppercase font-medium">Banned Users ({roomState.banList.length})</span>
              <div className="mt-1 flex flex-wrap gap-1">
                {roomState.banList.map((uid) => (
                  <span key={uid} className="text-[10px] bg-red-500/10 text-red-400 px-2 py-0.5 rounded">{uid.slice(0, 8)}...</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SettingRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-xs text-slate-400 shrink-0">{label}</span>
      {children}
    </div>
  );
}

function ToggleSetting({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={`text-[11px] px-3 py-1.5 rounded-lg border transition-all ${
        checked ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" : "bg-white/5 border-white/10 text-slate-500"
      }`}
    >
      {checked ? "✓ " : ""}{label}
    </button>
  );
}

/* ═══════════════════ ONBOARDING MODAL ═══════════════════ */
function OnboardingModal({ onComplete }: { onComplete: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass-card p-8 w-full max-w-md mx-4 space-y-6">
        <div className="space-y-5 text-center">
          <div className="text-4xl">🚀</div>
          <h2 className="text-xl font-bold text-white">You're All Set!</h2>
          <p className="text-sm text-slate-400">Head to the lobby to create or join a room and start playing. The host will decide the table settings.</p>
          <button onClick={onComplete} className="btn-success w-full !py-3 text-base font-bold">Start Playing</button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════ AUTH SCREEN COMPONENT ═══════════════════ */
function AuthScreen({ onAuth }: { onAuth: (s: AuthSession) => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [authDisplayName, setAuthDisplayName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [successMsg, setSuccessMsg] = useState("");
  const [cooldown, setCooldown] = useState(0);

  /* Cooldown countdown timer */
  useEffect(() => {
    const secs = getRateLimitSecondsLeft();
    if (secs > 0) setCooldown(secs);
    if (cooldown <= 0) return;
    const t = setInterval(() => {
      const left = getRateLimitSecondsLeft();
      setCooldown(left);
      if (left <= 0) clearInterval(t);
    }, 1000);
    return () => clearInterval(t);
  }, [cooldown]);

  /* Real-time validation hints */
  const emailHint = email ? validateEmail(email) : null;
  const pwHint = password ? validatePassword(password) : null;
  const confirmHint = mode === "signup" && confirmPw && confirmPw !== password ? "Passwords do not match." : null;

  const nameHint = mode === "signup" && authDisplayName.length > 0 && authDisplayName.trim().length < 2 ? "Name must be at least 2 characters." : null;

  const formValid =
    !emailHint && !pwHint && !confirmHint && !nameHint &&
    email.length > 0 && password.length > 0 &&
    (mode === "login" || (confirmPw === password && authDisplayName.trim().length >= 2));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setSuccessMsg("");

    if (!formValid) {
      setError(emailHint || pwHint || confirmHint || "Please fill in all fields correctly.");
      return;
    }

    setLoading(true);
    try {
      if (mode === "signup") {
        const session = await signUpWithEmail(email, password, authDisplayName.trim());
        onAuth(session);
      } else {
        const session = await signInWithEmail(email, password);
        onAuth(session);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("Check your email")) {
        setSuccessMsg(msg);
      } else {
        setError(msg);
      }
      /* Refresh cooldown in case rate limiter kicked in */
      const secs = getRateLimitSecondsLeft();
      if (secs > 0) setCooldown(secs);
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogleSignIn() {
    setError("");
    setSuccessMsg("");
    setLoading(true);
    try {
      await signInWithGoogle();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setLoading(false);
    }
  }

  async function handleGuest() {
    setError(""); setLoading(true);
    try {
      const guestName = authDisplayName.trim() || "Guest";
      const session = await ensureGuestSession(guestName);
      if (session) onAuth(session);
      else setError("Supabase not configured — cannot create guest session");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  const isDisabled = loading || cooldown > 0;

  return (
    <div className="min-h-screen p-4 flex justify-center">
      <div className="w-full max-w-md my-auto">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-3xl font-extrabold text-slate-900 shadow-xl mx-auto mb-4">C</div>
          <h1 className="text-3xl font-bold text-white">Card<span className="text-amber-400">Pilot</span></h1>
          <p className="text-slate-500 text-sm mt-2">GTO-powered poker training</p>
        </div>

        {/* Card */}
        <div className="glass-card p-8">
          {/* Tab switcher */}
          <div className="flex gap-1 bg-white/5 rounded-xl p-1 mb-6">
            {(["login", "signup"] as const).map((m) => (
              <button key={m} onClick={() => { setMode(m); setError(""); setSuccessMsg(""); setConfirmPw(""); }}
                className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${mode === m ? "bg-white/10 text-white shadow-sm" : "text-slate-400 hover:text-slate-200"}`}>
                {m === "login" ? "Log In" : "Sign Up"}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === "signup" && (
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Display Name</label>
                <input value={authDisplayName} onChange={(e) => setAuthDisplayName(e.target.value)}
                  placeholder="How others see you" maxLength={32}
                  className="input-field w-full" />
                {nameHint && <p className="text-xs text-amber-400 mt-1">{nameHint}</p>}
              </div>
            )}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Email</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
                placeholder="you@example.com"
                className="input-field w-full" />
              {emailHint && <p className="text-xs text-amber-400 mt-1">{emailHint}</p>}
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Password</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
                placeholder="Min 6 characters" minLength={6}
                className="input-field w-full" />
              {pwHint && <p className="text-xs text-amber-400 mt-1">{pwHint}</p>}
            </div>

            {mode === "signup" && (
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Confirm Password</label>
                <input type="password" value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} required
                  placeholder="Re-enter password" minLength={6}
                  className="input-field w-full" />
                {confirmHint && <p className="text-xs text-red-400 mt-1">{confirmHint}</p>}
              </div>
            )}

            {error && (
              <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-400">{error}</div>
            )}
            {successMsg && (
              <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-sm text-emerald-400">{successMsg}</div>
            )}

            {cooldown > 0 && (
              <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-sm text-amber-400 text-center">
                Rate limited — please wait {cooldown}s
              </div>
            )}

            <button type="submit" disabled={isDisabled || !formValid}
              className="btn-primary w-full !py-3 text-base font-semibold disabled:opacity-40">
              {loading ? "..." : cooldown > 0 ? `Wait ${cooldown}s` : mode === "login" ? "Log In" : "Create Account"}
            </button>

            <button
              type="button"
              onClick={handleGoogleSignIn}
              disabled={loading}
              className="w-full !py-3 text-sm font-medium rounded-xl border border-white/15 bg-white text-slate-900 hover:bg-slate-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
                <path fill="#EA4335" d="M12 10.2v3.9h5.5c-.2 1.3-1.6 3.9-5.5 3.9-3.3 0-6-2.8-6-6.2s2.7-6.2 6-6.2c1.9 0 3.2.8 3.9 1.5l2.7-2.7C16.8 2.7 14.6 1.8 12 1.8 6.9 1.8 2.8 6.2 2.8 11.8S6.9 21.8 12 21.8c6.9 0 9.2-5 9.2-7.6 0-.5-.1-.9-.1-1.3H12z"/>
              </svg>
              Continue with Google
            </button>
          </form>

          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-white/10" /></div>
            <div className="relative flex justify-center"><span className="bg-[#0f1724] px-3 text-xs text-slate-500">or</span></div>
          </div>

          <div className="space-y-3">
            <input value={authDisplayName} onChange={(e) => setAuthDisplayName(e.target.value)}
              placeholder="Enter your name (optional)" maxLength={32}
              className="input-field w-full text-center text-sm" />
            <button onClick={handleGuest} disabled={isDisabled}
              className="btn-ghost w-full !py-3 text-sm">
              Continue as Guest
            </button>
          </div>
        </div>

        <p className="text-center text-xs text-slate-600 mt-4">
          By continuing, you agree to our Terms of Service
        </p>
      </div>
    </div>
  );
}

/* ═══════ ActionBar ═══════ */

function ActionBar({
  canAct,
  legal,
  pot,
  bigBlind,
  currentBet,
  raiseTo,
  setRaiseTo,
  onAction,
  street,
  board,
  heroStack,
  numPlayers,
  advice,
  thinkExtensionEnabled,
  thinkExtensionRemainingUses,
  onThinkExtension,
  actionPending,
}: {
  canAct: boolean;
  legal: LegalActions | null;
  pot: number;
  bigBlind: number;
  currentBet: number;
  raiseTo: number;
  setRaiseTo: (v: number) => void;
  onAction: (action: "fold" | "check" | "call" | "raise" | "all_in", amount?: number) => void;
  street: string;
  board: string[];
  heroStack: number;
  numPlayers: number;
  advice: AdvicePayload | null;
  thinkExtensionEnabled?: boolean;
  thinkExtensionRemainingUses?: number;
  onThinkExtension?: () => void;
  actionPending?: boolean;
}) {
  const min = legal?.minRaise ?? bigBlind * 2;
  const max = legal?.maxRaise ?? 10000;
  const callAmt = legal?.callAmount ?? 0;
  const [showSuggest, setShowSuggest] = useState(false);

  // Auto-clamp raiseTo to legal range when it changes
  useEffect(() => {
    if (legal?.canRaise) {
      if (raiseTo < min) setRaiseTo(min);
      else if (raiseTo > max) setRaiseTo(max);
    }
  }, [min, max, legal?.canRaise]);

  const suggestedPresets = useMemo(() => {
    if (!legal?.canRaise || pot <= 0) return [];
    return getSuggestedPresets({ street: street as any, pot, heroStack, board, numPlayers });
  }, [legal, pot, street, board, heroStack, numPlayers]);

  const userPrefs = useMemo(() => loadPrefs(), []);
  const streetKey = street === "FLOP" ? "flop" : street === "TURN" ? "turn" : street === "RIVER" ? "river" : "flop";
  const customPresets = useMemo(() => {
    return userPresetsToButtons(userPrefs.betPresets[streetKey as keyof typeof userPrefs.betPresets] ?? [33, 66, 100]);
  }, [userPrefs, streetKey]);

  function presetToChips(pctOfPot: number): number {
    const raw = Math.round(pot * pctOfPot / 100);
    return Math.max(min, Math.min(max, raw));
  }

  const recommendedAction = advice?.recommended;
  const confidence = advice ? Math.max(advice.mix.raise, advice.mix.call, advice.mix.fold) : 0;
  const confidenceLabel = confidence > 0.7 ? "High confidence" : confidence > 0.5 ? "Mixed spot" : "Marginal";

  // Debug: log legal actions whenever they change so missing Call can be diagnosed
  useEffect(() => {
    if (canAct && legal) {
      console.log("[ActionBar] Legal actions:", JSON.stringify(legal), "| canAct:", canAct);
    }
  }, [canAct, legal]);

  // Determine the status hint: why is Call/Check shown or hidden?
  const statusHint = useMemo(() => {
    if (!canAct || !legal) return "";
    if (legal.canCheck) return "You are caught up. You can check.";
    if (legal.canCall) return `Call required: ${callAmt.toLocaleString()}`;
    return "";
  }, [canAct, legal, callAmt]);

  const [allInConfirm, setAllInConfirm] = useState(false);
  useEffect(() => { if (!canAct) setAllInConfirm(false); }, [canAct]);

  const btnBase = "btn-action min-h-[38px] py-1.5 px-3 text-xs font-semibold rounded-lg active:scale-95 transition-transform focus:outline-none focus:ring-2 focus:ring-white/20";

  return (
    <div className="glass-card px-2.5 py-1.5 space-y-1.5" style={{ maxHeight: 140 }}>
      {/* Row A: primary action buttons */}
      <div className={`flex items-center gap-1 flex-wrap ${actionPending ? 'opacity-50 pointer-events-none' : ''}`}>
        {actionPending && canAct && (
          <span className="text-[10px] text-amber-400 animate-pulse mr-0.5">Processing…</span>
        )}
        <button disabled={!canAct || actionPending} onClick={() => { onAction("fold"); setShowSuggest(false); }}
          aria-label="Fold" className={`${btnBase} bg-gradient-to-r from-slate-600 to-slate-700 hover:from-slate-500 hover:to-slate-600`}>Fold</button>

        {legal?.canCheck && (
          <button disabled={!canAct || actionPending} onClick={() => { onAction("check"); setShowSuggest(false); }}
            aria-label="Check" className={`${btnBase} bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600`}>Check</button>
        )}

        {legal?.canCall && (
          <button disabled={!canAct || actionPending} onClick={() => { onAction("call"); setShowSuggest(false); }}
            aria-label={`Call ${callAmt}`} className={`${btnBase} bg-gradient-to-r from-sky-600 to-sky-700 hover:from-sky-500 hover:to-sky-600`}>
            Call {callAmt.toLocaleString()}
          </button>
        )}

        {legal?.canRaise && (
          <button disabled={!canAct || actionPending} onClick={() => { onAction("raise", raiseTo); setShowSuggest(false); }}
            aria-label={`Raise to ${raiseTo}`} className={`${btnBase} bg-gradient-to-r from-red-600 to-red-700 hover:from-red-500 hover:to-red-600`}>
            Raise {raiseTo.toLocaleString()}
          </button>
        )}

        {legal?.canRaise && !allInConfirm && (
          <button disabled={!canAct || actionPending} onClick={() => setAllInConfirm(true)}
            aria-label="All-In" className={`${btnBase} bg-gradient-to-r from-orange-600 to-orange-700 hover:from-orange-500 hover:to-orange-600`}>All-In</button>
        )}
        {legal?.canRaise && allInConfirm && (
          <div className="flex items-center gap-1 animate-[fadeSlideUp_0.2s_ease-out]">
            <button disabled={!canAct || actionPending} onClick={() => { onAction("all_in"); setShowSuggest(false); setAllInConfirm(false); }}
              aria-label="Confirm All-In" className={`${btnBase} font-bold bg-gradient-to-r from-red-500 to-orange-600 hover:from-red-400 hover:to-orange-500 ring-2 ring-red-400/50 animate-pulse`}>Confirm All-In</button>
            <button onClick={() => setAllInConfirm(false)}
              className="min-h-[38px] py-1.5 px-2 text-[10px] rounded-lg bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10">✕</button>
          </div>
        )}

        {canAct && advice && (
          <button onClick={() => setShowSuggest(!showSuggest)}
            aria-label="AI suggestion"
            className={`${btnBase} ${
              showSuggest ? "bg-gradient-to-r from-amber-500 to-orange-600 text-white" : "bg-white/5 text-amber-400 border border-amber-500/30"
            }`}>AI</button>
        )}

        {canAct && thinkExtensionEnabled && (thinkExtensionRemainingUses ?? 0) > 0 && (
          <button onClick={() => onThinkExtension?.()} aria-label="Think extension"
            className={`${btnBase} bg-white/5 text-violet-300 border border-violet-500/30`}>
            +T({thinkExtensionRemainingUses})
          </button>
        )}
      </div>

      {/* Row B: raise sizing (slider + input + presets) — only when raise is legal */}
      {legal?.canRaise && canAct && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <input type="range" min={min} max={max} step={bigBlind} value={raiseTo}
            onChange={(e) => setRaiseTo(Number(e.target.value))}
            aria-label="Bet size slider"
            className="flex-1 min-w-[100px] h-1.5 rounded-full appearance-none bg-white/10 accent-red-500 cursor-pointer" />
          <input type="number" min={min} max={max} step={bigBlind} value={raiseTo}
            onChange={(e) => {
              const v = Number(e.target.value);
              if (!isNaN(v)) setRaiseTo(Math.max(min, Math.min(max, v)));
            }}
            aria-label="Bet size input"
            className="w-16 text-center text-xs font-mono font-semibold text-white bg-white/5 border border-white/10 rounded-lg py-1 focus:border-red-500/50 focus:outline-none" />
          <div className="w-px h-4 bg-white/10" />
          {(() => {
            const facingBet = callAmt > 0 && currentBet > 0;
            const showBBMultipliers = !facingBet && (pot <= bigBlind * 2 || (!legal?.canCheck && !legal?.canCall));
            if (facingBet) {
              return [2, 3].map((mult) => {
                const chips = Math.max(min, Math.min(max, Math.round(currentBet * mult)));
                return (
                  <button key={mult} onClick={() => setRaiseTo(chips)}
                    className={`min-h-[30px] px-2 py-1 rounded-md text-[10px] font-semibold transition-all ${
                      raiseTo === chips ? "bg-red-500/20 text-red-400 border border-red-500/30" : "bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10"
                    }`}>{mult}x</button>
                );
              });
            } else if (showBBMultipliers) {
              return [2, 3, 4].map((mult) => {
                const chips = Math.max(min, Math.min(max, Math.round(bigBlind * mult)));
                return (
                  <button key={mult} onClick={() => setRaiseTo(chips)}
                    className={`min-h-[30px] px-2 py-1 rounded-md text-[10px] font-semibold transition-all ${
                      raiseTo === chips ? "bg-red-500/20 text-red-400 border border-red-500/30" : "bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10"
                    }`}>{mult}x</button>
                );
              });
            } else {
              return suggestedPresets.slice(0, 3).map((p) => {
                const chips = presetToChips(p.pctOfPot);
                return (
                  <button key={p.label} onClick={() => setRaiseTo(chips)}
                    className={`min-h-[30px] px-2 py-1 rounded-md text-[10px] font-semibold transition-all ${
                      raiseTo === chips ? "bg-red-500/20 text-red-400 border border-red-500/30" : "bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10"
                    }`}>{p.label}</button>
                );
              });
            }
          })()}
          {customPresets.slice(0, 3).map((p) => {
            const chips = presetToChips(p.pctOfPot);
            return (
              <button key={p.label} onClick={() => setRaiseTo(chips)}
                className={`min-h-[30px] px-2 py-1 rounded-md text-[10px] font-semibold transition-all ${
                  raiseTo === chips ? "bg-amber-500/20 text-amber-400 border border-amber-500/30" : "bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10"
                }`}>{p.label}</button>
            );
          })}
        </div>
      )}

      {/* AI Suggestion — inline compact */}
      {showSuggest && advice && (
        <div className="px-2 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center gap-1.5 text-[10px]">
          <span className="font-bold text-white uppercase">{recommendedAction ?? "—"}</span>
          <span className="text-slate-300 flex-1 truncate">{advice.explanation}</span>
          <span className="text-red-400">R{Math.round(advice.mix.raise * 100)}%</span>
          <span className="text-blue-400">C{Math.round(advice.mix.call * 100)}%</span>
          {recommendedAction && (
            <button onClick={() => { onAction(recommendedAction, recommendedAction === "raise" ? raiseTo : undefined); setShowSuggest(false); }}
              className="text-amber-400 hover:text-amber-300 font-semibold min-h-[30px] px-2 rounded-md bg-amber-500/10">Apply</button>
          )}
        </div>
      )}
    </div>
  );
}

/* ═══════ Small helpers ═══════ */

function Field({ label, w, children }: { label: string; w: string; children: React.ReactNode }) {
  return (
    <div className={`space-y-1 ${w}`}>
      <label className="text-[10px] font-medium text-slate-500 uppercase tracking-wider">{label}</label>
      {children}
    </div>
  );
}

function InfoCell({ label, value, highlight, cyan }: { label: string; value: string; highlight?: boolean; cyan?: boolean }) {
  return (
    <div>
      <span className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</span>
      <div className={`text-sm font-semibold ${highlight ? "text-amber-400 uppercase" : cyan ? "text-cyan-400" : "text-white"} font-mono`}>{value}</div>
    </div>
  );
}

const SeatChip = memo(function SeatChip({ player, seatNum, isActor, isMe, isOwner, isCoHost, timer, posLabel, isButton, displayBB, bigBlind, equity, pendingLeave, revealedCards, isMucked, onClickEmpty }: {
  player?: TablePlayer; seatNum: number; isActor: boolean; isMe: boolean;
  isOwner?: boolean; isCoHost?: boolean; timer?: TimerState | null;
  posLabel?: string; isButton?: boolean; displayBB?: boolean; bigBlind?: number;
  equity?: { winRate: number; tieRate: number } | null;
  pendingLeave?: boolean;
  revealedCards?: [string, string];
  isMucked?: boolean;
  onClickEmpty?: (seatNum: number) => void;
}) {
  const bb = bigBlind || 1;
  const fmt = (v: number) => displayBB ? `${(v / bb).toFixed(1)}bb` : v.toLocaleString();

  if (!player) {
    return (
      <div onClick={() => onClickEmpty?.(seatNum)}
        className="w-16 h-16 md:w-18 md:h-18 rounded-full bg-black/50 border border-dashed border-white/15 flex items-center justify-center cursor-pointer hover:border-emerald-500/40 hover:bg-emerald-500/5 transition-colors group">
        <span className="text-[9px] text-slate-500 group-hover:text-emerald-400">+Sit</span>
      </div>
    );
  }

  // Timer progress calculation (for border color + inline badge)
  const timerUrgent = timer && timer.remaining <= 3;
  const timerColor = timerUrgent ? "text-red-400" : timer?.usingTimeBank ? "text-amber-400" : "text-emerald-400";
  // Border glow based on timer state
  const timerBorderClass = timer
    ? timerUrgent ? "ring-2 ring-red-500/60" : timer.usingTimeBank ? "ring-2 ring-amber-500/50" : "ring-2 ring-emerald-500/40"
    : "";

  // Position label colors
  const posColor = posLabel === "BTN" ? "bg-amber-500 text-white" : posLabel === "SB" ? "bg-blue-500 text-white" : posLabel === "BB" ? "bg-red-500 text-white" : "bg-slate-600 text-slate-200";

  return (
    <div className="relative flex flex-col items-center gap-0.5">
      {/* BTN dealer chip */}
      {isButton && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 z-30">
          <div className="w-5 h-5 rounded-full bg-gradient-to-br from-amber-300 to-amber-500 border-2 border-amber-200 shadow-lg flex items-center justify-center">
            <span className="text-[7px] font-black text-amber-900">D</span>
          </div>
        </div>
      )}
      <div className={`relative z-10 w-18 md:w-22 rounded-xl p-1 text-center transition-all ${timerBorderClass} ${
        isActor ? "bg-amber-500/20 border-2 border-amber-400 shadow-[0_0_16px_rgba(245,158,11,0.3)]"
        : isMe ? "bg-cyan-500/10 border-2 border-cyan-400/50"
        : "bg-black/60 border border-white/10"
      }`}>
        {/* Position label */}
        {posLabel && (
          <div className="absolute -top-2 -left-1 z-20">
            <span className={`text-[7px] px-1.5 py-0.5 rounded-full font-bold uppercase ${posColor}`}>{posLabel}</span>
          </div>
        )}
        {/* Host badge */}
        {(isOwner || isCoHost) && (
          <div className="absolute -top-2 -right-1 z-20">
            <span className={`text-[8px] px-1 py-0.5 rounded font-bold ${isOwner ? "bg-amber-500 text-white" : "bg-blue-500 text-white"}`}>
              {isOwner ? "👑" : "⭐"}
            </span>
          </div>
        )}
        <div className="text-[10px] font-semibold text-white truncate mt-0.5">{player.name}</div>
        <div className="text-[10px] font-mono text-amber-400">{fmt(player.stack)}</div>
        {player.folded && <div className="text-[8px] text-red-400 font-semibold">FOLDED</div>}
        {player.allIn && !equity && <div className="text-[8px] text-orange-400 font-bold">ALL-IN</div>}
        {/* Show equity when available */}
        {equity && player.allIn && (
          <div className="text-[8px] font-bold text-emerald-400">
            {Math.round(equity.winRate * 100)}%
          </div>
        )}
        {/* Timer countdown — integrated inside the seat chip */}
        {timer && (
          <div className={`text-[8px] font-bold tabular-nums ${timerColor} ${timerUrgent ? "animate-pulse" : ""}`}>
            {timer.usingTimeBank ? `⏱ ${Math.ceil(timer.timeBankRemaining)}s` : `${Math.ceil(timer.remaining)}s`}
          </div>
        )}
        {/* Pending leave indicator */}
        {pendingLeave && (
          <div className="text-[7px] text-slate-300 italic">Leaving after hand</div>
        )}
      </div>
      {revealedCards && (
        <div className="flex items-center gap-0.5">
          <CardImg card={revealedCards[0]} className="w-5 h-7 rounded shadow border border-emerald-500/30" />
          <CardImg card={revealedCards[1]} className="w-5 h-7 rounded shadow border border-emerald-500/30" />
        </div>
      )}
      {!revealedCards && isMucked && (
        <div className="text-[7px] uppercase tracking-wider text-slate-500">Mucked</div>
      )}
      {/* Street bet amount — shown below the chip */}
      {player.streetCommitted > 0 && !player.folded && (
        <div className="bg-black/70 px-1.5 py-0.5 rounded-full text-[9px] font-bold text-sky-400 shadow-sm border border-sky-500/20">
          {fmt(player.streetCommitted)}
        </div>
      )}
    </div>
  );
});

const CardImg = memo(function CardImg({ card, className }: { card: string; className?: string }) {
  return (
    <img src={getCardImagePath(card)} alt={card} className={className}
      onError={(e) => { (e.target as HTMLImageElement).src = getCardImagePath(""); }} />
  );
});

function Bar({ label, pct, color }: { label: string; pct: number; color: string }) {
  const p = Math.round(pct * 100);
  return (
    <div className="flex items-center gap-2">
      <span className="w-12 text-[11px] font-medium text-slate-400 uppercase">{label}</span>
      <div className="flex-1 h-5 rounded-full bg-white/5 overflow-hidden">
        <div className={`h-full rounded-full bg-gradient-to-r ${color} transition-all duration-500`} style={{ width: `${p}%` }} />
      </div>
      <span className="w-10 text-right text-xs font-semibold text-slate-300 tabular-nums">{p}%</span>
    </div>
  );
}

export default App;
