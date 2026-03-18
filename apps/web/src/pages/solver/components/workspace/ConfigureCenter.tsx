import { useCallback, useMemo } from 'react';
import { NavigationTreeView } from '../navigation-tree/NavigationTreeView';
import { buildSkeletonTree } from '../strategy/tree-skeleton-builder';
import { useSolverConfig } from '../../stores/solver-config';
import { useWorkspace } from '../../stores/workspace';

function getStreetFromBoard(boardLen: number): 'FLOP' | 'TURN' | 'RIVER' {
  if (boardLen >= 5) return 'RIVER';
  if (boardLen === 4) return 'TURN';
  return 'FLOP';
}

function getBetSizesForStreet(
  betSizes: { flop: number[]; turn: number[]; river: number[] },
  street: 'FLOP' | 'TURN' | 'RIVER',
): number[] {
  switch (street) {
    case 'FLOP':
      return betSizes.flop;
    case 'TURN':
      return betSizes.turn;
    case 'RIVER':
      return betSizes.river;
  }
}

export function ConfigureCenter() {
  const { treeConfig } = useSolverConfig();
  const boardCards = useWorkspace((s) => s.boardCards);
  const setBoardCards = useWorkspace((s) => s.setBoardCards);

  const handleSelectCard = useCallback(
    (card: string) => {
      if (boardCards.length < 5) {
        setBoardCards([...boardCards, card]);
      }
    },
    [boardCards, setBoardCards],
  );

  const startStreet = getStreetFromBoard(boardCards.length);
  const streetBetSizes = getBetSizesForStreet(treeConfig.betSizes, startStreet);

  // GTO+ style: always show only the current street's tree
  const singleStreet = true;

  const vizTree = useMemo(() => {
    if (
      streetBetSizes.length === 0 ||
      treeConfig.startingPot <= 0 ||
      treeConfig.effectiveStack <= 0
    )
      return null;
    return buildSkeletonTree({
      startingPot: treeConfig.startingPot,
      effectiveStack: treeConfig.effectiveStack,
      betSizes: treeConfig.betSizes,
      raiseCapPerStreet: treeConfig.raiseCapPerStreet,
      perLevelBetFractions: treeConfig.perLevelBetFractions,
      singleStreet,
      startStreet,
    });
  }, [treeConfig, startStreet, singleStreet, streetBetSizes]);

  const streetLabel = startStreet.charAt(0) + startStreet.slice(1).toLowerCase();

  return (
    <div className="flex flex-col h-full">
      {/* Tree View */}
      <div className="flex-1 min-h-0 p-2 overflow-auto">
        {vizTree ? (
          <NavigationTreeView
            vizTree={vizTree}
            boardCards={boardCards}
            onSelectCard={handleSelectCard}
          />
        ) : (
          <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
            Set pot, stack, and bet sizes to generate the decision tree
          </div>
        )}
      </div>

      {/* Tree Stats */}
      {vizTree && (
        <div className="flex-shrink-0 px-4 py-2 border-t border-border text-[11px] text-muted-foreground flex items-center gap-4">
          <span>Nodes: {vizTree.nodes.length}</span>
          <span>Edges: {vizTree.edges.length}</span>
          <span>{streetLabel}</span>
        </div>
      )}
    </div>
  );
}
