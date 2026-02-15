import type { LocalRoomSummary } from "../../lib/hand-history.js";

function formatRelativeTime(ts: number): string {
  const diff = Date.now() - ts;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function RoomList({
  rooms,
  selectedCode,
  onSelect,
  loading,
}: {
  rooms: LocalRoomSummary[];
  selectedCode: string | null;
  onSelect: (code: string) => void;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="flex-1 overflow-auto p-2 space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="history-row-skeleton h-[72px]" />
        ))}
      </div>
    );
  }

  if (rooms.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
        <div className="text-3xl mb-3 opacity-40">🃏</div>
        <p className="text-slate-400 text-sm font-medium">No rooms yet</p>
        <p className="text-slate-500 text-xs mt-1">Play a hand to populate history.</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto p-1.5 space-y-1">
      {rooms.map((room) => {
        const active = selectedCode === room.roomCode;
        const net = room.netResult;
        // Compute bb/100 if we have big blind info
        const bb100 = room.bigBlind > 0 && room.handsCount > 0
          ? ((net / room.bigBlind) / room.handsCount * 100).toFixed(1)
          : null;
        return (
          <button
            key={room.roomCode}
            onClick={() => onSelect(room.roomCode)}
            className={`w-full text-left rounded-xl p-3 transition-all border ${
              active
                ? "border-sky-500/60 bg-sky-500/10 shadow-lg shadow-sky-900/20"
                : "border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.05] hover:border-white/[0.12]"
            }`}
            style={{ minHeight: 64 }}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-white truncate">{room.roomName}</span>
                  {room.roomCode !== "_local" && (
                    <span className="text-[10px] font-mono text-slate-500 shrink-0">{room.roomCode}</span>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-1 text-[11px] text-slate-400">
                  <span className="font-medium">{room.stakes}</span>
                  <span className="text-slate-600">·</span>
                  <span>{room.handsCount} hand{room.handsCount !== 1 ? "s" : ""}</span>
                  <span className="text-slate-600">·</span>
                  <span>{formatRelativeTime(room.lastPlayedAt)}</span>
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className={`text-sm font-bold tabular-nums ${
                  net > 0 ? "text-emerald-400" : net < 0 ? "text-red-400" : "text-slate-400"
                }`}>
                  {net > 0 ? "+" : ""}{net.toLocaleString()}
                </div>
                {bb100 !== null && (
                  <div className={`text-[10px] tabular-nums ${
                    Number(bb100) > 0 ? "text-emerald-500/70" : Number(bb100) < 0 ? "text-red-500/70" : "text-slate-500"
                  }`}>
                    {Number(bb100) > 0 ? "+" : ""}{bb100} bb/100
                  </div>
                )}
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
