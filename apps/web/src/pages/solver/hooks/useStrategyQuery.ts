import { useQuery } from '@tanstack/react-query';
import { fetchFlops, fetchStrategyTree, fetchNearestFlop } from '../lib/api-client';

export function useFlops(config: string) {
  return useQuery({
    queryKey: ['flops', config],
    queryFn: () => fetchFlops(config),
    enabled: !!config,
  });
}

export function useNearestFlop(cards: string, config?: string) {
  return useQuery({
    queryKey: ['nearestFlop', cards, config],
    queryFn: () => fetchNearestFlop(cards, config),
    enabled: !!cards,
  });
}

export function useStrategyTree(config: string, flop: string, player?: string, history?: string) {
  return useQuery({
    queryKey: ['strategyTree', config, flop, player, history],
    queryFn: () => fetchStrategyTree(config, flop, player, history),
    enabled: !!config && !!flop,
  });
}
