import type { DatabaseSummary } from '../../lib/api-client';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { deleteDatabase } from '../../lib/api-client';
import { useDatabaseStore } from '../../stores/database';

interface DatabaseListProps {
  databases: DatabaseSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const STATUS_COLORS: Record<string, string> = {
  idle: 'bg-yellow-500/20 text-yellow-400',
  solving: 'bg-blue-500/20 text-blue-400',
  complete: 'bg-green-500/20 text-green-400',
};

export function DatabaseList({ databases, selectedId, onSelect }: DatabaseListProps) {
  const queryClient = useQueryClient();
  const setShowCreateDialog = useDatabaseStore((s) => s.setShowCreateDialog);

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteDatabase(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['databases'] });
    },
  });

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
          Databases
        </h2>
        <button
          onClick={() => setShowCreateDialog(true)}
          className="px-3 py-1 text-xs bg-primary text-primary-foreground rounded hover:bg-primary/90"
        >
          + New
        </button>
      </div>

      {databases.length === 0 ? (
        <p className="text-sm text-muted-foreground py-4 text-center">
          No databases yet. Create one to get started.
        </p>
      ) : (
        <div className="space-y-1">
          {databases.map((db) => (
            <div
              key={db.id}
              onClick={() => onSelect(db.id)}
              className={`group flex items-center justify-between px-3 py-2 rounded cursor-pointer transition-colors ${
                selectedId === db.id
                  ? 'bg-primary/10 border border-primary/30'
                  : 'hover:bg-secondary border border-transparent'
              }`}
            >
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium truncate">{db.name}</div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                  <span>{db.flopCount} flops</span>
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] ${STATUS_COLORS[db.status] || ''}`}
                  >
                    {db.status}
                  </span>
                </div>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirm(`Delete "${db.name}"?`)) {
                    deleteMutation.mutate(db.id);
                  }
                }}
                className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-opacity text-xs px-1"
                title="Delete database"
              >
                X
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
