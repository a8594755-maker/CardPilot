import { useMemo } from 'react';
import type { DatabaseReport } from '../../lib/api-client';

interface AggregateReportProps {
  report: DatabaseReport;
}

export function AggregateReport({ report }: AggregateReportProps) {
  const sortedFlops = useMemo(() => {
    return [...report.perFlop].sort((a, b) => {
      const aEq = a.results?.oopEquity ?? 0;
      const bEq = b.results?.oopEquity ?? 0;
      return bEq - aEq;
    });
  }, [report.perFlop]);

  return (
    <div className="space-y-6 p-4">
      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard label="Flops" value={`${report.solvedCount} / ${report.flopCount}`} />
        <StatCard label="Avg OOP Equity" value={`${report.averageOopEquity.toFixed(1)}%`} />
        <StatCard label="Avg IP Equity" value={`${report.averageIpEquity.toFixed(1)}%`} />
        <StatCard label="Avg OOP EV" value={report.averageOopEV.toFixed(3)} />
      </div>

      {/* EV Summary row */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-2">Average EVs</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div>
              <span className="text-muted-foreground">OOP EV:</span>
              <span className="font-mono ml-2">{report.averageOopEV.toFixed(3)}</span>
            </div>
            <div>
              <span className="text-muted-foreground">IP EV:</span>
              <span className="font-mono ml-2">{report.averageIpEV.toFixed(3)}</span>
            </div>
          </div>
        </div>

        <div className="bg-card border border-border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-2">Avg Betting Frequencies</h3>
          <div className="flex flex-wrap gap-2 text-xs">
            {Object.entries(report.averageBettingFreqs).map(([action, freq]) => (
              <div key={action} className="bg-secondary px-2 py-1 rounded">
                <span className="text-muted-foreground">{action}:</span>
                <span className="font-mono ml-1">{(freq * 100).toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Equity distribution chart (simple bar chart) */}
      {sortedFlops.length > 0 && (
        <div className="bg-card border border-border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3">OOP Equity by Flop</h3>
          <div className="space-y-1">
            {sortedFlops.map((flop) => {
              const eq = flop.results?.oopEquity ?? 50;
              return (
                <div key={flop.id} className="flex items-center gap-2 text-xs">
                  <div className="w-20 font-mono text-muted-foreground flex gap-0.5">
                    {flop.cards.map((c, i) => (
                      <span key={i}>{c}</span>
                    ))}
                  </div>
                  <div className="flex-1 h-3 bg-secondary/50 rounded overflow-hidden relative">
                    <div
                      className="h-full rounded"
                      style={{
                        width: `${eq}%`,
                        backgroundColor: eq > 55 ? '#22c55e' : eq < 45 ? '#ef4444' : '#eab308',
                      }}
                    />
                    <div className="absolute top-0 left-1/2 w-px h-full bg-muted-foreground/50" />
                  </div>
                  <div className="w-12 text-right font-mono">{eq.toFixed(1)}%</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Per-flop table */}
      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <h3 className="text-sm font-semibold p-4 border-b border-border">Per-Flop Results</h3>
        <div className="overflow-auto max-h-80">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-card">
              <tr className="border-b border-border">
                <th className="text-left px-3 py-2">Flop</th>
                <th className="text-right px-3 py-2">OOP Eq</th>
                <th className="text-right px-3 py-2">IP Eq</th>
                <th className="text-right px-3 py-2">OOP EV</th>
                <th className="text-right px-3 py-2">IP EV</th>
                <th className="text-right px-3 py-2">Exploit.</th>
                <th className="text-right px-3 py-2">Weight</th>
              </tr>
            </thead>
            <tbody>
              {sortedFlops.map((flop) => (
                <tr key={flop.id} className="border-b border-border/30 hover:bg-secondary/30">
                  <td className="px-3 py-1.5 font-mono">{flop.cards.join(' ')}</td>
                  <td className="text-right px-3 py-1.5 font-mono">
                    {flop.results ? `${flop.results.oopEquity.toFixed(1)}%` : '-'}
                  </td>
                  <td className="text-right px-3 py-1.5 font-mono">
                    {flop.results ? `${flop.results.ipEquity.toFixed(1)}%` : '-'}
                  </td>
                  <td className="text-right px-3 py-1.5 font-mono">
                    {flop.results ? flop.results.oopEV.toFixed(3) : '-'}
                  </td>
                  <td className="text-right px-3 py-1.5 font-mono">
                    {flop.results ? flop.results.ipEV.toFixed(3) : '-'}
                  </td>
                  <td className="text-right px-3 py-1.5 font-mono">
                    {flop.results ? flop.results.exploitability.toFixed(3) : '-'}
                  </td>
                  <td className="text-right px-3 py-1.5 font-mono">{flop.weight.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-xl font-mono font-semibold mt-1">{value}</div>
    </div>
  );
}
