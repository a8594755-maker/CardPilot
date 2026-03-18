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
    <div className="cp-lobby-card" style={{ borderColor: 'rgba(251, 191, 36, 0.2)' }}>
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
        {/* Left: icon + info */}
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-11 h-11 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-lg shrink-0">
            {isOwner ? '👑' : '♠'}
          </div>
          <div className="min-w-0">
            <div className="text-xs text-slate-400 uppercase tracking-wider font-medium">
              {isOwner ? 'Your Room' : 'Current Room'}
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="font-mono font-bold text-amber-400 text-lg tracking-[0.15em] cp-num">
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
