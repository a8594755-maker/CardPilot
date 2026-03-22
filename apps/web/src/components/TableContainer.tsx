import { useRef, useEffect, useState, useMemo } from 'react';
import { useGame } from '../contexts/GameContext';

import { useTableScale } from '../hooks/useTableScale';
import { useIsMobile } from '../hooks/useIsMobile';
import { useChipAnimationDriver, type ChipAnimationAnchors } from '../hooks/useChipAnimationDriver';
import { SeatChip } from './SeatChip';
import { PokerCard } from './PokerCard';
import { ChipAnimationLayer } from './ChipAnimationLayer';
import { loadAnimationSpeed, type AnimationSpeed } from '../lib/chip-animation';
import { formatChips } from '../lib/format-chips';
import { getSeatLayout, mapSeatToVisualIndex } from '../lib/seat-layout';

interface TableContainerProps {
  onSeatClick?: (seatNum: number) => void;
}

export function TableContainer({ onSeatClick }: TableContainerProps) {
  const {
    snapshot,
    roomState,
    seat,
    holeCards,
    settlement,
    sevenTwoRevealActive,
    lastActionBySeat,
    actionTimer,
  } = useGame();

  const tableStageRef = useRef<HTMLDivElement>(null);
  const tableContainerRef = useRef<HTMLDivElement>(null);
  const potRef = useRef<HTMLDivElement>(null);
  const seatRefs = useRef<Record<number, HTMLElement | null>>({});

  const [chipAnimSpeed] = useState<AnimationSpeed>(loadAnimationSpeed);

  const _isMobile = useIsMobile();
  const [isMobilePortrait, setIsMobilePortrait] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia('(max-width: 768px) and (orientation: portrait) and (pointer: coarse)')
      .matches;
  });

  useEffect(() => {
    const mq = window.matchMedia(
      '(max-width: 768px) and (orientation: portrait) and (pointer: coarse)',
    );
    const handler = (e: MediaQueryListEvent) => setIsMobilePortrait(e.matches);
    setIsMobilePortrait(mq.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const { scale: tableScale } = useTableScale({
    container: tableStageRef.current,
    baseWidth: isMobilePortrait ? 500 : 1600,
    baseHeight: 900,
    minScale: 0.28,
    maxScale: isMobilePortrait ? 1.0 : 1.4,
    enabled: true,
  });

  const chipAnchorsLive: ChipAnimationAnchors = {
    container: tableContainerRef.current,
    pot: potRef.current,
    seats: seatRefs.current,
  };

  const {
    transfers: chipTransfers,
    removeTransfer,
    onSnapshot: chipOnSnapshot,
    onSettlement: chipOnSettlement,
    onBountyClaim: chipOnBountyClaim,
  } = useChipAnimationDriver(chipAnchorsLive, chipAnimSpeed);

  useEffect(() => {
    if (snapshot) chipOnSnapshot(snapshot);
  }, [snapshot, chipOnSnapshot]);

  useEffect(() => {
    if (settlement) chipOnSettlement(settlement);
  }, [settlement, chipOnSettlement]);

  useEffect(() => {
    if (sevenTwoRevealActive) chipOnBountyClaim(sevenTwoRevealActive);
  }, [sevenTwoRevealActive, chipOnBountyClaim]);

  // Seat layout
  const maxPlayers = roomState?.settings?.maxPlayers ?? 6;
  const seatPositions = useMemo(() => getSeatLayout(maxPlayers), [maxPlayers]);

  const seatElements = useMemo(() => {
    return Array.from({ length: maxPlayers }, (_, i) => i + 1).map((seatNum) => {
      const visualSeatNum =
        seat == null ? seatNum : mapSeatToVisualIndex(seatNum, seat, maxPlayers);
      const pos = seatPositions[visualSeatNum];
      const player = snapshot?.players.find((p) => p.seat === seatNum);
      const isActor = snapshot?.actorSeat === seatNum;
      const isMe = seatNum === seat;
      const isOwner = player && roomState?.ownership.ownerId === player.userId;
      const isCo = player && roomState?.ownership.coHostIds.includes(player.userId);
      const posLabel = snapshot?.positions?.[seatNum] ?? '';
      const isButton = snapshot?.buttonSeat === seatNum && !!snapshot?.handId;
      const revealedCards = snapshot?.revealedHoles?.[seatNum] as [string, string] | undefined;
      const isMucked = snapshot?.muckedSeats?.includes(seatNum) ?? false;
      const winnerHandName = snapshot?.winners?.find(
        (w: { seat: number; handName?: string }) => w.seat === seatNum,
      )?.handName;

      return (
        <div
          key={seatNum}
          ref={(el) => {
            seatRefs.current[seatNum] = el;
          }}
          className="absolute -translate-x-1/2 -translate-y-1/2"
          style={{ top: pos?.top, left: pos?.left }}
        >
          <SeatChip
            player={player}
            seatNum={seatNum}
            isActor={!!isActor}
            isMe={isMe}
            isOwner={!!isOwner}
            isCoHost={!!isCo}
            isBot={player?.isBot}
            timer={actionTimer?.seat === seatNum && !player?.isBot ? actionTimer : null}
            timerTotal={roomState?.settings.actionTimerSeconds ?? 15}
            posLabel={posLabel}
            isButton={isButton}
            bigBlind={snapshot?.bigBlind ?? 3}
            lastAction={lastActionBySeat?.[seatNum] ?? null}
            revealedCards={revealedCards}
            revealedHandName={winnerHandName}
            isMucked={isMucked}
            onClickEmpty={onSeatClick}
          />
        </div>
      );
    });
  }, [
    snapshot,
    seat,
    roomState,
    maxPlayers,
    seatPositions,
    lastActionBySeat,
    onSeatClick,
    actionTimer,
  ]);

  const board = snapshot?.board ?? [];
  const totalPot = snapshot?.pot ?? 0;
  const bb = snapshot?.bigBlind ?? 3;

  return (
    <div
      ref={tableStageRef}
      className="flex-1 relative overflow-hidden bg-slate-950 flex items-center justify-center"
    >
      <div
        className="cp-table-scale-frame"
        style={{ '--cp-table-scale': tableScale } as React.CSSProperties}
      >
        <div className="cp-table-scale-layer">
          <div ref={tableContainerRef} className="cp-table-canvas">
            <div className="cp-table-felt cp-table-felt--green" />

            {/* Community cards */}
            <div className="cp-table-center">
              <div className="cp-board-row cp-board-row--single">
                {board.length > 0
                  ? board.map((c: string, i: number) => (
                      <div key={`${snapshot?.handId ?? 'h'}-${i}`}>
                        <PokerCard card={c} variant="table" />
                      </div>
                    ))
                  : Array.from({ length: 5 }).map((_, i) => (
                      <div key={i} className="cp-board-slot" />
                    ))}
              </div>
            </div>

            {/* Pot */}
            <div ref={potRef} className="cp-pot-anchor">
              {totalPot > 0 && (
                <div className="cp-pot-pill">
                  <div className="flex items-center justify-between gap-4 text-slate-300 uppercase tracking-wider text-base">
                    <span className="font-semibold">Pot</span>
                    <span className="text-amber-400 font-bold cp-num normal-case text-xl">
                      {formatChips(totalPot, { mode: 'chips', bbSize: bb })}
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* Seats */}
            <div className="cp-seat-ring">{seatElements}</div>

            {/* Chip animations */}
            <ChipAnimationLayer
              transfers={chipTransfers}
              onTransferDone={removeTransfer}
              speed={chipAnimSpeed}
            />
          </div>
        </div>
      </div>

      {/* Hero cards */}
      {holeCards.length > 0 && (
        <div className="cp-hero-strip">
          <span className="text-[9px] text-slate-500 uppercase tracking-wider mr-1">Your Hand</span>
          {holeCards.map((c, i) => (
            <PokerCard key={i} card={c} variant="table" />
          ))}
        </div>
      )}
    </div>
  );
}
