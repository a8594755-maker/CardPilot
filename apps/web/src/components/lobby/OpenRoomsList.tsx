import { memo, useCallback } from "react";
import type { LobbyRoomSummary } from "@cardpilot/shared-types";

export interface OpenRoomsListProps {
  rooms: LobbyRoomSummary[];
  disabled: boolean;
  onJoinRoom: (roomCode: string) => void;
  onRefresh: () => void;
  onCreatePublic: () => void;
}

/* ── Single room row ── */
const RoomCard = memo(function RoomCard({
  room,
  disabled,
  onJoin,
}: {
  room: LobbyRoomSummary;
  disabled: boolean;
  onJoin: (code: string) => void;
}) {
  const seatsAvailable = room.maxPlayers - room.playerCount;
  const isFull = seatsAvailable <= 0;

  return (
    <div className="cp-room-card group">
      {/* Left: seat count badge */}
      <div
        className={`w-7 h-7 rounded-md flex items-center justify-center text-[9px] font-semibold shrink-0 border ${
          isFull
            ? "bg-slate-700/20 border-slate-600/20 text-slate-500"
            : "bg-emerald-500/8 border-emerald-500/20 text-emerald-400/80"
        }`}
      >
        <span className="cp-num">{room.playerCount}</span>
        <span className="text-[8px] text-slate-500/80 font-normal">/{room.maxPlayers}</span>
      </div>

      {/* Center: room info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-white text-sm truncate">{room.roomName}</span>
          {room.visibility === "private" && (
            <span className="text-amber-400 text-xs" title="Private room">🔒</span>
          )}
        </div>
        <div className="mt-0.5 space-y-0.5">
          <div className="text-[11px] text-slate-500 leading-tight cp-num">
            Blinds <span className="text-slate-300">{room.smallBlind}/{room.bigBlind}</span>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] leading-tight">
            {isFull ? (
              <span className="text-red-400/70">Full</span>
            ) : (
              <span className="text-emerald-400/75">
                {seatsAvailable} seat{seatsAvailable !== 1 ? "s" : ""} open
              </span>
            )}
            {room.isClubTable && room.clubName && (
              <>
                <span className="text-white/15">·</span>
                <span className="text-blue-400/70 truncate max-w-[96px]">{room.clubName}</span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Right: join button */}
      <button
        disabled={disabled || isFull}
        onClick={() => onJoin(room.roomCode)}
        className={`cp-btn text-[10px] font-medium px-2.5 py-0.5 min-h-[24px] rounded shrink-0 mt-1.5 transition-opacity ${
          isFull
            ? "cp-btn-ghost opacity-40 cursor-not-allowed"
            : "cp-btn-primary opacity-70 group-hover:opacity-100"
        }`}
      >
        {isFull ? "Full" : "Join"}
      </button>
    </div>
  );
});

/* ── Empty state ── */
function EmptyState({
  disabled,
  onCreatePublic,
  onFocusJoinCode,
}: {
  disabled: boolean;
  onCreatePublic: () => void;
  onFocusJoinCode?: () => void;
}) {
  return (
    <div className="text-center py-10">
      <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-white/[0.03] border border-white/5 mb-4">
        <span className="text-2xl opacity-30">♠</span>
      </div>
      <p className="text-slate-400 text-sm font-medium">No public rooms right now.</p>
      <p className="text-slate-500 text-xs mt-1 mb-4">Create one or join with a code.</p>
      <div className="flex items-center justify-center gap-3">
        <button
          disabled={disabled}
          onClick={onCreatePublic}
          className="cp-btn cp-btn-primary text-xs px-4"
        >
          Create a public room
        </button>
      </div>
    </div>
  );
}

export const OpenRoomsList = memo(function OpenRoomsList({
  rooms,
  disabled,
  onJoinRoom,
  onRefresh,
  onCreatePublic,
}: OpenRoomsListProps) {
  const openRooms = rooms.filter((r) => r.status === "OPEN");

  return (
    <div className="cp-lobby-card">
      <div className="flex items-center justify-between mb-4">
        <h2 className="cp-lobby-title">Open Rooms</h2>
        <button
          onClick={onRefresh}
          disabled={disabled}
          className="cp-btn cp-btn-ghost text-xs px-3"
          style={{ minHeight: 32 }}
        >
          Refresh
        </button>
      </div>

      {openRooms.length === 0 ? (
        <EmptyState disabled={disabled} onCreatePublic={onCreatePublic} />
      ) : (
        <div className="space-y-2">
          {openRooms.map((r) => (
            <RoomCard key={r.tableId} room={r} disabled={disabled} onJoin={onJoinRoom} />
          ))}
        </div>
      )}
    </div>
  );
});
