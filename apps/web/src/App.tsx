import { useEffect, useMemo, useState } from "react";
import { io, type Socket } from "socket.io-client";
import type { AdvicePayload, LobbyRoomSummary, TableState, TablePlayer } from "@cardpilot/shared-types";
import { ensureGuestSession, signUpWithEmail, signInWithEmail, signOut, supabase, type AuthSession } from "./supabase";
import { preloadCardImages, getCardImagePath } from "./lib/card-images.js";

const SERVER = import.meta.env.VITE_SERVER_URL || "http://127.0.0.1:4000";

/* 6-max seat positions (% from top-left of table image) */
const SEAT_POSITIONS: Record<number, { top: string; left: string }> = {
  1: { top: "78%", left: "25%" },
  2: { top: "78%", left: "75%" },
  3: { top: "42%", left: "95%" },
  4: { top: "6%",  left: "75%" },
  5: { top: "6%",  left: "25%" },
  6: { top: "42%", left: "5%" },
};

/* ═══════════════════ MAIN APP ═══════════════════ */
export function App() {
  /* ── Auth state ── */
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [userEmail, setUserEmail] = useState<string | null>(null);

  /* ── Game state ── */
  const [socket, setSocket] = useState<Socket | null>(null);
  const [tableId, setTableId] = useState("table-1");
  const [seat, setSeat] = useState(1);
  const [name, setName] = useState("Hero");
  const [snapshot, setSnapshot] = useState<TableState | null>(null);
  const [holeCards, setHoleCards] = useState<string[]>([]);
  const [advice, setAdvice] = useState<AdvicePayload | null>(null);
  const [raiseTo, setRaiseTo] = useState(300);
  const [message, setMessage] = useState("Initializing...");

  const [lobbyRooms, setLobbyRooms] = useState<LobbyRoomSummary[]>([]);
  const [newRoomName, setNewRoomName] = useState("Training Room");
  const [roomCodeInput, setRoomCodeInput] = useState("");
  const [currentRoomCode, setCurrentRoomCode] = useState("");
  const [view, setView] = useState<"lobby" | "table">("lobby");

  useEffect(() => { preloadCardImages(); }, []);

  /* ── Check existing session on mount ── */
  useEffect(() => {
    let alive = true;
    ensureGuestSession()
      .then((session) => {
        if (!alive) return;
        if (session) {
          setAuthSession(session);
          setUserEmail(session.email ?? null);
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
        const s: AuthSession = { accessToken: session.access_token, userId: session.user.id, email: session.user.email };
        setAuthSession(s);
        setUserEmail(session.user.email ?? null);
      } else {
        setAuthSession(null);
        setUserEmail(null);
      }
    });
    return () => { data.subscription.unsubscribe(); };
  }, []);

  /* ── Socket: connect only when authenticated ── */
  useEffect(() => {
    if (!authSession) return;
    const s = io(SERVER, { auth: { accessToken: authSession.accessToken, displayName: name } });
    setSocket(s);

    s.on("connect", () => { setMessage("Connected"); s.emit("request_lobby"); });
    s.on("connected", (d: { userId: string; supabaseEnabled: boolean }) => {
      if (!d.supabaseEnabled) setMessage("Connected (no Supabase persistence)");
    });
    s.on("lobby_snapshot", (d: { rooms: LobbyRoomSummary[] }) => setLobbyRooms(d.rooms ?? []));
    s.on("room_created", (d: { tableId: string; roomCode: string; roomName: string }) => {
      setTableId(d.tableId); setCurrentRoomCode(d.roomCode);
      setMessage(`Room created: ${d.roomName} (${d.roomCode})`); setView("table");
    });
    s.on("room_joined", (d: { tableId: string; roomCode: string; roomName: string }) => {
      setTableId(d.tableId); setCurrentRoomCode(d.roomCode);
      setMessage(`Joined room: ${d.roomName} (${d.roomCode})`); setView("table");
    });
    s.on("table_snapshot", (d: TableState) => setSnapshot(d));
    s.on("hole_cards", (d: { cards: string[]; seat: number }) => {
      if (d.seat === seat) setHoleCards(d.cards);
    });
    s.on("advice_payload", (d: AdvicePayload) => setAdvice(d));
    s.on("error_event", (d: { message: string }) => setMessage(`Error: ${d.message}`));
    s.on("disconnect", () => setMessage("Disconnected"));

    return () => { s.disconnect(); };
  }, [authSession]);

  const canAct = useMemo(() => snapshot?.actorSeat === seat && snapshot?.handId, [snapshot, seat]);
  const isConnected = socket?.connected ?? false;

  function copyCode() {
    if (!currentRoomCode) return;
    void navigator.clipboard.writeText(currentRoomCode);
    setMessage(`Copied room code: ${currentRoomCode}`);
  }

  async function handleLogout() {
    socket?.disconnect();
    setSocket(null);
    await signOut();
    setAuthSession(null);
    setUserEmail(null);
    setSnapshot(null);
    setHoleCards([]);
    setView("lobby");
    setMessage("Signed out");
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
    return <AuthScreen onAuth={(s) => { setAuthSession(s); setUserEmail(s.email ?? null); setMessage("Signed in"); }} />;
  }

  /* ═══════════════════ RENDER ═══════════════════ */
  return (
    <div className="min-h-screen flex flex-col">
      {/* ── NAV ── */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-lg font-extrabold text-slate-900 shadow-lg">C</div>
          <h1 className="text-xl font-bold tracking-tight text-white">Card<span className="text-amber-400">Pilot</span></h1>
        </div>
        <nav className="flex items-center gap-1 bg-white/5 rounded-xl p-1">
          {(["lobby", "table"] as const).map((v) => (
            <button key={v} onClick={() => setView(v)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${view === v ? "bg-white/10 text-white shadow-sm" : "text-slate-400 hover:text-slate-200"}`}>
              {v === "lobby" ? "Lobby" : "Table"}
            </button>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          <span className={`status-dot ${isConnected ? "status-dot-online" : "status-dot-offline"}`} />
          <span className="text-xs text-slate-300 max-w-[140px] truncate">{userEmail ?? authSession.userId.slice(0, 8) + "…"}</span>
          <button onClick={handleLogout} className="text-xs text-slate-500 hover:text-red-400 transition-colors px-2 py-1 rounded-lg hover:bg-white/5">Sign Out</button>
        </div>
      </header>

      {/* ── Status ── */}
      {message && (
        <div className="px-6 py-1.5 bg-white/[0.02] border-b border-white/5">
          <p className="text-[11px] text-slate-500 truncate">{message}</p>
        </div>
      )}

      {/* ── CONTENT ── */}
      <div className="flex-1 flex overflow-hidden">
        {view === "lobby" ? (
          /* ═══════ LOBBY ═══════ */
          <main className="flex-1 p-6 overflow-y-auto">
            <div className="max-w-3xl mx-auto space-y-6">
              {/* Create / Join */}
              <div className="glass-card p-6">
                <h2 className="text-lg font-bold text-white mb-5">Create or Join a Room</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                  <div className="space-y-3">
                    <label className="block text-xs font-medium text-slate-400 uppercase tracking-wider">New Room</label>
                    <input value={newRoomName} onChange={(e) => setNewRoomName(e.target.value)} placeholder="Room name" className="input-field w-full" />
                    <button onClick={() => socket?.emit("create_room", { roomName: newRoomName, maxPlayers: 6, smallBlind: 50, bigBlind: 100 })} className="btn-primary w-full">Create Room</button>
                  </div>
                  <div className="space-y-3">
                    <label className="block text-xs font-medium text-slate-400 uppercase tracking-wider">Join by Code</label>
                    <input value={roomCodeInput} onChange={(e) => setRoomCodeInput(e.target.value.toUpperCase())} placeholder="ROOM CODE" className="input-field w-full uppercase tracking-widest text-center font-mono" />
                    <button onClick={() => socket?.emit("join_room_code", { roomCode: roomCodeInput })} className="btn-success w-full">Join Room</button>
                  </div>
                </div>
                {currentRoomCode && (
                  <div className="mt-4 flex items-center justify-center gap-3 py-3 px-4 rounded-xl bg-amber-500/10 border border-amber-500/20">
                    <span className="text-sm text-amber-200">My Room Code:</span>
                    <span className="font-mono font-bold text-amber-400 text-lg tracking-widest">{currentRoomCode}</span>
                    <button onClick={copyCode} className="btn-ghost text-xs !py-1.5 !px-3">Copy</button>
                  </div>
                )}
              </div>

              {/* Room List */}
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
                        <button onClick={() => { setRoomCodeInput(r.roomCode); socket?.emit("join_room_code", { roomCode: r.roomCode }); }} className="btn-primary text-xs !py-2 !px-4 opacity-70 group-hover:opacity-100">Join</button>
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
            <main className="flex-1 p-4 overflow-y-auto space-y-4">
              {/* Controls Bar */}
              <div className="glass-card p-4">
                <div className="flex flex-wrap items-end gap-3">
                  <Field label="Nickname" w="w-28"><input value={name} onChange={(e) => setName(e.target.value)} className="input-field w-full text-sm" /></Field>
                  <Field label="Seat" w="w-16"><input type="number" value={seat} min={1} max={6} onChange={(e) => setSeat(Number(e.target.value))} className="input-field w-full text-sm text-center" /></Field>
                  <button onClick={() => socket?.emit("sit_down", { tableId, seat, buyIn: 10000, name })} className="btn-success text-sm">Sit Down</button>
                  <button onClick={() => socket?.emit("start_hand", { tableId })} className="btn-primary text-sm">Deal</button>
                  <button onClick={() => socket?.emit("stand_up", { tableId, seat })} className="btn-ghost text-sm">Stand Up</button>
                  {currentRoomCode && <span className="ml-auto text-xs text-slate-500">Room <span className="font-mono text-amber-400">{currentRoomCode}</span></span>}
                </div>
              </div>

              {/* ── THE TABLE ── */}
              <div className="glass-card p-4">
                {/* Info strip */}
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-4">
                    <InfoCell label="Hand" value={snapshot?.handId ? snapshot.handId.slice(0, 8) : "—"} />
                    <div className="w-px h-7 bg-white/10" />
                    <InfoCell label="Street" value={snapshot?.street ?? "—"} highlight />
                    <div className="w-px h-7 bg-white/10" />
                    <InfoCell label="Action" value={snapshot?.actorSeat ? `Seat ${snapshot.actorSeat}` : "—"} cyan />
                  </div>
                  <div className="text-right">
                    <span className="text-[10px] text-slate-500 uppercase tracking-wider">Pot</span>
                    <div className="text-xl font-extrabold text-amber-400">{(snapshot?.pot ?? 0).toLocaleString()}</div>
                  </div>
                </div>

                {/* Table image + overlays */}
                <div className="relative w-full select-none" style={{ background: "#111827" }}>
                  <img src="/poker-table.png" alt="Table" className="w-full h-auto" style={{ mixBlendMode: "lighten" }} draggable={false} />

                  {/* Community cards */}
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div className="flex gap-1.5 pointer-events-auto">
                      {snapshot?.board && snapshot.board.length > 0
                        ? snapshot.board.map((c, i) => <CardImg key={i} card={c} className="w-[7%] rounded shadow-lg" />)
                        : Array.from({ length: 5 }).map((_, i) => (
                            <div key={i} className="w-[7%] aspect-[2.5/3.5] rounded border border-dashed border-white/15 bg-white/[0.04]" />
                          ))}
                    </div>
                  </div>

                  {/* Pot chip on table */}
                  {(snapshot?.pot ?? 0) > 0 && (
                    <div className="absolute top-[32%] left-1/2 -translate-x-1/2 pointer-events-none">
                      <div className="bg-black/70 backdrop-blur-sm px-3 py-1 rounded-full text-amber-400 font-bold text-xs shadow-lg">
                        {(snapshot?.pot ?? 0).toLocaleString()}
                      </div>
                    </div>
                  )}

                  {/* Player seats */}
                  {[1, 2, 3, 4, 5, 6].map((seatNum) => {
                    const pos = SEAT_POSITIONS[seatNum];
                    const player = snapshot?.players.find((p) => p.seat === seatNum);
                    const isActor = snapshot?.actorSeat === seatNum;
                    const isMe = seatNum === seat;
                    return (
                      <div key={seatNum} className="absolute -translate-x-1/2 -translate-y-1/2" style={{ top: pos.top, left: pos.left }}>
                        <SeatChip player={player} seatNum={seatNum} isActor={isActor} isMe={isMe} />
                      </div>
                    );
                  })}
                </div>

                {/* Hole cards below table */}
                {holeCards.length > 0 && (
                  <div className="mt-4 flex items-center justify-center gap-3">
                    <span className="text-[10px] text-slate-500 uppercase tracking-wider">Your Hand</span>
                    <div className="flex gap-1.5">
                      {holeCards.map((c, i) => <CardImg key={i} card={c} className="w-16 rounded-lg shadow-xl hover:scale-110 transition-transform" />)}
                    </div>
                  </div>
                )}
              </div>

              {/* ── ACTIONS ── */}
              <div className="glass-card p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <button disabled={!canAct} onClick={() => socket?.emit("action_submit", { tableId, handId: snapshot?.handId, action: "fold" })}
                    className="btn-action bg-gradient-to-r from-slate-600 to-slate-700 hover:from-slate-500 hover:to-slate-600 shadow-lg shadow-slate-900/30">Fold</button>
                  <button disabled={!canAct} onClick={() => socket?.emit("action_submit", { tableId, handId: snapshot?.handId, action: "check" })}
                    className="btn-action bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 shadow-lg shadow-blue-900/30">Check</button>
                  <button disabled={!canAct} onClick={() => socket?.emit("action_submit", { tableId, handId: snapshot?.handId, action: "call" })}
                    className="btn-action bg-gradient-to-r from-sky-600 to-sky-700 hover:from-sky-500 hover:to-sky-600 shadow-lg shadow-sky-900/30">Call</button>
                  <div className="flex items-center gap-2">
                    <input type="number" value={raiseTo} onChange={(e) => setRaiseTo(Number(e.target.value))} className="input-field w-24 text-center font-mono text-sm" />
                    <button disabled={!canAct} onClick={() => socket?.emit("action_submit", { tableId, handId: snapshot?.handId, action: "raise", amount: raiseTo })}
                      className="btn-action bg-gradient-to-r from-red-600 to-red-700 hover:from-red-500 hover:to-red-600 shadow-lg shadow-red-900/30">Raise</button>
                  </div>
                </div>
              </div>
            </main>

            {/* ── GTO SIDEBAR ── */}
            <aside className="w-80 border-l border-white/5 p-5 overflow-y-auto hidden lg:block">
              <div className="sticky top-0 space-y-5">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-xs font-extrabold text-slate-900">G</div>
                  <h2 className="text-sm font-bold text-white uppercase tracking-wider">GTO Coach</h2>
                </div>
                {advice ? (
                  <div className="space-y-4">
                    <div className="text-xs text-slate-500 font-mono">{advice.spotKey}</div>
                    <div className="flex items-center gap-3 py-3 px-4 rounded-xl bg-white/[0.05]">
                      <span className="text-xs text-slate-500">Hand</span>
                      <span className="text-xl font-extrabold text-white tracking-wide">{advice.heroHand}</span>
                    </div>
                    <div className="space-y-2">
                      <Bar label="Raise" pct={advice.mix.raise} color="from-red-500 to-red-600" />
                      <Bar label="Call" pct={advice.mix.call} color="from-blue-500 to-blue-600" />
                      <Bar label="Fold" pct={advice.mix.fold} color="from-slate-500 to-slate-600" />
                    </div>
                    <div className="p-3 rounded-xl bg-white/[0.03] border border-white/5 text-sm text-slate-300 leading-relaxed">{advice.explanation}</div>
                  </div>
                ) : (
                  <div className="text-center py-16">
                    <div className="text-3xl mb-3 opacity-20">🎯</div>
                    <p className="text-slate-500 text-sm">Advice will appear when it's your turn…</p>
                  </div>
                )}
              </div>
            </aside>
          </>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════ AUTH SCREEN COMPONENT ═══════════════════ */
function AuthScreen({ onAuth }: { onAuth: (s: AuthSession) => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [successMsg, setSuccessMsg] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setSuccessMsg(""); setLoading(true);
    try {
      if (mode === "signup") {
        const session = await signUpWithEmail(email, password);
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
    } finally {
      setLoading(false);
    }
  }

  async function handleGuest() {
    setError(""); setLoading(true);
    try {
      const session = await ensureGuestSession();
      if (session) onAuth(session);
      else setError("Supabase not configured — cannot create guest session");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md">
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
              <button key={m} onClick={() => { setMode(m); setError(""); setSuccessMsg(""); }}
                className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${mode === m ? "bg-white/10 text-white shadow-sm" : "text-slate-400 hover:text-slate-200"}`}>
                {m === "login" ? "Log In" : "Sign Up"}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Email</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
                placeholder="you@example.com"
                className="input-field w-full" />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Password</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
                placeholder="Min 6 characters" minLength={6}
                className="input-field w-full" />
            </div>

            {error && (
              <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-400">{error}</div>
            )}
            {successMsg && (
              <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-sm text-emerald-400">{successMsg}</div>
            )}

            <button type="submit" disabled={loading}
              className="btn-primary w-full !py-3 text-base font-semibold">
              {loading ? "..." : mode === "login" ? "Log In" : "Create Account"}
            </button>
          </form>

          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-white/10" /></div>
            <div className="relative flex justify-center"><span className="bg-[#0f1724] px-3 text-xs text-slate-500">or</span></div>
          </div>

          <button onClick={handleGuest} disabled={loading}
            className="btn-ghost w-full !py-3 text-sm">
            Continue as Guest
          </button>
        </div>

        <p className="text-center text-xs text-slate-600 mt-4">
          By continuing, you agree to our Terms of Service
        </p>
      </div>
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

function SeatChip({ player, seatNum, isActor, isMe }: { player?: TablePlayer; seatNum: number; isActor: boolean; isMe: boolean }) {
  if (!player) {
    return (
      <div className="w-16 h-16 md:w-20 md:h-20 rounded-full bg-black/40 backdrop-blur-sm border border-dashed border-white/15 flex items-center justify-center">
        <span className="text-[10px] text-slate-500">Seat {seatNum}</span>
      </div>
    );
  }
  return (
    <div className={`w-20 md:w-24 rounded-xl p-1.5 text-center transition-all ${
      isActor ? "bg-amber-500/20 border-2 border-amber-400 shadow-[0_0_16px_rgba(245,158,11,0.3)] animate-pulse"
      : isMe ? "bg-cyan-500/10 border-2 border-cyan-400/50"
      : "bg-black/50 backdrop-blur-sm border border-white/10"
    }`}>
      <div className="text-[11px] font-semibold text-white truncate">{player.name}</div>
      <div className="text-[10px] font-mono text-amber-400">{player.stack.toLocaleString()}</div>
      {player.folded && <div className="text-[9px] text-red-400 font-semibold">FOLDED</div>}
      {player.allIn && <div className="text-[9px] text-orange-400 font-bold">ALL-IN</div>}
    </div>
  );
}

function CardImg({ card, className }: { card: string; className?: string }) {
  return (
    <img src={getCardImagePath(card)} alt={card} className={className}
      onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
  );
}

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
