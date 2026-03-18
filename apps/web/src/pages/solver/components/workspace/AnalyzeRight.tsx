import type { GtoPlusCombo } from '../../lib/api-client';
import { RightPanel } from '../strategy-browser/RightPanel';
import { useStrategyBrowser } from '../../stores/strategy-browser';
import { useWorkspace } from '../../stores/workspace';

interface AnalyzeRightProps {
  allCombos: GtoPlusCombo[];
  ipCombos?: GtoPlusCombo[];
}

export function AnalyzeRight({ allCombos, ipCombos }: AnalyzeRightProps) {
  const store = useStrategyBrowser();
  const boardCards = useWorkspace((s) => s.boardCards);
  const board = boardCards.length > 0 ? boardCards : undefined;

  return (
    <RightPanel
      combos={allCombos}
      actions={store.nodeActions}
      context={store.nodeContext}
      ipCombos={ipCombos}
      boardCards={board}
    />
  );
}
