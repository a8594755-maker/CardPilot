import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { fetchPreflopRange } from './lib/api-client';
import { RangeMatrix13x13 } from './components/range/RangeMatrix13x13';
import { useState } from 'react';

export function SolverPreflopSpot() {
  const { config, spot } = useParams<{ config: string; spot: string }>();
  const [selectedHand, setSelectedHand] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['preflopRange', config, spot],
    queryFn: () => fetchPreflopRange(config!, spot!),
    enabled: !!config && !!spot,
  });

  if (isLoading) {
    return <div className="text-muted-foreground py-12 text-center">Loading range data...</div>;
  }

  if (error || !data) {
    return (
      <div className="text-destructive py-12 text-center">
        Failed to load range: {error?.message || 'Unknown error'}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">{data.spot?.replace(/_/g, ' ')}</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {data.heroPosition} · {data.format} · Pot: {data.summary?.totalCombos || 169} combos
        </p>
        {data.coverage && (
          <p className="text-xs text-muted-foreground mt-1">
            Coverage: <span className="font-mono">{data.coverage}</span>
            {data.coverage === 'exact' ? ' (chart ground truth)' : ''}
          </p>
        )}
      </div>

      {/* Summary Stats */}
      {data.summary && (
        <div className="flex gap-4 text-sm">
          <div className="bg-card border border-border rounded-lg px-4 py-2">
            <div className="text-xs text-muted-foreground">Range Size</div>
            <div className="font-mono font-medium">
              {data.summary.rangeSize} / {data.summary.totalCombos}
            </div>
          </div>
          {data.summary.actionFrequencies &&
            Object.entries(data.summary.actionFrequencies).map(([action, freq]) => (
              <div key={action} className="bg-card border border-border rounded-lg px-4 py-2">
                <div className="text-xs text-muted-foreground capitalize">{action}</div>
                <div className="font-mono font-medium">{(freq * 100).toFixed(1)}%</div>
              </div>
            ))}
        </div>
      )}

      {/* Range Matrix */}
      <RangeMatrix13x13
        grid={data.grid}
        actions={data.actions}
        selectedHand={selectedHand}
        onCellClick={(hand) => setSelectedHand(hand === selectedHand ? null : hand)}
      />
    </div>
  );
}
