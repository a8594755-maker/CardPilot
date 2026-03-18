import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { DatabaseFlop } from '../../lib/api-client';
import { toggleFlopIgnored, deleteFlopFromDatabase } from '../../lib/api-client';
import { useDatabaseStore } from '../../stores/database';

interface FlopTableProps {
  databaseId: string;
  flops: DatabaseFlop[];
}

const STATUS_STYLES: Record<string, string> = {
  pending: 'bg-yellow-500/20 text-yellow-400',
  solving: 'bg-blue-500/20 text-blue-400',
  solved: 'bg-green-500/20 text-green-400',
  error: 'bg-red-500/20 text-red-400',
  ignored: 'bg-secondary text-muted-foreground line-through',
};

const CARD_SUIT_COLORS: Record<string, string> = {
  s: 'text-foreground',
  h: 'text-red-500',
  d: 'text-blue-400',
  c: 'text-green-500',
};

function CardDisplay({ card }: { card: string }) {
  const suit = card[1];
  const suitSymbol = { s: '\u2660', h: '\u2665', d: '\u2666', c: '\u2663' }[suit] || suit;
  return (
    <span className={`font-mono font-bold ${CARD_SUIT_COLORS[suit] || ''}`}>
      {card[0]}
      {suitSymbol}
    </span>
  );
}

export function FlopTable({ databaseId, flops }: FlopTableProps) {
  const queryClient = useQueryClient();
  const { flopFilter, setFlopFilter } = useDatabaseStore();
  const [selectedFlops, setSelectedFlops] = useState<Set<string>>(new Set());

  const toggleMutation = useMutation({
    mutationFn: (flopId: string) => toggleFlopIgnored(databaseId, flopId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['database', databaseId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (flopId: string) => deleteFlopFromDatabase(databaseId, flopId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['database', databaseId] });
      queryClient.invalidateQueries({ queryKey: ['databases'] });
    },
  });

  // Filter flops
  let filtered = flops;
  if (flopFilter.statusFilter !== 'all') {
    filtered = filtered.filter((f) => f.status === flopFilter.statusFilter);
  }

  // Sort flops
  filtered = [...filtered].sort((a, b) => {
    const dir = flopFilter.sortDir === 'asc' ? 1 : -1;
    switch (flopFilter.sortBy) {
      case 'cards':
        return dir * a.cards.join('').localeCompare(b.cards.join(''));
      case 'weight':
        return dir * (a.weight - b.weight);
      case 'status':
        return dir * a.status.localeCompare(b.status);
      case 'oopEquity':
        return dir * ((a.results?.oopEquity ?? 0) - (b.results?.oopEquity ?? 0));
      case 'ipEquity':
        return dir * ((a.results?.ipEquity ?? 0) - (b.results?.ipEquity ?? 0));
      default:
        return 0;
    }
  });

  function toggleSort(col: typeof flopFilter.sortBy) {
    if (flopFilter.sortBy === col) {
      setFlopFilter({ sortDir: flopFilter.sortDir === 'asc' ? 'desc' : 'asc' });
    } else {
      setFlopFilter({ sortBy: col, sortDir: 'asc' });
    }
  }

  const sortArrow = (col: typeof flopFilter.sortBy) =>
    flopFilter.sortBy === col ? (flopFilter.sortDir === 'asc' ? ' ^' : ' v') : '';

  return (
    <div className="flex flex-col h-full">
      {/* Filter bar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border text-xs">
        <span className="text-muted-foreground">Status:</span>
        {(['all', 'pending', 'solved', 'ignored', 'error'] as const).map((s) => (
          <button
            key={s}
            onClick={() => setFlopFilter({ statusFilter: s })}
            className={`px-2 py-0.5 rounded capitalize ${
              flopFilter.statusFilter === s
                ? 'bg-primary/20 text-primary'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {s}
          </button>
        ))}
        <span className="ml-auto text-muted-foreground">
          {filtered.length}/{flops.length} flops
        </span>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-card border-b border-border">
            <tr>
              <th className="w-8 px-2 py-1.5">
                <input
                  type="checkbox"
                  checked={selectedFlops.size === filtered.length && filtered.length > 0}
                  onChange={(e) => {
                    setSelectedFlops(
                      e.target.checked ? new Set(filtered.map((f) => f.id)) : new Set(),
                    );
                  }}
                />
              </th>
              <th
                onClick={() => toggleSort('cards')}
                className="text-left px-2 py-1.5 cursor-pointer hover:text-primary"
              >
                Flop{sortArrow('cards')}
              </th>
              <th
                onClick={() => toggleSort('weight')}
                className="text-right px-2 py-1.5 cursor-pointer hover:text-primary"
              >
                Weight{sortArrow('weight')}
              </th>
              <th
                onClick={() => toggleSort('status')}
                className="text-center px-2 py-1.5 cursor-pointer hover:text-primary"
              >
                Status{sortArrow('status')}
              </th>
              <th
                onClick={() => toggleSort('oopEquity')}
                className="text-right px-2 py-1.5 cursor-pointer hover:text-primary"
              >
                OOP Eq{sortArrow('oopEquity')}
              </th>
              <th
                onClick={() => toggleSort('ipEquity')}
                className="text-right px-2 py-1.5 cursor-pointer hover:text-primary"
              >
                IP Eq{sortArrow('ipEquity')}
              </th>
              <th className="text-right px-2 py-1.5">OOP EV</th>
              <th className="text-right px-2 py-1.5">IP EV</th>
              <th className="w-16 px-2 py-1.5"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((flop) => (
              <tr
                key={flop.id}
                className={`border-b border-border/50 hover:bg-secondary/50 ${
                  flop.status === 'ignored' ? 'opacity-50' : ''
                }`}
              >
                <td className="px-2 py-1.5">
                  <input
                    type="checkbox"
                    checked={selectedFlops.has(flop.id)}
                    onChange={(e) => {
                      const next = new Set(selectedFlops);
                      if (e.target.checked) next.add(flop.id);
                      else next.delete(flop.id);
                      setSelectedFlops(next);
                    }}
                  />
                </td>
                <td className="px-2 py-1.5">
                  <div className="flex gap-1">
                    {flop.cards.map((c, i) => (
                      <CardDisplay key={i} card={c} />
                    ))}
                  </div>
                </td>
                <td className="text-right px-2 py-1.5 font-mono text-xs">
                  {flop.weight.toFixed(1)}
                </td>
                <td className="text-center px-2 py-1.5">
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] ${STATUS_STYLES[flop.status] || ''}`}
                  >
                    {flop.status}
                  </span>
                </td>
                <td className="text-right px-2 py-1.5 font-mono text-xs">
                  {flop.results ? `${flop.results.oopEquity.toFixed(1)}%` : '-'}
                </td>
                <td className="text-right px-2 py-1.5 font-mono text-xs">
                  {flop.results ? `${flop.results.ipEquity.toFixed(1)}%` : '-'}
                </td>
                <td className="text-right px-2 py-1.5 font-mono text-xs">
                  {flop.results ? flop.results.oopEV.toFixed(2) : '-'}
                </td>
                <td className="text-right px-2 py-1.5 font-mono text-xs">
                  {flop.results ? flop.results.ipEV.toFixed(2) : '-'}
                </td>
                <td className="px-2 py-1.5">
                  <div className="flex gap-1 justify-end">
                    <button
                      onClick={() => toggleMutation.mutate(flop.id)}
                      className="text-xs text-muted-foreground hover:text-foreground"
                      title={flop.status === 'ignored' ? 'Include' : 'Ignore'}
                    >
                      {flop.status === 'ignored' ? '+' : '-'}
                    </button>
                    <button
                      onClick={() => deleteMutation.mutate(flop.id)}
                      className="text-xs text-muted-foreground hover:text-destructive"
                      title="Delete flop"
                    >
                      X
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {filtered.length === 0 && (
          <div className="text-center py-8 text-sm text-muted-foreground">
            No flops match the current filter.
          </div>
        )}
      </div>
    </div>
  );
}
