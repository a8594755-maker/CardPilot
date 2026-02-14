import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// Load .env.local from project root (Vite does this for the frontend; we do it manually for the server)
try {
  const envPath = resolve(process.cwd(), ".env.local");
  const envContent = readFileSync(envPath, "utf-8");
  for (const line of envContent.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eqIdx = trimmed.indexOf("=");
    if (eqIdx < 0) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    const value = trimmed.slice(eqIdx + 1).trim();
    if (!process.env[key]) process.env[key] = value;
  }
} catch { /* .env.local not found — that's OK */ }

import express from "express";
import cors from "cors";
import { createServer } from "node:http";
import { randomInt, randomUUID } from "node:crypto";
import { Server } from "socket.io";
import { GameTable } from "@cardpilot/game-engine";
import { getPreflopAdvice, getPostflopAdvice, calculateDeviation } from "@cardpilot/advice-engine";
import type {
  ActionSubmitPayload, AdvicePayload, LobbyRoomSummary, TableState,
  UpdateSettingsPayload, KickPlayerPayload, TransferOwnershipPayload,
  SetCoHostPayload, GameControlPayload, JoinRoomWithPasswordPayload,
  RoomFullState, TimerState,
} from "@cardpilot/shared-types";
import { SupabasePersistence, type RoomRecord, type VerifiedIdentity } from "./supabase";
import { RoomManager } from "./room-manager";

const app = express();
app.use(cors());
app.get("/health", (_req, res) => res.json({ ok: true }));

const httpServer = createServer(app);
const io = new Server(httpServer, {
  cors: {
    origin: process.env.CORS_ORIGIN?.split(",") || true,
    credentials: true
  }
});

type SeatBinding = {
  tableId: string;
  seat: number;
  userId: string;
  name: string;
};

type RoomInfo = RoomRecord & {
  createdAt: string;
};

const ROOM_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

const tables = new Map<string, GameTable>();
const roomsByTableId = new Map<string, RoomInfo>();
const roomCodeToTableId = new Map<string, string>();
const socketSeat = new Map<string, SeatBinding>();
const socketIdentity = new Map<string, VerifiedIdentity>();
const lastAdvice = new Map<string, AdvicePayload>(); // key: `${tableId}:${seat}`

// Pending seat requests: orderId -> request data
type SeatRequest = { orderId: string; tableId: string; seat: number; buyIn: number; userId: string; userName: string; socketId: string };
const pendingSeatRequests = new Map<string, SeatRequest>();
const supabase = new SupabasePersistence();

// Room manager handles ownership, settings, timers, kick/ban, auto-close
const roomManager = new RoomManager((tableId, event, data) => {
  io.to(tableId).emit(event, data);
});

io.use(async (socket, next) => {
  const auth = (socket.handshake.auth ?? {}) as {
    accessToken?: string;
    displayName?: string;
    userId?: string; // Accept userId from client
  };

  try {
    const identity = await supabase.verifyAccessToken(auth.accessToken, auth.displayName);
    // If client sends userId and server uses guest fallback, use client's userId instead
    if (auth.userId && identity.userId.startsWith('guest-')) {
      console.log("[AUTH] Using client-provided userId instead of guest ID:", auth.userId);
      socketIdentity.set(socket.id, {
        userId: auth.userId,
        displayName: identity.displayName
      });
    } else {
      socketIdentity.set(socket.id, identity);
    }
    next();
  } catch {
    next(new Error("unauthorized"));
  }
});

function registerRoom(room: RoomInfo): void {
  roomsByTableId.set(room.tableId, room);
  roomCodeToTableId.set(room.roomCode, room.tableId);
}

function createTableIfNeeded(room: RoomInfo): GameTable {
  let table = tables.get(room.tableId);
  if (!table) {
    table = new GameTable({
      tableId: room.tableId,
      smallBlind: room.smallBlind,
      bigBlind: room.bigBlind
    });
    tables.set(room.tableId, table);
  }
  return table;
}

function bindingByUser(tableId: string, userId: string): SeatBinding | undefined {
  for (const binding of socketSeat.values()) {
    if (binding.tableId === tableId && binding.userId === userId) {
      return binding;
    }
  }
  return undefined;
}

function bindingsByTable(tableId: string): Array<{ socketId: string; binding: SeatBinding }> {
  const result: Array<{ socketId: string; binding: SeatBinding }> = [];
  for (const [socketId, binding] of socketSeat.entries()) {
    if (binding.tableId === tableId) {
      result.push({ socketId, binding });
    }
  }
  return result;
}

function socketIdBySeat(tableId: string, seat: number): string {
  for (const [sid, binding] of socketSeat.entries()) {
    if (binding.tableId === tableId && binding.seat === seat) return sid;
  }
  return "";
}

function hasVoluntaryPreflopAction(state: TableState): boolean {
  const blindSeats = new Set<number>();
  for (const action of state.actions) {
    if (action.street !== "PREFLOP") continue;
    if ((action.type === "call" || action.type === "raise") && !blindSeats.has(action.seat)) {
      blindSeats.add(action.seat);
      continue;
    }
    if (action.type === "raise" || action.type === "call") {
      return true;
    }
  }
  return false;
}

function pushAdviceIfNeeded(tableId: string, state: TableState) {
  if (!state.handId || !state.actorSeat) return;

  const table = tables.get(tableId);
  if (!table) return;

  // Only push advice in COACH mode immediately; REVIEW mode waits until hand end
  if (table.getMode() === "REVIEW") return;

  const seat = state.actorSeat;
  const binding = bindingsByTable(tableId).find((entry) => entry.binding.seat === seat)?.binding;
  if (!binding) return;

  const heroPos = table.getPosition(seat);
  const heroHand = table.getHeroHandCode(seat);
  
  let advice: any;

  // Preflop advice
  if (state.street === "PREFLOP") {
    const line = hasVoluntaryPreflopAction(state) ? "facing_open" : "unopened";
    let villainPos = "BB";
    
    if (line === "facing_open") {
      for (const action of state.actions) {
        if (action.street === "PREFLOP" && action.type === "raise" && action.seat !== seat) {
          villainPos = table.getPosition(action.seat);
          break;
        }
      }
    }

    advice = getPreflopAdvice({
      tableId,
      handId: state.handId,
      seat,
      heroPos,
      villainPos,
      line,
      heroHand
    });
  } 
  // Postflop advice (flop/turn/river)
  else if (["FLOP", "TURN", "RIVER"].includes(state.street)) {
    const heroHandCards = (table as any).state?.holeCards?.get(seat);
    if (!heroHandCards || heroHandCards.length !== 2) return;

    const context = buildPostflopContext(tableId, state, seat, heroPos, heroHandCards);
    if (!context) return;

    try {
      advice = getPostflopAdvice(context);
    } catch (error) {
      console.error(`[advice] postflop error for ${tableId}:${seat}:`, error);
      return;
    }
  } else {
    return; // Showdown or invalid street
  }

  // Store for deviation calc
  lastAdvice.set(`${tableId}:${seat}`, advice);

  io.to(socketIdBySeat(tableId, seat)).emit("advice_payload", advice);
}

function buildPostflopContext(tableId: string, state: TableState, seat: number, heroPos: string, heroHand: string[]) {
  const table = tables.get(tableId);
  if (!table || !state.handId) return null;

  // Find villain position (last aggressor or first active opponent)
  let villainPos = "BTN";
  let aggressor: "hero" | "villain" | "none" = "none";
  
  const streetActions = state.actions.filter(a => a.street === state.street);
  let lastRaiserSeat: number | null = null;
  
  for (const action of streetActions) {
    if (action.type === "raise") {
      lastRaiserSeat = action.seat;
      aggressor = action.seat === seat ? "hero" : "villain";
    }
  }
  
  if (lastRaiserSeat !== null && lastRaiserSeat !== seat) {
    villainPos = table.getPosition(lastRaiserSeat);
  }

  // Count active opponents
  const numVillains = state.players.filter(p => 
    p.inHand && !p.folded && p.seat !== seat
  ).length;

  // Calculate pot size and amount to call
  const potSize = state.pot;
  const toCall = Math.max(0, state.currentBet - (state.players.find(p => p.seat === seat)?.streetCommitted ?? 0));
  const effectiveStack = state.players.find(p => p.seat === seat)?.stack ?? 0;

  return {
    tableId,
    handId: state.handId,
    seat,
    street: state.street as "FLOP" | "TURN" | "RIVER",
    heroHand: [heroHand[0], heroHand[1]] as [string, string],
    board: state.board,
    heroPosition: heroPos,
    villainPosition: villainPos,
    potSize,
    toCall,
    effectiveStack,
    aggressor,
    numVillains
  };
}

function emitPresence(tableId: string) {
  const presence = bindingsByTable(tableId).map(({ binding }) => ({
    seat: binding.seat,
    userId: binding.userId,
    name: binding.name
  }));
  io.to(tableId).emit("table_presence", { tableId, presence });
}

function currentPlayerCount(tableId: string): number {
  return tables.get(tableId)?.getPublicState().players.length ?? 0;
}

function toLobbySummary(room: RoomInfo): LobbyRoomSummary {
  const managed = roomManager.getRoom(room.tableId);
  return {
    tableId: room.tableId,
    roomCode: room.roomCode,
    roomName: room.roomName,
    smallBlind: room.smallBlind,
    bigBlind: room.bigBlind,
    maxPlayers: room.maxPlayers,
    playerCount: currentPlayerCount(room.tableId),
    status: room.status,
    visibility: managed?.settings.visibility ?? "public",
    updatedAt: room.updatedAt ?? room.createdAt
  };
}

async function emitLobbySnapshot(targetSocketId?: string): Promise<void> {
  const localRooms = [...roomsByTableId.values()].map(toLobbySummary);
  const roomMap = new Map(localRooms.map((room) => [room.tableId, room]));

  if (supabase.enabled()) {
    const remoteRooms = await supabase.listLobbyRooms(50);
    for (const room of remoteRooms) {
      if (!roomMap.has(room.tableId)) {
        roomMap.set(room.tableId, room);
      }
    }
  }

  // Filter out private rooms from lobby list
  const payload = {
    rooms: [...roomMap.values()]
      .filter((room) => room.status === "OPEN" && room.visibility === "public")
      .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt))
      .slice(0, 50)
  };

  if (targetSocketId) {
    io.to(targetSocketId).emit("lobby_snapshot", payload);
  } else {
    io.emit("lobby_snapshot", payload);
  }
}

function broadcastSnapshot(tableId: string) {
  const table = tables.get(tableId);
  if (!table) return;
  const snapshot = table.getPublicState();
  io.to(tableId).emit("table_snapshot", snapshot);
  emitPresence(tableId);
  pushAdviceIfNeeded(tableId, snapshot);
}

function handleRoomAutoClose(tableId: string): void {
  const count = currentPlayerCount(tableId);
  const closed = roomManager.finalizeAutoClose(tableId, count);
  if (closed) {
    io.to(tableId).emit("room_closed", { tableId, reason: "empty" });
    tables.delete(tableId);
    const room = roomsByTableId.get(tableId);
    if (room) {
      roomCodeToTableId.delete(room.roomCode);
      roomsByTableId.delete(tableId);
      supabase.touchRoom(tableId, "CLOSED").catch(() => {});
    }
    void emitLobbySnapshot();
  }
}

/** Start action timer for the current actor after a hand event */
function startTimerForActor(tableId: string): void {
  const table = tables.get(tableId);
  if (!table) return;
  const state = table.getPublicState();
  if (!state.actorSeat || !state.handId) return;

  const actorBinding = bindingsByTable(tableId).find((e) => e.binding.seat === state.actorSeat);
  if (!actorBinding) return;

  roomManager.startActionTimer(
    tableId,
    state.actorSeat,
    actorBinding.binding.userId,
    () => {
      // Timeout: auto-fold or auto-check
      const tbl = tables.get(tableId);
      if (!tbl) return;
      const s = tbl.getPublicState();
      if (!s.actorSeat || !s.legalActions) return;
      const autoAction = s.legalActions.canCheck ? "check" : "fold";
      try {
        tbl.applyAction(s.actorSeat, autoAction as any);
        io.to(tableId).emit("action_applied", {
          seat: s.actorSeat,
          action: autoAction,
          amount: 0,
          pot: tbl.getPublicState().pot,
          auto: true,
        });
        const newState = tbl.getPublicState();
        if (!newState.actorSeat) {
          io.to(tableId).emit("hand_ended", {
            board: newState.board,
            players: newState.players,
            pot: newState.pot,
            winners: newState.winners,
          });
          roomManager.setHandActive(tableId, false);
        }
        broadcastSnapshot(tableId);
        // Start timer for next actor
        if (newState.actorSeat) {
          startTimerForActor(tableId);
        }
      } catch (err) {
        console.warn("auto-action on timeout failed:", (err as Error).message);
      }
    }
  );
}

function normalizeRoomCode(roomCode: string): string {
  return roomCode.trim().toUpperCase();
}

function sanitizeRoomName(name?: string): string {
  const trimmed = (name ?? "Training Room").trim();
  if (trimmed.length === 0) return "Training Room";
  return trimmed.slice(0, 48);
}

function randomRoomCode(length = 6): string {
  let code = "";
  for (let i = 0; i < length; i += 1) {
    code += ROOM_CODE_CHARS[randomInt(ROOM_CODE_CHARS.length)];
  }
  return code;
}

async function generateUniqueRoomCode(): Promise<string> {
  for (let i = 0; i < 30; i += 1) {
    const candidate = randomRoomCode(6);
    if (roomCodeToTableId.has(candidate)) continue;
    try {
      const existing = await supabase.findRoomByCode(candidate);
      if (!existing) return candidate;
    } catch (err) {
      // Supabase unavailable or table missing — fall back to in-memory uniqueness only
      console.warn("generateUniqueRoomCode: Supabase check failed, using in-memory only:", (err as Error).message);
      return candidate;
    }
  }
  throw new Error("cannot generate unique room code");
}

async function ensureRoomByTableId(tableId: string): Promise<RoomInfo> {
  const local = roomsByTableId.get(tableId);
  if (local) return local;

  const remote = await supabase.findRoomByTableId(tableId);
  if (remote) {
    const hydrated: RoomInfo = {
      ...remote,
      createdAt: remote.updatedAt ?? new Date().toISOString(),
      updatedAt: remote.updatedAt ?? new Date().toISOString()
    };
    registerRoom(hydrated);
    createTableIfNeeded(hydrated);
    return hydrated;
  }

  const fallback: RoomInfo = {
    tableId,
    roomCode: await generateUniqueRoomCode(),
    roomName: `Table ${tableId.slice(0, 6)}`,
    maxPlayers: 6,
    smallBlind: 50,
    bigBlind: 100,
    status: "OPEN",
    isPublic: true,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  };

  registerRoom(fallback);
  createTableIfNeeded(fallback);
  await supabase.upsertRoom(fallback);
  return fallback;
}

async function ensureRoomByCode(roomCode: string): Promise<RoomInfo | null> {
  const normalized = normalizeRoomCode(roomCode);
  const localTableId = roomCodeToTableId.get(normalized);
  if (localTableId) {
    return roomsByTableId.get(localTableId) ?? null;
  }

  const remote = await supabase.findRoomByCode(normalized);
  if (!remote) return null;

  const hydrated: RoomInfo = {
    ...remote,
    createdAt: remote.updatedAt ?? new Date().toISOString(),
    updatedAt: remote.updatedAt ?? new Date().toISOString()
  };
  registerRoom(hydrated);
  createTableIfNeeded(hydrated);
  return hydrated;
}

function touchLocalRoom(tableId: string): void {
  const room = roomsByTableId.get(tableId);
  if (!room) return;
  room.updatedAt = new Date().toISOString();
  roomsByTableId.set(tableId, room);
}

io.on("connection", (socket) => {
  const identity = socketIdentity.get(socket.id);
  if (!identity) {
    socket.disconnect(true);
    return;
  }

  socket.emit("connected", {
    socketId: socket.id,
    userId: identity.userId,
    displayName: identity.displayName,
    supabaseEnabled: supabase.enabled()
  });
  void emitLobbySnapshot(socket.id);

  socket.on(
    "create_room",
    async (payload: { roomName?: string; maxPlayers?: number; smallBlind?: number; bigBlind?: number; isPublic?: boolean; buyInMin?: number; buyInMax?: number; visibility?: "public" | "private" }) => {
      try {
        console.log("[CREATE_ROOM] Request from", identity.userId, identity.displayName, "payload:", payload);
        const roomCode = await generateUniqueRoomCode();
        const tableId = `tbl_${randomUUID().replace(/-/g, "").slice(0, 10)}`;
        const room: RoomInfo = {
          tableId,
          roomCode,
          roomName: sanitizeRoomName(payload.roomName),
          maxPlayers: Math.min(9, Math.max(2, Number(payload.maxPlayers ?? 6))),
          smallBlind: Math.max(1, Number(payload.smallBlind ?? 50)),
          bigBlind: Math.max(2, Number(payload.bigBlind ?? 100)),
          status: "OPEN",
          isPublic: payload.isPublic ?? true,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString()
        };

        if (room.bigBlind <= room.smallBlind) {
          room.bigBlind = room.smallBlind * 2;
        }

        registerRoom(room);
        const table = createTableIfNeeded(room);
        socket.join(room.tableId);

        // Register with room manager — creator is the owner
        roomManager.createRoom({
          tableId: room.tableId,
          roomCode: room.roomCode,
          roomName: room.roomName,
          ownerId: identity.userId,
          ownerName: identity.displayName,
          settings: {
            maxPlayers: room.maxPlayers,
            smallBlind: room.smallBlind,
            bigBlind: room.bigBlind,
            buyInMin: Math.max(1, Number(payload.buyInMin ?? room.bigBlind * 20)),
            buyInMax: Math.max(1, Number(payload.buyInMax ?? room.bigBlind * 200)),
            visibility: payload.visibility ?? (payload.isPublic === false ? "private" : "public"),
          },
        });

        // Persist to Supabase in background — don't block room creation
        supabase.upsertRoom(room).catch((e) => console.warn("create_room: upsertRoom failed:", (e as Error).message));
        supabase.logEvent({
          tableId: room.tableId,
          eventType: "CREATE_ROOM",
          actorUserId: identity.userId,
          payload: {
            roomCode: room.roomCode,
            roomName: room.roomName,
            maxPlayers: room.maxPlayers,
            smallBlind: room.smallBlind,
            bigBlind: room.bigBlind
          }
        }).catch((e) => console.warn("create_room: logEvent failed:", (e as Error).message));

        socket.emit("room_created", {
          tableId: room.tableId,
          roomCode: room.roomCode,
          roomName: room.roomName
        });
        socket.emit("room_joined", {
          tableId: room.tableId,
          roomCode: room.roomCode,
          roomName: room.roomName
        });
        socket.emit("table_snapshot", table.getPublicState());
        const fullState = roomManager.getFullState(room.tableId);
        console.log("[create_room] room_state_update:", fullState ? `owner=${fullState.ownership.ownerId}` : "NULL");
        if (fullState) socket.emit("room_state_update", fullState);
        emitPresence(room.tableId);
        void emitLobbySnapshot();
      } catch (error) {
        socket.emit("error_event", { message: (error as Error).message });
      }
    }
  );

  socket.on("request_lobby", async () => {
    await emitLobbySnapshot(socket.id);
  });

  socket.on("join_room_code", async (payload: { roomCode: string; password?: string }) => {
    try {
      const room = await ensureRoomByCode(payload.roomCode);
      if (!room || room.status !== "OPEN") {
        throw new Error("Room not found or closed");
      }

      // Check ban list
      if (roomManager.isBanned(room.tableId, identity.userId)) {
        throw new Error("You are banned from this room");
      }

      // Check password for private rooms
      const managed = roomManager.getRoom(room.tableId);
      if (managed?.settings.visibility === "private" && managed.settings.password) {
        if (payload.password !== managed.settings.password) {
          throw new Error("Incorrect room password");
        }
      }

      socket.join(room.tableId);
      const table = createTableIfNeeded(room);

      // Cancel empty timer if someone joins
      roomManager.checkRoomEmpty(room.tableId, currentPlayerCount(room.tableId) + 1, () => {
        handleRoomAutoClose(room.tableId);
      });

      supabase.touchRoom(room.tableId, "OPEN").catch((e) => console.warn("join_room_code: touchRoom failed:", (e as Error).message));
      supabase.logEvent({
        tableId: room.tableId,
        eventType: "JOIN_BY_CODE",
        actorUserId: identity.userId,
        payload: { roomCode: room.roomCode }
      }).catch((e) => console.warn("join_room_code: logEvent failed:", (e as Error).message));

      socket.emit("room_joined", {
        tableId: room.tableId,
        roomCode: room.roomCode,
        roomName: room.roomName
      });
      socket.emit("table_snapshot", table.getPublicState());
      socket.emit("room_state_update", roomManager.getFullState(room.tableId));
      emitPresence(room.tableId);
      void emitLobbySnapshot();
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("join_table", async (payload: { tableId: string }) => {
    const room = await ensureRoomByTableId(payload.tableId);
    const table = createTableIfNeeded(room);
    socket.join(payload.tableId);

    supabase.touchRoom(payload.tableId, "OPEN").catch((e) => console.warn("join_table: touchRoom failed:", (e as Error).message));
    supabase.logEvent({
      tableId: payload.tableId,
      eventType: "JOIN_TABLE",
      actorUserId: identity.userId,
      payload: { socketId: socket.id }
    }).catch((e) => console.warn("join_table: logEvent failed:", (e as Error).message));

    socket.emit("room_joined", {
      tableId: room.tableId,
      roomCode: room.roomCode,
      roomName: room.roomName
    });
    socket.emit("table_snapshot", table.getPublicState());
    emitPresence(payload.tableId);
    void emitLobbySnapshot();
  });

  socket.on("sit_down", async (payload: { tableId: string; seat: number; buyIn: number; name?: string }) => {
    try {
      console.log("[SIT_DOWN] Request from", identity.userId, "payload:", payload);
      
      const room = await ensureRoomByTableId(payload.tableId);
      const table = createTableIfNeeded(room);
      
      console.log("[SIT_DOWN] Current players:", table.getPublicState().players.map(p => ({ seat: p.seat, name: p.name })));
      
      const existing = bindingByUser(payload.tableId, identity.userId);
      if (existing && existing.seat !== payload.seat) {
        console.log("[SIT_DOWN] User already seated at", existing.seat);
        throw new Error("You are already seated at this table. Stand up first to switch seats.");
      }

      // Validate buy-in against room settings
      const managed = roomManager.getRoom(payload.tableId);
      if (managed) {
        const { buyInMin, buyInMax } = managed.settings;
        console.log("[SIT_DOWN] Buy-in validation:", payload.buyIn, "range:", buyInMin, "-", buyInMax);
        if (payload.buyIn < buyInMin || payload.buyIn > buyInMax) {
          throw new Error(`Buy-in must be between ${buyInMin} and ${buyInMax}`);
        }
      }

      const name = payload.name?.slice(0, 32) || identity.displayName;
      console.log("[SIT_DOWN] Adding player:", { seat: payload.seat, userId: identity.userId, name, stack: payload.buyIn });
      
      table.addPlayer({
        seat: payload.seat,
        userId: identity.userId,
        name,
        stack: payload.buyIn
      });
      
      console.log("[SIT_DOWN] Player added successfully");

      socketSeat.set(socket.id, {
        tableId: payload.tableId,
        seat: payload.seat,
        userId: identity.userId,
        name
      });

      supabase.upsertSeat({
        table_id: payload.tableId,
        seat_no: payload.seat,
        user_id: identity.userId,
        display_name: name,
        stack: payload.buyIn,
        is_connected: true
      }).catch((e) => console.warn("sit_down: upsertSeat failed:", (e as Error).message));

      supabase.touchRoom(payload.tableId, "OPEN").catch((e) => console.warn("sit_down: touchRoom failed:", (e as Error).message));
      supabase.logEvent({
        tableId: payload.tableId,
        eventType: "SIT_DOWN",
        actorUserId: identity.userId,
        payload: { seat: payload.seat, buyIn: payload.buyIn }
      }).catch((e) => console.warn("sit_down: logEvent failed:", (e as Error).message));

      touchLocalRoom(payload.tableId);
      broadcastSnapshot(payload.tableId);
      void emitLobbySnapshot();
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  /* ═══════════ SEAT REQUEST / APPROVE / REJECT ═══════════ */

  socket.on("seat_request", (payload: { tableId: string; seat: number; buyIn: number; name?: string }) => {
    try {
      console.log("[SEAT_REQUEST] Received from", identity.userId, identity.displayName, "payload:", payload);
      
      const managed = roomManager.getRoom(payload.tableId);
      if (!managed) throw new Error("Room not found");

      console.log("[SEAT_REQUEST] Room found, owner:", managed.ownership.ownerId);

      // Validate buy-in range
      const { buyInMin, buyInMax } = managed.settings;
      if (payload.buyIn < buyInMin || payload.buyIn > buyInMax) {
        throw new Error(`Buy-in must be between ${buyInMin} and ${buyInMax}`);
      }

      // Check seat availability
      const table = tables.get(payload.tableId);
      if (table) {
        const state = table.getPublicState();
        if (state.players.some((p) => p.seat === payload.seat)) {
          throw new Error("Seat already occupied");
        }
      }

      const orderId = `req_${randomUUID().replace(/-/g, "").slice(0, 8)}`;
      const userName = payload.name?.slice(0, 32) || identity.displayName;
      const request: SeatRequest = {
        orderId,
        tableId: payload.tableId,
        seat: payload.seat,
        buyIn: payload.buyIn,
        userId: identity.userId,
        userName,
        socketId: socket.id,
      };
      pendingSeatRequests.set(orderId, request);
      console.log("[SEAT_REQUEST] Stored request:", orderId);

      // Notify host/co-hosts
      const hostBindings = bindingsByTable(payload.tableId).filter(({ binding: b }) =>
        roomManager.isHostOrCoHost(payload.tableId, b.userId)
      );
      console.log("[SEAT_REQUEST] Found", hostBindings.length, "host/co-host bindings");
      
      for (const { socketId: sid } of hostBindings) {
        console.log("[SEAT_REQUEST] Notifying host socket:", sid);
        io.to(sid).emit("seat_request_pending", {
          orderId, userId: identity.userId, userName, seat: payload.seat, buyIn: payload.buyIn,
        });
      }

      socket.emit("seat_request_sent", { orderId, seat: payload.seat });
    } catch (error) {
      console.error("[SEAT_REQUEST] Error:", (error as Error).message);
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("approve_seat", (payload: { tableId: string; orderId: string }) => {
    try {
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId)) {
        throw new Error("Only host/co-host can approve seat requests");
      }

      const request = pendingSeatRequests.get(payload.orderId);
      if (!request || request.tableId !== payload.tableId) {
        throw new Error("Seat request not found or expired");
      }
      pendingSeatRequests.delete(payload.orderId);

      const room = roomsByTableId.get(payload.tableId);
      if (!room) throw new Error("Room not found");
      const table = createTableIfNeeded(room);

      table.addPlayer({
        seat: request.seat,
        userId: request.userId,
        name: request.userName,
        stack: request.buyIn,
      });

      // Bind the requester's socket to the seat
      socketSeat.set(request.socketId, {
        tableId: request.tableId,
        seat: request.seat,
        userId: request.userId,
        name: request.userName,
      });

      // Notify the requester
      io.to(request.socketId).emit("seat_approved", { seat: request.seat, buyIn: request.buyIn });

      broadcastSnapshot(payload.tableId);
      void emitLobbySnapshot();
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("reject_seat", (payload: { tableId: string; orderId: string }) => {
    try {
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId)) {
        throw new Error("Only host/co-host can reject seat requests");
      }

      const request = pendingSeatRequests.get(payload.orderId);
      if (!request || request.tableId !== payload.tableId) {
        throw new Error("Seat request not found or expired");
      }
      pendingSeatRequests.delete(payload.orderId);

      // Notify the requester
      io.to(request.socketId).emit("seat_rejected", { seat: request.seat, reason: "Host declined your request" });
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("stand_up", async (payload: { tableId: string; seat: number }) => {
    const table = tables.get(payload.tableId);
    if (!table) return;

    const binding = socketSeat.get(socket.id);
    if (!binding || binding.tableId !== payload.tableId || binding.seat !== payload.seat) {
      socket.emit("error_event", { message: "You can only stand up from your own seat" });
      return;
    }

    table.removePlayer(payload.seat);
    socketSeat.delete(socket.id);

    supabase.removeSeat(payload.tableId, payload.seat).catch((e) => console.warn("stand_up: removeSeat failed:", (e as Error).message));
    supabase.touchRoom(payload.tableId, "OPEN").catch((e) => console.warn("stand_up: touchRoom failed:", (e as Error).message));
    supabase.logEvent({
      tableId: payload.tableId,
      eventType: "STAND_UP",
      actorUserId: identity.userId,
      payload: { seat: payload.seat }
    }).catch((e) => console.warn("stand_up: logEvent failed:", (e as Error).message));

    touchLocalRoom(payload.tableId);
    broadcastSnapshot(payload.tableId);
    void emitLobbySnapshot();
  });

  socket.on("start_hand", async (payload: { tableId: string }) => {
    try {
      const room = await ensureRoomByTableId(payload.tableId);

      // Check if game is paused
      if (roomManager.isPaused(payload.tableId)) {
        throw new Error("Game is paused");
      }

      // Check host-start-required
      const managed = roomManager.getRoom(payload.tableId);
      if (managed?.settings.hostStartRequired && !roomManager.isHostOrCoHost(payload.tableId, identity.userId)) {
        throw new Error("Only the host can start the hand");
      }

      const table = createTableIfNeeded(room);
      const { handId } = table.startHand();

      // Mark hand active and refill time banks
      roomManager.setHandActive(payload.tableId, true);
      const playerUserIds = bindingsByTable(payload.tableId).map((b) => b.binding.userId);
      roomManager.refillTimeBanks(payload.tableId, playerUserIds);

      io.to(payload.tableId).emit("hand_started", { handId });

      for (const { socketId, binding } of bindingsByTable(payload.tableId)) {
        const cards = table.getHoleCards(binding.seat);
        if (cards) {
          io.to(socketId).emit("hole_cards", { handId, cards, seat: binding.seat });
        }
      }

      supabase.logEvent({
        tableId: payload.tableId,
        eventType: "HAND_STARTED",
        actorUserId: identity.userId,
        handId,
        payload: { buttonSeat: table.getPublicState().buttonSeat }
      }).catch((e) => console.warn("start_hand: logEvent failed:", (e as Error).message));

      touchLocalRoom(payload.tableId);
      broadcastSnapshot(payload.tableId);

      // Start action timer for first actor
      startTimerForActor(payload.tableId);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("action_submit", async (payload: ActionSubmitPayload) => {
    try {
      const table = tables.get(payload.tableId);
      if (!table) throw new Error("table not found");

      // Check if game is paused
      if (roomManager.isPaused(payload.tableId)) {
        throw new Error("Game is paused");
      }

      const binding = socketSeat.get(socket.id);
      if (!binding || binding.tableId !== payload.tableId) {
        throw new Error("player seat not found");
      }

      // Player acted in time — stop timer
      roomManager.playerActedInTime(payload.tableId, identity.userId);

      // Check for stored advice to calculate deviation
      const adviceKey = `${payload.tableId}:${binding.seat}`;
      const storedAdvice = lastAdvice.get(adviceKey);

      const newState = table.applyAction(binding.seat, payload.action, payload.amount);

      io.to(payload.tableId).emit("action_applied", {
        seat: binding.seat,
        action: payload.action,
        amount: payload.amount ?? 0,
        pot: newState.pot
      });

      // Send deviation feedback if we had advice for this spot
      if (storedAdvice && storedAdvice.handId === payload.handId) {
        const deviation = calculateDeviation(storedAdvice.mix, payload.action);
        const deviationPayload = {
          ...storedAdvice,
          deviation,
          playerAction: payload.action
        };
        io.to(socketIdBySeat(payload.tableId, binding.seat)).emit("advice_deviation", deviationPayload);
        lastAdvice.delete(adviceKey);
      }

      if (newState.street !== "PREFLOP") {
        io.to(payload.tableId).emit("street_advanced", { street: newState.street, board: newState.board });
      }

      if (!newState.actorSeat) {
        io.to(payload.tableId).emit("hand_ended", {
          board: newState.board,
          players: newState.players,
          pot: newState.pot,
          winners: newState.winners
        });
        roomManager.setHandActive(payload.tableId, false);
      }

      supabase.logEvent({
        tableId: payload.tableId,
        eventType: "ACTION_SUBMIT",
        actorUserId: identity.userId,
        handId: payload.handId,
        payload: {
          seat: binding.seat,
          action: payload.action,
          amount: payload.amount ?? 0,
          pot: newState.pot
        }
      }).catch((e) => console.warn("action_submit: logEvent failed:", (e as Error).message));

      touchLocalRoom(payload.tableId);
      broadcastSnapshot(payload.tableId);

      // Start timer for next actor
      if (newState.actorSeat) {
        startTimerForActor(payload.tableId);
      }
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("leave_table", async (payload: { tableId: string }) => {
    socket.leave(payload.tableId);
    supabase.logEvent({
      tableId: payload.tableId,
      eventType: "LEAVE_TABLE",
      actorUserId: identity.userId,
      payload: { socketId: socket.id }
    }).catch((e) => console.warn("leave_table: logEvent failed:", (e as Error).message));
    socket.emit("left_table", { tableId: payload.tableId });
    void emitLobbySnapshot();
  });

  /* ═══════════ ROOM MANAGEMENT SOCKET HANDLERS ═══════════ */

  socket.on("request_room_state", (payload: { tableId: string }) => {
    const state = roomManager.getFullState(payload.tableId);
    if (state) socket.emit("room_state_update", state);
  });

  socket.on("update_settings", (payload: UpdateSettingsPayload) => {
    try {
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId)) {
        throw new Error("Only the host or co-host can change settings");
      }
      const result = roomManager.updateSettings(payload.tableId, payload.settings, identity.userId, identity.displayName);
      if (!result) throw new Error("Room not found");

      // Sync key settings back to RoomInfo for lobby display
      const managed = roomManager.getRoom(payload.tableId);
      const roomInfo = roomsByTableId.get(payload.tableId);
      if (managed && roomInfo) {
        roomInfo.smallBlind = managed.settings.smallBlind;
        roomInfo.bigBlind = managed.settings.bigBlind;
        roomInfo.maxPlayers = managed.settings.maxPlayers;
        roomInfo.isPublic = managed.settings.visibility === "public";
        roomInfo.updatedAt = new Date().toISOString();
      }

      socket.emit("settings_updated", { applied: result.applied, deferred: result.deferred });
      if (Object.keys(result.deferred).length > 0) {
        socket.emit("system_message", { message: `Some settings will apply next hand: ${Object.keys(result.deferred).join(", ")}` });
      }
      void emitLobbySnapshot();
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("kick_player", (payload: KickPlayerPayload) => {
    try {
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId)) {
        throw new Error("Only the host or co-host can kick players");
      }
      // Cannot kick yourself
      if (payload.targetUserId === identity.userId) {
        throw new Error("Cannot kick yourself");
      }

      // Find target's socket and binding
      let targetSocketId: string | null = null;
      let targetName = "Unknown";
      for (const [sid, b] of socketSeat.entries()) {
        if (b.tableId === payload.tableId && b.userId === payload.targetUserId) {
          targetSocketId = sid;
          targetName = b.name;
          break;
        }
      }

      roomManager.kickPlayer(
        payload.tableId, payload.targetUserId, targetName,
        payload.reason ?? "", payload.ban ?? false,
        identity.userId, identity.displayName
      );

      if (targetSocketId) {
        const table = tables.get(payload.tableId);
        const targetBinding = socketSeat.get(targetSocketId);
        if (table && targetBinding) {
          table.removePlayer(targetBinding.seat);
          socketSeat.delete(targetSocketId);
        }
        io.to(targetSocketId).emit("kicked", {
          reason: payload.reason ?? "Removed by host",
          banned: payload.ban ?? false,
        });
        const targetSocket = io.sockets.sockets.get(targetSocketId);
        if (targetSocket) targetSocket.leave(payload.tableId);
      }

      broadcastSnapshot(payload.tableId);
      void emitLobbySnapshot();
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("transfer_ownership", (payload: TransferOwnershipPayload) => {
    try {
      if (!roomManager.isOwner(payload.tableId, identity.userId)) {
        throw new Error("Only the owner can transfer ownership");
      }
      // Find target name
      let targetName = "Unknown";
      for (const b of socketSeat.values()) {
        if (b.tableId === payload.tableId && b.userId === payload.newOwnerId) {
          targetName = b.name;
          break;
        }
      }
      const ok = roomManager.transferOwnership(payload.tableId, payload.newOwnerId, targetName, identity.userId, identity.displayName);
      if (!ok) throw new Error("Transfer failed");
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("set_cohost", (payload: SetCoHostPayload) => {
    try {
      if (!roomManager.isOwner(payload.tableId, identity.userId)) {
        throw new Error("Only the owner can manage co-hosts");
      }
      let userName = "Unknown";
      for (const b of socketSeat.values()) {
        if (b.tableId === payload.tableId && b.userId === payload.userId) {
          userName = b.name;
          break;
        }
      }
      const ok = roomManager.setCoHost(payload.tableId, payload.userId, userName, payload.add, identity.userId, identity.displayName);
      if (!ok) throw new Error("Failed to update co-host");
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("game_control", (payload: GameControlPayload) => {
    try {
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId)) {
        throw new Error("Only the host or co-host can control the game");
      }

      switch (payload.action) {
        case "pause":
          roomManager.pauseGame(payload.tableId, identity.userId, identity.displayName);
          break;
        case "resume":
          roomManager.resumeGame(payload.tableId, identity.userId, identity.displayName);
          // Restart timer if hand is active
          if (roomManager.getRoom(payload.tableId)?.handActive) {
            startTimerForActor(payload.tableId);
          }
          break;
        case "end":
          roomManager.endGame(payload.tableId, identity.userId, identity.displayName);
          break;
        case "start":
          // Delegate to start_hand logic
          socket.emit("error_event", { message: "Use start_hand event to start a hand" });
          return;
        case "restart":
          roomManager.endGame(payload.tableId, identity.userId, identity.displayName);
          // Client should call start_hand after restart
          break;
      }

      broadcastSnapshot(payload.tableId);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  /* ═══════════ DISCONNECT ═══════════ */

  socket.on("disconnect", async () => {
    const binding = socketSeat.get(socket.id);
    if (binding) {
      const managed = roomManager.getRoom(binding.tableId);
      const table = tables.get(binding.tableId);

      // If hand is active, use disconnect grace period instead of immediate removal
      if (managed && table && table.isHandActive()) {
        roomManager.startDisconnectGrace(
          binding.tableId,
          binding.seat,
          identity.userId,
          () => {
            // Grace expired — auto-fold and remove player
            const tbl = tables.get(binding.tableId);
            if (tbl && tbl.isHandActive()) {
              const state = tbl.getPublicState();
              if (state.actorSeat === binding.seat) {
                try {
                  tbl.applyAction(binding.seat, "fold");
                  io.to(binding.tableId).emit("action_applied", {
                    seat: binding.seat, action: "fold", amount: 0,
                    pot: tbl.getPublicState().pot, auto: true,
                  });
                  const newState = tbl.getPublicState();
                  if (!newState.actorSeat) {
                    io.to(binding.tableId).emit("hand_ended", {
                      board: newState.board, players: newState.players,
                      pot: newState.pot, winners: newState.winners,
                    });
                    roomManager.setHandActive(binding.tableId, false);
                  }
                  broadcastSnapshot(binding.tableId);
                  if (newState.actorSeat) startTimerForActor(binding.tableId);
                } catch { /* already folded or hand ended */ }
              }
            }
            // Now remove the player
            const tbl2 = tables.get(binding.tableId);
            if (tbl2) {
              tbl2.removePlayer(binding.seat);
              broadcastSnapshot(binding.tableId);
            }
            supabase.removeSeat(binding.tableId, binding.seat).catch(() => {});
            // Check room empty
            roomManager.checkRoomEmpty(binding.tableId, currentPlayerCount(binding.tableId), () => {
              handleRoomAutoClose(binding.tableId);
            });
            void emitLobbySnapshot();
          }
        );
        // Mark disconnected in Supabase but keep seat for grace period
        supabase.setDisconnected(binding.tableId, binding.seat).catch((e) => console.warn("disconnect: setDisconnected failed:", (e as Error).message));
      } else {
        // No active hand — remove player immediately
        if (table) {
          table.removePlayer(binding.seat);
          broadcastSnapshot(binding.tableId);
        }
        supabase.setDisconnected(binding.tableId, binding.seat).catch((e) => console.warn("disconnect: setDisconnected failed:", (e as Error).message));
        supabase.removeSeat(binding.tableId, binding.seat).catch(() => {});
      }

      // Ownership transfer if disconnected player is the owner
      if (roomManager.isOwner(binding.tableId, identity.userId)) {
        const onlinePlayers = bindingsByTable(binding.tableId)
          .filter(({ socketId: sid }) => sid !== socket.id)
          .map(({ binding: b }) => ({ userId: b.userId, name: b.name }));
        roomManager.autoTransferOwnership(binding.tableId, onlinePlayers);
      }

      supabase.touchRoom(binding.tableId, "OPEN").catch((e) => console.warn("disconnect: touchRoom failed:", (e as Error).message));
      supabase.logEvent({
        tableId: binding.tableId,
        eventType: "SOCKET_DISCONNECT",
        actorUserId: identity.userId,
        payload: { seat: binding.seat }
      }).catch((e) => console.warn("disconnect: logEvent failed:", (e as Error).message));

      socketSeat.delete(socket.id);
      touchLocalRoom(binding.tableId);

      // Check room empty auto-close
      roomManager.checkRoomEmpty(binding.tableId, currentPlayerCount(binding.tableId), () => {
        handleRoomAutoClose(binding.tableId);
      });

      void emitLobbySnapshot();
    }
    socketIdentity.delete(socket.id);
  });
});

const port = Number(process.env.PORT || 4000);
httpServer.listen(port, () => {
  console.log(`game-server listening on http://localhost:${port}`);
  console.log(`supabase persistence: ${supabase.enabled() ? "enabled" : "disabled (env missing)"}`);
});
