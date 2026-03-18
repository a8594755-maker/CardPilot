import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchGtoPlusSamples } from '../../lib/api-client';
import type { PlayRole } from '../../stores/play-mode';

interface PlayModeSetupProps {
  onStart: (config: {
    heroRole: PlayRole;
    oopGridFile: string;
    ipGridFile: string;
    startingPot: number;
    effectiveStack: number;
  }) => void;
}

export function PlayModeSetup({ onStart }: PlayModeSetupProps) {
  const [heroRole, setHeroRole] = useState<PlayRole>('oop');
  const [oopFile, setOopFile] = useState('');
  const [ipFile, setIpFile] = useState('');
  const [startingPot, setStartingPot] = useState(6);
  const [effectiveStack, setEffectiveStack] = useState(97);

  const { data: samplesData } = useQuery({
    queryKey: ['gtoPlusSamples'],
    queryFn: () => fetchGtoPlusSamples(),
  });

  const files = samplesData?.files || [];
  const oopFiles = files.filter(
    (f) => f.name.toLowerCase().includes('oop') || f.name.toLowerCase().includes('bb'),
  );
  const ipFiles = files.filter(
    (f) =>
      f.name.toLowerCase().includes('ip') ||
      f.name.toLowerCase().includes('btn') ||
      f.name.toLowerCase().includes('bu'),
  );

  const canStart = oopFile && ipFile;

  return (
    <div className="max-w-lg mx-auto mt-12">
      <h1 className="text-2xl font-bold mb-6">Play Against Solution</h1>
      <p className="text-sm text-muted-foreground mb-6">
        Practice playing against a GTO opponent. Select strategy files for both players and choose
        your position.
      </p>

      <div className="space-y-4">
        {/* Hero role */}
        <div>
          <label className="text-sm text-muted-foreground mb-2 block">Your Position</label>
          <div className="flex gap-2">
            {(['oop', 'ip'] as PlayRole[]).map((role) => (
              <button
                key={role}
                onClick={() => setHeroRole(role)}
                className={`flex-1 py-2 rounded text-sm font-medium border ${
                  heroRole === role
                    ? 'bg-primary/10 border-primary text-primary'
                    : 'border-border text-muted-foreground hover:text-foreground'
                }`}
              >
                {role === 'oop' ? 'Out of Position (OOP)' : 'In Position (IP)'}
              </button>
            ))}
          </div>
        </div>

        {/* OOP strategy file */}
        <div>
          <label className="text-sm text-muted-foreground mb-1 block">OOP Strategy File</label>
          <select
            value={oopFile}
            onChange={(e) => setOopFile(e.target.value)}
            className="w-full px-3 py-2 bg-secondary border border-border rounded text-sm"
          >
            <option value="">Select OOP file...</option>
            {(oopFiles.length > 0 ? oopFiles : files).map((f) => (
              <option key={f.name} value={f.name}>
                {f.name}
              </option>
            ))}
          </select>
        </div>

        {/* IP strategy file */}
        <div>
          <label className="text-sm text-muted-foreground mb-1 block">IP Strategy File</label>
          <select
            value={ipFile}
            onChange={(e) => setIpFile(e.target.value)}
            className="w-full px-3 py-2 bg-secondary border border-border rounded text-sm"
          >
            <option value="">Select IP file...</option>
            {(ipFiles.length > 0 ? ipFiles : files).map((f) => (
              <option key={f.name} value={f.name}>
                {f.name}
              </option>
            ))}
          </select>
        </div>

        {/* Pot and stack */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-sm text-muted-foreground mb-1 block">Starting Pot</label>
            <input
              type="number"
              value={startingPot}
              onChange={(e) => setStartingPot(Number(e.target.value))}
              className="w-full px-3 py-2 bg-secondary border border-border rounded text-sm"
            />
          </div>
          <div>
            <label className="text-sm text-muted-foreground mb-1 block">Effective Stack</label>
            <input
              type="number"
              value={effectiveStack}
              onChange={(e) => setEffectiveStack(Number(e.target.value))}
              className="w-full px-3 py-2 bg-secondary border border-border rounded text-sm"
            />
          </div>
        </div>

        <button
          onClick={() =>
            onStart({
              heroRole,
              oopGridFile: oopFile,
              ipGridFile: ipFile,
              startingPot,
              effectiveStack,
            })
          }
          disabled={!canStart}
          className="w-full py-3 text-sm font-medium bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50 mt-4"
        >
          Start Playing
        </button>
      </div>
    </div>
  );
}
