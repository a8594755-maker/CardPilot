import { useCallback, useEffect, useRef } from 'react';
import { useRangeEditor } from '../../stores/range-editor';

const RANKS = 'AKQJT98765432';

function getHandLabel(row: number, col: number): string {
  if (row === col) return `${RANKS[row]}${RANKS[col]}`;
  if (row < col) return `${RANKS[row]}${RANKS[col]}s`;
  return `${RANKS[col]}${RANKS[row]}o`;
}

function getHandType(row: number, col: number): 'pair' | 'suited' | 'offsuit' {
  if (row === col) return 'pair';
  if (row < col) return 'suited';
  return 'offsuit';
}

export function RangeEditorMatrix() {
  const { selectedHands, selectHand, deselectHand } = useRangeEditor();

  // Drag state (refs to avoid re-renders during drag)
  const isDragging = useRef(false);
  const dragMode = useRef<'select' | 'deselect'>('select');

  const handleMouseDown = useCallback(
    (hand: string, isSelected: boolean) => {
      isDragging.current = true;
      // If cell is already selected, drag will deselect; otherwise drag will select
      dragMode.current = isSelected ? 'deselect' : 'select';
      // Apply to the first cell immediately
      if (dragMode.current === 'select') {
        selectHand(hand);
      } else {
        deselectHand(hand);
      }
    },
    [selectHand, deselectHand],
  );

  const handleMouseEnter = useCallback(
    (hand: string) => {
      if (!isDragging.current) return;
      if (dragMode.current === 'select') {
        selectHand(hand);
      } else {
        deselectHand(hand);
      }
    },
    [selectHand, deselectHand],
  );

  // Global mouseup to stop drag
  useEffect(() => {
    const stopDrag = () => {
      isDragging.current = false;
    };
    document.addEventListener('mouseup', stopDrag);
    return () => document.removeEventListener('mouseup', stopDrag);
  }, []);

  return (
    <div
      className="inline-grid gap-[1px] p-[1px] rounded-md select-none"
      style={{ gridTemplateColumns: 'repeat(13, 1fr)', background: '#999' }}
      onDragStart={(e) => e.preventDefault()}
    >
      {Array.from({ length: 13 }, (_, row) =>
        Array.from({ length: 13 }, (_, col) => {
          const hand = getHandLabel(row, col);
          const type = getHandType(row, col);
          const isSelected = selectedHands.has(hand);

          let bgColor: string;
          if (isSelected) {
            switch (type) {
              case 'pair':
                bgColor = '#ef4444'; // red
                break;
              case 'suited':
                bgColor = '#3b82f6'; // blue
                break;
              case 'offsuit':
                bgColor = '#22c55e'; // green
                break;
            }
          } else {
            bgColor = '#1a1a2e';
          }

          return (
            <button
              key={hand}
              onMouseDown={() => handleMouseDown(hand, isSelected)}
              onMouseEnter={() => handleMouseEnter(hand)}
              className="w-[34px] h-[26px] text-[9px] font-mono leading-none flex items-center justify-center hover:brightness-110 cursor-pointer"
              style={{
                backgroundColor: bgColor,
                color: isSelected ? 'white' : '#888',
              }}
            >
              {hand}
            </button>
          );
        }),
      )}
    </div>
  );
}
