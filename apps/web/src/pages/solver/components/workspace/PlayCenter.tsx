import { usePlayMode } from '../../stores/play-mode';
import { PlayBoard } from '../play/PlayBoard';
import { ActionButtons } from '../play/ActionButtons';
import { StrategyBar } from '../play/StrategyBar';
import { dealNewHand, handleHeroAction } from '../../lib/play-engine';

export function PlayCenter() {
  const store = usePlayMode();

  async function handleAction(action: string, amount?: number) {
    await handleHeroAction(action, amount);
  }

  async function handleNextHand() {
    store.nextHand();
    await dealNewHand(
      store.oopGridFile,
      store.ipGridFile,
      store.heroRole,
      store.startingPot,
      store.effectiveStack,
    );
  }

  if (!store.isActive) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        Set up a play session in the left panel to begin
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Top bar */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-2 border-b border-border">
        <div className="flex items-center gap-4">
          <span className="text-sm font-semibold">Hand #{store.handId}</span>
          <span className="text-xs text-muted-foreground">
            {store.heroRole.toUpperCase()} | {store.street}
          </span>
        </div>
        {store.street === 'showdown' && (
          <button
            onClick={handleNextHand}
            className="px-4 py-1.5 text-sm bg-primary text-primary-foreground rounded hover:bg-primary/90"
          >
            Next Hand
          </button>
        )}
      </div>

      {/* Board */}
      <div className="flex-1 flex items-center justify-center overflow-auto">
        <PlayBoard />
      </div>

      {/* GTO Strategy feedback */}
      <div className="flex-shrink-0 px-4 py-1">
        <StrategyBar />
      </div>

      {/* Action buttons */}
      <ActionButtons onAction={handleAction} />
    </div>
  );
}
