import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createDatabase } from '../../lib/api-client';
import { useDatabaseStore } from '../../stores/database';

export function CreateDatabaseDialog() {
  const queryClient = useQueryClient();
  const { showCreateDialog, setShowCreateDialog } = useDatabaseStore();
  const [name, setName] = useState('');
  const [treeConfigName, setTreeConfigName] = useState('hu_btn_bb_srp_100bb');
  const [oopRange, setOopRange] = useState('');
  const [ipRange, setIpRange] = useState('');
  const [startingPot, setStartingPot] = useState(6);
  const [effectiveStack, setEffectiveStack] = useState(97);
  const [rakeEnabled, setRakeEnabled] = useState(false);
  const [rakePercent, setRakePercent] = useState(5);
  const [rakeCap, setRakeCap] = useState(3);

  const mutation = useMutation({
    mutationFn: () =>
      createDatabase(name, {
        treeConfigName,
        oopRange,
        ipRange,
        startingPot,
        effectiveStack,
        rake: rakeEnabled ? { percent: rakePercent, cap: rakeCap } : undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['databases'] });
      setShowCreateDialog(false);
      resetForm();
    },
  });

  function resetForm() {
    setName('');
    setOopRange('');
    setIpRange('');
    setStartingPot(6);
    setEffectiveStack(97);
    setRakeEnabled(false);
  }

  if (!showCreateDialog) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-card border border-border rounded-lg shadow-xl w-full max-w-lg p-6">
        <h2 className="text-lg font-semibold mb-4">Create New Database</h2>

        <div className="space-y-3">
          <div>
            <label className="text-sm text-muted-foreground">Database Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. BTN vs BB SRP"
              className="w-full mt-1 px-3 py-2 bg-secondary border border-border rounded text-sm"
            />
          </div>

          <div>
            <label className="text-sm text-muted-foreground">Tree Config</label>
            <select
              value={treeConfigName}
              onChange={(e) => setTreeConfigName(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-secondary border border-border rounded text-sm"
            >
              <option value="hu_btn_bb_srp_100bb">HU BTN vs BB SRP 100bb</option>
              <option value="hu_btn_bb_3bp_100bb">HU BTN vs BB 3BP 100bb</option>
              <option value="hu_bb_btn_srp_100bb">HU BB vs BTN SRP 100bb</option>
              <option value="hu_co_bb_srp_100bb">HU CO vs BB SRP 100bb</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm text-muted-foreground">OOP Range</label>
              <input
                value={oopRange}
                onChange={(e) => setOopRange(e.target.value)}
                placeholder="e.g. AA-22,AKs-A2s..."
                className="w-full mt-1 px-3 py-2 bg-secondary border border-border rounded text-sm font-mono text-xs"
              />
            </div>
            <div>
              <label className="text-sm text-muted-foreground">IP Range</label>
              <input
                value={ipRange}
                onChange={(e) => setIpRange(e.target.value)}
                placeholder="e.g. AA-22,AKs-A2s..."
                className="w-full mt-1 px-3 py-2 bg-secondary border border-border rounded text-sm font-mono text-xs"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm text-muted-foreground">Starting Pot</label>
              <input
                type="number"
                value={startingPot}
                onChange={(e) => setStartingPot(Number(e.target.value))}
                className="w-full mt-1 px-3 py-2 bg-secondary border border-border rounded text-sm"
              />
            </div>
            <div>
              <label className="text-sm text-muted-foreground">Effective Stack</label>
              <input
                type="number"
                value={effectiveStack}
                onChange={(e) => setEffectiveStack(Number(e.target.value))}
                className="w-full mt-1 px-3 py-2 bg-secondary border border-border rounded text-sm"
              />
            </div>
          </div>

          <div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={rakeEnabled}
                onChange={(e) => setRakeEnabled(e.target.checked)}
              />
              <span className="text-muted-foreground">Enable Rake</span>
            </label>
            {rakeEnabled && (
              <div className="grid grid-cols-2 gap-3 mt-2">
                <div>
                  <label className="text-xs text-muted-foreground">Rake %</label>
                  <input
                    type="number"
                    value={rakePercent}
                    onChange={(e) => setRakePercent(Number(e.target.value))}
                    className="w-full mt-1 px-3 py-1.5 bg-secondary border border-border rounded text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Rake Cap</label>
                  <input
                    type="number"
                    value={rakeCap}
                    onChange={(e) => setRakeCap(Number(e.target.value))}
                    className="w-full mt-1 px-3 py-1.5 bg-secondary border border-border rounded text-sm"
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button
            onClick={() => setShowCreateDialog(false)}
            className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={!name || mutation.isPending}
            className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50"
          >
            {mutation.isPending ? 'Creating...' : 'Create Database'}
          </button>
        </div>

        {mutation.isError && (
          <p className="text-sm text-destructive mt-2">{(mutation.error as Error).message}</p>
        )}
      </div>
    </div>
  );
}
