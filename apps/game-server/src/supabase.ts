import { createClient, type SupabaseClient, type User } from "@supabase/supabase-js";
import type { LobbyRoomSummary } from "@cardpilot/shared-types";

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
      .select("id, room_code, room_name, status, max_players, small_blind, big_blind, is_public, updated_at")
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
      updatedAt: String(data.updated_at ?? new Date().toISOString())
    };
  }

  async findRoomByTableId(tableId: string): Promise<RoomRecord | null> {
    if (!this.admin) return null;
    const { data, error } = await this.admin
      .from("live_tables")
      .select("id, room_code, room_name, status, max_players, small_blind, big_blind, is_public, updated_at")
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
      updatedAt: String(data.updated_at ?? new Date().toISOString())
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
