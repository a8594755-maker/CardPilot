import type { LocalRoomSummary } from '../../lib/hand-history.js';

function formatRelativeTime(ts: number): string {
  const diff = Date.now() - ts;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** Tiny inline spark bar to visualize W/L ratio */
function WinLossBar({ wins, total }: { wins: number; total: number }) {
  if (total === 0) return null;
  const pct = Math.round((wins / total) * 100);
  return (
    <div className="flex items-center gap-1.5 mt-1.5">
      <div className="flex-1 h-[3px] rounded-full bg-slate-700/60 overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[9px] text-slate-500 tabular-nums shrink-0">{pct}%</span>
    </div>
  );
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
          <div key={i} className="cp-history-skeleton h-[80px] rounded-xl" />
        ))}
      </div>
    );
  }

  if (rooms.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <div className="w-12 h-12 rounded-2xl bg-white/[0.04] border border-white/[0.08] flex items-center justify-center mb-3">
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-slate-500"
          >
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <path d="M3 9h18" />
            <path d="M9 21V9" />
          </svg>
        </div>
        <p className="text-slate-400 text-sm font-medium">No rooms yet</p>
        <p className="text-slate-600 text-xs mt-1.5 max-w-[180px] leading-relaxed">
          Play some hands and they'll appear here automatically.
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto p-2 space-y-1 cp-history-scroll">
      {rooms.map((room) => {
        const active = selectedCode === room.roomCode;
        const net = room.netResult;
        const handsWon = room.handsWon ?? 0;
        const handsLost = Math.max(0, room.handsCount - handsWon);
        // Compute bb/100 if we have big blind info
        const bb100 =
          room.bigBlind > 0 && room.handsCount > 0
            ? ((net / room.bigBlind / room.handsCount) * 100).toFixed(1)
            : null;
        return (
          <button
            key={room.roomCode}
            onClick={() => onSelect(room.roomCode)}
            className={`cp-history-room-card w-full text-left rounded-xl p-3 transition-all border ${
              active
                ? 'border-sky-500/40 bg-sky-500/[0.08] shadow-lg shadow-sky-900/15'
                : 'border-white/[0.05] bg-white/[0.02] hover:bg-white/[0.04] hover:border-white/[0.10]'
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-0.5">
                  <span
                    className={`text-[13px] font-semibold truncate ${active ? 'text-white' : 'text-slate-200'}`}
                  >
                    {room.roomName}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 text-[10px] text-slate-500">
                  {room.roomCode !== '_local' && (
                    <>
                      <span className="font-mono text-slate-600">{room.roomCode}</span>
                      <span className="text-slate-700">·</span>
                    </>
                  )}
                  <span className="font-medium text-slate-400">{room.stakes}</span>
                  <span className="text-slate-700">·</span>
                  <span>{room.handsCount} hands</span>
                </div>
              </div>
              <div className="text-right shrink-0">
                <div
                  className={`text-[13px] font-bold tabular-nums leading-tight ${
                    net > 0 ? 'text-emerald-400' : net < 0 ? 'text-red-400' : 'text-slate-500'
                  }`}
                >
                  {net > 0 ? '+' : ''}
                  {net.toLocaleString()}
                </div>
                {bb100 !== null && (
                  <div
                    className={`text-[10px] tabular-nums mt-0.5 ${
                      Number(bb100) > 0
                        ? 'text-emerald-500/60'
                        : Number(bb100) < 0
                          ? 'text-red-500/60'
                          : 'text-slate-600'
                    }`}
                  >
                    {Number(bb100) > 0 ? '+' : ''}
                    {bb100} bb/100
                  </div>
                )}
              </div>
            </div>
            {/* Win/Loss bar */}
            <WinLossBar wins={handsWon} total={handsWon + handsLost} />
            {/* Footer: time + W/L count */}
            <div className="flex items-center justify-between mt-1.5 text-[9px] text-slate-600">
              <span>{formatRelativeTime(room.lastPlayedAt)}</span>
              <span className="tabular-nums">
                <span className="text-emerald-500/50">W{handsWon}</span>
                {' / '}
                <span className="text-red-500/50">L{handsLost}</span>
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
