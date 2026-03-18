import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  addFlopsToDatabase,
  addRandomFlopsToDatabase,
  loadSubsetToDatabase,
  fetchFlopSubsets,
} from '../../lib/api-client';
import { useDatabaseStore } from '../../stores/database';

interface AddFlopsDialogProps {
  databaseId: string;
}

type TabMode = 'random' | 'subset' | 'manual';

export function AddFlopsDialog({ databaseId }: AddFlopsDialogProps) {
  const queryClient = useQueryClient();
  const { showAddFlopsDialog, setShowAddFlopsDialog } = useDatabaseStore();
  const [tab, setTab] = useState<TabMode>('random');
  const [randomCount, setRandomCount] = useState(50);
  const [selectedSubset, setSelectedSubset] = useState('');
  const [manualFlops, setManualFlops] = useState('');

  const { data: subsetsData } = useQuery({
    queryKey: ['flopSubsets'],
    queryFn: fetchFlopSubsets,
    enabled: showAddFlopsDialog,
  });

  const invalidateDb = () => {
    queryClient.invalidateQueries({ queryKey: ['database', databaseId] });
    queryClient.invalidateQueries({ queryKey: ['databases'] });
    setShowAddFlopsDialog(false);
  };

  const randomMutation = useMutation({
    mutationFn: () => addRandomFlopsToDatabase(databaseId, randomCount),
    onSuccess: invalidateDb,
  });

  const subsetMutation = useMutation({
    mutationFn: () => loadSubsetToDatabase(databaseId, selectedSubset),
    onSuccess: invalidateDb,
  });

  const manualMutation = useMutation({
    mutationFn: () => {
      const parsed = parseManualFlops(manualFlops);
      return addFlopsToDatabase(databaseId, parsed);
    },
    onSuccess: invalidateDb,
  });

  if (!showAddFlopsDialog) return null;

  const isPending =
    randomMutation.isPending || subsetMutation.isPending || manualMutation.isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-card border border-border rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 className="text-lg font-semibold mb-4">Add Flops</h2>

        {/* Tabs */}
        <div className="flex border-b border-border mb-4">
          {(['random', 'subset', 'manual'] as TabMode[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm capitalize border-b-2 transition-colors ${
                tab === t
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Random tab */}
        {tab === 'random' && (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Add randomly selected flops from all 1755 isomorphic flops.
            </p>
            <div>
              <label className="text-sm text-muted-foreground">Number of flops</label>
              <input
                type="number"
                value={randomCount}
                onChange={(e) => setRandomCount(Number(e.target.value))}
                min={1}
                max={1755}
                className="w-full mt-1 px-3 py-2 bg-secondary border border-border rounded text-sm"
              />
            </div>
            <div className="flex gap-2">
              {[23, 50, 100, 200, 500].map((n) => (
                <button
                  key={n}
                  onClick={() => setRandomCount(n)}
                  className={`px-3 py-1 text-xs rounded border ${
                    randomCount === n
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
            <button
              onClick={() => randomMutation.mutate()}
              disabled={isPending}
              className="w-full py-2 text-sm bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50"
            >
              {randomMutation.isPending ? 'Adding...' : `Add ${randomCount} Random Flops`}
            </button>
          </div>
        )}

        {/* Subset tab */}
        {tab === 'subset' && (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Load a predefined weighted subset of representative flops.
            </p>
            {subsetsData?.subsets.map((s) => (
              <div
                key={s.name}
                onClick={() => setSelectedSubset(s.name)}
                className={`p-3 rounded border cursor-pointer transition-colors ${
                  selectedSubset === s.name
                    ? 'border-primary bg-primary/10'
                    : 'border-border hover:border-muted-foreground'
                }`}
              >
                <div className="text-sm font-medium">{s.description}</div>
                <div className="text-xs text-muted-foreground mt-1">{s.count} flops (weighted)</div>
              </div>
            ))}
            <button
              onClick={() => subsetMutation.mutate()}
              disabled={isPending || !selectedSubset}
              className="w-full py-2 text-sm bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50"
            >
              {subsetMutation.isPending ? 'Loading...' : 'Load Subset'}
            </button>
          </div>
        )}

        {/* Manual tab */}
        {tab === 'manual' && (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Enter flops manually, one per line (e.g. "As Kh Qd" or "AKQ").
            </p>
            <textarea
              value={manualFlops}
              onChange={(e) => setManualFlops(e.target.value)}
              placeholder={'As Kh Qd\nKs Th 5d\n9s 7h 5d'}
              rows={6}
              className="w-full px-3 py-2 bg-secondary border border-border rounded text-sm font-mono"
            />
            <button
              onClick={() => manualMutation.mutate()}
              disabled={isPending || !manualFlops.trim()}
              className="w-full py-2 text-sm bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50"
            >
              {manualMutation.isPending ? 'Adding...' : 'Add Flops'}
            </button>
          </div>
        )}

        <div className="flex justify-end mt-4">
          <button
            onClick={() => setShowAddFlopsDialog(false)}
            className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground"
          >
            Close
          </button>
        </div>

        {(randomMutation.isError || subsetMutation.isError || manualMutation.isError) && (
          <p className="text-sm text-destructive mt-2">
            {
              ((randomMutation.error || subsetMutation.error || manualMutation.error) as Error)
                ?.message
            }
          </p>
        )}
      </div>
    </div>
  );
}

function parseManualFlops(text: string): Array<{ cards: [string, string, string] }> {
  const lines = text.trim().split('\n').filter(Boolean);
  const results: Array<{ cards: [string, string, string] }> = [];

  for (const line of lines) {
    const parts = line.trim().split(/\s+/);
    if (parts.length === 3 && parts.every((p) => p.length === 2)) {
      results.push({ cards: parts as [string, string, string] });
    } else if (parts.length === 1 && parts[0].length === 6) {
      // Compact format: "AsKhQd"
      const s = parts[0];
      results.push({
        cards: [s.substring(0, 2), s.substring(2, 4), s.substring(4, 6)],
      });
    }
  }

  return results;
}
