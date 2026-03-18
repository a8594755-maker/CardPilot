import type { SeatInfo } from '@cardpilot/shared-types';
import { PokerCard } from '../PokerCard.js';

interface SeatProps {
  seat: SeatInfo;
  isMySeat?: boolean;
  holeCards?: [string, string];
  isActor?: boolean;
  onClick?: () => void;
}

export function Seat({ seat, isMySeat, holeCards, isActor, onClick }: SeatProps) {
  const isEmpty = seat.status === 'empty';

  return (
    <div
      className={`
        relative p-3 rounded-xl transition-all duration-200
        ${
          isEmpty
            ? 'bg-slate-800/80 border-2 border-dashed border-slate-600 cursor-pointer hover:border-slate-400'
            : 'bg-slate-900/90 border-2 border-slate-700'
        }
        ${isMySeat ? 'ring-2 ring-cyan-500' : ''}
        ${isActor ? 'ring-2 ring-yellow-400 animate-pulse' : ''}
      `}
      onClick={onClick}
    >
      {/* Position markers */}
      <div className="absolute -top-2 -right-2 flex gap-1">
        {seat.isButton && (
          <span className="w-5 h-5 bg-white text-black text-xs font-bold rounded-full flex items-center justify-center shadow-lg">
            D
          </span>
        )}
        {seat.isSmallBlind && (
          <span className="w-5 h-5 bg-blue-500 text-white text-xs font-bold rounded-full flex items-center justify-center shadow-lg">
            SB
          </span>
        )}
        {seat.isBigBlind && (
          <span className="w-5 h-5 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center shadow-lg">
            BB
          </span>
        )}
      </div>

      {isEmpty ? (
        <div className="w-28 h-24 flex items-center justify-center">
          <span className="text-slate-500 text-sm">Seat {seat.index + 1}</span>
        </div>
      ) : (
        <div className="w-32">
          {/* Player Info */}
          <div className="text-center mb-2">
            <div className="text-white font-medium text-sm truncate">
              {seat.user?.nickname || `Player ${seat.index + 1}`}
            </div>
            <div className="text-yellow-400 font-mono text-sm">{seat.stack.toLocaleString()}</div>
          </div>

          {/* Sit Out badge */}
          {seat.status === 'sitting_out' && (
            <div className="text-center text-[10px] text-orange-400 font-bold uppercase mb-1">
              Sit Out
            </div>
          )}

          {/* Hole Cards */}
          {holeCards ? (
            <div className="flex justify-center gap-1">
              {holeCards.map((card, i) => (
                <PokerCard key={i} card={card} variant="seat" />
              ))}
            </div>
          ) : seat.status === 'sitting_out' ? (
            <div className="flex justify-center gap-1 opacity-30">
              <PokerCard faceDown variant="seat" />
              <PokerCard faceDown variant="seat" />
            </div>
          ) : (
            <div className="flex justify-center gap-1">
              <PokerCard faceDown variant="seat" />
              <PokerCard faceDown variant="seat" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default Seat;
