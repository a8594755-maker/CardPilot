import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { fetchPreflopConfigs, fetchPreflopSpots } from './lib/api-client';
import { useState } from 'react';

export function SolverPreflopRanges() {
  const { data: configData } = useQuery({
    queryKey: ['preflopConfigs'],
    queryFn: fetchPreflopConfigs,
  });
  const [selectedConfig, setSelectedConfig] = useState<string>('');

  const config = selectedConfig || configData?.configs[0] || '';
  const coverage = configData?.coverageByConfig?.[config];

  const { data: spotsData } = useQuery({
    queryKey: ['preflopSpots', config],
    queryFn: () => fetchPreflopSpots(config),
    enabled: !!config,
  });

  // Group spots by position
  type Spot = {
    spot: string;
    heroPosition: string;
    scenario: string;
    coverage: 'exact' | 'solver';
  };
  const spotsByPosition = (spotsData?.spots || []).reduce<Record<string, Spot[]>>((acc, spot) => {
    const pos = spot.heroPosition;
    if (!acc[pos]) acc[pos] = [];
    acc[pos].push(spot);
    return acc;
  }, {});

  const positions = ['LJ', 'HJ', 'CO', 'BTN', 'SB', 'BB', 'UTG', 'MP'];

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold">Preflop Ranges</h1>
        <p className="text-sm text-muted-foreground mt-1">
          GTO preflop strategies by position and scenario
        </p>
        {coverage && (
          <p className="text-xs mt-2 text-muted-foreground">
            Coverage: <span className="font-mono">{coverage}</span>
            {coverage === 'exact' ? ' (chart ground truth only)' : ''}
          </p>
        )}
      </div>

      {/* Config Selector */}
      {configData && configData.configs.length > 0 && (
        <div className="space-y-2">
          <label className="text-sm font-medium">Configuration</label>
          <select
            value={config}
            onChange={(e) => setSelectedConfig(e.target.value)}
            className="w-full max-w-xs px-3 py-2 rounded-md bg-secondary border border-border text-sm"
          >
            {configData.configs.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
            {configData.hasGtoWizardData && (
              <option value="gto-wizard">GTO Wizard (imported)</option>
            )}
          </select>
        </div>
      )}

      {/* Spots by Position */}
      <div className="space-y-4">
        {positions.map((pos) => {
          const spots = spotsByPosition[pos];
          if (!spots || spots.length === 0) {
            if (coverage === 'exact' && ['LJ', 'HJ', 'CO', 'BTN', 'SB', 'BB'].includes(pos)) {
              return (
                <div key={pos} className="space-y-2">
                  <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                    {pos}
                  </h3>
                  <div className="text-xs text-muted-foreground border border-dashed border-border rounded-lg px-3 py-2">
                    Not covered by current exact chart library.
                  </div>
                </div>
              );
            }
            return null;
          }
          return (
            <div key={pos} className="space-y-2">
              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                {pos}
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                {spots.map((spot) => (
                  <Link
                    key={spot.spot}
                    to={`/solver/ranges/${config}/${encodeURIComponent(spot.spot)}`}
                    className="bg-card border border-border rounded-lg px-4 py-3 hover:border-primary/50 transition-colors"
                  >
                    <div className="text-sm font-medium">{spot.spot.replace(/_/g, ' ')}</div>
                    <div className="text-xs text-muted-foreground capitalize">
                      {spot.scenario} · {spot.coverage}
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {!spotsData && config && (
        <div className="text-center text-muted-foreground py-12">Loading spots...</div>
      )}

      {spotsData && spotsData.spots.length === 0 && (
        <div className="text-center text-muted-foreground py-12">
          No preflop solutions found. Run <code className="text-primary">pnpm preflop:solve</code>{' '}
          first.
        </div>
      )}
    </div>
  );
}
