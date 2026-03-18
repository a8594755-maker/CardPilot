import { useWorkspace } from '../stores/workspace';

export type Street = 'preflop' | 'flop' | 'turn' | 'river';

export function useBoardContext() {
  const boardCards = useWorkspace((s) => s.boardCards);

  const street: Street =
    boardCards.length >= 5
      ? 'river'
      : boardCards.length === 4
        ? 'turn'
        : boardCards.length >= 3
          ? 'flop'
          : 'preflop';

  const isComplete = boardCards.length >= 3;
  const canSolve = boardCards.length >= 3 && boardCards.length <= 5;

  return { boardCards, street, isComplete, canSolve };
}
