import { useMemo } from 'react';
import type { SngPlayerRow } from '../../stores/solver-config';
import { PlayerTable } from './PlayerTable';

interface SngTabProps {
  players: SngPlayerRow[];
  startingPot: number;
  onUpdatePlayer: (index: number, changes: Partial<SngPlayerRow>) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
  onStartingPotChange: (pot: number) => void;
}

const SNG_COLUMNS = [
  { key: 'chipCount', label: 'Chip Count' },
  { key: 'prize', label: 'Prize' },
];

export function SngTab({
  players,
  startingPot,
  onUpdatePlayer,
  onAdd,
  onRemove,
  onStartingPotChange,
}: SngTabProps) {
  const totals = useMemo(
    () => ({
      totalChips: players.reduce((sum, p) => sum + p.chipCount, 0),
      totalPrize: players.reduce((sum, p) => sum + p.prize, 0),
    }),
    [players],
  );

  return (
    <PlayerTable
      columns={SNG_COLUMNS}
      rows={players as unknown as Record<string, number>[]}
      maxRows={10}
      onUpdate={(index, key, value) => onUpdatePlayer(index, { [key]: value })}
      onAdd={onAdd}
      onRemove={onRemove}
      startingPot={startingPot}
      onStartingPotChange={onStartingPotChange}
      totals={totals}
      totalLabels={{ totalChips: 'Total Chips', totalPrize: 'Total Prize' }}
    />
  );
}
