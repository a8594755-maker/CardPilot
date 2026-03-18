import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchDatabase, fetchDatabaseReport, solveDatabaseFlops } from '../../lib/api-client';
import { useDatabaseStore } from '../../stores/database';
import { FlopTable } from './FlopTable';
import { AggregateReport } from './AggregateReport';
import { AddFlopsDialog } from './AddFlopsDialog';
import { useEffect } from 'react';

interface DatabaseDetailProps {
  databaseId: string;
}

export function DatabaseDetail({ databaseId }: DatabaseDetailProps) {
  const queryClient = useQueryClient();
  const { showReport, setShowReport, setShowAddFlopsDialog, setCurrentDatabase, setReport } =
    useDatabaseStore();

  const { data: db } = useQuery({
    queryKey: ['database', databaseId],
    queryFn: () => fetchDatabase(databaseId),
  });

  const { data: reportData } = useQuery({
    queryKey: ['databaseReport', databaseId],
    queryFn: () => fetchDatabaseReport(databaseId),
    enabled: showReport,
  });

  const solveMutation = useMutation({
    mutationFn: () => solveDatabaseFlops(databaseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['database', databaseId] });
    },
  });

  useEffect(() => {
    if (db) setCurrentDatabase(db);
  }, [db]);

  useEffect(() => {
    if (reportData) setReport(reportData);
  }, [reportData]);

  if (!db) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        Loading database...
      </div>
    );
  }

  const pendingCount = db.flops.filter((f) => f.status === 'pending').length;
  const solvedCount = db.flops.filter((f) => f.status === 'solved').length;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-border">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">{db.name}</h2>
            <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1">
              <span>{db.config.treeConfigName}</span>
              <span>Pot: {db.config.startingPot}</span>
              <span>Stack: {db.config.effectiveStack}</span>
              {db.config.rake && (
                <span>
                  Rake: {db.config.rake.percent}% / {db.config.rake.cap}
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowAddFlopsDialog(true)}
              className="px-3 py-1.5 text-xs bg-secondary border border-border rounded hover:bg-secondary/80"
            >
              + Add Flops
            </button>
            <button
              onClick={() => solveMutation.mutate()}
              disabled={pendingCount === 0 || solveMutation.isPending}
              className="px-3 py-1.5 text-xs bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50"
            >
              {solveMutation.isPending ? 'Starting...' : `Solve (${pendingCount} pending)`}
            </button>
            <button
              onClick={() => setShowReport(!showReport)}
              disabled={solvedCount === 0}
              className={`px-3 py-1.5 text-xs rounded border ${
                showReport
                  ? 'bg-primary/10 border-primary text-primary'
                  : 'border-border text-muted-foreground hover:text-foreground disabled:opacity-50'
              }`}
            >
              Report
            </button>
          </div>
        </div>

        {/* Progress bar */}
        {db.flops.length > 0 && (
          <div className="mt-2">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{solvedCount} solved</span>
              <span>{pendingCount} pending</span>
              <span>{db.flops.filter((f) => f.status === 'ignored').length} ignored</span>
            </div>
            <div className="h-1.5 bg-secondary rounded mt-1 overflow-hidden">
              <div
                className="h-full bg-green-500 rounded"
                style={{
                  width: `${db.flops.length > 0 ? (solvedCount / db.flops.length) * 100 : 0}%`,
                }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Content */}
      {showReport && reportData ? (
        <div className="flex-1 overflow-auto">
          <AggregateReport report={reportData} />
        </div>
      ) : (
        <div className="flex-1 overflow-hidden">
          <FlopTable databaseId={databaseId} flops={db.flops} />
        </div>
      )}

      {/* Dialogs */}
      <AddFlopsDialog databaseId={databaseId} />
    </div>
  );
}
