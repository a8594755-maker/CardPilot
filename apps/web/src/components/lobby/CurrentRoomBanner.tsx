import { memo } from 'react';

export interface CurrentRoomBannerProps {
  roomCode: string;
  roomName: string;
  isOwner: boolean;
  onCopyCode: () => void;
  onGoToTable: () => void;
  onLeave: () => void;
}

export const CurrentRoomBanner = memo(function CurrentRoomBanner({
  roomCode,
  roomName,
  isOwner,
  onCopyCode,
  onGoToTable,
  onLeave,
}: CurrentRoomBannerProps) {
  return (
    <div
      className="cp-lobby-card"
      style={{
        borderColor: 'rgba(217, 119, 6, 0.25)',
        background: 'linear-gradient(145deg, rgba(217, 119, 6, 0.06), rgba(15, 23, 36, 0.82))',
      }}
    >
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
        {/* Left: icon + info */}
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-11 h-11 rounded-xl bg-amber-600/12 border border-amber-500/25 flex items-center justify-center shrink-0">
            {isOwner ? (
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="#f59e0b"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M2 4l3 12h14l3-12-6 7-5-7-5 7-4-7z" />
                <path d="M5 16h14v4H5z" />
              </svg>
            ) : (
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="#94a3b8"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z" />
                <circle cx="12" cy="9" r="2.5" />
              </svg>
            )}
          </div>
          <div className="min-w-0">
            <div className="text-xs text-slate-400 uppercase tracking-wider font-medium">
              {isOwner ? 'Your Room' : 'Current Room'}
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="font-mono font-extrabold text-amber-500 text-lg tracking-[0.15em] cp-num">
                {roomCode}
              </span>
              {roomName && (
                <span className="text-sm text-slate-400 truncate max-w-[160px]">{roomName}</span>
              )}
            </div>
          </div>
        </div>

        {/* Right: actions */}
        <div className="flex items-center gap-2 sm:ml-auto shrink-0">
          <button
            onClick={onCopyCode}
            className="cp-btn cp-btn-ghost text-xs px-3"
            style={{ minHeight: 36 }}
          >
            Copy Code
          </button>
          <button
            onClick={onGoToTable}
            className="cp-btn cp-btn-success text-xs px-4 font-semibold"
            style={{ minHeight: 36 }}
          >
            Go to Table
          </button>
          <button
            onClick={onLeave}
            className="cp-btn cp-btn-ghost text-xs px-3"
            style={{ minHeight: 36, borderColor: 'rgba(239, 68, 68, 0.2)', color: '#f87171' }}
          >
            Leave
          </button>
        </div>
      </div>
    </div>
  );
});
