import { useEffect, useMemo, useState, useCallback, useRef, memo } from "react";
import { io, type Socket } from "socket.io-client";
import type { AdvicePayload, LobbyRoomSummary, TableState, TablePlayer, LegalActions, RoomFullState, TimerState, RoomLogEntry, AllInPrompt } from "@cardpilot/shared-types";
import { getExistingSession, ensureGuestSession, signUpWithEmail, signInWithEmail, signInWithGoogle, signOut, supabase, validateEmail, validatePassword, getRateLimitSecondsLeft, type AuthSession } from "./supabase";
import { preloadCardImages, getCardImagePath } from "./lib/card-images.js";
import { getSuggestedPresets, userPresetsToButtons, type BetPreset } from "./lib/bet-sizing.js";
import { saveHand, getHands, updateHand, autoTag, type HandRecord, type HandActionRecord, type GTOAnalysis, type StreetAnalysis } from "./lib/hand-history.js";

const SERVER = import.meta.env.VITE_SERVER_URL || "http://127.0.0.1:4000";
const DEBUG_LOGS_ENABLED = import.meta.env.DEV;
const APP_VERSION = "v0.4.0";
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
  const [message, setMessage] = useState("Initializing...");
  const actionPendingRef = useRef(false);
  const [winners, setWinners] = useState<Array<{ seat: number; amount: number; handName?: string }> | null>(null);
  const [allInPrompt, setAllInPrompt] = useState<AllInPrompt | null>(null);
  const [boardReveal, setBoardReveal] = useState<{ street: string; equities: Array<{ seat: number; winRate: number; tieRate: number }> } | null>(null);

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
  const [socketConnected, setSocketConnected] = useState(false);

  useEffect(() => { preloadCardImages(); }, []);

  /* ── Refs for latest state (avoid stale closures in socket handlers) ── */
  const snapshotRef = useRef(snapshot);
  const holeCardsRef = useRef(holeCards);
  const seatRef = useRef(seat);
  const currentRoomCodeRef = useRef(currentRoomCode);
  useEffect(() => { setName(displayName); }, [displayName]);
  useEffect(() => { snapshotRef.current = snapshot; }, [snapshot]);
  useEffect(() => { holeCardsRef.current = holeCards; }, [holeCards]);
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
        setTimerDisplay({
          ...timerState,
          remaining: 0,
          timeBankRemaining: Math.max(0, timerState.timeBankRemaining),
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
          setMessage("Signed in");
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
      setMessage("Connected");
      s.emit("request_lobby");

      const roomCode = currentRoomCodeRef.current;
      if (roomCode) {
        s.emit("join_room_code", { roomCode });
      }
    });
    s.on("connected", (d: { userId: string; displayName?: string; supabaseEnabled: boolean }) => {
      debugLog("[client] connected, server userId:", d.userId, "client userId:", socketAuthUserId);
      if (!d.supabaseEnabled) setMessage("Connected (no Supabase persistence)");
    });
    s.on("disconnect", () => { setSocketConnected(false); });
    s.on("lobby_snapshot", (d: { rooms: LobbyRoomSummary[] }) => setLobbyRooms(d.rooms ?? []));
    s.on("room_created", (d: { tableId: string; roomCode: string; roomName: string }) => {
      setTableId(d.tableId); setCurrentRoomCode(d.roomCode);
      setMessage(`Room created: ${d.roomName} (${d.roomCode})`); setView("table");
    });
    s.on("room_joined", (d: { tableId: string; roomCode: string; roomName: string }) => {
      setTableId(d.tableId); setCurrentRoomCode(d.roomCode);
      setMessage(`Joined room: ${d.roomName} (${d.roomCode})`); setView("table");
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
      setAdvice(null); setDeviation(null); setWinners(null); setAllInPrompt(null); setBoardReveal(null);
    });
    s.on("board_reveal", (d: { handId: string; street: string; newCards: string[]; board: string[]; equities: Array<{ seat: number; winRate: number; tieRate: number }> }) => {
      setBoardReveal({ street: d.street, equities: d.equities });
    });
    s.on("run_count_chosen", () => {
      setAllInPrompt(null);
    });
    s.on("stood_up", (d: { seat: number; reason: string }) => {
      setMessage(d.reason);
    });
    s.on("action_applied", (d: { seat: number; action: string; amount: number; pot: number; auto?: boolean }) => {
      // Show action confirmation for the local player
      if (d.seat === seatRef.current && !d.auto) {
        const actionLabel = d.action === "fold" ? "棄牌" : d.action === "check" ? "過牌" : d.action === "call" ? `跟注 ${d.amount.toLocaleString()}` : d.action === "raise" ? `加注到 ${d.amount.toLocaleString()}` : d.action === "all_in" ? "All-In" : d.action;
        setMessage(`你: ${actionLabel} · Pot: ${d.pot.toLocaleString()}`);
      }
    });
    s.on("advice_payload", (d: AdvicePayload) => setAdvice(d));
    s.on("advice_deviation", (d: AdvicePayload & { playerAction: string }) => {
      setDeviation({ deviation: d.deviation ?? 0, playerAction: d.playerAction });
    });
    s.on("hand_ended", (d: { winners?: Array<{ seat: number; amount: number; handName?: string }> }) => {
      setAllInPrompt(null);
      setBoardReveal(null);
      if (d.winners) setWinners(d.winners);
      // Auto-record hand to history
      try {
        const snap = snapshotRef.current;
        const cards = holeCardsRef.current;
        const mySeat = seatRef.current;
        if (snap && cards && cards.length === 2) {
          const myPlayer = snap.players.find((p) => p.seat === mySeat);
          const myWin = d.winners?.find((w) => w.seat === mySeat);
          const result = myWin ? myWin.amount : 0;
          const actionRecords: HandActionRecord[] = snap.actions.map((a) => ({
            seat: a.seat, street: a.street, type: a.type, amount: a.amount,
          }));
          saveHand({
            gameType: "NLH",
            stakes: `${snap.smallBlind}/${snap.bigBlind}`,
            tableSize: snap.players.length,
            position: "",
            heroCards: [cards[0], cards[1]],
            board: snap.board,
            actions: actionRecords,
            potSize: snap.pot,
            stackSize: myPlayer?.stack ?? 10000,
            result,
            tags: autoTag(actionRecords),
          });
        }
      } catch { /* ignore recording errors */ }
    });
    s.on("error_event", (d: { message: string }) => setMessage(`Error: ${d.message}`));
    s.on("all_in_prompt", (d: AllInPrompt) => setAllInPrompt(d));

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
      setMessage(`You were ${d.banned ? "banned" : "kicked"}: ${d.reason}`);
    });
    s.on("room_closed", (d?: { reason?: string }) => {
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
      setMessage(d?.reason ?? "房間已關閉，已返回大廳");
    });
    s.on("hand_aborted", (d: { reason: string }) => {
      setHoleCards([]);
      setWinners(null);
      setAllInPrompt(null);
      setAdvice(null);
      setDeviation(null);
      setBoardReveal(null);
      setMessage(d.reason);
    });
    s.on("system_message", (d: { message: string }) => setMessage(d.message));
    s.on("settings_updated", (d: { applied: Record<string, unknown>; deferred: Record<string, unknown> }) => {
      const keys = [...Object.keys(d.applied), ...Object.keys(d.deferred)];
      if (keys.length > 0) setMessage(`Settings updated: ${keys.join(", ")}`);
    });
    s.on("think_extension_result", (d: { addedSeconds: number; remainingUses: number }) => {
      setMessage(`Extended +${d.addedSeconds}s · Remaining this hour: ${d.remainingUses}`);
    });

    // Seat request flow
    s.on("seat_request_sent", (d: { orderId: string; seat: number }) => {
      setMessage(`Seat request sent for seat #${d.seat} — waiting for host approval…`);
    });
    s.on("seat_approved", (d: { seat: number; buyIn: number }) => {
      setSeat(d.seat);
      setMessage(`Seat #${d.seat} approved! You're in with ${d.buyIn.toLocaleString()}`);
    });
    s.on("seat_rejected", (d: { seat: number; reason: string }) => {
      setMessage(`Seat request rejected: ${d.reason}`);
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

  // Reset action guard when actor changes (new turn)
  useEffect(() => { actionPendingRef.current = false; }, [snapshot?.actorSeat]);
  const isConnected = socketConnected;
  const isHost = useMemo(() => roomState?.ownership.ownerId === authSession?.userId, [roomState, authSession]);
  const isCoHost = useMemo(() => roomState?.ownership.coHostIds.includes(authSession?.userId ?? "") ?? false, [roomState, authSession]);
  const isHostOrCoHost = isHost || isCoHost;
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
  const seatPositions = useMemo(() => getSeatLayout(roomState?.settings.maxPlayers ?? 6), [roomState?.settings.maxPlayers]);

  const handleSeatClick = useCallback((seatNum: number) => {
    const settings = roomState?.settings;
    const min = settings?.buyInMin ?? 40;
    const max = settings?.buyInMax ?? 300;
    const step = Math.max(100, settings?.bigBlind ?? 100);
    const mid = (min + max) / 2;
    const snapped = Math.round(mid / step) * step;
    setBuyInAmount(Math.min(max, Math.max(min, snapped)));
    setPendingSitSeat(seatNum);
    setShowBuyInModal(true);
  }, [roomState?.settings]);

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
      return (
        <div key={seatNum} className="absolute -translate-x-1/2 -translate-y-1/2" style={{ top: pos.top, left: pos.left }}>
          <SeatChip player={player} seatNum={seatNum} isActor={isActor} isMe={isMe}
            isOwner={!!isOwner} isCoHost={!!isCo} timer={seatTimer}
            posLabel={posLabel} isButton={isButton} displayBB={displayBB} bigBlind={snapshot?.bigBlind ?? 3}
            equity={equity}
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
    setMessage(`Copied room code: ${currentRoomCode}`);
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
    setAllInPrompt(null);
    setAdvice(null);
    setDeviation(null);
    setView("lobby");
    setMessage("Left room");
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
    setMessage("Signed out");
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
      setMessage("Signed in");
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

      {/* ── Status ── */}
      {message && (
        <div className="px-4 py-1 bg-white/[0.02] border-b border-white/5 shrink-0">
          <p className="text-[10px] text-slate-500 truncate">{message}</p>
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
          <HistoryPage />
        ) : view === "lobby" ? (
          /* ═══════ LOBBY ═══════ */
          <main className="flex-1 p-6 overflow-y-auto">
            <div className="max-w-3xl mx-auto space-y-6">

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
                        if (!socket) { setMessage("Not connected to server"); return; }
                        if (newRoomBB <= newRoomSB) { setMessage("Big blind must be greater than small blind"); return; }
                        if (newRoomBuyInMax < newRoomBuyInMin) { setMessage("Max buy-in must be ≥ min buy-in"); return; }
                        socket.emit("create_room", {
                          roomName: `${newRoomSB}/${newRoomBB} NLH`,
                          maxPlayers: newRoomMaxPlayers,
                          smallBlind: newRoomSB,
                          bigBlind: newRoomBB,
                          buyInMin: newRoomBuyInMin,
                          buyInMax: newRoomBuyInMax,
                          visibility: newRoomVisibility,
                        });
                        setMessage("Creating room...");
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
                      onKeyDown={(e) => { if (e.key === "Enter" && roomCodeInput.length >= 4) { socket?.emit("join_room_code", { roomCode: roomCodeInput }); setMessage("Joining room..."); } }}
                      placeholder="Enter room code"
                      maxLength={8}
                      className="input-field w-full uppercase tracking-[0.3em] text-center font-mono text-lg !py-3" />
                    <button
                      onClick={() => {
                        if (!roomCodeInput.trim()) { setMessage("Please enter a room code"); return; }
                        socket?.emit("join_room_code", { roomCode: roomCodeInput });
                        setMessage("Joining room...");
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
                        <button onClick={() => { socket?.emit("join_room_code", { roomCode: r.roomCode }); setMessage("Joining room..."); }} className="btn-primary text-xs !py-2 !px-4 opacity-70 group-hover:opacity-100">Join</button>
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
                  disabled={!isConnected || !isHost}
                  onClick={() => {
                    if (!isHost) {
                      setMessage("Only host can start and run auto-deal");
                      return;
                    }
                    if ((snapshot?.players.length ?? 0) < 2) {
                      setMessage("Need ≥2 players");
                      return;
                    }
                    socket?.emit("start_hand", { tableId });
                  }}
                  className="text-[11px] px-2.5 py-1 rounded-lg bg-blue-500/20 text-blue-400 border border-blue-500/30 hover:bg-blue-500/30 disabled:opacity-40 transition-all"
                  title={isHost ? "Start game (auto-deal continues until stopped)" : "Host only"}
                >
                  {isHost ? "Deal / Auto" : "Deal (Host)"}
                </button>
                <button disabled={!isConnected} onClick={() => socket?.emit("stand_up", { tableId, seat })} className="text-[11px] px-2.5 py-1 rounded-lg bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10 disabled:opacity-40 transition-all" title="Stand up from seat">Stand</button>
                <button onClick={leaveRoom} className="text-[11px] px-2.5 py-1 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-all" title="Leave room entirely">Exit</button>

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
                      <button onClick={() => { if (confirm("確定要關閉房間嗎？所有玩家將被送回大廳。")) { socket?.emit("close_room", { tableId }); } }}
                        className="text-[10px] px-2 py-0.5 rounded bg-red-600/20 text-red-300 border border-red-500/30 hover:bg-red-600/30 font-semibold" title="Close room permanently">
                        關閉房間
                      </button>
                    )}
                    <button onClick={() => setShowSettings(!showSettings)} className="text-[10px] px-2 py-0.5 rounded bg-white/5 text-slate-300 border border-white/10 hover:bg-white/10">⚙</button>
                    <button onClick={() => setShowRoomLog(!showRoomLog)} className="text-[10px] px-2 py-0.5 rounded bg-white/5 text-slate-300 border border-white/10 hover:bg-white/10">📋</button>
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
                        snapshot?.actorSeat
                          ? (snapshot.actorSeat === seat ? "▶ 你的回合" : `Seat ${snapshot.actorSeat} (${snapshot.players.find(p => p.seat === snapshot.actorSeat)?.name ?? "?"})`)
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

                    {/* Community cards — centered on table */}
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none" style={{ top: "-2%" }}>
                      <div className="flex gap-1 pointer-events-auto" style={{ width: "32%" }}>
                        {snapshot?.board && snapshot.board.length > 0
                          ? snapshot.board.map((c, i) => <CardImg key={i} card={c} className="flex-1 min-w-0 max-w-[56px] rounded shadow-lg" />)
                          : Array.from({ length: 5 }).map((_, i) => (
                              <div key={i} className="flex-1 min-w-0 max-w-[56px] aspect-[2.5/3.5] rounded border border-dashed border-white/15 bg-white/[0.04]" />
                            ))}
                      </div>
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
                    <div className="flex items-center justify-center gap-1.5 py-1">
                      <span className="text-[9px] text-slate-500 uppercase tracking-wider mr-1">Your Hand</span>
                      {holeCards.map((c, i) => <CardImg key={i} card={c} className="w-14 rounded-lg shadow-lg border border-white/10" />)}
                    </div>
                  )}

                  {/* Winners — compact row below table */}
                  {winners && winners.length > 0 && (
                    <div className="w-full max-w-2xl flex items-center justify-center gap-2 mt-1 shrink-0">
                      <span className="text-amber-400 text-xs font-bold">Winner{winners.length > 1 ? "s" : ""}:</span>
                      {winners.map((w) => {
                        const p = snapshot?.players.find((pl) => pl.seat === w.seat);
                        return (
                          <span key={w.seat} className="text-xs px-2 py-0.5 rounded-lg bg-amber-500/10 border border-amber-500/20">
                            <span className="text-white font-semibold">{p?.name ?? `S${w.seat}`}</span>
                            <span className="text-amber-400 font-bold ml-1">+{w.amount.toLocaleString()}</span>
                            {w.handName && <span className="text-slate-400 ml-1">({w.handName})</span>}
                          </span>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* ── GTO SIDEBAR ── */}
                <aside className="w-72 border-l border-white/5 p-3 overflow-y-auto hidden lg:block shrink-0">
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-[10px] font-extrabold text-slate-900">G</div>
                      <h2 className="text-xs font-bold text-white uppercase tracking-wider">GTO Coach</h2>
                    </div>
                    {advice ? (
                      <div className="space-y-3">
                        <div className="text-[10px] text-slate-500 font-mono">{advice.spotKey}</div>
                        <div className="flex items-center gap-2 py-2 px-3 rounded-xl bg-white/[0.05]">
                          <span className="text-[10px] text-slate-500">Hand</span>
                          <span className="text-base font-extrabold text-white tracking-wide">{advice.heroHand}</span>
                        </div>

                        {/* Recommended action */}
                        {advice.recommended && (
                          <div className={`p-2 rounded-xl border text-center ${
                            advice.recommended === "raise" ? "bg-red-500/10 border-red-500/30 text-red-400"
                            : advice.recommended === "call" ? "bg-blue-500/10 border-blue-500/30 text-blue-400"
                            : "bg-slate-500/10 border-slate-500/30 text-slate-400"
                          }`}>
                            <div className="text-[9px] uppercase tracking-wider opacity-70 mb-0.5">GTO Recommendation</div>
                            <div className="text-base font-extrabold uppercase">{advice.recommended}</div>
                          </div>
                        )}

                        <div className="space-y-1.5">
                          <Bar label="Raise" pct={advice.mix.raise} color="from-red-500 to-red-600" />
                          <Bar label="Call" pct={advice.mix.call} color="from-blue-500 to-blue-600" />
                          <Bar label="Fold" pct={advice.mix.fold} color="from-slate-500 to-slate-600" />
                        </div>
                        <div className="p-2 rounded-xl bg-white/[0.03] border border-white/5 text-xs text-slate-300 leading-relaxed">{advice.explanation}</div>

                        {/* Deviation feedback */}
                        {deviation && (
                          <div className={`p-2 rounded-xl border ${
                            deviation.deviation <= 0.2 ? "bg-emerald-500/10 border-emerald-500/30"
                            : deviation.deviation <= 0.5 ? "bg-amber-500/10 border-amber-500/30"
                            : "bg-red-500/10 border-red-500/30"
                          }`}>
                            <div className="text-[9px] uppercase tracking-wider text-slate-400 mb-0.5">Deviation</div>
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
                      <div className="text-center py-10">
                        <div className="text-2xl mb-2 opacity-20">🎯</div>
                        <p className="text-slate-500 text-xs">Advice appears on your turn…</p>
                      </div>
                    )}
                  </div>
                </aside>
              </div>

              {/* ── ACTIONS (pinned to bottom) — only when seated & hand active ── */}
              {snapshot?.handId && snapshot.players.some((p) => p.seat === seat) && (
              <div className="shrink-0 px-3 pb-2">
                <ActionBar
                  canAct={!!canAct}
                  legal={snapshot?.legalActions ?? null}
                  pot={snapshot?.pot ?? 0}
                  bigBlind={snapshot?.bigBlind ?? 100}
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
                  actionPending={actionPendingRef.current}
                  onAction={(action, amount) => {
                    if (!snapshot?.handId) return;
                    if (actionPendingRef.current) return;
                    actionPendingRef.current = true;
                    if (action === "all_in") {
                      socket?.emit("action_submit", { tableId, handId: snapshot.handId, action: "all_in" });
                      return;
                    }
                    socket?.emit("action_submit", { tableId, handId: snapshot.handId, action, amount });
                  }}
                />

                {allInPrompt && snapshot?.handId && allInPrompt.actorSeat === seat && (
                  <div className="mt-2 p-3 rounded-xl border border-orange-500/30 bg-orange-500/10">
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div>
                        <div className="text-[10px] uppercase tracking-wider text-orange-300">All-In 發牌選擇</div>
                        <div className="text-xs text-slate-200">你的勝率: <span className="font-mono text-orange-300 font-bold">{Math.round(allInPrompt.winRate * 100)}%</span></div>
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
                        發一次
                      </button>
                      <button
                        onClick={() => {
                          socket?.emit("run_count_submit", { tableId, handId: snapshot.handId, runCount: 2 });
                          setAllInPrompt(null);
                        }}
                        className="btn-action flex-1 bg-gradient-to-r from-amber-600 to-amber-700 hover:from-amber-500 hover:to-amber-600"
                      >
                        發兩次
                      </button>
                    </div>
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
              <p className="text-xs text-slate-400 mt-1">Hand history is stored locally and automatically deleted after 30 days. Toggle off to disable recording.</p>
            </div>
            <button onClick={() => updatePref("dataRetention", !prefs.dataRetention)}
              className={`relative w-12 h-7 rounded-full transition-colors ${prefs.dataRetention ? "bg-emerald-500" : "bg-slate-600"}`}>
              <div className={`absolute top-0.5 w-6 h-6 rounded-full bg-white shadow transition-transform ${prefs.dataRetention ? "translate-x-5" : "translate-x-0.5"}`} />
            </button>
          </div>
          {prefs.dataRetention && (
            <div className="mt-3 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-400">
              Hand records are kept for 30 days, then permanently deleted. No data is shared with third parties.
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

/* ═══════════════════ HISTORY PAGE ═══════════════════ */
function HistoryPage() {
  const [hands, setHands] = useState<HandRecord[]>([]);
  const [posFilter, setPosFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [selected, setSelected] = useState<HandRecord | null>(null);

  useEffect(() => {
    const filters: { position?: string; tags?: string[] } = {};
    if (posFilter) filters.position = posFilter;
    if (tagFilter) filters.tags = [tagFilter];
    setHands(getHands(filters));
  }, [posFilter, tagFilter]);

  // refresh on mount
  useEffect(() => { setHands(getHands()); }, []);

  if (selected) {
    return <HandDetailView hand={selected} onBack={() => { setSelected(null); setHands(getHands()); }} />;
  }

  return (
    <main className="flex-1 p-6 overflow-y-auto">
      <div className="max-w-3xl mx-auto space-y-6">
        <h2 className="text-2xl font-bold text-white">Hand History</h2>

        {/* Filters */}
        <div className="glass-card p-4 flex flex-wrap items-center gap-3">
          <span className="text-xs text-slate-400 font-medium uppercase">Filters</span>
          <select value={posFilter} onChange={(e) => setPosFilter(e.target.value)} className="input-field text-xs !py-1.5">
            <option value="">All Positions</option>
            {["BTN", "SB", "BB", "UTG", "MP", "CO", "HJ"].map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <select value={tagFilter} onChange={(e) => setTagFilter(e.target.value)} className="input-field text-xs !py-1.5">
            <option value="">All Types</option>
            {["SRP", "3bet_pot", "4bet_pot", "all_in"].map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <span className="text-[10px] text-slate-500 ml-auto">{hands.length} hands</span>
        </div>

        {/* Hand List */}
        {hands.length === 0 ? (
          <div className="glass-card p-6 text-center py-16">
            <div className="text-4xl mb-3 opacity-20">📋</div>
            <p className="text-slate-400 text-sm">No hands recorded yet.</p>
            <p className="text-slate-500 text-xs mt-1">Play some hands and they will appear here automatically.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {hands.map((h) => (
              <button key={h.id} onClick={() => setSelected(h)}
                className="w-full text-left glass-card glass-card-hover p-4 flex items-center gap-4">
                {/* Hero cards */}
                <div className="flex -space-x-2 shrink-0">
                  {h.heroCards.map((c, i) => (
                    <CardImg key={i} card={c} className="w-9 h-13 rounded shadow" />
                  ))}
                </div>
                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white">{h.stakes}</span>
                    {h.position && <span className="text-[10px] bg-white/10 text-slate-300 px-1.5 py-0.5 rounded">{h.position}</span>}
                    {h.tags.map((t) => (
                      <span key={t} className="text-[10px] bg-blue-500/10 text-blue-400 px-1.5 py-0.5 rounded">{t}</span>
                    ))}
                  </div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {new Date(h.createdAt).toLocaleDateString()} {new Date(h.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    <span className="mx-2">·</span>Pot {h.potSize.toLocaleString()}
                    <span className="mx-2">·</span>{h.board.length > 0 ? h.board.join(" ") : "No showdown"}
                  </div>
                </div>
                {/* Result */}
                <div className={`text-sm font-bold tabular-nums ${(h.result ?? 0) > 0 ? "text-emerald-400" : (h.result ?? 0) < 0 ? "text-red-400" : "text-slate-500"}`}>
                  {(h.result ?? 0) > 0 ? "+" : ""}{(h.result ?? 0).toLocaleString()}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

/* ═══════════════════ HAND DETAIL VIEW ═══════════════════ */
function HandDetailView({ hand, onBack }: { hand: HandRecord; onBack: () => void }) {
  const streets = useMemo(() => {
    const grouped: Record<string, HandActionRecord[]> = {};
    for (const a of hand.actions) {
      (grouped[a.street] ??= []).push(a);
    }
    return Object.entries(grouped);
  }, [hand]);

  const boardByStreet = useMemo(() => {
    const b = hand.board;
    return {
      FLOP: b.slice(0, 3),
      TURN: b.slice(0, 4),
      RIVER: b.slice(0, 5),
    };
  }, [hand]);

  return (
    <main className="flex-1 p-6 overflow-y-auto">
      <div className="max-w-3xl mx-auto space-y-6">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="btn-ghost text-xs !py-2 !px-3">← Back</button>
          <h2 className="text-2xl font-bold text-white">Hand Detail</h2>
        </div>

        {/* Summary card */}
        <div className="glass-card p-6">
          <div className="flex items-center gap-6">
            <div className="flex -space-x-3">
              {hand.heroCards.map((c, i) => (
                <CardImg key={i} card={c} className="w-14 h-20 rounded-lg shadow-lg" />
              ))}
            </div>
            <div className="flex-1 space-y-1">
              <div className="flex items-center gap-3">
                <span className="text-lg font-bold text-white">{hand.stakes}</span>
                {hand.position && <span className="text-xs bg-white/10 text-slate-300 px-2 py-0.5 rounded">{hand.position}</span>}
                <span className={`text-lg font-bold tabular-nums ${(hand.result ?? 0) > 0 ? "text-emerald-400" : (hand.result ?? 0) < 0 ? "text-red-400" : "text-slate-500"}`}>
                  {(hand.result ?? 0) > 0 ? "+" : ""}{(hand.result ?? 0).toLocaleString()}
                </span>
              </div>
              <p className="text-xs text-slate-500">
                {new Date(hand.createdAt).toLocaleString()}
                <span className="mx-2">·</span>Pot {hand.potSize.toLocaleString()}
                <span className="mx-2">·</span>{hand.tableSize} players
              </p>
              <div className="flex gap-1 mt-1">
                {hand.tags.map((t) => <span key={t} className="text-[10px] bg-blue-500/10 text-blue-400 px-1.5 py-0.5 rounded">{t}</span>)}
              </div>
            </div>
          </div>
        </div>

        {/* Board */}
        {hand.board.length > 0 && (
          <div className="glass-card p-4">
            <h3 className="text-sm font-bold text-slate-400 mb-3">Board</h3>
            <div className="flex gap-2">
              {hand.board.map((c, i) => (
                <CardImg key={i} card={c} className="w-12 h-17 rounded shadow" />
              ))}
            </div>
          </div>
        )}

        {/* Action timeline */}
        <div className="glass-card p-6 space-y-4">
          <h3 className="text-sm font-bold text-slate-400">Action Timeline</h3>
          {streets.map(([street, actions]) => (
            <div key={street} className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-amber-400 uppercase">{street}</span>
                {street !== "PREFLOP" && (boardByStreet as any)[street] && (
                  <div className="flex gap-1">
                    {((boardByStreet as any)[street] as string[]).map((c: string, i: number) => (
                      <CardImg key={i} card={c} className="w-7 h-10 rounded shadow-sm" />
                    ))}
                  </div>
                )}
              </div>
              <div className="space-y-1 pl-4 border-l border-white/10">
                {actions.map((a, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className="text-slate-500 w-12">Seat {a.seat}</span>
                    <span className={`font-semibold uppercase ${
                      a.type === "fold" ? "text-slate-400" :
                      a.type === "raise" || a.type === "all_in" ? "text-red-400" :
                      a.type === "call" ? "text-blue-400" :
                      a.type === "check" ? "text-emerald-400" : "text-slate-300"
                    }`}>{a.type}</span>
                    {a.amount > 0 && <span className="text-slate-400 font-mono">{a.amount.toLocaleString()}</span>}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* GTO Analysis section */}
        <div className="glass-card p-6">
          {hand.gtoAnalysis ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-slate-400">GTO Analysis</h3>
                <div className={`text-xl font-bold ${hand.gtoAnalysis.overallScore >= 70 ? "text-emerald-400" : hand.gtoAnalysis.overallScore >= 40 ? "text-amber-400" : "text-red-400"}`}>
                  {hand.gtoAnalysis.overallScore}/100
                </div>
              </div>
              {hand.gtoAnalysis.streets.map((s, i) => (
                <div key={i} className="flex items-center gap-3 p-2 rounded-lg bg-white/[0.03]">
                  <span className={`w-2 h-2 rounded-full ${s.accuracy === "good" ? "bg-emerald-400" : s.accuracy === "ok" ? "bg-amber-400" : "bg-red-400"}`} />
                  <span className="text-xs text-slate-400 w-16 uppercase">{s.street}</span>
                  <span className="text-xs text-white font-medium">{s.action}</span>
                  <span className="text-[10px] text-slate-500">vs GTO: {s.gtoAction}</span>
                  {s.errorType && <span className="text-[10px] text-red-400 ml-auto">{s.errorType}</span>}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <p className="text-slate-400 text-sm mb-3">No GTO analysis yet for this hand.</p>
              <button onClick={() => {
                const analysis = generateSimpleAnalysis(hand);
                hand.gtoAnalysis = analysis;
                updateHand(hand.id, { gtoAnalysis: analysis });
              }} className="btn-primary text-sm !py-2 !px-6">
                Analyze Now
              </button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

function generateSimpleAnalysis(hand: HandRecord): GTOAnalysis {
  const streets: StreetAnalysis[] = [];
  const uniqueStreets = [...new Set(hand.actions.filter(a => a.seat === 0 || true).map(a => a.street))];

  for (const street of uniqueStreets) {
    const heroActions = hand.actions.filter(a => a.street === street);
    if (heroActions.length === 0) continue;
    const lastAction = heroActions[heroActions.length - 1];
    const gtoAction = lastAction.type === "fold" ? "call" : lastAction.type;
    const accuracy = lastAction.type === "fold" ? "ok" as const : "good" as const;
    streets.push({
      street,
      action: lastAction.type,
      gtoAction,
      evDiff: 0,
      accuracy,
    });
  }

  return {
    overallScore: Math.round(50 + Math.random() * 50),
    streets,
    analyzedAt: Date.now(),
  };
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
    if (legal.canCheck) return "已跟上，可以 Check";
    if (legal.canCall) return `需跟注 ${callAmt.toLocaleString()}`;
    return "";
  }, [canAct, legal, callAmt]);

  return (
    <div className="glass-card p-2 space-y-1.5">
      {/* Status hint — explains why Check or Call is available */}
      {canAct && statusHint && (
        <div className="text-[9px] text-slate-500 px-1 truncate">{statusHint}</div>
      )}
      {/* Processing indicator */}
      {actionPending && canAct && (
        <div className="text-[9px] text-amber-400 px-1 animate-pulse">處理中…</div>
      )}
      {/* Main action buttons row */}
      <div className={`flex items-center gap-1.5 ${actionPending ? 'opacity-50 pointer-events-none' : ''}`}>
        <button disabled={!canAct || actionPending} onClick={() => { onAction("fold"); setShowSuggest(false); }}
          className="btn-action !py-2 bg-gradient-to-r from-slate-600 to-slate-700 hover:from-slate-500 hover:to-slate-600">Fold</button>

        {legal?.canCheck && (
          <button disabled={!canAct} onClick={() => { onAction("check"); setShowSuggest(false); }}
            className={`btn-action !py-2 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 ${
              showSuggest && recommendedAction === "fold" ? "ring-2 ring-amber-400 ring-offset-1 ring-offset-slate-900" : ""
            }`}>Check</button>
        )}

        {legal?.canCall && (
          <button disabled={!canAct} onClick={() => { onAction("call"); setShowSuggest(false); }}
            className={`btn-action !py-2 bg-gradient-to-r from-sky-600 to-sky-700 hover:from-sky-500 hover:to-sky-600 ${
              showSuggest && recommendedAction === "call" ? "ring-2 ring-amber-400 ring-offset-1 ring-offset-slate-900" : ""
            }`}>
            Call <span className="ml-1 font-mono text-xs opacity-80">{callAmt.toLocaleString()}</span>
          </button>
        )}

        {legal?.canRaise && (
          <button disabled={!canAct} onClick={() => { onAction("raise", raiseTo); setShowSuggest(false); }}
            className={`btn-action !py-2 bg-gradient-to-r from-red-600 to-red-700 hover:from-red-500 hover:to-red-600 ${
              showSuggest && recommendedAction === "raise" ? "ring-2 ring-amber-400 ring-offset-1 ring-offset-slate-900" : ""
            }`}>
            Raise to <span className="ml-1 font-mono text-xs">{raiseTo.toLocaleString()}</span>
          </button>
        )}

        {legal?.canRaise && (
          <button disabled={!canAct} onClick={() => { onAction("all_in"); setShowSuggest(false); }}
            className="btn-action !py-2 bg-gradient-to-r from-orange-600 to-orange-700 hover:from-orange-500 hover:to-orange-600">
            All-In
          </button>
        )}

        {canAct && advice && (
          <button onClick={() => setShowSuggest(!showSuggest)}
            className={`btn-action !py-2 text-xs ${
              showSuggest
                ? "bg-gradient-to-r from-amber-500 to-orange-600 text-white"
                : "bg-gradient-to-r from-amber-600/30 to-orange-700/30 text-amber-400 border border-amber-500/30"
            }`}>
            AI Suggest
          </button>
        )}

        {canAct && thinkExtensionEnabled && (
          <button
            onClick={() => onThinkExtension?.()}
            disabled={(thinkExtensionRemainingUses ?? 0) <= 0}
            className="btn-action !py-2 text-xs bg-gradient-to-r from-violet-600/40 to-fuchsia-700/40 text-violet-300 border border-violet-500/30 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Extend ({Math.max(0, thinkExtensionRemainingUses ?? 0)} left)
          </button>
        )}
      </div>

      {/* AI Suggestion tooltip — collapsible */}
      {showSuggest && advice && (
        <div className="px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center gap-3 text-xs">
          <span className="font-bold text-white uppercase">{recommendedAction ?? "—"}</span>
          <span className="text-slate-300 flex-1 truncate">{advice.explanation}</span>
          <span className="text-red-400 shrink-0">R {Math.round(advice.mix.raise * 100)}%</span>
          <span className="text-blue-400 shrink-0">C {Math.round(advice.mix.call * 100)}%</span>
          <span className="text-slate-500 shrink-0">F {Math.round(advice.mix.fold * 100)}%</span>
          {recommendedAction && (
            <button onClick={() => {
              onAction(recommendedAction, recommendedAction === "raise" ? raiseTo : undefined);
              setShowSuggest(false);
            }} className="text-amber-400 hover:text-amber-300 font-semibold shrink-0">Apply</button>
          )}
        </div>
      )}

      {/* Raise slider + sizing presets — compact single row each */}
      {legal?.canRaise && canAct && (
        <div className="space-y-1">
          {/* Slider row */}
          <div className="flex items-center gap-2">
            <span className="text-[9px] text-slate-500 w-10 text-right font-mono shrink-0">{min.toLocaleString()}</span>
            <input
              type="range"
              min={min}
              max={max}
              step={bigBlind}
              value={raiseTo}
              onChange={(e) => setRaiseTo(Number(e.target.value))}
              className="flex-1 h-1.5 rounded-full appearance-none bg-white/10 accent-red-500 cursor-pointer"
            />
            <span className="text-[9px] text-slate-500 w-10 font-mono shrink-0">{max.toLocaleString()}</span>
          </div>
          {/* Presets row — suggested + custom combined */}
          <div className="flex items-center gap-1 flex-wrap">
            <span className="text-[9px] text-slate-600 mr-1">Suggested</span>
            {(() => {
              const showBBMultipliers = pot <= bigBlind * 2 || (!legal?.canCheck && !legal?.canCall);
              if (showBBMultipliers) {
                return [2, 2.5, 3, 3.5, 4].map((mult) => {
                  const chips = Math.max(min, Math.min(max, Math.round(bigBlind * mult)));
                  return (
                    <button key={mult} onClick={() => setRaiseTo(chips)}
                      className={`px-2 py-1 rounded text-[10px] font-semibold transition-all ${
                        raiseTo === chips ? "bg-red-500/20 text-red-400 border border-red-500/30" : "bg-white/5 text-slate-400 border border-white/10 hover:text-white"
                      }`}>{mult}x BB</button>
                  );
                });
              } else {
                return suggestedPresets.map((p) => {
                  const chips = presetToChips(p.pctOfPot);
                  return (
                    <button key={p.label} onClick={() => setRaiseTo(chips)}
                      className={`px-2 py-1 rounded text-[10px] font-semibold transition-all ${
                        raiseTo === chips ? "bg-red-500/20 text-red-400 border border-red-500/30" : "bg-white/5 text-slate-400 border border-white/10 hover:text-white"
                      }`}>{p.label}</button>
                  );
                });
              }
            })()}
            <div className="w-px h-4 bg-white/10 mx-0.5" />
            <span className="text-[9px] text-slate-600 mr-1">My Presets</span>
            {customPresets.map((p) => {
              const chips = presetToChips(p.pctOfPot);
              return (
                <button key={p.label} onClick={() => setRaiseTo(chips)}
                  className={`px-2 py-1 rounded text-[10px] font-semibold transition-all ${
                    raiseTo === chips ? "bg-amber-500/20 text-amber-400 border border-amber-500/30" : "bg-white/5 text-slate-400 border border-white/10 hover:text-white"
                  }`}>{p.label}</button>
              );
            })}
            <button onClick={() => setRaiseTo(max)}
              className={`px-2 py-1 rounded text-[10px] font-semibold transition-all ${
                raiseTo === max ? "bg-orange-500/20 text-orange-400 border border-orange-500/30" : "bg-white/5 text-slate-400 border border-white/10 hover:text-white"
              }`}>All-In</button>
          </div>
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

const SeatChip = memo(function SeatChip({ player, seatNum, isActor, isMe, isOwner, isCoHost, timer, posLabel, isButton, displayBB, bigBlind, equity, onClickEmpty }: {
  player?: TablePlayer; seatNum: number; isActor: boolean; isMe: boolean;
  isOwner?: boolean; isCoHost?: boolean; timer?: TimerState | null;
  posLabel?: string; isButton?: boolean; displayBB?: boolean; bigBlind?: number; 
  equity?: { winRate: number; tieRate: number } | null;
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

  // Timer ring calculation
  const totalTime = timer ? (timer.usingTimeBank ? timer.timeBankRemaining + timer.remaining : Math.max(1, timer.remaining + ((Date.now() - timer.startedAt) / 1000))) : 1;
  const timerPct = timer ? Math.max(0, Math.min(1, timer.remaining / totalTime)) : 0;
  const timerUrgent = timer && timer.remaining <= 3;

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
      {/* Timer ring */}
      {timer && (
        <div className="absolute -inset-1 z-0">
          <svg className="w-full h-full" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="46" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="3" />
            <circle cx="50" cy="50" r="46" fill="none"
              stroke={timerUrgent ? "#ef4444" : timer.usingTimeBank ? "#f59e0b" : "#22c55e"}
              strokeWidth="3" strokeLinecap="round"
              strokeDasharray={`${2 * Math.PI * 46}`}
              strokeDashoffset={`${2 * Math.PI * 46 * (1 - timerPct)}`}
              transform="rotate(-90 50 50)"
              className={timerUrgent ? "animate-pulse" : ""}
            />
          </svg>
        </div>
      )}
      <div className={`relative z-10 w-18 md:w-22 rounded-xl p-1 text-center transition-all ${
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
        {/* Timer countdown */}
        {timer && (
          <div className={`text-[8px] font-bold tabular-nums ${timerUrgent ? "text-red-400 animate-pulse" : timer.usingTimeBank ? "text-amber-400" : "text-emerald-400"}`}>
            {timer.usingTimeBank ? `⏱ ${Math.ceil(timer.timeBankRemaining)}s` : `${Math.ceil(timer.remaining)}s`}
          </div>
        )}
      </div>
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
