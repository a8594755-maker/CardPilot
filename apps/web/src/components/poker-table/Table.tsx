import type { TableSnapshotPayload, SeatInfo } from '@cardpilot/shared-types';
import { Seat } from './Seat.js';
import { CommunityCards } from './CommunityCards.js';

interface TableProps {
  snapshot: TableSnapshotPayload | null;
  mySeatIndex?: number;
  holeCards?: [string, string];
  onSeatClick?: (seatIndex: number) => void;
}

export function Table({ snapshot, mySeatIndex, holeCards, onSeatClick }: TableProps) {
  if (!snapshot) {
    return (
      <div className="w-full max-w-4xl aspect-[16/10] bg-slate-800 rounded-3xl flex items-center justify-center">
        <p className="text-slate-400">Loading...</p>
      </div>
    );
  }

  const { seats, currentHand, smallBlind, bigBlind } = snapshot;

  return (
    <div className="w-full max-w-4xl">
      {/* Table Header */}
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-xl font-bold text-white">{snapshot.name}</h2>
          <p className="text-sm text-slate-400">
            Blinds: {smallBlind}/{bigBlind} | Code: {snapshot.roomCode}
          </p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold text-yellow-400">{currentHand?.pot || 0}</div>
          <div className="text-xs text-slate-400">Pot</div>
        </div>
      </div>

      {/* Table Surface */}
      <div className="relative aspect-[16/10] rounded-[50%] poker-table-surface">
        {/* Community Cards - Center */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
          <CommunityCards cards={currentHand?.communityCards || []} />
        </div>

        {/* Pot - Above community cards */}
        <div className="absolute top-[35%] left-1/2 -translate-x-1/2">
          <div className="bg-black/50 px-4 py-2 rounded-full text-yellow-400 font-bold">
            {currentHand?.pot || 0}
          </div>
        </div>

        {/* Seats */}
        {seats.map((seat, index) => (
          <SeatPosition
            key={seat.index}
            seat={seat}
            index={index}
            totalSeats={seats.length}
            isMySeat={seat.index === mySeatIndex}
            holeCards={seat.index === mySeatIndex ? holeCards : undefined}
            isActor={currentHand?.actorSeat === seat.index}
            onClick={() => onSeatClick?.(seat.index)}
          />
        ))}

        {/* Current Bet */}
        {currentHand && currentHand.currentBet > 0 && (
          <div className="absolute bottom-[30%] left-1/2 -translate-x-1/2">
            <div className="text-white/80 text-sm">Bet: {currentHand.currentBet}</div>
          </div>
        )}
      </div>

      {/* Hand Info */}
      {currentHand && (
        <div className="mt-4 flex justify-center gap-4 text-sm">
          <span className="text-slate-400">Hand #{currentHand.handNumber}</span>
          <span className="text-slate-400">|</span>
          <span className="text-yellow-400 uppercase">{currentHand.status}</span>
          {currentHand.actorSeat !== null && (
            <>
              <span className="text-slate-400">|</span>
              <span className="text-cyan-400">Action: Seat {currentHand.actorSeat + 1}</span>
            </>
          )}
        </div>
      )}
    </div>
  );
}

interface SeatPositionProps {
  seat: SeatInfo;
  index: number;
  totalSeats: number;
  isMySeat?: boolean;
  holeCards?: [string, string];
  isActor?: boolean;
  onClick?: () => void;
}

function SeatPosition({
  seat,
  index,
  totalSeats,
  isMySeat,
  holeCards,
  isActor,
  onClick,
}: SeatPositionProps) {
  // Calculate position on the oval table
  // For 6max: positions at roughly 12, 2, 4, 6, 8, 10 o'clock
  const angle = (index / totalSeats) * 2 * Math.PI - Math.PI / 2;
  const radiusX = 42; // % from center (horizontal)
  const radiusY = 38; // % from center (vertical)

  const left = 50 + radiusX * Math.cos(angle);
  const top = 50 + radiusY * Math.sin(angle);

  return (
    <div
      className="absolute -translate-x-1/2 -translate-y-1/2"
      style={{ left: `${left}%`, top: `${top}%` }}
    >
      <Seat
        seat={seat}
        isMySeat={isMySeat}
        holeCards={holeCards}
        isActor={isActor}
        onClick={onClick}
      />
    </div>
  );
}

export default Table;
