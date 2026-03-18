import { useWorkspace } from '../../stores/workspace';
import { useBoardContext } from '../../hooks/useBoardContext';
import { CardComponent } from '../board/CardComponent';

export function BoardBar() {
  const { boardCards, openBoardSelector, toggleBoardCard, clearBoard, randomBoard } =
    useWorkspace();
  const { street } = useBoardContext();

  const slots = Array.from({ length: 5 }, (_, i) => boardCards[i] ?? null);

  return (
    <div className="flex items-center gap-3">
      {/* Card slots */}
      <div className="flex items-center gap-1">
        {slots.map((card, i) => (
          <button
            key={i}
            onClick={() => {
              if (card) {
                toggleBoardCard(card);
              } else {
                openBoardSelector();
              }
            }}
            className="transition-all hover:scale-105"
            title={card ? `Click to remove ${card}` : 'Click to add card'}
          >
            {card ? (
              <CardComponent card={card} size="sm" />
            ) : (
              <div className="w-8 h-11 rounded-md border-2 border-dashed border-border/60 flex items-center justify-center text-muted-foreground/40 text-xs">
                {i < 3 ? '' : i === 3 ? 'T' : 'R'}
              </div>
            )}
          </button>
        ))}
      </div>

      {/* Street label */}
      <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider min-w-[40px]">
        {boardCards.length > 0 ? street : ''}
      </span>

      {/* Action buttons */}
      <div className="flex gap-1">
        <button
          onClick={() => randomBoard(3)}
          className="px-2 py-0.5 text-[10px] rounded bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors"
          title="Random flop"
        >
          Random
        </button>
        {boardCards.length > 0 && (
          <button
            onClick={clearBoard}
            className="px-2 py-0.5 text-[10px] rounded bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors"
            title="Clear board"
          >
            Clear
          </button>
        )}
      </div>
    </div>
  );
}
