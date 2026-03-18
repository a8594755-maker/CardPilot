import { useRef, useEffect, useState, useMemo } from 'react';
import { useGame } from '../contexts/GameContext';
import { useTableScale } from '../hooks/useTableScale';
import { useIsMobile } from '../hooks/useIsMobile';
import { useChipAnimationDriver, type ChipAnimationAnchors } from '../hooks/useChipAnimationDriver';
import { Table } from './poker-table/Table';
import { ChipAnimationLayer } from './ChipAnimationLayer';
import { loadAnimationSpeed, type AnimationSpeed } from '../lib/chip-animation';
import type { TableSnapshotPayload } from '@cardpilot/shared-types';

export function TableContainer() {
  const { snapshot, roomState, seat, holeCards, settlement, sevenTwoRevealActive } = useGame();

  const tableStageRef = useRef<HTMLDivElement>(null);
  const tableContainerRef = useRef<HTMLDivElement>(null);
  const potRef = useRef<HTMLDivElement>(null);
  const seatRefs = useRef<Record<number, HTMLElement | null>>({});

  // Chip animation speed state
  const [chipAnimSpeed, setChipAnimSpeed] = useState<AnimationSpeed>(loadAnimationSpeed);

  const isMobile = useIsMobile();
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

  // Re-create anchors object on each render so driver reads live DOM refs
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

  // Drive animations from GameContext state updates
  useEffect(() => {
    if (snapshot) chipOnSnapshot(snapshot);
  }, [snapshot, chipOnSnapshot]);

  useEffect(() => {
    if (settlement) chipOnSettlement(settlement);
  }, [settlement, chipOnSettlement]);

  useEffect(() => {
    if (sevenTwoRevealActive) chipOnBountyClaim(sevenTwoRevealActive);
  }, [sevenTwoRevealActive, chipOnBountyClaim]);

  // Combine snapshot and roomState to match TableProps requirements
  const tableSnapshot = useMemo<TableSnapshotPayload | null>(() => {
    if (!snapshot) return null;
    return {
      ...snapshot,
      // Map missing properties from RoomFullState or defaults
      roomId: roomState?.tableId ?? snapshot.tableId,
      roomCode: roomState?.roomCode ?? '???',
      name: roomState?.roomName ?? 'Table',
      status: roomState?.status ?? 'OPEN',
      // Ensure we satisfy TableSnapshotPayload interface
      maxPlayers: roomState?.settings?.maxPlayers ?? 9,
      isPublic: roomState?.settings?.visibility === 'public',
    } as unknown as TableSnapshotPayload;
    // using unknown cast as safety hatch if types are slightly mismatched in strict check
    // effectively we are polyfilling the display fields Table.tsx needs
  }, [snapshot, roomState]);

  return (
    <div
      ref={tableStageRef}
      className="flex-1 relative overflow-hidden bg-slate-950 flex items-center justify-center"
    >
      <div
        ref={tableContainerRef}
        style={{
          width: isMobilePortrait ? 500 : 1600,
          height: 900,
          transform: `scale(${tableScale})`,
          transformOrigin: 'center center',
        }}
        className="relative"
      >
        <Table
          snapshot={tableSnapshot}
          mySeatIndex={seat}
          holeCards={holeCards as [string, string]}
          onSeatClick={(s) => console.log('Seat clicked', s)}
        />

        {/* Pot Ref Anchor (invisible or overlaid) */}
        <div
          ref={potRef}
          className="absolute top-[35%] left-1/2 -translate-x-1/2 w-16 h-16 pointer-events-none"
        />

        <ChipAnimationLayer
          transfers={chipTransfers}
          onTransferDone={removeTransfer}
          speed={chipAnimSpeed}
        />
      </div>
    </div>
  );
}
