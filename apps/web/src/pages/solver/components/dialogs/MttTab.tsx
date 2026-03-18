import { useMemo } from 'react';
import type { MttPlayerRow } from '../../stores/solver-config';
import { PlayerTable } from './PlayerTable';

interface MttTabProps {
  players: MttPlayerRow[];
  startingPot: number;
  onUpdatePlayer: (index: number, changes: Partial<MttPlayerRow>) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
  onStartingPotChange: (pot: number) => void;
}

const MTT_COLUMNS = [
  { key: 'chipCount', label: 'Chip Count' },
  { key: 'chipMultiplier', label: '#:', narrow: true },
  { key: 'prize', label: 'Prize' },
  { key: 'prizeMultiplier', label: '#:', narrow: true },
];

export function MttTab({
  players,
  startingPot,
  onUpdatePlayer,
  onAdd,
  onRemove,
  onStartingPotChange,
}: MttTabProps) {
  const totals = useMemo(
    () => ({
      totalChips: players.reduce((sum, p) => sum + p.chipCount * p.chipMultiplier, 0),
      totalPrize: players.reduce((sum, p) => sum + p.prize * p.prizeMultiplier, 0),
    }),
    [players],
  );

  return (
    <PlayerTable
      columns={MTT_COLUMNS}
      rows={players as unknown as Record<string, number>[]}
      maxRows={20}
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
