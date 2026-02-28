// Config selector — toggle between 100bb / 50bb / ante variants.

import { memo } from 'react';

export interface PreflopConfig {
  id: string;
  label: string;
  shortLabel: string;
  description: string;
}

export const AVAILABLE_CONFIGS: PreflopConfig[] = [
  { id: 'cash_6max_100bb', label: '100bb Cash', shortLabel: '100bb', description: '100bb deep, no ante' },
  { id: 'cash_6max_50bb', label: '50bb Cash', shortLabel: '50bb', description: '50bb short stack' },
  { id: 'cash_6max_100bb_ante', label: '100bb + Ante', shortLabel: 'Ante', description: '100bb with 0.25bb ante' },
];

interface ConfigSelectorProps {
  selectedConfig: string;
  availableConfigs?: string[];
  onSelectConfig: (configId: string) => void;
}

export const ConfigSelector = memo(function ConfigSelector({
  selectedConfig,
  availableConfigs,
  onSelectConfig,
}: ConfigSelectorProps) {
  return (
    <div className="flex gap-1">
      {AVAILABLE_CONFIGS.map(cfg => {
        const isAvailable = !availableConfigs || availableConfigs.includes(cfg.id);
        const isSelected = selectedConfig === cfg.id;
        return (
          <button
            key={cfg.id}
            className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
              isSelected
                ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40'
                : isAvailable
                  ? 'bg-slate-800 text-slate-400 hover:bg-slate-700 border border-transparent'
                  : 'bg-slate-800/30 text-slate-600 cursor-not-allowed border border-transparent'
            }`}
            onClick={() => isAvailable && onSelectConfig(cfg.id)}
            disabled={!isAvailable}
            title={cfg.description}
          >
            {cfg.shortLabel}
          </button>
        );
      })}
    </div>
  );
});
