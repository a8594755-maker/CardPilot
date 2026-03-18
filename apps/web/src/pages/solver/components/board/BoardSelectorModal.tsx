import { Dialog, DialogContent } from '../ui/Dialog';
import { useWorkspace } from '../../stores/workspace';

const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'] as const;
const SUITS = ['h', 'c', 'd', 's'] as const;

const SUIT_BG: Record<string, string> = {
  h: '#fce4ec', // hearts - pink
  c: '#e8f5e9', // clubs - green
  d: '#e3f2fd', // diamonds - blue
  s: '#e2e8f0', // spades - gray
};

const SUIT_BG_SELECTED: Record<string, string> = {
  h: '#ef5350', // hearts - strong red
  c: '#66bb6a', // clubs - strong green
  d: '#42a5f5', // diamonds - strong blue
  s: '#78909c', // spades - strong gray
};

const SUIT_TEXT: Record<string, string> = {
  h: '#c62828',
  c: '#2e7d32',
  d: '#1565c0',
  s: '#37474f',
};

export function BoardSelectorModal() {
  const {
    boardSelectorOpen,
    closeBoardSelector,
    boardCards,
    toggleBoardCard,
    clearBoard,
    randomBoard,
  } = useWorkspace();

  return (
    <Dialog open={boardSelectorOpen} onOpenChange={(open) => !open && closeBoardSelector()}>
      <DialogContent title="Board Selector" className="!max-w-[420px] !w-[420px]">
        <div className="-mx-4 -my-3 p-4">
          <div className="flex gap-4">
            {/* Card grid: 4 columns (suits) x 13 rows (ranks) */}
            <div
              className="inline-grid gap-[2px]"
              style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}
            >
              {RANKS.map((rank) =>
                SUITS.map((suit) => {
                  const card = `${rank}${suit}`;
                  const isSelected = boardCards.includes(card);
                  const isFull = boardCards.length >= 5 && !isSelected;

                  return (
                    <button
                      key={card}
                      onClick={() => !isFull && toggleBoardCard(card)}
                      disabled={isFull}
                      className="w-[52px] h-[36px] rounded text-[13px] font-mono font-semibold flex items-center justify-center transition-all"
                      style={{
                        backgroundColor: isSelected ? SUIT_BG_SELECTED[suit] : SUIT_BG[suit],
                        color: isSelected ? '#fff' : SUIT_TEXT[suit],
                        opacity: isFull ? 0.4 : 1,
                        cursor: isFull ? 'not-allowed' : 'pointer',
                        border: isSelected ? '2px solid #333' : '1px solid #ccc',
                      }}
                    >
                      {card}
                    </button>
                  );
                }),
              )}
            </div>

            {/* Right side: buttons + selected cards */}
            <div className="flex flex-col gap-3">
              <button
                onClick={clearBoard}
                className="gto-btn gto-btn-primary"
                style={{ minWidth: 80 }}
              >
                Clear
              </button>
              <button
                onClick={() => randomBoard(3)}
                className="gto-btn gto-btn-primary"
                style={{ minWidth: 80 }}
              >
                Random
              </button>

              {/* Selected cards display */}
              {boardCards.length > 0 && (
                <div
                  className="mt-2 p-2 rounded flex gap-1 flex-wrap"
                  style={{ background: '#fff', border: '1px solid #ccc', minHeight: 36 }}
                >
                  {boardCards.map((card) => (
                    <span
                      key={card}
                      className="px-1.5 py-0.5 rounded text-xs font-mono font-semibold"
                      style={{
                        backgroundColor: SUIT_BG_SELECTED[card[1]],
                        color: '#fff',
                      }}
                    >
                      {card}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="gto-footer -mx-4 -mb-4 mt-4">
            <div />
            <button
              onClick={closeBoardSelector}
              className="gto-btn gto-btn-primary"
              style={{ minWidth: 80 }}
            >
              Done
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
