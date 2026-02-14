import express from "express";
import cors from "cors";
import { createServer } from "node:http";
import { randomInt, randomUUID } from "node:crypto";
import { Server } from "socket.io";
import { GameTable } from "@cardpilot/game-engine";
import { getPreflopAdvice, calculateDeviation } from "@cardpilot/advice-engine";
import type { ActionSubmitPayload, AdvicePayload, LobbyRoomSummary, TableState } from "@cardpilot/shared-types";
import { SupabasePersistence, type RoomRecord, type VerifiedIdentity } from "./supabase";

const app = express();
app.use(cors());
app.get("/health", (_req, res) => res.json({ ok: true }));

const httpServer = createServer(app);
const io = new Server(httpServer, {
  cors: {
    origin: process.env.CORS_ORIGIN?.split(",") || ["http://localhost:5173", "http://127.0.0.1:5173"],
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
const supabase = new SupabasePersistence();

io.use(async (socket, next) => {
  const auth = (socket.handshake.auth ?? {}) as {
    accessToken?: string;
    displayName?: string;
  };

  try {
    const identity = await supabase.verifyAccessToken(auth.accessToken, auth.displayName);
    socketIdentity.set(socket.id, identity);
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
  if (!state.handId || state.street !== "PREFLOP" || !state.actorSeat) return;

  const table = tables.get(tableId);
  if (!table) return;

  // Only push advice in COACH mode immediately; REVIEW mode waits until hand end
  if (table.getMode() === "REVIEW") return;

  const seat = state.actorSeat;
  const binding = bindingsByTable(tableId).find((entry) => entry.binding.seat === seat)?.binding;
  if (!binding) return;

  const heroPos = table.getPosition(seat);
  const line = hasVoluntaryPreflopAction(state) ? "facing_open" : "unopened";
  const heroHand = table.getHeroHandCode(seat);

  // For unopened pots, villain doesn't matter; for facing open, find the opener's position
  let villainPos = "BB";
  if (line === "facing_open") {
    // Find the first raiser's position
    for (const action of state.actions) {
      if (action.street === "PREFLOP" && action.type === "raise" && action.seat !== seat) {
        villainPos = table.getPosition(action.seat);
        break;
      }
    }
  }

  const advice = getPreflopAdvice({
    tableId,
    handId: state.handId,
    seat,
    heroPos,
    villainPos,
    line,
    heroHand
  });

  // Store for deviation calc
  lastAdvice.set(`${tableId}:${seat}`, advice);

  io.to(socketIdBySeat(tableId, seat)).emit("advice_payload", advice);
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
  return {
    tableId: room.tableId,
    roomCode: room.roomCode,
    roomName: room.roomName,
    smallBlind: room.smallBlind,
    bigBlind: room.bigBlind,
    maxPlayers: room.maxPlayers,
    playerCount: currentPlayerCount(room.tableId),
    status: room.status,
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

  const payload = {
    rooms: [...roomMap.values()]
      .filter((room) => room.status === "OPEN")
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
    const existing = await supabase.findRoomByCode(candidate);
    if (!existing) return candidate;
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
    async (payload: { roomName?: string; maxPlayers?: number; smallBlind?: number; bigBlind?: number; isPublic?: boolean }) => {
      try {
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

        await supabase.upsertRoom(room);
        await supabase.logEvent({
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
        });

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

  socket.on("join_room_code", async (payload: { roomCode: string }) => {
    try {
      const room = await ensureRoomByCode(payload.roomCode);
      if (!room || room.status !== "OPEN") {
        throw new Error("找不到可加入的房間碼");
      }

      socket.join(room.tableId);
      const table = createTableIfNeeded(room);

      await supabase.touchRoom(room.tableId, "OPEN");
      await supabase.logEvent({
        tableId: room.tableId,
        eventType: "JOIN_BY_CODE",
        actorUserId: identity.userId,
        payload: { roomCode: room.roomCode }
      });

      socket.emit("room_joined", {
        tableId: room.tableId,
        roomCode: room.roomCode,
        roomName: room.roomName
      });
      socket.emit("table_snapshot", table.getPublicState());
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

    await supabase.touchRoom(payload.tableId, "OPEN");
    await supabase.logEvent({
      tableId: payload.tableId,
      eventType: "JOIN_TABLE",
      actorUserId: identity.userId,
      payload: { socketId: socket.id }
    });

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
      const room = await ensureRoomByTableId(payload.tableId);
      const table = createTableIfNeeded(room);
      const existing = bindingByUser(payload.tableId, identity.userId);
      if (existing && existing.seat !== payload.seat) {
        throw new Error("你已在此桌入座，請先站起再換位");
      }

      const name = payload.name?.slice(0, 32) || identity.displayName;
      table.addPlayer({
        seat: payload.seat,
        userId: identity.userId,
        name,
        stack: payload.buyIn
      });

      socketSeat.set(socket.id, {
        tableId: payload.tableId,
        seat: payload.seat,
        userId: identity.userId,
        name
      });

      await supabase.upsertSeat({
        table_id: payload.tableId,
        seat_no: payload.seat,
        user_id: identity.userId,
        display_name: name,
        stack: payload.buyIn,
        is_connected: true
      });

      await supabase.touchRoom(payload.tableId, "OPEN");
      await supabase.logEvent({
        tableId: payload.tableId,
        eventType: "SIT_DOWN",
        actorUserId: identity.userId,
        payload: { seat: payload.seat, buyIn: payload.buyIn }
      });

      touchLocalRoom(payload.tableId);
      broadcastSnapshot(payload.tableId);
      void emitLobbySnapshot();
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("stand_up", async (payload: { tableId: string; seat: number }) => {
    const table = tables.get(payload.tableId);
    if (!table) return;

    const binding = socketSeat.get(socket.id);
    if (!binding || binding.tableId !== payload.tableId || binding.seat !== payload.seat) {
      socket.emit("error_event", { message: "只能站起自己的座位" });
      return;
    }

    table.removePlayer(payload.seat);
    socketSeat.delete(socket.id);

    await supabase.removeSeat(payload.tableId, payload.seat);
    await supabase.touchRoom(payload.tableId, "OPEN");
    await supabase.logEvent({
      tableId: payload.tableId,
      eventType: "STAND_UP",
      actorUserId: identity.userId,
      payload: { seat: payload.seat }
    });

    touchLocalRoom(payload.tableId);
    broadcastSnapshot(payload.tableId);
    void emitLobbySnapshot();
  });

  socket.on("start_hand", async (payload: { tableId: string }) => {
    try {
      const room = await ensureRoomByTableId(payload.tableId);
      const table = createTableIfNeeded(room);
      const { handId } = table.startHand();

      io.to(payload.tableId).emit("hand_started", { handId });

      for (const { socketId, binding } of bindingsByTable(payload.tableId)) {
        const cards = table.getHoleCards(binding.seat);
        if (cards) {
          io.to(socketId).emit("hole_cards", { handId, cards, seat: binding.seat });
        }
      }

      await supabase.logEvent({
        tableId: payload.tableId,
        eventType: "HAND_STARTED",
        actorUserId: identity.userId,
        handId,
        payload: { buttonSeat: table.getPublicState().buttonSeat }
      });

      touchLocalRoom(payload.tableId);
      broadcastSnapshot(payload.tableId);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("action_submit", async (payload: ActionSubmitPayload) => {
    try {
      const table = tables.get(payload.tableId);
      if (!table) throw new Error("table not found");

      const binding = socketSeat.get(socket.id);
      if (!binding || binding.tableId !== payload.tableId) {
        throw new Error("player seat not found");
      }

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
      }

      await supabase.logEvent({
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
      });

      touchLocalRoom(payload.tableId);
      broadcastSnapshot(payload.tableId);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("leave_table", async (payload: { tableId: string }) => {
    socket.leave(payload.tableId);
    await supabase.logEvent({
      tableId: payload.tableId,
      eventType: "LEAVE_TABLE",
      actorUserId: identity.userId,
      payload: { socketId: socket.id }
    });
    socket.emit("left_table", { tableId: payload.tableId });
    void emitLobbySnapshot();
  });

  socket.on("disconnect", async () => {
    const binding = socketSeat.get(socket.id);
    if (binding) {
      const table = tables.get(binding.tableId);
      if (table) {
        table.removePlayer(binding.seat);
        broadcastSnapshot(binding.tableId);
      }
      await supabase.setDisconnected(binding.tableId, binding.seat);
      await supabase.touchRoom(binding.tableId, "OPEN");
      await supabase.logEvent({
        tableId: binding.tableId,
        eventType: "SOCKET_DISCONNECT",
        actorUserId: identity.userId,
        payload: { seat: binding.seat }
      });
      socketSeat.delete(socket.id);
      touchLocalRoom(binding.tableId);
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
