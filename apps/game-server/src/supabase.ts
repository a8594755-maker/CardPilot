import { createClient, type SupabaseClient, type User } from "@supabase/supabase-js";
import type {
  HandActionType,
  HistoryHandDetail,
  HistoryHandDetailCore,
  HistoryHandPlayerSummary,
  HistoryHandSummary,
  HistoryHandSummaryCore,
  HistoryRoomSummary,
  HistorySessionSummary,
  LobbyRoomSummary,
  Street,
} from "@cardpilot/shared-types";

type Json = string | number | boolean | null | { [key: string]: Json } | Json[];

type TableStatus = "OPEN" | "CLOSED";

export type VerifiedIdentity = {
  userId: string;
  displayName: string;
};

export type SeatPersistenceRecord = {
  table_id: string;
  seat_no: number;
  user_id: string;
  display_name: string;
  stack: number;
  is_connected: boolean;
};

export type RoomRecord = {
  tableId: string;
  roomCode: string;
  roomName: string;
  maxPlayers: number;
  smallBlind: number;
  bigBlind: number;
  status: TableStatus;
  isPublic: boolean;
  updatedAt?: string;
  createdBy?: string | null;
};

export type SessionContextMetadata = {
  roomCode: string;
  roomName: string;
  ownerId?: string;
  ownerName?: string;
  coHostIds?: string[];
  trigger?: string;
};

export type PersistHandHistoryPayload = {
  roomId: string;
  handId: string;
  endedAt: string;
  blinds: { sb: number; bb: number };
  players: HistoryHandPlayerSummary[];
  summary: HistoryHandSummaryCore;
  detail: HistoryHandDetailCore;
  viewerUserIds: string[];
  sessionMetadata?: SessionContextMetadata;
};

export class SupabasePersistence {
  private readonly admin: SupabaseClient | null;
  private readonly authClient: SupabaseClient | null;

  constructor() {
    const url = process.env.SUPABASE_URL;
    const anonKey = process.env.SUPABASE_ANON_KEY;
    const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

    this.admin = url && serviceKey ? createClient(url, serviceKey, { auth: { persistSession: false } }) : null;
    this.authClient = url && anonKey ? createClient(url, anonKey, { auth: { persistSession: false } }) : null;
    console.log(`[supabase] admin=${!!this.admin} authClient=${!!this.authClient} url=${url ? "set" : "missing"} anonKey=${anonKey ? "set" : "missing"}`);
  }

  enabled(): boolean {
    return this.admin !== null;
  }

  getAdminClient(): SupabaseClient | null {
    return this.admin;
  }

  async verifyAccessToken(accessToken?: string, fallbackName?: string): Promise<VerifiedIdentity> {
    if (!accessToken || !this.authClient) {
      if (this.admin) {
        throw new Error("supabase access token required");
      }
      return {
        userId: `guest-${Math.random().toString(36).slice(2, 10)}`,
        displayName: safeDisplayName(fallbackName)
      };
    }

    const { data, error } = await this.authClient.auth.getUser(accessToken);
    if (error || !data.user) {
      throw new Error("invalid supabase access token");
    }

    const displayName = extractDisplayName(data.user, fallbackName);

    if (this.admin) {
      const { error: upsertError } = await this.admin.from("player_profiles").upsert(
        {
          user_id: data.user.id,
          display_name: displayName,
          last_seen_at: new Date().toISOString()
        },
        { onConflict: "user_id" }
      );
      if (upsertError) {
        console.warn("player_profiles upsert failed:", upsertError.message);
      }
    }

    return {
      userId: data.user.id,
      displayName
    };
  }

  async upsertRoom(record: RoomRecord): Promise<void> {
    if (!this.admin) return;
    const { error } = await this.admin.from("live_tables").upsert(
      {
        id: record.tableId,
        room_code: record.roomCode,
        room_name: record.roomName,
        status: record.status,
        max_players: record.maxPlayers,
        small_blind: record.smallBlind,
        big_blind: record.bigBlind,
        is_public: record.isPublic,
        created_by: record.createdBy ?? null,
        updated_at: record.updatedAt ?? new Date().toISOString()
      },
      { onConflict: "id" }
    );
    if (error) {
      console.warn("live_tables upsertRoom failed:", error.message);
    }
  }

  async ensureTable(tableId: string): Promise<void> {
    if (!this.admin) return;
    const { error } = await this.admin.from("live_tables").upsert(
      {
        id: tableId,
        status: "OPEN",
        max_players: 6,
        updated_at: new Date().toISOString()
      },
      { onConflict: "id" }
    );
    if (error) {
      console.warn("live_tables ensureTable failed:", error.message);
    }
  }

  async findRoomByCode(roomCode: string): Promise<RoomRecord | null> {
    if (!this.admin) return null;

    const normalized = normalizeRoomCode(roomCode);
    const { data, error } = await this.admin
      .from("live_tables")
      .select("id, room_code, room_name, status, max_players, small_blind, big_blind, is_public, updated_at, created_by")
      .eq("room_code", normalized)
      .maybeSingle();

    if (error) {
      console.warn("findRoomByCode failed:", error.message);
      return null;
    }
    if (!data) return null;

    return {
      tableId: String(data.id),
      roomCode: String(data.room_code ?? normalized),
      roomName: String(data.room_name ?? `Table ${normalized}`),
      status: (data.status === "CLOSED" ? "CLOSED" : "OPEN") as TableStatus,
      maxPlayers: Number(data.max_players ?? 6),
      smallBlind: Number(data.small_blind ?? 50),
      bigBlind: Number(data.big_blind ?? 100),
      isPublic: Boolean(data.is_public ?? true),
      updatedAt: String(data.updated_at ?? new Date().toISOString()),
      createdBy: typeof data.created_by === "string" ? data.created_by : null,
    };
  }

  async findRoomByTableId(tableId: string): Promise<RoomRecord | null> {
    if (!this.admin) return null;
    const { data, error } = await this.admin
      .from("live_tables")
      .select("id, room_code, room_name, status, max_players, small_blind, big_blind, is_public, updated_at, created_by")
      .eq("id", tableId)
      .maybeSingle();

    if (error) {
      console.warn("findRoomByTableId failed:", error.message);
      return null;
    }
    if (!data) return null;

    return {
      tableId: String(data.id),
      roomCode: String(data.room_code ?? "------"),
      roomName: String(data.room_name ?? `Table ${tableId}`),
      status: (data.status === "CLOSED" ? "CLOSED" : "OPEN") as TableStatus,
      maxPlayers: Number(data.max_players ?? 6),
      smallBlind: Number(data.small_blind ?? 50),
      bigBlind: Number(data.big_blind ?? 100),
      isPublic: Boolean(data.is_public ?? true),
      updatedAt: String(data.updated_at ?? new Date().toISOString()),
      createdBy: typeof data.created_by === "string" ? data.created_by : null,
    };
  }

  async listLobbyRooms(limit = 30): Promise<LobbyRoomSummary[]> {
    if (!this.admin) return [];

    const { data: rows, error } = await this.admin
      .from("live_tables")
      .select("id, room_code, room_name, status, max_players, small_blind, big_blind, is_public, updated_at")
      .eq("status", "OPEN")
      .eq("is_public", true)
      .order("updated_at", { ascending: false })
      .limit(limit);

    if (error || !rows) {
      if (error) {
        console.warn("listLobbyRooms(live_tables) failed:", error.message);
      }
      return [];
    }

    const tableIds = rows.map((r) => String(r.id));
    let seatCounts = new Map<string, number>();

    if (tableIds.length > 0) {
      const { data: seats, error: seatError } = await this.admin
        .from("live_table_seats")
        .select("table_id, seat_no")
        .in("table_id", tableIds)
        .eq("is_connected", true);

      if (seatError) {
        console.warn("listLobbyRooms(live_table_seats) failed:", seatError.message);
      } else if (seats) {
        seatCounts = seats.reduce((acc, row) => {
          const key = String(row.table_id);
          acc.set(key, (acc.get(key) ?? 0) + 1);
          return acc;
        }, new Map<string, number>());
      }
    }

    return rows.map((row) => ({
      tableId: String(row.id),
      roomCode: String(row.room_code ?? "------"),
      roomName: String(row.room_name ?? `Table ${row.id}`),
      status: row.status === "CLOSED" ? "CLOSED" : "OPEN",
      maxPlayers: Number(row.max_players ?? 6),
      smallBlind: Number(row.small_blind ?? 50),
      bigBlind: Number(row.big_blind ?? 100),
      playerCount: seatCounts.get(String(row.id)) ?? 0,
      visibility: "public" as const,
      updatedAt: String(row.updated_at ?? new Date().toISOString())
    }));
  }

  async touchRoom(tableId: string, status: TableStatus = "OPEN"): Promise<void> {
    if (!this.admin) return;
    const { error } = await this.admin
      .from("live_tables")
      .update({ updated_at: new Date().toISOString(), status })
      .eq("id", tableId);

    if (error) {
      console.warn("touchRoom failed:", error.message);
    }
  }

  async openRoomSession(roomId: string, metadata?: SessionContextMetadata): Promise<string | null> {
    if (!this.admin) return null;
    const { data, error } = await this.admin.rpc("open_room_session", {
      _room_id: roomId,
      _metadata_json: metadataToJson(metadata),
    });
    if (error) {
      console.warn("openRoomSession failed:", error.message);
      return null;
    }
    if (typeof data === "string") return data;
    return null;
  }

  async closeRoomSession(roomId: string, metadata?: Record<string, Json>): Promise<string | null> {
    if (!this.admin) return null;
    const { data, error } = await this.admin.rpc("close_room_session", {
      _room_id: roomId,
      _metadata_json: metadata ?? null,
    });
    if (error) {
      console.warn("closeRoomSession failed:", error.message);
      return null;
    }
    if (typeof data === "string") return data;
    return null;
  }

  async recordHandHistory(payload: PersistHandHistoryPayload): Promise<{ inserted: boolean; handNo: number; handHistoryId: string; roomSessionId: string } | null> {
    if (!this.admin) return null;
    const viewerUserIds = dedupeStrings(payload.viewerUserIds.filter(isUuid));
    const { data, error } = await this.admin.rpc("record_hand_history", {
      _room_id: payload.roomId,
      _hand_id: payload.handId,
      _ended_at: payload.endedAt,
      _blinds_json: payload.blinds,
      _players_summary_json: payload.players,
      _summary_json: payload.summary,
      _detail_json: payload.detail,
      _viewer_user_ids: viewerUserIds.length > 0 ? viewerUserIds : null,
      _session_metadata_json: metadataToJson(payload.sessionMetadata),
    });
    if (error) {
      console.warn("recordHandHistory failed:", error.message);
      return null;
    }

    const row = Array.isArray(data) ? data[0] : null;
    if (!row) return null;
    return {
      inserted: Boolean(row.inserted),
      handNo: Number(row.hand_no ?? 0),
      handHistoryId: String(row.hand_history_id ?? ""),
      roomSessionId: String(row.room_session_id ?? ""),
    };
  }

  async listHistoryRooms(userId: string, limit = 50): Promise<HistoryRoomSummary[]> {
    if (!this.admin || !isUuid(userId)) return [];
    const { data, error } = await this.admin.rpc("history_list_rooms", {
      _user_id: userId,
      _limit: Math.max(1, Math.min(limit, 200)),
    });
    if (error || !Array.isArray(data)) {
      if (error) console.warn("listHistoryRooms failed:", error.message);
      return [];
    }
    return data.map((row) => ({
      roomId: String(row.room_id),
      roomCode: String(row.room_code ?? "------"),
      roomName: String(row.room_name ?? `Room ${String(row.room_id).slice(0, 6)}`),
      lastPlayedAt: String(row.last_played_at ?? new Date().toISOString()),
      totalHands: Number(row.total_hands ?? 0),
    }));
  }

  async listHistorySessions(userId: string, roomId: string, limit = 100): Promise<HistorySessionSummary[]> {
    if (!this.admin || !isUuid(userId)) return [];
    const { data, error } = await this.admin.rpc("history_list_sessions", {
      _user_id: userId,
      _room_id: roomId,
      _limit: Math.max(1, Math.min(limit, 500)),
    });
    if (error || !Array.isArray(data)) {
      if (error) console.warn("listHistorySessions failed:", error.message);
      return [];
    }
    return data.map((row) => ({
      roomSessionId: String(row.room_session_id),
      roomId: String(row.room_id ?? roomId),
      openedAt: String(row.opened_at),
      closedAt: row.closed_at ? String(row.closed_at) : null,
      handCount: Number(row.hand_count ?? 0),
    }));
  }

  async listHistoryHands(userId: string, roomSessionId: string, params?: { limit?: number; beforeEndedAt?: string }): Promise<{ hands: HistoryHandSummary[]; hasMore: boolean; nextCursor?: string }> {
    if (!this.admin || !isUuid(userId)) {
      return { hands: [], hasMore: false };
    }
    const pageSize = Math.max(1, Math.min(params?.limit ?? 50, 200));
    const { data, error } = await this.admin.rpc("history_list_hands", {
      _user_id: userId,
      _room_session_id: roomSessionId,
      _limit: pageSize + 1,
      _before_ended_at: params?.beforeEndedAt ?? null,
    });
    if (error || !Array.isArray(data)) {
      if (error) console.warn("listHistoryHands failed:", error.message);
      return { hands: [], hasMore: false };
    }

    const rows = data.slice(0, pageSize);
    const hands = rows.map((row) => mapHistorySummaryRow(row));
    const hasMore = data.length > pageSize;
    const nextCursor = hasMore && hands.length > 0 ? hands[hands.length - 1].endedAt : undefined;

    return { hands, hasMore, nextCursor };
  }

  async getHistoryHandDetail(userId: string, handHistoryId: string): Promise<HistoryHandDetail | null> {
    if (!this.admin || !isUuid(userId)) return null;
    const { data, error } = await this.admin.rpc("history_get_hand_detail", {
      _user_id: userId,
      _hand_history_id: handHistoryId,
    });
    if (error) {
      console.warn("getHistoryHandDetail failed:", error.message);
      return null;
    }
    if (!Array.isArray(data) || data.length === 0) return null;
    const row = data[0];
    const summary = mapHistorySummaryRow(row);
    return {
      ...summary,
      detail: toHistoryDetail(row.detail_json),
    };
  }

  async upsertSeat(record: SeatPersistenceRecord): Promise<void> {
    if (!this.admin) return;
    const { error } = await this.admin.from("live_table_seats").upsert(
      {
        ...record,
        updated_at: new Date().toISOString()
      },
      { onConflict: "table_id,seat_no" }
    );
    if (error) {
      console.warn("upsertSeat failed:", error.message);
    }
  }

  async removeSeat(tableId: string, seatNo: number): Promise<void> {
    if (!this.admin) return;
    const { error } = await this.admin.from("live_table_seats").delete().eq("table_id", tableId).eq("seat_no", seatNo);
    if (error) {
      console.warn("removeSeat failed:", error.message);
    }
  }

  async setDisconnected(tableId: string, seatNo: number): Promise<void> {
    if (!this.admin) return;
    const { error } = await this.admin
      .from("live_table_seats")
      .update({ is_connected: false, updated_at: new Date().toISOString() })
      .eq("table_id", tableId)
      .eq("seat_no", seatNo);
    if (error) {
      console.warn("setDisconnected failed:", error.message);
    }
  }

  async logEvent(payload: {
    tableId: string;
    eventType: string;
    actorUserId?: string;
    handId?: string;
    payload?: Json;
  }): Promise<void> {
    if (!this.admin) return;
    const { error } = await this.admin.from("live_table_events").insert({
      table_id: payload.tableId,
      event_type: payload.eventType,
      actor_user_id: payload.actorUserId,
      hand_id: payload.handId,
      payload: payload.payload ?? {}
    });
    if (error) {
      console.warn("logEvent failed:", error.message);
    }
  }
}

function extractDisplayName(user: User, fallbackName?: string): string {
  const metaName =
    (typeof user.user_metadata?.display_name === "string" && user.user_metadata.display_name) ||
    (typeof user.user_metadata?.name === "string" && user.user_metadata.name);

  return safeDisplayName(metaName || fallbackName || user.email || `user-${user.id.slice(0, 8)}`);
}

function safeDisplayName(input?: string): string {
  const trimmed = (input ?? "Guest").trim();
  if (trimmed.length === 0) return "Guest";
  return trimmed.slice(0, 32);
}

function normalizeRoomCode(roomCode: string): string {
  return roomCode.trim().toUpperCase();
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

function dedupeStrings(values: string[]): string[] {
  return [...new Set(values)];
}

function toFiniteNumber(value: unknown, fallback = 0): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function toStreet(value: unknown): Street {
  const street = String(value ?? "PREFLOP").toUpperCase();
  if (street === "FLOP" || street === "TURN" || street === "RIVER" || street === "SHOWDOWN") {
    return street;
  }
  return "PREFLOP";
}

function toHandActionType(value: unknown): HandActionType {
  const action = String(value ?? "check").toLowerCase();
  if (
    action === "fold" ||
    action === "check" ||
    action === "call" ||
    action === "raise" ||
    action === "all_in" ||
    action === "post_sb" ||
    action === "post_bb" ||
    action === "post_dead_blind"
  ) {
    return action;
  }
  return "check";
}

function metadataToJson(metadata?: SessionContextMetadata): Record<string, Json> {
  if (!metadata) return {};
  const result: Record<string, Json> = {};
  if (metadata.roomCode) result.roomCode = metadata.roomCode;
  if (metadata.roomName) result.roomName = metadata.roomName;
  if (metadata.ownerId) result.ownerId = metadata.ownerId;
  if (metadata.ownerName) result.ownerName = metadata.ownerName;
  if (metadata.trigger) result.trigger = metadata.trigger;
  if (Array.isArray(metadata.coHostIds)) {
    result.coHostIds = metadata.coHostIds.filter((id) => typeof id === "string");
  }
  return result;
}

function mapHistorySummaryRow(row: Record<string, unknown>): HistoryHandSummary {
  return {
    id: String(row.hand_history_id ?? row.id ?? ""),
    roomId: String(row.room_id ?? ""),
    roomSessionId: String(row.room_session_id ?? ""),
    handId: String(row.hand_id ?? ""),
    handNo: toFiniteNumber(row.hand_no, 0),
    endedAt: String(row.ended_at ?? new Date().toISOString()),
    blinds: toBlinds(row.blinds_json),
    players: toHistoryPlayers(row.players_summary_json),
    summary: toHistorySummary(row.summary_json),
  };
}

function toBlinds(value: unknown): { sb: number; bb: number } {
  const src = typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
  return {
    sb: toFiniteNumber(src.sb, 0),
    bb: toFiniteNumber(src.bb, 0),
  };
}

function toHistoryPlayers(value: unknown): HistoryHandPlayerSummary[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((entry) => {
      if (typeof entry !== "object" || entry === null) return null;
      const row = entry as Record<string, unknown>;
      return {
        seat: toFiniteNumber(row.seat, 0),
        userId: String(row.userId ?? ""),
        name: String(row.name ?? `Seat ${toFiniteNumber(row.seat, 0)}`),
      };
    })
    .filter((row): row is HistoryHandPlayerSummary => row !== null && row.seat > 0 && row.userId.length > 0);
}

function toHistoryWinners(value: unknown): Array<{ seat: number; amount: number; handName?: string }> {
  if (!Array.isArray(value)) return [];
  const winners: Array<{ seat: number; amount: number; handName?: string }> = [];
  for (const entry of value) {
    if (typeof entry !== "object" || entry === null) continue;
    const row = entry as Record<string, unknown>;
    const seat = toFiniteNumber(row.seat, 0);
    if (seat <= 0) continue;
    winners.push({
      seat,
      amount: toFiniteNumber(row.amount, 0),
      handName: typeof row.handName === "string" ? row.handName : undefined,
    });
  }
  return winners;
}

function toHistorySummary(value: unknown): HistoryHandSummaryCore {
  const src = typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
  const flagsSource = typeof src.flags === "object" && src.flags !== null ? (src.flags as Record<string, unknown>) : {};
  const myNetSource = typeof src.my_net_by_user === "object" && src.my_net_by_user !== null
    ? src.my_net_by_user as Record<string, unknown>
    : typeof src.myNetByUser === "object" && src.myNetByUser !== null
      ? src.myNetByUser as Record<string, unknown>
      : {};
  const myNetByUser: Record<string, number> = {};
  for (const [userId, net] of Object.entries(myNetSource)) {
    myNetByUser[userId] = toFiniteNumber(net, 0);
  }

  const netByPositionSource = typeof src.net_by_position === "object" && src.net_by_position !== null
    ? src.net_by_position as Record<string, unknown>
    : typeof src.netByPosition === "object" && src.netByPosition !== null
      ? src.netByPosition as Record<string, unknown>
      : {};
  const netByPosition: Record<string, number> = {};
  for (const [position, net] of Object.entries(netByPositionSource)) {
    netByPosition[position] = toFiniteNumber(net, 0);
  }

  const bucketSource = typeof src.starting_hand_buckets_by_user === "object" && src.starting_hand_buckets_by_user !== null
    ? src.starting_hand_buckets_by_user as Record<string, unknown>
    : typeof src.startingHandBucketsByUser === "object" && src.startingHandBucketsByUser !== null
      ? src.startingHandBucketsByUser as Record<string, unknown>
      : {};
  const startingHandBucketsByUser: Record<string, string> = {};
  for (const [userId, bucket] of Object.entries(bucketSource)) {
    if (typeof bucket === "string" && bucket.length > 0) {
      startingHandBucketsByUser[userId] = bucket;
    }
  }

  const runCountRaw = toFiniteNumber(src.run_count ?? src.runCount, 1);
  const runCount: 1 | 2 | 3 = runCountRaw >= 3 ? 3 : runCountRaw === 2 ? 2 : 1;

  return {
    totalPot: toFiniteNumber(src.total_pot ?? src.totalPot, 0),
    runCount,
    winners: toHistoryWinners(src.winners),
    myNetByUser,
    netByPosition: Object.keys(netByPosition).length > 0 ? netByPosition : undefined,
    startingHandBucketsByUser: Object.keys(startingHandBucketsByUser).length > 0 ? startingHandBucketsByUser : undefined,
    gameType: typeof src.game_type === "string"
      ? (src.game_type as HistoryHandSummaryCore["gameType"])
      : typeof src.gameType === "string"
        ? (src.gameType as HistoryHandSummaryCore["gameType"])
        : undefined,
    flags: {
      allIn: Boolean(flagsSource.all_in ?? flagsSource.allIn),
      runItTwice: Boolean(flagsSource.run_it_twice ?? flagsSource.runItTwice),
      showdown: Boolean(flagsSource.showdown),
      bombPot: Boolean(flagsSource.bomb_pot ?? flagsSource.bombPot),
      doubleBoard: Boolean(flagsSource.double_board ?? flagsSource.doubleBoard),
    },
  };
}

function toHistoryDetail(value: unknown): HistoryHandDetailCore {
  const src = typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
  const board = Array.isArray(src.board) ? src.board.filter((card): card is string => typeof card === "string") : [];
  const runoutBoards = Array.isArray(src.runoutBoards)
    ? src.runoutBoards.map((run) => Array.isArray(run) ? run.filter((card): card is string => typeof card === "string") : [])
    : [];

  const potLayers = Array.isArray(src.potLayers)
    ? src.potLayers
        .map((layer) => {
          if (typeof layer !== "object" || layer === null) return null;
          const row = layer as Record<string, unknown>;
          const eligibleSeats = Array.isArray(row.eligibleSeats)
            ? row.eligibleSeats.map((seat) => toFiniteNumber(seat, 0)).filter((seat) => seat > 0)
            : [];
          return {
            label: String(row.label ?? "Pot"),
            amount: toFiniteNumber(row.amount, 0),
            eligibleSeats,
          };
        })
        .filter((layer): layer is { label: string; amount: number; eligibleSeats: number[] } => layer !== null)
    : [];

  const contributionsSource = typeof src.contributionsBySeat === "object" && src.contributionsBySeat !== null
    ? src.contributionsBySeat as Record<string, unknown>
    : {};
  const contributionsBySeat: Record<number, number> = {};
  for (const [seatKey, amount] of Object.entries(contributionsSource)) {
    const seat = toFiniteNumber(seatKey, 0);
    if (seat > 0) {
      contributionsBySeat[seat] = toFiniteNumber(amount, 0);
    }
  }

  const actionTimeline = Array.isArray(src.actionTimeline)
    ? src.actionTimeline
        .map((action) => {
          if (typeof action !== "object" || action === null) return null;
          const row = action as Record<string, unknown>;
          return {
            seat: toFiniteNumber(row.seat, 0),
            street: toStreet(row.street),
            type: toHandActionType(row.type),
            amount: toFiniteNumber(row.amount, 0),
            at: toFiniteNumber(row.at, Date.now()),
          };
        })
        .filter((action): action is { seat: number; street: Street; type: HandActionType; amount: number; at: number } => action !== null && action.seat > 0)
    : [];

  const revealedSource = typeof src.revealedHoles === "object" && src.revealedHoles !== null
    ? src.revealedHoles as Record<string, unknown>
    : {};
  const revealedHoles: Record<number, [string, string]> = {};
  for (const [seatKey, cards] of Object.entries(revealedSource)) {
    const seat = toFiniteNumber(seatKey, 0);
    if (seat <= 0 || !Array.isArray(cards) || cards.length !== 2) continue;
    const c1 = String(cards[0] ?? "");
    const c2 = String(cards[1] ?? "");
    if (!c1 || !c2) continue;
    revealedHoles[seat] = [c1, c2];
  }

  // Extract private hole cards by userId (for hero's folded cards)
  const privateSource = typeof src.privateHoleCardsByUser === "object" && src.privateHoleCardsByUser !== null
    ? src.privateHoleCardsByUser as Record<string, unknown>
    : {};
  const privateHoleCardsByUser: Record<string, [string, string]> = {};
  for (const [userId, cards] of Object.entries(privateSource)) {
    if (!userId || !Array.isArray(cards) || cards.length !== 2) continue;
    const c1 = String(cards[0] ?? "");
    const c2 = String(cards[1] ?? "");
    if (!c1 || !c2) continue;
    privateHoleCardsByUser[userId] = [c1, c2];
  }

  const payoutLedger = Array.isArray(src.payoutLedger)
    ? src.payoutLedger
        .map((entry) => {
          if (typeof entry !== "object" || entry === null) return null;
          const row = entry as Record<string, unknown>;
          return {
            seat: toFiniteNumber(row.seat, 0),
            playerName: String(row.playerName ?? `Seat ${toFiniteNumber(row.seat, 0)}`),
            startStack: toFiniteNumber(row.startStack, 0),
            invested: toFiniteNumber(row.invested, 0),
            won: toFiniteNumber(row.won, 0),
            endStack: toFiniteNumber(row.endStack, 0),
            net: toFiniteNumber(row.net, 0),
          };
        })
        .filter((entry): entry is { seat: number; playerName: string; startStack: number; invested: number; won: number; endStack: number; net: number } => entry !== null && entry.seat > 0)
    : [];

  const doubleBoardPayouts = Array.isArray(src.doubleBoardPayouts)
    ? src.doubleBoardPayouts
        .map((entry) => {
          if (typeof entry !== "object" || entry === null) return null;
          const row = entry as Record<string, unknown>;
          const board = Array.isArray(row.board)
            ? row.board.filter((card): card is string => typeof card === "string")
            : [];
          const winners = toHistoryWinners(row.winners);
          const run = toFiniteNumber(row.run, 1) === 2 ? 2 : 1;
          return { run: run as 1 | 2, board, winners };
        })
        .filter((entry): entry is { run: 1 | 2; board: string[]; winners: Array<{ seat: number; amount: number; handName?: string }> } => entry !== null)
    : undefined;

  return {
    board,
    runoutBoards,
    doubleBoardPayouts,
    potLayers,
    contributionsBySeat,
    actionTimeline,
    revealedHoles,
    privateHoleCardsByUser: Object.keys(privateHoleCardsByUser).length > 0 ? privateHoleCardsByUser : undefined,
    payoutLedger,
  };
}
